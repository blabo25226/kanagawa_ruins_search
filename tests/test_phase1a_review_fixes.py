"""PR #3 regressions: mixed-CRS attributes and explicit dry-run coverage."""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import duckdb
import geopandas as gpd
from shapely.geometry import Point

from kanagawa_ruins.cli import ingest_main
from kanagawa_ruins.geo.spatial import spatial_connection
from kanagawa_ruins.pipeline import TSUKUI_BBOX
from kanagawa_ruins.qa.hashing import sha256
from kanagawa_ruins.qa.sql import register_landuse_attributes


class LanduseAttributeViewTests(unittest.TestCase):
    def test_mixed_crs_aggregation_has_no_geometry_and_preserves_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for year, crs, point in [
                ("1976", 4301, Point(139.2, 35.6)),
                ("2014", 6677, Point(-60000, -40000)),
                ("2021", 6677, Point(-60000, -40000)),
            ]:
                path = Path(tmp) / f"{year}.parquet"
                gpd.GeoDataFrame(
                    {
                        "source_vintage": [year + "_5338"] * 3,
                        "landuse_code": ["0100", "0100", None],
                        "landuse_label": ["田", "田", None],
                    },
                    geometry=[point] * 3,
                    crs=crs,
                ).to_parquet(path)
                paths.append(path)
            before = [sha256(p) for p in paths]
            with spatial_connection() as con:
                register_landuse_attributes(con, paths)
                con.execute("CREATE VIEW layer AS SELECT * FROM landuse")
                for view in ["landuse", "layer"]:
                    schema = con.execute(f"DESCRIBE {view}").fetchall()
                    self.assertEqual(
                        [row[0] for row in schema],
                        ["source_vintage", "landuse_code", "landuse_label"],
                    )
                    self.assertFalse(any("GEOMETRY" in row[1] for row in schema))
                    with self.assertRaises(duckdb.BinderException):
                        con.execute(f"SELECT ST_AsText(geometry) FROM {view}")
                queries = Path(__file__).parents[1] / "src/kanagawa_ruins/queries"
                self.assertEqual(
                    con.execute(
                        (queries / "landuse_counts.sql").read_text()
                    ).fetchall(),
                    [
                        row
                        for year in ["1976", "2014", "2021"]
                        for row in [(year, "0100", "田", 2), (year, None, None, 1)]
                    ],
                )
                self.assertEqual(
                    con.execute((queries / "year_counts.sql").read_text()).fetchall(),
                    [("1976", 3), ("2014", 3), ("2021", 3)],
                )
            self.assertEqual([sha256(p) for p in paths], before)

    def test_empty_input_is_rejected(self):
        with spatial_connection() as con:
            with self.assertRaisesRegex(ValueError, "At least one landuse"):
                register_landuse_attributes(con, [])


class AreaDocumentationTests(unittest.TestCase):
    def run_plan(self, argv):
        paths = [
            "raw/N03-20260101_14.zip",
            "raw/codh_example.geojson",
            "raw/tsukui.osm",
            "raw/kanto.osm.pbf",
            "raw/chubu.osm.pbf",
            "raw/N02-24.zip",
            "raw/W05-08.zip",
            "raw/P32-14.zip",
            "raw/L03-b-14_5338.zip",
        ]
        sources = [
            SimpleNamespace(source_id=f"synthetic_{i}", relative_path=path)
            for i, path in enumerate(paths)
        ]
        out = io.StringIO()
        with (
            patch("kanagawa_ruins.cli.Settings.from_env") as settings,
            patch("kanagawa_ruins.cli.plan", return_value=sources) as plan,
            patch("kanagawa_ruins.cli.ingest_source") as ingest,
            redirect_stdout(out),
        ):
            self.assertEqual(ingest_main(argv), 0)
            ingest.assert_not_called()
            plan.assert_called_once_with(
                settings.return_value,
                ["admin", "osm", "railways", "rivers", "cultural", "landuse"],
                "all" if "all" in argv else "tsukui",
                True,
            )
        return [json.loads(line) for line in out.getvalue().splitlines()]

    def test_default_dry_run_reports_bbox_only_for_pbf(self):
        records = self.run_plan(["--include-pbf"])
        for record in records:
            with self.subTest(path=record["path"]):
                self.assertEqual(record["action"], "dry-run")
                self.assertEqual(record["area"], "tsukui")
                is_pbf = record["path"].endswith(".pbf")
                self.assertEqual(
                    record["spatial_scope"],
                    "tsukui_bbox_intersection_no_clipping"
                    if is_pbf
                    else "original_source_coverage",
                )
                self.assertEqual(
                    record["bbox_wgs84"], list(TSUKUI_BBOX) if is_pbf else None
                )

    def test_explicit_dry_run_and_list_report_the_same_scope(self):
        dry = self.run_plan(["--dry-run", "--area", "tsukui", "--include-pbf"])
        listed = self.run_plan(["--list", "--area", "tsukui", "--include-pbf"])
        self.assertEqual(dry, [dict(record, action="dry-run") for record in listed])
        self.assertTrue(all(record["action"] == "list" for record in listed))

    def test_area_all_keeps_every_sources_original_coverage(self):
        records = self.run_plan(["--dry-run", "--area", "all", "--include-pbf"])
        for record in records:
            self.assertEqual(record["area"], "all")
            self.assertEqual(record["spatial_scope"], "original_source_coverage")
            self.assertIsNone(record["bbox_wgs84"])

    def test_help_explains_pbf_only_selection_before_accessing_data(self):
        out = io.StringIO()
        with (
            patch("kanagawa_ruins.cli.Settings.from_env") as settings,
            redirect_stdout(out),
            self.assertRaises(SystemExit) as error,
        ):
            ingest_main(["--help"])
        self.assertEqual(error.exception.code, 0)
        settings.assert_not_called()
        help_text = " ".join(out.getvalue().split())
        self.assertIn("OSM PBF only", help_text)
        self.assertIn("without clipping", help_text)
        self.assertIn("all disables this selection", help_text)
        self.assertIn(
            "OSM XML and all other GIS inputs retain their original coverage",
            help_text,
        )
