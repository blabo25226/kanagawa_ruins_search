"""Independent chunked readback; raw/hash, schema, geometry and SQL checks."""

import json
import geopandas as gpd
import numpy as np
import pyarrow.parquet as pq
import shapely
from pyproj import CRS
from ..catalog import list_layers, get_layer
from ..catalog.sources import read_sources
from ..config import Settings
from ..geo.validate import validate_frame
from ..geo.spatial import spatial_connection
from .hashing import sha256


def verify_layer(layer_id, *, settings=None):
    settings = settings or Settings.from_env()
    m, p = get_layer(layer_id, settings=settings)
    sources = {s.source_id: s for s in read_sources(settings.data_root)}
    s = sources[m["source_id"]]
    if s.relative_path != m["original_path"] or s.sha256 != m["source_sha256"]:
        raise ValueError("Manifest/acquisition ledger mismatch")
    s.verify(settings.data_root)
    if sha256(p) != m["output_sha256"]:
        raise ValueError("Output hash mismatch")
    pf = pq.ParquetFile(p)
    geo = json.loads(pf.schema_arrow.metadata[b"geo"])
    if geo["version"] != "1.1.0" or geo["primary_column"] != "geometry":
        raise ValueError("GeoParquet metadata invalid")
    c = CRS.from_json_dict(geo["columns"]["geometry"]["crs"])
    if c != CRS.from_user_input(m["processed_crs"]) or (
        m.get("analysis_ready", True) and c != CRS.from_epsg(6677)
    ):
        raise ValueError("Incorrect processed CRS")
    if pf.schema_arrow.names != m["columns"]:
        raise ValueError("Column mismatch")
    count = 0
    bbox = None
    types = set()
    for batch in pf.iter_batches(batch_size=50000):
        df = batch.to_pandas()
        df["geometry"] = shapely.from_wkb(df.geometry.to_numpy())
        frame = gpd.GeoDataFrame(df, geometry="geometry", crs=c)
        qa = validate_frame(frame)
        if (
            not (frame.source_id == s.source_id).all()
            or not (frame.original_crs == m["original_crs"]).all()
        ):
            raise ValueError("Row provenance mismatch")
        count += len(frame)
        types.update(qa["geometry_type"])
        b = qa["bbox"]
        if b:
            bbox = (
                b
                if bbox is None
                else [
                    min(bbox[0], b[0]),
                    min(bbox[1], b[1]),
                    max(bbox[2], b[2]),
                    max(bbox[3], b[3]),
                ]
            )
    if count != m["feature_count"] or count != pf.metadata.num_rows:
        raise ValueError("Record count mismatch")
    if not np.allclose(bbox, m["bbox"], rtol=0, atol=1e-8):
        raise ValueError("Bbox mismatch")
    if (
        sorted(types) != m["geometry_type"]
        or sorted(types) != geo["columns"]["geometry"]["geometry_types"]
    ):
        raise ValueError("Geometry types mismatch")
    with spatial_connection() as con:
        n, invalid = con.execute(
            "SELECT count(*),count(*) FILTER(WHERE NOT ST_IsValid(geometry)) FROM read_parquet(?)",
            [str(p)],
        ).fetchone()
        if n != count or invalid:
            raise ValueError("DuckDB geometry/count disagreement")
        if bbox:
            filtered = con.execute(
                "SELECT count(*) FROM read_parquet(?) WHERE ST_Intersects(geometry,ST_MakeEnvelope(?,?,?,?))",
                [str(p), *bbox],
            ).fetchone()[0]
            if filtered != count:
                raise ValueError("DuckDB full bbox query mismatch")
        ext = con.execute(
            "SELECT extension_version FROM duckdb_extensions() WHERE extension_name='spatial'"
        ).fetchone()[0]
    return dict(
        layer_id=layer_id,
        status="PASS",
        feature_count=count,
        bytes=p.stat().st_size,
        crs=c.to_string(),
        output_sha256=m["output_sha256"],
        source_sha256=s.sha256,
        duckdb_spatial_version=ext,
        reproduction="Requires --execute rerun; not inferred from readback",
    )


def verify_all(*, settings=None):
    settings = settings or Settings.from_env()
    results = []
    for m in list_layers(settings=settings):
        try:
            results.append(verify_layer(m["layer_id"], settings=settings))
        except Exception as e:
            results.append(dict(layer_id=m["layer_id"], status="FAIL", error=str(e)))
    return dict(
        status="PASS"
        if results and all(r["status"] == "PASS" for r in results)
        else "FAIL",
        layers=results,
    )
