"""Small synthetic fixtures exercise complete publication and query paths, without external data."""

from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import geopandas as gpd
import numpy as np
import osmium
from pyproj import CRS, Transformer
from shapely.geometry import Point, Polygon, LineString, box
from kanagawa_ruins.config import Settings
from kanagawa_ruins.catalog import list_layers, load_layer, get_layer
from kanagawa_ruins.catalog.sources import read_sources, Source
from kanagawa_ruins.catalog.layers import validate_layer_id
from kanagawa_ruins.geo.crs import to_analysis_crs, validate_crs
from kanagawa_ruins.geo.validate import validate_frame
from kanagawa_ruins.geo.spatial import (
    spatial_connection,
    register_layer,
    register_osm_union,
)
from kanagawa_ruins.ingest.kokudo import (
    checked_members,
    vector_chunks,
    metadata_crs,
    vector_files,
)
from kanagawa_ruins.ingest.landuse_mesh import load_codes, normalize_landuse, evidence
from kanagawa_ruins.pipeline import ingest_source
from kanagawa_ruins.qa.hashing import sha256
from kanagawa_ruins.qa.verify import verify_layer
from kanagawa_ruins.storage.scratch import scratch_job

OSM = """<?xml version="1.0"?><osm version="0.6" generator="synthetic-test">
<node id="1" version="1" lat="35.60" lon="139.20"><tag k="amenity" v="place_of_worship"/><tag k="name" v="合成施設"/></node>
<node id="2" version="1" lat="35.61" lon="139.21"/>
<node id="3" version="1" lat="35.61" lon="139.20"/>
<way id="9" version="1"><nd ref="1"/><nd ref="2"/><nd ref="3"/><nd ref="1"/><tag k="highway" v="residential"/></way>
<way id="10" version="1"><nd ref="1"/><nd ref="2"/><nd ref="3"/><nd ref="1"/><tag k="landuse" v="forest"/></way>
<way id="11" version="1"><nd ref="1"/><nd ref="999"/><tag k="highway" v="path"/></way>
<relation id="99" version="1"><member type="way" ref="9" role="outer"/><tag k="historic" v="memorial"/></relation>
</osm>"""


