"""One manifest per immutable layer; listing reads metadata only."""

import json
import re
import geopandas as gpd
from ..config import Settings, contained_path

LAYER_RE = re.compile(r"^[a-z0-9_]+__[a-z0-9_]+__[a-z0-9_]+$")


def validate_layer_id(layer_id):
    if not LAYER_RE.fullmatch(layer_id):
        raise ValueError(f"Invalid layer id: {layer_id}")
    return layer_id


def list_layers(*, settings=None):
    s = settings or Settings.from_env()
    s.check_mount()
    result = []
    for p in sorted((s.output_root / "manifests").glob("*.json")):
        m = json.loads(p.read_text(encoding="utf-8"))
        validate_layer_id(m["layer_id"])
        if p.stem != m["layer_id"]:
            raise ValueError("Manifest filename/id mismatch")
        result.append(m)
    return result


def get_layer(layer_id, *, settings=None):
    validate_layer_id(layer_id)
    s = settings or Settings.from_env()
    s.check_mount()
    path = s.output_root / "manifests" / f"{layer_id}.json"
    if not path.is_file():
        raise KeyError(f"Unknown layer: {layer_id}")
    m = json.loads(path.read_text(encoding="utf-8"))
    if m["layer_id"] != layer_id:
        raise ValueError("Manifest id mismatch")
    p = contained_path(s.data_root, m["processed_path"])
    if not p.is_relative_to(s.output_root.resolve()) or p.suffix != ".parquet":
        raise ValueError("Catalog path outside processed/phase1a")
    return m, p


def load_layer(layer_id, *, columns=None, bbox=None, limit=None, settings=None):
    """bbox is in the stored CRS x/y units. SQL filters before materialization; no full scan at listing."""
    m, p = get_layer(layer_id, settings=settings)
    if bbox is None and limit is None:
        return gpd.read_parquet(p, columns=columns)
    from ..geo.spatial import spatial_connection, quote_identifier
    import shapely

    selected = columns or m["columns"]
    if "geometry" not in selected:
        raise ValueError("Filtered GeoDataFrame requires geometry column")
    if any(c not in m["columns"] for c in selected):
        raise ValueError("Unknown column")
    fields = ", ".join(
        "ST_AsWKB(geometry) AS geometry" if c == "geometry" else quote_identifier(c)
        for c in selected
    )
    with spatial_connection() as con:
        where = ""
        args = [str(p)]
        if bbox is not None:
            from ..geo.spatial import validate_bbox

            validate_bbox(bbox)
            where = " WHERE ST_Intersects(geometry,ST_MakeEnvelope(?,?,?,?))"
            args.extend(bbox)
        if limit is not None and (not isinstance(limit, int) or limit < 0):
            raise ValueError("limit must be a nonnegative integer")
        sql = (
            f"SELECT {fields} FROM read_parquet(?)"
            + where
            + (f" LIMIT {limit}" if limit is not None else "")
        )
        df = con.execute(sql, args).fetchdf()
    df["geometry"] = shapely.from_wkb([bytes(v) for v in df.geometry])
    return gpd.GeoDataFrame(df, geometry="geometry", crs=m["processed_crs"])
