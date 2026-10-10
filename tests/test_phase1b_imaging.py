"""Synthetic rasters exercise XYZ, lossless COG, metadata search and publication safety."""

from contextlib import ExitStack, redirect_stdout
import io
import json
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import warnings

import numpy as np
import rasterio
from rasterio.transform import from_origin
from pyproj import Transformer

from kanagawa_ruins.catalog.sources import Source
from kanagawa_ruins.imaging.tiles import (
    XYZ,
    HALF_WORLD,
    pixel_to_ground,
    ground_to_pixel,
    tile_to_cog,
    check_tile_location,
)
from kanagawa_ruins.imaging.catalog import (
    normalize_catalog,
    search_catalog,
    nearby_photos,
)
from kanagawa_ruins.raster.cog import validate_cog, to_cog, pixels_equal
from kanagawa_ruins.raster.io import read_windows, local_output
from kanagawa_ruins.raster.config import RasterSettings
from kanagawa_ruins.raster.storage import publish_artifact
from kanagawa_ruins.raster.cli import main
from kanagawa_ruins.storage.scratch import scratch_job
from kanagawa_ruins.qa.hashing import sha256
from kanagawa_ruins.qa.derived import registered_derived_files


def rgb(path, size=256):
    a = np.arange(size * size, dtype=np.uint8).reshape(size, size)
    data = np.stack([a, np.flipud(a), np.fliplr(a)])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", rasterio.errors.NotGeoreferencedWarning)
        with rasterio.open(
            path, "w", driver="GTiff", width=size, height=size, count=3, dtype="uint8"
        ) as dst:
            dst.write(data)
    return data