class CRSTests(unittest.TestCase):
    def frame(self, crs=6668, geom=None):
        return gpd.GeoDataFrame(
            {"name": ["合成点"]},
            geometry=[geom if geom is not None else Point(139.2, 35.6)],
            crs=crs,
        )

    def test_projection_matches_independent_pyproj_and_preserves_input(self):
        a = self.frame()
        before = a.copy()
        b = to_analysis_crs(a)
        x, y = Transformer.from_crs(a.crs, 6677, always_xy=True).transform(139.2, 35.6)
        self.assertAlmostEqual(b.geometry[0].x, x, places=6)
        self.assertAlmostEqual(b.geometry[0].y, y, places=6)
        self.assertTrue(a.equals(before))
        self.assertEqual(b.crs.to_epsg(), 6677)

    def test_missing_crs(self):
        with self.assertRaisesRegex(ValueError, "Undefined CRS"):
            to_analysis_crs(self.frame(None))

    def test_swapped_axes(self):
        with self.assertRaisesRegex(ValueError, "swapped"):
            validate_crs(self.frame(geom=Point(35.6, 139.2)))

    def test_nonfinite(self):
        with self.assertRaises(ValueError):
            validate_crs(self.frame(geom=Point(np.inf, 35)))

    def test_vertical_rejected(self):
        with self.assertRaisesRegex(ValueError, "2D"):
            to_analysis_crs(self.frame(geom=Point(139, 35, 10)))

    def test_invalid_geometry_rejected_without_repair(self):
        with self.assertRaisesRegex(ValueError, "Invalid geometries"):
            validate_frame(
                self.frame(
                    geom=Polygon(
                        [(139, 35), (140, 36), (140, 35), (139, 36), (139, 35)]
                    )
                )
            )

    def test_empty_rejected(self):
        with self.assertRaises(ValueError):
            validate_frame(self.frame(geom=Point()))

    def test_datum_families(self):
        self.assertIn("2000", CRS.from_epsg(4612).datum.name)
        self.assertIn(CRS.from_epsg(6668).datum.name.split()[-1], {"2011", "2024"})

    def test_bbox(self):
        self.assertEqual(
            validate_frame(self.frame())["bbox"], [139.2, 35.6, 139.2, 35.6]
        )


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "raw").mkdir()
        (self.root / "provenance.jsonl").write_text("")
        self.settings = Settings(self.root)
        self.stack = ExitStack()
        # Only synthetic test isolation replaces the mount probe; production has no bypass.
        self.stack.enter_context(
            patch(
                "kanagawa_ruins.config.is_rclone_mounted",
                return_value=(True, "synthetic"),
            )
        )
        self.stack.enter_context(
            patch(
                "kanagawa_ruins.storage.drive.is_rclone_mounted",
                return_value=(True, "synthetic"),
            )
        )

    def tearDown(self):
        self.stack.close()
        self.tmp.cleanup()

    def source(self, name, data, sid="synthetic", vintage="2026"):
        p = self.root / "raw" / name
        p.write_bytes(data)
        source = Source(
            sid, "raw/" + name, sha256(p), vintage, None, "test-only", None, None
        )
        r = dict(
            source_id=sid,
            relative_path=source.relative_path,
            sha256=source.sha256,
            temporal_coverage=vintage,
        )
        with (self.root / "provenance.jsonl").open("a") as f:
            f.write(json.dumps(r) + "\n")
        return source

    def admin(self):
        d = self.root / "shape"
        d.mkdir()
        frame = gpd.GeoDataFrame(
            {"N03_001": ["神奈川県"], "N03_004": ["合成市"], "N03_007": ["00000"]},
            geometry=[box(139.2, 35.6, 139.21, 35.61)],
            crs=6668,
        )
        frame.to_file(d / "n03.shp", encoding="UTF-8")
        z = self.root / "n.zip"
        with zipfile.ZipFile(z, "w") as out:
            for p in sorted(d.iterdir()):
                out.write(p, p.name)
        return self.source("N03-2026.zip", z.read_bytes(), "mlit_n03_2026_synthetic")

    def ingest_admin(self):
        s = self.admin()
        layers = ingest_source(s, settings=self.settings)
        return s, layers[0]

    def test_n03_geoparquet_roundtrip_and_japanese(self):
        _, m = self.ingest_admin()
        a = load_layer(m["layer_id"], settings=self.settings)
        self.assertEqual(a.N03_001.tolist(), ["神奈川県"])
        self.assertEqual(a.muni.tolist(), ["合成市"])
        self.assertEqual(a.source_id.tolist(), [m["source_id"]])
        self.assertEqual(a.crs.to_epsg(), 6677)
        self.assertEqual(
            verify_layer(m["layer_id"], settings=self.settings)["status"], "PASS"
        )

    def test_idempotence_byte_reproducibility(self):
        s, m = self.ingest_admin()
        p = self.settings.data_root / m["processed_path"]
        first = p.read_bytes()
        again = ingest_source(s, settings=self.settings)[0]
        self.assertEqual(again["status"], "already_present_reproduced")
        self.assertEqual(first, p.read_bytes())
        self.assertEqual(len(list_layers(settings=self.settings)), 1)

    def test_output_failure_protects_raw_and_ledger_and_cleans_partial(self):
        s = self.admin()
        raw = s.verify(self.root).read_bytes()
        ledger = (self.root / "provenance.jsonl").read_bytes()
        with patch(
            "kanagawa_ruins.pipeline.shutil.copyfileobj",
            side_effect=OSError("simulated output failure"),
        ):
            with self.assertRaises(OSError):
                ingest_source(s, settings=self.settings)
        self.assertEqual(raw, s.verify(self.root).read_bytes())
        self.assertEqual(ledger, (self.root / "provenance.jsonl").read_bytes())
        self.assertEqual(list(self.settings.output_root.rglob("*.partial")), [])
        self.assertEqual(list_layers(settings=self.settings), [])

    def test_drive_unmounted_stops_before_write(self):
        s = self.admin()
        with patch(
            "kanagawa_ruins.config.is_rclone_mounted", return_value=(False, "unmounted")
        ):
            with self.assertRaises(Exception):
                ingest_source(s, settings=self.settings)
        self.assertFalse(self.settings.output_root.exists())

    def test_mounted_root_but_unmounted_output_stops(self):
        s = self.admin()

        def mounted(p):
            return (Path(p) == self.root, "probe")

        with patch("kanagawa_ruins.config.is_rclone_mounted", side_effect=mounted):
            with self.assertRaises(Exception):
                ingest_source(s, settings=self.settings)
        self.assertFalse(self.settings.output_root.exists())

    def test_input_hash_mismatch_refused(self):
        s = self.admin()
        (self.root / s.relative_path).write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            ingest_source(s, settings=self.settings)

    def test_listing_does_not_read_geodata(self):
        self.ingest_admin()
        with patch(
            "geopandas.read_parquet", side_effect=AssertionError("read forbidden")
        ):
            self.assertEqual(len(list_layers(settings=self.settings)), 1)

    def test_sql_bbox_matches_shapely(self):
        _, m = self.ingest_admin()
        a = load_layer(m["layer_id"], settings=self.settings)
        bbox = a.total_bounds.tolist()
        b = load_layer(
            m["layer_id"],
            settings=self.settings,
            bbox=bbox,
            columns=["muni", "geometry"],
            limit=1,
        )
        self.assertEqual(len(b), int(a.intersects(box(*bbox)).sum()))
        self.assertEqual(b.muni.tolist(), a.muni.tolist())
        with spatial_connection() as con:
            register_layer(con, m["layer_id"], settings=self.settings)
            con.execute('CREATE VIEW layer AS SELECT * FROM "' + m["layer_id"] + '"')
            sql = (Path(__file__).parents[1] / "queries/bbox.sql").read_text()
            self.assertEqual(len(con.execute(sql, bbox).fetchall()), len(a))

    def test_osm_xml_node_way_and_explicit_omissions(self):
        s = self.source("test.osm", OSM.encode(), "osm_synthetic")
        layers = ingest_source(s, settings=self.settings)
        by_domain = {m["layer_id"].split("__")[1]: m for m in layers}
        self.assertEqual(set(by_domain), {"roads", "worship", "landuse"})
        for m in layers:
            stats = m["ingest_statistics"]
            self.assertEqual(stats["missing_way_refs"], 1)
            self.assertEqual(stats["unsupported_relations"], 1)
        roads = load_layer(by_domain["roads"]["layer_id"], settings=self.settings)
        self.assertEqual(roads.geom_type.tolist(), ["LineString"])
        land = load_layer(by_domain["landuse"]["layer_id"], settings=self.settings)
        self.assertEqual(land.geom_type.tolist(), ["Polygon"])
        worship = load_layer(by_domain["worship"]["layer_id"], settings=self.settings)
        self.assertEqual(worship["name"].tolist(), ["合成施設"])
        self.assertTrue(worship.religion.isna().all())

    def test_osm_pbf_streaming_and_cross_extract_dedup(self):
        # Produce genuine protobuf using libosmium, not a header-only stub.
        p = self.root / "synthetic.osm"
        p.write_text(OSM, encoding="utf-8")
        out = self.root / "synthetic.osm.pbf"
        with osmium.SimpleWriter(str(out)) as writer:
            for obj in osmium.FileProcessor(str(p)):
                writer.add(obj)
        s1 = self.source("a.osm.pbf", out.read_bytes(), "osm_a")
        s2 = self.source("b.osm.pbf", out.read_bytes(), "osm_b")
        # Exercise the default PBF bbox, including its JSON publication/readback.
        a = ingest_source(s1, settings=self.settings, area="tsukui")
        b = ingest_source(s2, settings=self.settings, area="tsukui")
        self.assertEqual(a[0]["parameters"]["pbf_bbox"], [139.12, 35.51, 139.25, 35.62])
        repeated = ingest_source(s1, settings=self.settings, area="tsukui")
        self.assertTrue(
            all(m["status"] == "already_present_reproduced" for m in repeated)
        )
        roads = [
            m["layer_id"] for m in a + b if m["layer_id"].split("__")[1] == "roads"
        ]
        with spatial_connection() as con:
            duplicates = register_osm_union(con, roads, settings=self.settings)
            self.assertEqual(len(duplicates), 1)
            self.assertEqual(
                con.sql("SELECT count(*) FROM osm_unique").fetchone()[0], 1
            )

    def test_malformed_xml_refused_without_publication(self):
        s = self.source("broken.osm", OSM.encode()[:-8], "osm_broken")
        with self.assertRaises(Exception):
            ingest_source(s, settings=self.settings)
        self.assertEqual(list_layers(settings=self.settings), [])

    def test_output_symlink_escape(self):
        s = self.admin()
        self.settings.output_root.mkdir(parents=True)
        outside = self.root / "outside"
        outside.mkdir()
        (self.settings.output_root / "vectors").symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "escapes"):
            ingest_source(s, settings=self.settings)
        self.assertEqual(list(outside.iterdir()), [])

    def test_catalog_traversal_refused(self):
        with self.assertRaises(ValueError):
            get_layer("../../raw/x", settings=self.settings)

    def test_source_ids_unique(self):
        self.source("a.osm", OSM.encode())
        self.source("b.osm", OSM.encode())
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            read_sources(self.root)

    def test_layer_names_unique_and_valid(self):
        _, m = self.ingest_admin()
        self.assertEqual(validate_layer_id(m["layer_id"]), m["layer_id"])
        with self.assertRaises(ValueError):
            validate_layer_id("a/../../raw")

    def test_landuse_year_and_unknown_codes(self):
        codes = load_codes()
        self.assertEqual(set(codes), {"1976", "2014", "2021"})
        a = gpd.GeoDataFrame(
            {"L03b_002": ["9999", None]},
            geometry=[Point(139, 35), Point(139.1, 35.1)],
            crs=4612,
        )
        b = normalize_landuse(a, 1976)
        self.assertEqual(b.landuse_label.tolist(), ["unknown", "unknown"])
        self.assertEqual(b.L03b_002.tolist(), a.L03b_002.tolist())

    def test_zip_traversal_refused(self):
        p = self.root / "bad.zip"
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("../escape", "bad")
        with zipfile.ZipFile(p) as z:
            with self.assertRaises(ValueError):
                checked_members(z, 100)

    def test_scratch_budget_and_cleanup(self):
        path = None
        with self.assertRaises(OSError):
            with scratch_job(100) as j:
                path = j.path
                (path / "x").write_bytes(b"x" * 101)
                j.check()
        self.assertFalse(path.exists())

    def test_metadata_crs_explicit_and_undefined(self):
        p = self.root / "x.shp"
        p.touch()
        with self.assertRaises(ValueError):
            metadata_crs(p)
        (self.root / "KS-META.xml").write_text(
            "<root><referenceSystemInfo><code>TD / (B, L)</code></referenceSystemInfo></root>"
        )
        self.assertEqual(metadata_crs(p)[0], "EPSG:4301")

    def test_landuse_internal_year_mismatch_rejected(self):
        p = self.root / "x.shp"
        p.touch()
        (self.root / "KS-META.xml").write_text(
            "<root><title>土地利用（L03-b-14_5339）</title></root>"
        )
        with self.assertRaisesRegex(ValueError, "year mismatch"):
            evidence(p, "2021")
        self.assertTrue(evidence(p, "2014"))


