"""Read-only inventory anchored to the acquisition ledger, never filename-derived dates."""

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import warnings
import rasterio
from ..catalog.sources import read_sources
from ..qa.hashing import sha256
from ..config import Settings
from ..raster.io import open_image
from .tiles import XYZ, check_tile_location


def inventory(settings):
    settings.check_mount()
    root = settings.data_root
    sources = {s.relative_path: s for s in read_sources(root)}
    assets = []
    directories = [
        "raw/aerial_photos",
        "raw/historical_maps",
        "raw/fgd",
        "raw/dem",
        "raw/dem_fgd",
        "raw/maps_historical",
    ]
    paths = sorted(
        {p for d in directories for p in (root / d).rglob("*") if p.is_file()}
    )
    for path in paths:
        rel = str(path.relative_to(root))
        source = sources.get(rel)
        digest = sha256(path)
        item = dict(
            relative_path=rel,
            format=path.suffix.lower().lstrip("."),
            size_bytes=path.stat().st_size,
            sha256=digest,
            source_id=source.source_id if source else None,
            source=source.source_url if source else None,
            license=source.license if source else None,
            ledger_sha256_match=(digest == source.sha256) if source else None,
            acquisition_date=source.acquired_at if source else None,
            temporal_coverage=source.temporal_coverage if source else None,
            capture_date=None,
            creation_date=None,
            crs=None,
            georeferenced=False,
            bbox=None,
            resolution=None,
            width=None,
            height=None,
            missing_metadata=[],
            processable=False,
            status="metadata_only",
        )
        if path.suffix.lower() in {".tif", ".tiff", ".jpeg", ".jpg", ".png"}:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter(
                        "ignore", rasterio.errors.NotGeoreferencedWarning
                    )
                    with open_image(path) as ds:
                        georef = ds.crs is not None and not ds.transform.is_identity
                        item.update(
                            width=ds.width,
                            height=ds.height,
                            bands=ds.count,
                            crs=ds.crs.to_string() if ds.crs else None,
                            georeferenced=georef,
                            bbox=list(ds.bounds) if georef else None,
                            resolution=list(ds.res) if georef else None,
                        )
                if not georef:
                    item["missing_metadata"].extend(["crs", "affine_transform"])
                    try:
                        tile = XYZ.from_filename(path)
                        item["xyz"] = dict(z=tile.z, x=tile.x, y=tile.y)
                        item["xyz_bbox_wgs84"] = list(check_tile_location(tile))
                        item["processable"] = (
                            item["width"],
                            item["height"],
                            item["bands"],
                        ) == (256, 256, 3)
                        item["status"] = "xyz_georeference_available"
                    except ValueError:
                        item["status"] = "manual_gcp_required"
                else:
                    item.update(processable=True, status="georeferenced_raster")
                item["missing_metadata"].extend(["capture_date", "geometric_accuracy"])
            except (OSError, rasterio.errors.RasterioError, ValueError) as e:
                item.update(status="invalid_raster", error=str(e))
        if not source:
            item["missing_metadata"].extend(["acquisition_provenance", "license"])
            item["processable"] = False
        elif not item["ledger_sha256_match"]:
            item.update(processable=False, status="hash_mismatch")
        assets.append(item)
    catalog = next(
        (p for p in paths if p.name == "tsukui_aerial_photos_catalog.json"), None
    )
    catalog_info = None
    if catalog:
        from .catalog import normalize_catalog

        records = normalize_catalog(json.loads(catalog.read_text(encoding="utf-8")))
        catalog_info = dict(
            count=len(records),
            actual_keys=sorted(set().union(*(r["original"].keys() for r in records))),
            date_unknown=sum(r["capture_date"] is None for r in records),
            footprint_states=dict(Counter(r["footprint_state"] for r in records)),
            coordinate_crs=None,
            missing_metadata=[
                "coordinate_crs",
                "altitude",
                "image_acquisition_evidence",
                "per_photo_license_verification",
            ],
        )
    from ..catalog import list_layers

    layers = list_layers(settings=Settings(root))
    return dict(
        generated_at=datetime.now(timezone.utc).isoformat(),
        assets=assets,
        aerial_catalog=catalog_info,
        phase1a_layer_count=len(layers),
        historical_map_image_count=sum(
            "historical" in a["relative_path"] and a["width"] is not None
            for a in assets
        ),
        dem_input_count=sum(
            any(
                part in {"fgd", "dem", "dem_fgd"}
                for part in Path(a["relative_path"]).parts
            )
            and (a["format"] in {"xml", "gml", "zip", "tif", "tiff"})
            for a in assets
        ),
    )
