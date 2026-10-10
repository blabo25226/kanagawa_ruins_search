"""Photo metadata search; native coordinates never imply a verified CRS or footprint."""

from datetime import date
import json
import math
from shapely.geometry import Point, Polygon, box
from pyproj import CRS, Transformer


def coordinate(value):
    if value is None:
        return None
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 2
        or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in value)
    ):
        raise ValueError("Invalid catalog coordinate")
    if not (-180 <= value[0] <= 180 and -90 <= value[1] <= 90):
        raise ValueError("Catalog coordinate axis/range error")
    return list(value)


def normalize_catalog(
    records, *, acquisition_inventory_complete=False, acquired_spec_ids=()
):
    if not isinstance(records, list):
        raise ValueError("Photo catalog must be a JSON array")
    result, ids = [], set()
    for record in records:
        sid = record.get("specification_id")
        if sid is None or str(sid) in ids:
            raise ValueError("Missing/duplicate specification_id")
        ids.add(str(sid))
        raw_date = record.get("date")
        capture = (
            None
            if raw_date in {None, "", "1111-11-11"}
            else date.fromisoformat(raw_date).isoformat()
        )
        center = coordinate(record.get("center_pos"))
        corners = [
            coordinate(record.get("geom_image_" + pos + "_pos"))
            for pos in ["left_top", "right_top", "right_bottom", "left_bottom"]
        ]
        polygon = Polygon(corners) if all(c is not None for c in corners) else None
        usable = (
            polygon is not None
            and polygon.is_valid
            and polygon.area > 0
            and not record.get("is_point_only", False)
            and record.get("footprint_status") != "unknown"
        )
        state = (
            "footprint_approximate"
            if usable
            else ("center_only" if center else "footprint_unknown")
        )
        # A legacy 'valid' tag means geometry validity, not independent location accuracy.
        if (
            usable
            and record.get("footprint_verified") is True
            and record.get("footprint_verification_evidence")
        ):
            state = "footprint_verified"
        result.append(
            dict(
                specId=str(sid),
                reference_number=record.get("reference_number"),
                course_number=record.get("course_number"),
                photo_number=record.get("photo_number"),
                capture_date=capture,
                decade=f"{int(capture[:4]) // 10 * 10}s" if capture else None,
                organization=record.get("planning_organization"),
                center_pos=center,
                footprint_corners=corners if usable else None,
                footprint_state=state,
                scale=record.get("scale"),
                altitude=None,
                color=record.get("color_type_name"),
                coordinate_crs=record.get("coordinate_crs"),
                image_acquisition_state=(
                    "acquired"
                    if str(sid) in {str(v) for v in acquired_spec_ids}
                    else "not_acquired"
                    if acquisition_inventory_complete
                    else "unknown"
                ),
                license_verification_state="unknown",
                original=record,
            )
        )
    return result


def search_catalog(
    records,
    *,
    bbox_native=None,
    decade=None,
    footprints_only=False,
    unacquired_only=False,
):
    """bbox_native compares stored numeric lon/lat coordinates; it does not assign a datum."""
    region = None
    if bbox_native is not None:
        if (
            len(bbox_native) != 4
            or not all(math.isfinite(v) for v in bbox_native)
            or bbox_native[0] >= bbox_native[2]
            or bbox_native[1] >= bbox_native[3]
        ):
            raise ValueError("Invalid native-coordinate search bbox")
        region = box(*bbox_native)
    result = []
    for r in records:
        if decade is not None and r["decade"] != decade:
            continue
        if unacquired_only and r["image_acquisition_state"] != "not_acquired":
            continue
        corners = r["footprint_corners"]
        if footprints_only and corners is None:
            continue
        geometry = (
            Polygon(corners)
            if corners is not None
            else Point(r["center_pos"])
            if r["center_pos"]
            else None
        )
        if region is not None and (geometry is None or not geometry.intersects(region)):
            continue
        result.append(r)
    return result


def nearby_photos(records, x, y, radius_m, *, coordinate_crs=None):
    if coordinate_crs is None:
        raise ValueError(
            "Catalog CRS unconfirmed; metric search requires an explicit verified CRS"
        )
    crs = CRS.from_user_input(coordinate_crs)
    if (
        not crs.is_geographic
        or radius_m <= 0
        or not all(math.isfinite(v) for v in [x, y, radius_m])
    ):
        raise ValueError(
            "Expected a geographic catalog CRS, finite point and positive metre radius"
        )
    t = Transformer.from_crs(
        crs, 6677, always_xy=True, allow_ballpark=False, only_best=True
    )
    px, py = t.transform(x, y, errcheck=True)
    result = []
    for r in records:
        if (
            r.get("coordinate_crs") is not None
            and CRS.from_user_input(r["coordinate_crs"]) != crs
        ):
            raise ValueError("Catalog record CRS differs from the verified search CRS")
        if r["center_pos"]:
            cx, cy = t.transform(*r["center_pos"], errcheck=True)
            distance = math.hypot(cx - px, cy - py)
            if distance <= radius_m:
                result.append(
                    dict(
                        r,
                        center_distance_m=distance,
                        query_crs=crs.to_string(),
                        location_accuracy="unverified",
                    )
                )
    return result


def write_catalog(records, path):
    from ..raster.io import local_output

    path = local_output(path)
    path.write_text(
        json.dumps(
            records, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
        )
        + "\n",
        encoding="utf-8",
    )
    return path