class LanduseSchemaTests(unittest.TestCase):
    def test_2014_japanese_field_preserved_and_official_label(self):
        frame = gpd.GeoDataFrame(
            {"土地利用種": ["0500", "9999"]},
            geometry=[Point(139, 35), Point(139, 35.1)],
            crs=4612,
        )
        out = normalize_landuse(frame, 2014)
        self.assertEqual(out["土地利用種"].tolist(), ["0500", "9999"])
        self.assertEqual(out.landuse_label.tolist(), ["森林", "unknown"])

    def test_1976_has_distinct_official_codes(self):
        codes = load_codes()
        self.assertEqual(codes["1976"]["codes"]["7"], "建物用地A")
        self.assertNotIn("7", codes["2014"]["codes"])


class GMLIntegrationTests(unittest.TestCase):
    def test_standalone_gml_driver_sidecars_cannot_touch_source(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "N02-synthetic.gml"
            gpd.GeoDataFrame(
                {"name": ["合成路線"]}, geometry=[Point(139, 35)], crs=4612
            ).to_file(path, driver="GML")
            before = {p.name: p.read_bytes() for p in path.parent.iterdir()}
            with scratch_job() as job:
                with vector_files(path, job) as files:
                    self.assertNotEqual(files[0], path)
                    self.assertEqual(sum(len(f) for _, f in vector_chunks(files[0])), 1)
            self.assertEqual(
                before, {p.name: p.read_bytes() for p in path.parent.iterdir()}
            )

    def test_gml_vector_loader(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "N02-synthetic.gml"
            frame = gpd.GeoDataFrame(
                {"name": ["合成路線"]},
                geometry=[LineString([(139, 35), (139.1, 35.1)])],
                crs=4612,
            )
            frame.to_file(path, driver="GML")
            chunks = list(vector_chunks(path))
            self.assertEqual(sum(len(f) for _, f in chunks), 1)
            self.assertEqual(chunks[0][1]["name"].tolist(), ["合成路線"])
            self.assertTrue(chunks[0][1].geometry.is_valid.all())


class DuckDBCRSTests(unittest.TestCase):
    def test_duckdb_always_xy_matches_pyproj(self):
        with spatial_connection() as con:
            x, y = con.execute(
                "SELECT ST_X(g),ST_Y(g) FROM (SELECT ST_Transform(ST_Point(139.2,35.6),'EPSG:6668','EPSG:6677',always_xy:=true) AS g)"
            ).fetchone()
        px, py = Transformer.from_crs(6668, 6677, always_xy=True).transform(139.2, 35.6)
        self.assertAlmostEqual(x, px, places=5)
        self.assertAlmostEqual(y, py, places=5)


if __name__ == "__main__":
    unittest.main()