class XYZTests(unittest.TestCase):
    def test_world_and_adjacent_tile_bounds(self):
        self.assertEqual(
            XYZ(0, 0, 0).bounds(), (-HALF_WORLD, -HALF_WORLD, HALF_WORLD, HALF_WORLD)
        )
        self.assertAlmostEqual(XYZ(2, 1, 1).bounds()[2], XYZ(2, 2, 1).bounds()[0])
        self.assertAlmostEqual(XYZ(2, 1, 1).bounds()[1], XYZ(2, 1, 2).bounds()[3])

    def test_north_origin_and_pixel_centers_roundtrip(self):
        tile = XYZ(15, 29054, 12916)
        a = pixel_to_ground(tile, 0, 0)
        b = pixel_to_ground(tile, 0, 255)
        self.assertGreater(a[1], b[1])
        self.assertLess(tile.affine().e, 0)
        for crs in ["EPSG:3857", "EPSG:4326", "EPSG:6677"]:
            x, y = pixel_to_ground(tile, 10, 20, crs=crs)
            c, r = ground_to_pixel(tile, x, y, crs=crs)
            self.assertAlmostEqual(c, 10, places=6)
            self.assertAlmostEqual(r, 20, places=6)
        self.assertEqual(
            pixel_to_ground(tile, 0, 0, center=False),
            (tile.bounds()[0], tile.bounds()[3]),
        )

    def test_lonlat_matches_independent_slippy_formula(self):
        tile = XYZ.from_filename("aonohara_1974_z15_29054_12916.jpg")
        w, s, e, n = tile.lonlat_bounds()
        self.assertAlmostEqual(w, tile.x / 2**tile.z * 360 - 180)
        self.assertAlmostEqual(
            n,
            math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * tile.y / 2**tile.z)))),
        )
        mx, my = tile.affine() @ (10.5, 20.5)
        self.assertTrue(
            np.allclose(
                pixel_to_ground(tile, 10, 20, crs="EPSG:6677"),
                Transformer.from_crs(3857, 6677, always_xy=True).transform(mx, my),
            )
        )

    def test_bad_xyz_missing_metadata_and_distant_tile_rejected(self):
        for args in [(2, 4, 0), (2, 0, -1), (True, 1, 1), (31, 1, 1)]:
            with self.assertRaises(ValueError):
                XYZ(*args)
        with self.assertRaises(ValueError):
            XYZ.from_filename("1974.jpg")
        with self.assertRaisesRegex(ValueError, "outside the expected"):
            check_tile_location(XYZ(15, 1, 1))
        with self.assertRaises(ValueError):
            XYZ(1, 0, 0).affine(512)

    def test_real_conversion_code_preserves_pixels_and_cog_bounds(self):
        with scratch_job(1_000_000_000) as job:
            src = job.path / "synthetic_z15_29054_12916.tif"
            expected = rgb(src)
            output = job.path / "output.tif"
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", rasterio.errors.NotGeoreferencedWarning)
                info = tile_to_cog(src, output, job=job)
            self.assertEqual(info["crs"], "EPSG:3857")
            self.assertEqual(info["overviews"], [2])
            self.assertEqual(info["compression"].lower(), "deflate")
            self.assertTrue(info["cog_full_check"])
            with rasterio.open(output) as ds:
                np.testing.assert_array_equal(ds.read(), expected)
            self.assertTrue(pixels_equal(src, output))
            self.assertTrue(np.allclose(info["bbox"], XYZ.from_filename(src).bounds()))

    def test_wrong_tile_size_and_non_cog_rejected(self):
        with scratch_job(1_000_000_000) as job:
            src = job.path / "bad_z15_29054_12916.tif"
            rgb(src, 32)
            with self.assertRaisesRegex(ValueError, "256x256"):
                tile_to_cog(src, job.path / "out.tif", job=job)
            with self.assertRaises(ValueError):
                validate_cog(src)

    def test_windowed_io_and_deterministic_cog(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root / "source.tif"
            with rasterio.open(
                source,
                "w",
                driver="GTiff",
                width=600,
                height=600,
                count=1,
                dtype="uint16",
                crs=6677,
                transform=from_origin(-60000, -40000, 5, 5),
            ) as dst:
                dst.write(np.ones((1, 600, 600), dtype="uint16"))
            chunks = list(read_windows(source, 128))
            self.assertEqual(len(chunks), 25)
            self.assertTrue(
                all(a.shape[1] <= 128 and a.shape[2] <= 128 for _, a in chunks)
            )
            for name in ["one.tif", "two.tif"]:
                to_cog(source, root / name)
            self.assertEqual(sha256(root / "one.tif"), sha256(root / "two.tif"))


def photo(sid=1, *, center=(139.2, 35.6), corners=True, capture="1969-06-10"):
    r = dict(
        specification_id=sid,
        date=capture,
        center_pos=list(center) if center else None,
        footprint_status="valid",
    )
    if corners:
        for k, v in zip(
            ["left_top", "right_top", "right_bottom", "left_bottom"],
            [(139.19, 35.61), (139.21, 35.61), (139.21, 35.59), (139.19, 35.59)],
        ):
            r["geom_image_" + k + "_pos"] = v
    return r


class CatalogTests(unittest.TestCase):
    def test_actual_keys_unknown_fields_and_original_retained(self):
        r = photo()
        r["planning_organization"] = "合成機関"
        a = normalize_catalog([r])[0]
        self.assertEqual(a["specId"], "1")
        self.assertEqual(a["organization"], "合成機関")
        self.assertEqual(a["footprint_state"], "footprint_approximate")
        self.assertIsNone(a["altitude"])
        self.assertIsNone(a["coordinate_crs"])
        self.assertEqual(a["image_acquisition_state"], "unknown")
        self.assertEqual(a["original"], r)

    def test_center_only_never_satisfies_footprint_query(self):
        r = photo(corners=False, capture="1111-11-11")
        a = normalize_catalog([r])[0]
        self.assertEqual(a["footprint_state"], "center_only")
        self.assertIsNone(a["capture_date"])
        self.assertIsNone(a["decade"])
        self.assertEqual(
            search_catalog(
                [a], bbox_native=[139.1, 35.5, 139.3, 35.7], footprints_only=True
            ),
            [],
        )
        self.assertEqual(
            len(search_catalog([a], bbox_native=[139.1, 35.5, 139.3, 35.7])), 1
        )

    def test_degenerate_invalid_unknown_footprints_and_missing_center(self):
        r = photo(center=None)
        for k in ["left_top", "right_top", "right_bottom", "left_bottom"]:
            r["geom_image_" + k + "_pos"] = [139.2, 35.6]
        self.assertEqual(
            normalize_catalog([r])[0]["footprint_state"], "footprint_unknown"
        )
        r = photo()
        r["footprint_status"] = "unknown"
        self.assertEqual(normalize_catalog([r])[0]["footprint_state"], "center_only")

    def test_search_date_bbox_and_acquisition_status(self):
        a = normalize_catalog(
            [photo(1), photo(2, capture=None)], acquisition_inventory_complete=True
        )
        self.assertEqual(len(search_catalog(a, decade="1960s")), 1)
        self.assertEqual(len(search_catalog(a, unacquired_only=True)), 2)
        self.assertEqual(search_catalog(a, bbox_native=[0, 0, 1, 1]), [])
        with self.assertRaises(ValueError):
            nearby_photos(a, 139.2, 35.6, 100)
        self.assertEqual(
            len(nearby_photos(a, 139.2, 35.6, 100, coordinate_crs="EPSG:4326")), 2
        )

    def test_false_verification_and_duplicate_ids_rejected(self):
        r = photo()
        r["verification_status"] = "verified"
        self.assertEqual(
            normalize_catalog([r])[0]["footprint_state"], "footprint_approximate"
        )
        with self.assertRaises(ValueError):
            normalize_catalog([r, r])
        with self.assertRaises(ValueError):
            normalize_catalog([{"specId": 1}])


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data = self.root / "bank"
        (self.data / "raw").mkdir(parents=True)
        self.raw = self.data / "raw/source.json"
        self.raw.write_text("{}")
        self.source = Source(
            "synthetic",
            "raw/source.json",
            sha256(self.raw),
            None,
            None,
            None,
            None,
            None,
        )
        (self.data / "provenance.jsonl").write_text(
            json.dumps(
                dict(
                    source_id=self.source.source_id,
                    relative_path=self.source.relative_path,
                    sha256=self.source.sha256,
                    size_bytes=self.raw.stat().st_size,
                )
            )
            + "\n"
        )
        self.settings = RasterSettings(self.data)
        self.stack = ExitStack()
        self.stack.enter_context(
            patch(
                "kanagawa_ruins.raster.config.is_rclone_mounted",
                return_value=(True, "synthetic"),
            )
        )
        self.stack.enter_context(
            patch(
                "kanagawa_ruins.storage.drive.is_rclone_mounted",
                return_value=(True, "synthetic"),
            )
        )
        self.local = self.root / "output.json"
        self.local.write_text('{"synthetic": true}')

    def tearDown(self):
        self.stack.close()
        self.temp.cleanup()

    def publish(self):
        return publish_artifact(
            self.settings,
            self.local,
            asset_id="aerial__synthetic__v1",
            relative_output="aerial/catalog/aerial__synthetic__v1.json",
            source=self.source,
            parameters={},
            metadata={"kind": "photo_catalog"},
        )

    def test_registration_idempotence_and_input_protection(self):
        before = sha256(self.raw)
        a = self.publish()
        b = self.publish()
        self.assertEqual(a["output_sha256"], b["output_sha256"])
        self.assertEqual(b["status"], "already_present_reproduced")
        files = {
            str(p.relative_to(self.data)): p
            for p in self.data.rglob("*")
            if p.is_file()
        }
        self.assertEqual(len(registered_derived_files(self.data, files)), 2)
        self.assertEqual(sha256(self.raw), before)
        (self.data / a["processed_path"]).write_text("corrupt")
        self.assertEqual(registered_derived_files(self.data, files), set())
        with self.assertRaises(ValueError):
            self.publish()

    def test_unmounted_escape_and_raw_phase1a_write_rejected(self):
        with patch(
            "kanagawa_ruins.raster.config.is_rclone_mounted",
            return_value=(False, "unmounted"),
        ):
            with self.assertRaises(Exception):
                self.publish()
        for rel in [
            "../../raw/aerial__synthetic__v1.json",
            "../phase1a/aerial__synthetic__v1.json",
        ]:
            with self.assertRaises(ValueError):
                publish_artifact(
                    self.settings,
                    self.local,
                    asset_id="aerial__synthetic__v1",
                    relative_output=rel,
                    source=self.source,
                    parameters={},
                    metadata={},
                )
        with patch.dict(os.environ, {"RUINS_DATA_ROOT": str(self.data)}):
            for rel in ["raw/new.tif", "processed/phase1a/new.tif"]:
                with self.assertRaises(ValueError):
                    local_output(self.data / rel)

    def test_interruption_rolls_back_only_new_output_and_cleans_partials(self):
        original = Path.rename

        def interrupt_manifest(path, target):
            if "manifests" in path.parts:
                raise KeyboardInterrupt()
            return original(path, target)

        with patch.object(Path, "rename", interrupt_manifest):
            with self.assertRaises(KeyboardInterrupt):
                self.publish()
        self.assertEqual(list(self.settings.output_root.rglob("*.partial")), [])
        self.assertEqual(list(self.settings.output_root.rglob("*.json")), [])
        self.assertEqual(self.raw.read_text(), "{}")

    def test_scratch_cleanup_on_interruption(self):
        with self.assertRaises(KeyboardInterrupt):
            with scratch_job(1_000_000_000) as job:
                d = job.path
                (d / "temporary").write_text("synthetic")
                raise KeyboardInterrupt()
        self.assertFalse(d.exists())

    def test_default_cli_is_dry_run_and_does_not_ingest(self):
        with (
            patch(
                "kanagawa_ruins.raster.cli.RasterSettings.from_env",
                return_value=self.settings,
            ),
            patch(
                "kanagawa_ruins.raster.cli.imagery_sources", return_value=[self.source]
            ),
            patch("kanagawa_ruins.raster.cli.ingest_tile") as ingest,
            redirect_stdout(io.StringIO()) as out,
        ):
            self.assertEqual(main("imaging", []), 0)
            ingest.assert_not_called()
        self.assertEqual(json.loads(out.getvalue())["status"], "PLANNED")

    def test_audit_rejects_unregistered_and_corrupted_derivatives(self):
        from scripts.audit_databank import audit_databank

        self.publish()
        self.assertEqual(audit_databank(self.data)["audit_verdict"], "FAST_PASS")
        stray = self.settings.output_root / "unregistered.json"
        stray.write_text("{}")
        self.assertEqual(audit_databank(self.data)["audit_verdict"], "FAIL")
        stray.unlink()
        output = self.settings.output_root / "aerial/catalog/aerial__synthetic__v1.json"
        output.write_text("corrupted")
        audit = audit_databank(self.data)
        self.assertEqual(audit["audit_verdict"], "FAIL")
        self.assertEqual(audit["unregistered_files_count"], 2)

    def test_future_georef_cli_executes_only_explicit_registered_synthetic_input(self):
        from argparse import Namespace
        from dataclasses import asdict
        from kanagawa_ruins.raster.jobs import execute_job, planned_job
        from kanagawa_ruins.qa.raster_verify import verify_artifact
        from tests.test_phase1b_georef_terrain import points

        image = self.data / "raw/synthetic.tif"
        rgb(image, 32)
        self.source = Source(
            "synthetic",
            "raw/synthetic.tif",
            sha256(image),
            None,
            None,
            None,
            None,
            None,
        )
        (self.data / "provenance.jsonl").write_text(
            json.dumps(
                dict(
                    source_id="synthetic",
                    relative_path=self.source.relative_path,
                    sha256=self.source.sha256,
                )
            )
            + "\n"
        )
        train, valid = points()
        control = self.root / "controls.json"
        control.write_text(
            json.dumps(
                dict(
                    training=[asdict(p) for p in train],
                    validation=[asdict(p) for p in valid],
                )
            )
        )
        args = Namespace(
            source_id=["synthetic"],
            asset_id="historical__synthetic__v1",
            gcps=control,
            list=False,
        )
        self.assertFalse(planned_job("georef", args, self.settings)["writes"])
        result = execute_job("georef", args, self.settings)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(
            verify_artifact(result["results"][0], self.settings)["status"], "PASS"
        )
        again = execute_job("georef", args, self.settings)
        self.assertEqual(again["results"][0]["status"], "already_present_reproduced")
        self.assertEqual(sha256(image), self.source.sha256)

    def test_future_dem_job_publishes_validated_products_and_reproduces(self):
        from argparse import Namespace
        from dataclasses import asdict
        from kanagawa_ruins.raster.jobs import execute_job
        from kanagawa_ruins.qa.raster_verify import verify_artifact
        from tests.test_phase1b_georef_terrain import raster, reference

        image = self.data / "raw/synthetic_dem.tif"
        raster(image, np.arange(64, dtype="float32").reshape(8, 8))
        self.source = Source(
            "synthetic",
            "raw/synthetic_dem.tif",
            sha256(image),
            None,
            None,
            None,
            None,
            None,
        )
        (self.data / "provenance.jsonl").write_text(
            json.dumps(
                dict(
                    source_id="synthetic",
                    relative_path=self.source.relative_path,
                    sha256=self.source.sha256,
                    size_bytes=image.stat().st_size,
                )
            )
            + "\n"
        )
        ref = self.root / "reference.json"
        ref.write_text(json.dumps(asdict(reference())))
        args = Namespace(
            source_id=["synthetic"],
            asset_id="terrain__synthetic__v1",
            reference=ref,
            target_crs=None,
            terrain=True,
        )
        result = execute_job("dem", args, self.settings)
        self.assertEqual(len(result["results"]), 3)
        for artifact in result["results"]:
            self.assertEqual(verify_artifact(artifact, self.settings)["status"], "PASS")
            self.assertEqual(artifact["original_crs"], "EPSG:6677")
            self.assertEqual(artifact["processed_crs"], "EPSG:6677")
        again = execute_job("dem", args, self.settings)
        self.assertTrue(
            all(a["status"] == "already_present_reproduced" for a in again["results"])
        )
        self.assertEqual(sha256(image), self.source.sha256)
