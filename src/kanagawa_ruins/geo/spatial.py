"""Memory-only DuckDB Spatial views. Geometry carries no reliable SRID in DuckDB 1.4."""

from contextlib import contextmanager
import math
import duckdb


def quote_identifier(value):
    return '"' + value.replace('"', '""') + '"'


def validate_bbox(bbox):
    if (
        len(bbox) != 4
        or not all(math.isfinite(v) for v in bbox)
        or bbox[0] > bbox[2]
        or bbox[1] > bbox[3]
    ):
        raise ValueError("Invalid x/y bounding box")


@contextmanager
def spatial_connection(*, install=False):
    con = duckdb.connect(
        ":memory:",
        config={"memory_limit": "1GB", "threads": 2, "max_temp_directory_size": "0B"},
    )
    try:
        if install:
            con.execute("INSTALL spatial")
        try:
            con.execute("LOAD spatial")
        except duckdb.Error as e:
            raise RuntimeError(
                "Spatial extension unavailable; run spatial_connection(install=True) once with network access"
            ) from e
        yield con
    finally:
        con.close()


def register_layer(con, layer_id, *, settings=None):
    from ..catalog.layers import get_layer

    m, p = get_layer(layer_id, settings=settings)
    if m["processed_crs"] != "EPSG:6677":
        raise ValueError("Query views require normalized EPSG:6677")
    # Values are escaped; identifiers are quoted. CREATE VIEW cannot bind path parameters.
    path = str(p).replace("'", "''")
    con.execute(
        f"CREATE OR REPLACE VIEW {quote_identifier(layer_id)} AS SELECT * FROM read_parquet('{path}')"
    )
    return m


def register_osm_union(con, layer_ids, *, settings=None, name="osm_unique"):
    """Deduplicate overlapping extracts by type/id. First caller-specified source wins, no filling."""
    if not layer_ids:
        raise ValueError("At least one OSM layer required")
    arms = []
    for rank, lid in enumerate(layer_ids):
        register_layer(con, lid, settings=settings)
        if not lid.startswith("osm__"):
            raise ValueError("Only same-domain OSM layers may be combined")
        arms.append(f"SELECT *, {rank} AS source_priority FROM {quote_identifier(lid)}")
    domains = {lid.split("__")[1] for lid in layer_ids}
    if len(domains) != 1:
        raise ValueError("Mixing OSM domains would incorrectly drop multi-tag objects")
    union = " UNION ALL BY NAME ".join(arms)
    duplicates = con.sql(
        f"SELECT osm_type,osm_id,count(*) AS copies,count(DISTINCT tags_json) AS tag_versions,count(DISTINCT ST_AsWKB(geometry)) AS geometry_versions FROM ({union}) GROUP BY osm_type,osm_id HAVING count(*)>1"
    ).fetchdf()
    con.execute(
        f"CREATE OR REPLACE VIEW {quote_identifier(name)} AS SELECT * EXCLUDE(source_priority) FROM ({union}) QUALIFY row_number() OVER(PARTITION BY osm_type,osm_id ORDER BY source_priority)=1"
    )
    return duplicates
