"""Real-data SQL verification against independently evaluated Shapely selections."""

from pathlib import Path
from shapely.geometry import box
from ..catalog import list_layers, load_layer, get_layer
from ..geo.spatial import (
    spatial_connection,
    register_layer,
    register_osm_union,
    quote_identifier,
)
from ..pipeline import implementation_sha256, versions


def register_landuse_attributes(con, paths):
    """Register only aggregation attributes; input geometries may have different CRSs."""
    arms = [
        "SELECT source_vintage, landuse_code, landuse_label FROM read_parquet('"
        + str(p).replace("'", "''")
        + "')"
        for p in paths
    ]
    if not arms:
        raise ValueError("At least one landuse layer required")
    # Project before UNION: no mixed-CRS geometry may enter this attribute view.
    con.execute("CREATE VIEW landuse AS " + " UNION ALL BY NAME ".join(arms))


def validate_sql():
    layers = list_layers()
    result = {"implementation_sha256": implementation_sha256(), "versions": versions()}
    with spatial_connection() as con:
        result["spatial_extension"] = (
            con.sql(
                "SELECT extension_name,extension_version,installed_from FROM duckdb_extensions() WHERE extension_name='spatial'"
            )
            .fetchdf()
            .to_dict("records")
        )
        duplicates = []
        for domain in ["roads", "waterways", "worship", "historic", "landuse"]:
            lids = [
                m["layer_id"]
                for m in layers
                if m["layer_id"].startswith("osm__" + domain + "__")
            ]
            if not lids:
                continue
            d = register_osm_union(con, lids, name="osm_unique_" + domain)
            duplicates.append(
                {
                    "domain": domain,
                    "input_layers": len(lids),
                    "duplicate_ids": len(d),
                    "duplicate_rows": int((d.copies - 1).sum()),
                    "conflicting_tags": int((d.tag_versions > 1).sum()),
                    "conflicting_geometry": int((d.geometry_versions > 1).sum()),
                    "unique_rows": con.sql(
                        "SELECT count(*) FROM "
                        + quote_identifier("osm_unique_" + domain)
                    ).fetchone()[0],
                }
            )
        result["osm_duplicates"] = duplicates
        lid = "osm__roads__2026_10_osm_tsukui_core"
        register_layer(con, lid)
        con.execute("CREATE VIEW layer AS SELECT * FROM " + quote_identifier(lid))
        roads = load_layer(lid)
        xmin, ymin, xmax, ymax = roads.total_bounds
        bbox = [xmin, ymin, (xmin + xmax) / 2, (ymin + ymax) / 2]
        actual = con.execute(
            (Path(__file__).parents[1] / "queries" / "bbox.sql").read_text(), bbox
        ).fetchdf()
        expected = roads[roads.intersects(box(*bbox))]
        if set(actual.osm_id) != set(expected.osm_id):
            raise ValueError("SQL bbox selection disagrees with Shapely")
        result["bbox_query"] = {
            "sql_count": len(actual),
            "shapely_count": len(expected),
            "match": True,
        }
        register_layer(con, "admin__n03__2026_kanagawa")
        con.execute('CREATE VIEW admin AS SELECT * FROM "admin__n03__2026_kanagawa"')
        con.execute("CREATE VIEW roads AS SELECT * FROM " + quote_identifier(lid))
        actual = con.execute(
            (Path(__file__).parents[1] / "queries" / "admin_extract.sql").read_text(),
            ["14151"],
        ).fetchdf()
        admin = load_layer("admin__n03__2026_kanagawa")
        geom = admin.loc[admin.muni_code == "14151"].geometry.union_all()
        expected = roads[roads.intersects(geom)]
        if set(actual.osm_id) != set(expected.osm_id):
            raise ValueError("SQL administrative selection disagrees with Shapely")
        result["admin_query"] = {
            "sql_count": len(actual),
            "shapely_count": len(expected),
            "match": True,
        }
        register_landuse_attributes(
            con,
            [
                get_layer(m["layer_id"])[1]
                for m in layers
                if m["layer_id"].startswith("landuse__l03b__")
            ],
        )
        result["landuse_attribute_columns"] = [
            row[0] for row in con.execute("DESCRIBE landuse").fetchall()
        ]
        result["landuse_counts"] = (
            con.execute(
                (
                    Path(__file__).parents[1] / "queries" / "landuse_counts.sql"
                ).read_text()
            )
            .fetchdf()
            .to_dict("records")
        )
        con.execute("CREATE OR REPLACE VIEW layer AS SELECT * FROM landuse")
        result["year_counts"] = (
            con.execute(
                (Path(__file__).parents[1] / "queries" / "year_counts.sql").read_text()
            )
            .fetchdf()
            .to_dict("records")
        )
        expected = {
            year: sum(
                m["feature_count"]
                for m in layers
                if m["layer_id"].startswith("landuse__l03b__")
                and m["temporal_coverage"] == year
            )
            for year in ["1976", "2014", "2021"]
        }
        if {
            r["source_year"]: r["feature_count"] for r in result["year_counts"]
        } != expected:
            raise ValueError("SQL year counts disagree with catalog")
        result["year_counts_match_catalog"] = True
        # Raw input Japanese P32 preference codes establish actual coverage, without assuming all 47.
        pref = []
        for m in layers:
            if m["source_id"] == "mlit_cultural_properties_nationwide":
                _, p = get_layer(m["layer_id"])
                pref += [
                    r[0]
                    for r in con.execute(
                        "SELECT DISTINCT P32_002 FROM read_parquet(?)", [str(p)]
                    ).fetchall()
                ]
        result["p32_nationwide_pref_codes"] = sorted(set(pref))
    result["status"] = "PASS"
    return result
