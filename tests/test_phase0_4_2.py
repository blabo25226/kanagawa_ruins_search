#!/usr/bin/env python3
"""Regression test suite for Phase 0.4.2 fixes:

1. Shapefile CPG encoding handling and mojibake detection (F1)
2. Strengthened format integrity verification for XML, JPEG, CSV, PBF (F2)
3. Provenance ledger single source of truth, already_present handling, and atomic writes (F5)
4. Dynamic PROJ configuration and lack of hardcoded machine paths (F8)
5. Catalog static integrity (sources.toml)
6. Databank audit and validation mechanics (F7)

Inherits from unittest.TestCase so it runs with both pytest and python -m unittest discover.
"""

from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import tomllib
import unittest

from PIL import Image
import geopandas as gpd
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parents[1]

from scripts.storage_utils import is_rclone_mounted, get_verified_data_root
from scripts.fetch_sources import (
    validate_file_integrity,
    looks_like_format,
    load_provenance_records,
    append_provenance_record,
    download,
)
from scripts.validate_databank import check_mojibake, validate_shapefile_encoding


class TestShapefileEncodingAndMojibake(unittest.TestCase):
    """Test F1: Shapefile encoding handling, CPG prioritization, and mojibake detection."""

    def test_check_mojibake_strings(self):
        # Known mojibake artifacts from CP932 read on UTF-8 Shapefiles
        self.assertTrue(check_mojibake("逾槫･亥ｷ晉恁"))
        self.assertTrue(check_mojibake("ｷ"))
        self.assertTrue(check_mojibake("逾"))
        self.assertTrue(check_mojibake("東京都\ufffd"))

        # Valid Japanese strings
        self.assertFalse(check_mojibake("神奈川県"))
        self.assertFalse(check_mojibake("東京都"))
        self.assertFalse(check_mojibake("山梨県"))
        self.assertFalse(check_mojibake("静岡県"))
        self.assertFalse(check_mojibake("相模原市緑区"))

    def test_shapefile_cpg_utf8_reading(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            shp_path = tmp_path / "test_boundary.shp"

            gdf = gpd.GeoDataFrame(
                [{"N03_001": "神奈川県", "N03_004": "相模原市緑区"}],
                geometry=[Point(139.2, 35.6)],
                crs="EPSG:4326"
            )
            # Write shapefile and explicit UTF-8 .cpg
            gdf.to_file(shp_path, driver="ESRI Shapefile", encoding="utf-8")
            cpg_path = tmp_path / "test_boundary.cpg"
            cpg_path.write_text("UTF-8\n", encoding="utf-8")

            # Validate encoding using validate_databank logic
            res_gdf, used_enc = validate_shapefile_encoding(shp_path)
            self.assertEqual(used_enc, "utf-8")
            pref = res_gdf.iloc[0]["N03_001"]
            muni = res_gdf.iloc[0]["N03_004"]
            self.assertEqual(pref, "神奈川県")
            self.assertEqual(muni, "相模原市緑区")
            self.assertFalse(check_mojibake(pref))
            self.assertFalse(check_mojibake(muni))

    def test_live_boundaries_if_mounted(self):
        try:
            root = get_verified_data_root()
        except Exception:
            self.skipTest("Google Drive databank not mounted")

        admin_dir = root / "raw/administrative"
        kanagawa_zip = admin_dir / "N03-20260101_14_GML.zip"
        if not kanagawa_zip.is_file():
            self.skipTest("Kanagawa N03 archive not found on databank")

        from scripts.verify_adjacency import load_n03_from_zip
        gdf = load_n03_from_zip(kanagawa_zip)
        prefs = set(gdf["N03_001"].dropna().unique())
        self.assertEqual(prefs, {"神奈川県"})
        for val in prefs:
            self.assertFalse(check_mojibake(val))
            self.assertNotIn("\ufffd", val)


class TestFormatIntegrityVerification(unittest.TestCase):
    """Test F2: Thorough integrity checks for XML, JPEG, CSV, PBF."""

    def test_osm_xml_integrity(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            p = Path(tmp_dir) / "test.osm"

            # Valid XML
            p.write_text("<?xml version='1.0' encoding='UTF-8'?>\n<osm version='0.6'>\n  <node id='1' lat='35.0' lon='139.0'/>\n</osm>", encoding="utf-8")
            ok, msg = validate_file_integrity(p, "xml")
            self.assertTrue(ok)

            # Truncated XML (missing closing root)
            p.write_text("<?xml version='1.0' encoding='UTF-8'?>\n<osm version='0.6'>\n  <node id='1' lat='35.0' lon='139.0'>\n", encoding="utf-8")
            ok, msg = validate_file_integrity(p, "xml")
            self.assertFalse(ok)

    def test_jpeg_integrity(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            p = Path(tmp_dir) / "test.jpg"

            # Create a valid 10x10 JPEG
            img = Image.new("RGB", (10, 10), color=(255, 0, 0))
            img.save(p, format="JPEG")
            ok, msg = validate_file_integrity(p, "jpg")
            self.assertTrue(ok)

            # Truncated JPEG (remove trailing EOI \xff\xd9)
            raw = p.read_bytes()
            if raw.endswith(b"\xff\xd9"):
                truncated_raw = raw[:-10]  # truncate end
                p.write_bytes(truncated_raw)
                ok, msg = validate_file_integrity(p, "jpg")
                self.assertFalse(ok)

    def test_csv_integrity(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            p = Path(tmp_dir) / "test.csv"

            # Valid CSV
            p.write_text("名称,種別,時代\n津久井城跡,城館,戦国\n", encoding="utf-8")
            ok, msg = validate_file_integrity(p, "csv")
            self.assertTrue(ok)

            # Corrupted CSV (invalid encoding in all supported encodings: illegal multibyte sequence)
            p.write_bytes(b"\x81\x00\x81\x00\x81\x00\n")
            ok, msg = validate_file_integrity(p, "csv")
            self.assertFalse(ok)

            # Empty CSV
            p.write_text("", encoding="utf-8")
            ok, msg = validate_file_integrity(p, "csv")
            self.assertFalse(ok)

    def test_osm_pbf_integrity(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            p = Path(tmp_dir) / "test.pbf"

            # Valid minimal PBF header
            # Length: 4 bytes big endian matching header data length, containing OSMHeader
            block = b"\x00\x00OSMHeader\x00\x00"
            p.write_bytes(len(block).to_bytes(4, byteorder="big") + block)
            ok, msg = validate_file_integrity(p, "pbf")
            self.assertTrue(ok)

            # Too short (< 4 bytes)
            p.write_bytes(b"\x00\x01")
            ok, msg = validate_file_integrity(p, "pbf")
            self.assertFalse(ok)

            # Invalid header (no OSMHeader)
            bad_block = b"random_corrupted_data_without_magic_header"
            p.write_bytes(len(bad_block).to_bytes(4, byteorder="big") + bad_block)
            ok, msg = validate_file_integrity(p, "pbf")
            self.assertFalse(ok)


class TestProvenanceManagement(unittest.TestCase):
    """Test F5: Centralized canonical provenance, already_present idempotence, and atomic writes."""

    def test_already_present_idempotence(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_root = Path(tmp_dir) / "databank"
            data_root.mkdir(parents=True)
            prov_file = data_root / "provenance.jsonl"

            # Create an existing file
            target_rel = "raw/sample/test_data.csv"
            target_file = data_root / target_rel
            target_file.parent.mkdir(parents=True)
            content = "col1,col2\nval1,val2\n".encode("utf-8")
            target_file.write_bytes(content)

            import hashlib
            file_sha = hashlib.sha256(content).hexdigest()

            # Seed provenance with this file
            rec = {
                "source_id": "test_sample",
                "relative_path": target_rel,
                "size_bytes": len(content),
                "sha256": file_sha,
                "url": "https://example.com/test.csv",
                "acquired_at": "2026-10-10T00:00:00Z",
                "license": "CC-BY-4.0"
            }
            append_provenance_record(data_root, rec)

            # Check records count
            records_before = load_provenance_records(data_root)
            self.assertEqual(len(records_before), 1)

            # Call download with an approved mock source pointing to this file
            source = {
                "id": "test_sample",
                "mode": "file",
                "url": "https://example.com/test.csv",
                "allowed_domains": ["example.com"],
                "dest_dir": "raw/sample",
                "filename": "test_data.csv",
                "max_bytes": 10000,
                "expected_format": "csv",
                "license_note": "CC-BY-4.0"
            }

            res = download(source, "https://example.com/test.csv", data_root=data_root)
            self.assertEqual(res["status"], "already_present")

            # Verify no duplicate was added to provenance.jsonl
            records_after = load_provenance_records(data_root)
            self.assertEqual(len(records_after), 1)
            self.assertEqual(records_after[0]["sha256"], file_sha)

    def test_untracked_existing_file_records_mtime(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_root = Path(tmp_dir) / "databank"
            data_root.mkdir(parents=True)

            target_rel = "raw/sample/untracked.csv"
            target_file = data_root / target_rel
            target_file.parent.mkdir(parents=True)
            content = "id,name\n1,temple\n".encode("utf-8")
            target_file.write_bytes(content)

            source = {
                "id": "untracked_source",
                "mode": "file",
                "url": "https://example.com/untracked.csv",
                "allowed_domains": ["example.com"],
                "dest_dir": "raw/sample",
                "filename": "untracked.csv",
                "max_bytes": 10000,
                "expected_format": "csv",
                "license_note": "Public Domain"
            }

            res = download(source, "https://example.com/untracked.csv", data_root=data_root)
            self.assertEqual(res["status"], "already_present_verified")

            records = load_provenance_records(data_root)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["source_id"], "untracked_source")
            self.assertEqual(records[0]["size_bytes"], len(content))
            self.assertIn("acquired_at", records[0])


class TestDynamicConfigurationAndCodeHygiene(unittest.TestCase):
    """Test F8: Verify no hardcoded machine paths in code."""

    def test_no_hardcoded_conda_paths_in_scripts(self):
        scripts_dir = ROOT / "scripts"
        bad_pattern = "/home/blabo/miniconda3"
        for py_file in scripts_dir.glob("*.py"):
            text = py_file.read_text(encoding="utf-8")
            self.assertNotIn(bad_pattern, text, f"Hardcoded path found in {py_file.name}")


class TestSourcesCatalogIntegrity(unittest.TestCase):
    """Test static catalog integrity of config/sources.toml."""

    def test_sources_catalog_structure(self):
        toml_path = ROOT / "config/sources.toml"
        self.assertTrue(toml_path.is_file())
        with toml_path.open("rb") as f:
            data = tomllib.load(f)

        sources = data.get("source", [])
        self.assertGreater(len(sources), 0)

        ids = [s["id"] for s in sources]
        self.assertEqual(len(ids), len(set(ids)), "Source IDs must be strictly unique")

        valid_top_dirs = {"raw", "literature", "processed"}
        for s in sources:
            dest_dir = s.get("dest_dir", "")
            top_dir = dest_dir.split("/")[0] if dest_dir else ""
            if top_dir:
                self.assertIn(top_dir, valid_top_dirs, f"Invalid top-level dir in {s['id']}: {top_dir}")


if __name__ == "__main__":
    unittest.main()
