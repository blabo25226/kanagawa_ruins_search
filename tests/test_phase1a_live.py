"""Opt-in real-data integration checks, separate from synthetic tests."""

import os
from pathlib import Path
import zipfile
import tempfile
import geopandas as gpd
import pytest
from kanagawa_ruins.catalog import list_layers, load_layer
from kanagawa_ruins.config import Settings
from kanagawa_ruins.geo.spatial import spatial_connection, register_layer

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("RUINS_RUN_LIVE") != "1",
        reason="set RUINS_RUN_LIVE=1 for mounted Drive integration",
    ),
]


def test_real_n03_attributes_match_raw():
    settings = Settings.from_env()
    path = settings.data_root / "raw/administrative/N03-20260101_14_GML.zip"
    with tempfile.TemporaryDirectory(prefix="ruins-live-test-") as d:
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if Path(name).suffix in {".shp", ".shx", ".dbf", ".prj", ".cpg"}:
                    z.extract(name, d)
        shp = next(Path(d).rglob("*.shp"))
        original = gpd.read_file(shp)
    result = load_layer("admin__n03__2026_kanagawa")
    assert len(result) == len(original)
    for col in original.columns.drop("geometry"):
        assert result[col].isna().equals(original[col].isna())
        present = original[col].notna()
        assert result.loc[present, col].tolist() == original.loc[present, col].tolist()
    assert result.crs.to_epsg() == 6677


def test_real_osm_sql_range_matches_shapely():
    lid = "osm__roads__2026_10_osm_tsukui_core"
    roads = load_layer(lid)
    xmin, ymin, xmax, ymax = roads.total_bounds
    bbox = (xmin, ymin, (xmin + xmax) / 2, (ymin + ymax) / 2)
    from shapely.geometry import box

    expected = set(roads.loc[roads.intersects(box(*bbox)), "osm_id"])
    with spatial_connection() as con:
        register_layer(con, lid)
        con.execute('CREATE VIEW layer AS SELECT * FROM "' + lid + '"')
        sql = (Path(__file__).parents[1] / "queries/bbox.sql").read_text()
        df = con.execute(sql, bbox).fetchdf()
    assert set(df.osm_id) == expected


def test_real_six_landuse_vintages_are_distinct():
    layers = [m for m in list_layers() if m["layer_id"].startswith("landuse__l03b__")]
    assert {m["layer_id"] for m in layers} == {
        f"landuse__l03b__{year}_{mesh}"
        for year in [1976, 2014, 2021]
        for mesh in [5338, 5339]
    }
    for m in layers:
        assert m["source_sha256"] and m["output_sha256"]
        if m["temporal_coverage"] == "1976":
            assert m["processed_crs"] == "EPSG:4301"
            assert not m["analysis_ready"]
        else:
            assert m["processed_crs"] == "EPSG:6677"
