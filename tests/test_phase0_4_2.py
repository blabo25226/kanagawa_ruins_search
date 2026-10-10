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
import errno
import fcntl
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from PIL import Image
import geopandas as gpd
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parents[1]

from scripts.storage_utils import is_rclone_mounted, get_verified_data_root
from scripts.fetch_sources import (
    validate_file_integrity,
    validate_pbf_file,
    looks_like_format,
    load_provenance_records,
    append_provenance_record,
    download,
    ProvenanceLock,
    ProvenanceCorruptedError,
)
from scripts.validate_databank import check_mojibake, validate_shapefile_encoding
from scripts.audit_databank import (
    audit_databank,
    generate_markdown_integrity_audit,
    generate_markdown_inventory,
)


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

    def test_osm_pbf_full_scan_valid_and_truncated(self):
        """Verify full scan detects mid-stream truncation while header-only misses it."""
        def _make_block(block_type: str, data_len: int) -> bytes:
            type_bytes = block_type.encode("utf-8")
            header_bytes = bytearray()
            # field 1 (string type): wire type 2 -> 0x0a
            header_bytes.extend([0x0a, len(type_bytes)])
            header_bytes.extend(type_bytes)
            # field 3 (int32 datasize): wire type 0 -> 0x18
            header_bytes.append(0x18)
            val = data_len
            while val >= 0x80:
                header_bytes.append((val & 0x7F) | 0x80)
                val >>= 7
            header_bytes.append(val)
            hlen = len(header_bytes)
            blob_data = b"D" * data_len
            return hlen.to_bytes(4, "big") + bytes(header_bytes) + blob_data

        with tempfile.TemporaryDirectory() as tmp_dir:
            p = Path(tmp_dir) / "stream.pbf"
            b0 = _make_block("OSMHeader", 20)
            b1 = _make_block("OSMData", 50)
            full_data = b0 + b1
            p.write_bytes(full_data)

            # Valid stream: both header-only and full scan succeed
            ok_hdr, msg_hdr = validate_pbf_file(p, full_scan=False)
            self.assertTrue(ok_hdr)
            self.assertIn("ヘッダー確認のみ", msg_hdr)

            ok_full, msg_full = validate_pbf_file(p, full_scan=True)
            self.assertTrue(ok_full)
            self.assertIn("全ブロック構造検証完了", msg_full)
            self.assertIn("2ブロック", msg_full)

            # Truncated file (cutting off 10 bytes from block 1 blob)
            p.write_bytes(full_data[:-10])

            # Header-only check still passes because block 0 is intact
            ok_trunc_hdr, msg_trunc_hdr = validate_pbf_file(p, full_scan=False)
            self.assertTrue(ok_trunc_hdr)

            # Full scan strictly catches the truncation in block 1
            ok_trunc_full, msg_trunc_full = validate_pbf_file(p, full_scan=True)
            self.assertFalse(ok_trunc_full)
            self.assertIn("truncated", msg_trunc_full)


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

    def test_provenance_lock_mutual_exclusion(self):
        """Verify ProvenanceLock provides mutual exclusion against concurrent contention."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_root = Path(tmp_dir) / "databank"
            data_root.mkdir(parents=True)

            with ProvenanceLock(data_root, timeout=1.0):
                # Inside locked section: another attempt to acquire lock must fail on timeout
                with self.assertRaises(TimeoutError):
                    with ProvenanceLock(data_root, timeout=0.1):
                        pass

            # Outside locked section: new acquisition succeeds immediately
            with ProvenanceLock(data_root, timeout=1.0):
                lock_file = data_root / ".provenance.lock"
                self.assertTrue(lock_file.is_file())
                lock_content = lock_file.read_text()
                self.assertIn("pid=", lock_content)

    def test_load_provenance_records_strict_corrupted_line_protection(self):
        """Verify strict load raises ProvenanceCorruptedError on invalid JSON lines without dropping history."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_root = Path(tmp_dir) / "databank"
            data_root.mkdir(parents=True)
            prov_file = data_root / "provenance.jsonl"

            # Create a ledger with 1 valid line and 1 malformed JSON line
            valid_rec = {"source_id": "valid1", "relative_path": "raw/val.csv", "sha256": "abc"}
            prov_file.write_text(json.dumps(valid_rec) + "\n{broken unparseable json line\n", encoding="utf-8")

            # Strict mode load must raise ProvenanceCorruptedError
            with self.assertRaises(ProvenanceCorruptedError) as ctx:
                load_provenance_records(data_root, strict=True)
            self.assertIn("Line 2", str(ctx.exception))

            # Non-strict load returns available records without crashing
            records = load_provenance_records(data_root, strict=False)
            self.assertEqual(len(records), 1)

            # append_provenance_record must refuse rewrite to protect corrupted history
            new_rec = {"source_id": "new", "relative_path": "raw/new.csv", "sha256": "def"}
            with self.assertRaises(ProvenanceCorruptedError):
                append_provenance_record(data_root, new_rec)

            # Confirm original ledger file was not rewritten and corrupted line is intact
            raw_lines = prov_file.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(raw_lines), 2)
            self.assertEqual(raw_lines[1], "{broken unparseable json line")

    def test_provenance_lock_force_local_lock(self):
        """Verify ProvenanceLock functions cleanly on local filesystem when force_local_lock is True."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_root = Path(tmp_dir) / "databank"
            data_root.mkdir(parents=True)

            with ProvenanceLock(data_root, timeout=1.0, force_local_lock=True) as lock:
                self.assertTrue(lock.use_local_lock)
                self.assertTrue(lock.lock_file.is_file())
                # Contention with another local lock attempt
                with self.assertRaises(TimeoutError):
                    with ProvenanceLock(data_root, timeout=0.1, force_local_lock=True):
                        pass

            # Re-acquisition after release
            with ProvenanceLock(data_root, timeout=1.0, force_local_lock=True) as lock2:
                self.assertTrue(lock2.lock_file.is_file())

    def test_provenance_lock_fuse_unsupported_fallback(self):
        """Verify ProvenanceLock seamlessly falls back to local lock if FUSE raises ENOSYS or EOPNOTSUPP."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_root = Path(tmp_dir) / "databank"
            data_root.mkdir(parents=True)

            orig_flock = fcntl.flock
            first_call = True

            def mock_flock_enosys(fd, op):
                nonlocal first_call
                if first_call:
                    first_call = False
                    raise OSError(errno.ENOSYS, "Function not implemented on FUSE")
                return orig_flock(fd, op)

            with patch("fcntl.flock", side_effect=mock_flock_enosys):
                with ProvenanceLock(data_root, timeout=1.0) as lock:
                    self.assertTrue(lock.use_local_lock)
                    self.assertEqual(lock.lock_file, lock.local_lock_file)
                    self.assertTrue(lock.lock_file.is_file())

    def test_provenance_lock_live_gdrive_fuse_sandbox(self):
        """Verify ProvenanceLock on actual live rclone FUSE mount in an isolated sandbox directory."""
        try:
            data_root = get_verified_data_root()
        except Exception:
            self.skipTest("Google Drive databank not mounted")

        sandbox_dir = data_root / ".test_provenance_lock_sandbox"
        sandbox_dir.mkdir(parents=True, exist_ok=True)
        try:
            # 1. Lock acquisition on live FUSE
            with ProvenanceLock(sandbox_dir, timeout=5.0) as pl:
                self.assertTrue(pl.lock_file.is_file())

                # 2. Contention wait & timeout in separate subprocess
                sub_code_block = f"""
import sys
from pathlib import Path
from scripts.fetch_sources import ProvenanceLock
try:
    with ProvenanceLock(Path("{sandbox_dir}"), timeout=0.3):
        print("FAIL: Acquired lock while parent held it")
        sys.exit(1)
except TimeoutError:
    print("PASS: Contention timed out as expected")
    sys.exit(0)
"""
                res = subprocess.run([sys.executable, "-c", sub_code_block], capture_output=True, text=True)
                self.assertEqual(res.returncode, 0, f"Subprocess contention failed: {res.stdout} {res.stderr}")

            # 3. Re-acquisition after release
            sub_code_reacquire = f"""
import sys
from pathlib import Path
from scripts.fetch_sources import ProvenanceLock
try:
    with ProvenanceLock(Path("{sandbox_dir}"), timeout=2.0):
        print("PASS: Re-acquired lock cleanly")
        sys.exit(0)
except TimeoutError:
    print("FAIL: Could not re-acquire released lock")
    sys.exit(1)
"""
            res_reacquire = subprocess.run([sys.executable, "-c", sub_code_reacquire], capture_output=True, text=True)
            self.assertEqual(res_reacquire.returncode, 0, f"Subprocess re-acquisition failed: {res_reacquire.stdout} {res_reacquire.stderr}")

        finally:
            shutil.rmtree(sandbox_dir, ignore_errors=True)


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


class TestTruthfulHashReportingAndAudit(unittest.TestCase):
    """Test truthful reporting of hash verification states: FAST vs PARTIAL vs FULL."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        # Create 1 CSV file and 1 dummy PBF
        self.csv_path = self.root / "raw/cultural_properties/bunkazai.csv"
        self.csv_path.parent.mkdir(parents=True)
        csv_data = "名称,種別\n石仏,石造物\n".encode("utf-8")
        self.csv_path.write_bytes(csv_data)
        import hashlib
        self.csv_sha = hashlib.sha256(csv_data).hexdigest()

        self.pbf_path = self.root / "raw/osm/chubu-latest.osm.pbf"
        self.pbf_path.parent.mkdir(parents=True)

        def _make_block(block_type: str, data_len: int) -> bytes:
            type_bytes = block_type.encode("utf-8")
            header_bytes = bytearray()
            header_bytes.extend([0x0a, len(type_bytes)])
            header_bytes.extend(type_bytes)
            header_bytes.append(0x18)
            val = data_len
            while val >= 0x80:
                header_bytes.append((val & 0x7F) | 0x80)
                val >>= 7
            header_bytes.append(val)
            hlen = len(header_bytes)
            blob_data = b"D" * data_len
            return hlen.to_bytes(4, "big") + bytes(header_bytes) + blob_data

        pbf_data = _make_block("OSMHeader", 20)
        self.pbf_path.write_bytes(pbf_data)
        self.pbf_sha = hashlib.sha256(pbf_data).hexdigest()

        # Seed provenance.jsonl
        self.prov_path = self.root / "provenance.jsonl"
        recs = [
            {
                "source_id": "bunkazai",
                "relative_path": "raw/cultural_properties/bunkazai.csv",
                "size_bytes": len(csv_data),
                "sha256": self.csv_sha,
                "license": "CC-BY-4.0"
            },
            {
                "source_id": "osm_pbf",
                "relative_path": "raw/osm/chubu-latest.osm.pbf",
                "size_bytes": len(pbf_data),
                "sha256": self.pbf_sha,
                "license": "ODbL"
            }
        ]
        self.prov_path.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_audit_verdict_fast_pass_and_no_hash_claims(self):
        """In Fast mode, audit report must NEVER claim that hashes were recalculated."""
        summary = audit_databank(self.root, mode="fast")
        self.assertEqual(summary["audit_verdict"], "FAST_PASS")
        self.assertEqual(summary["hashes_recalculated_count"], 0)
        self.assertEqual(summary["hashes_unverified_count"], 2)

        # Check records
        for r in summary["records"]:
            self.assertIsNone(r["actual_sha256"])
            self.assertEqual(r["hash_verification_state"], "UNCHECKED_FAST")

        md_integrity = generate_markdown_integrity_audit(summary)
        self.assertIn("FAST PASS", md_integrity)
        self.assertIn("未実施 (0件)", md_integrity)
        self.assertNotIn("FULL PASS", md_integrity)
        self.assertNotIn("全件完了・完全一致", md_integrity)

        md_inv = generate_markdown_inventory(summary)
        self.assertIn("サイズ確認済 (ハッシュ未再計算)", md_inv)

    def test_audit_verdict_partial_pass_when_pbf_omitted(self):
        """In Full mode with PBF omitted, audit report must report PARTIAL PASS."""
        summary = audit_databank(self.root, mode="full", skip_large_pbf=True, pbf_size_threshold=10)
        self.assertEqual(summary["audit_verdict"], "PARTIAL_PASS")
        self.assertEqual(summary["hashes_omitted_count"], 1)
        self.assertEqual(summary["hashes_recalculated_count"], 1)

        md_integrity = generate_markdown_integrity_audit(summary)
        self.assertIn("PARTIAL PASS", md_integrity)
        self.assertIn("部分検証完了", md_integrity)
        self.assertNotIn("FULL PASS", md_integrity)

    def test_audit_verdict_full_pass_only_when_all_recalculated(self):
        """In Full mode with check-all-hashes, audit report reports FULL PASS."""
        summary = audit_databank(self.root, mode="full", skip_large_pbf=False)
        self.assertEqual(summary["audit_verdict"], "FULL_PASS")
        self.assertEqual(summary["hashes_omitted_count"], 0)
        self.assertEqual(summary["hashes_recalculated_count"], 2)
        self.assertEqual(summary["hashes_matched_count"], 2)

        md_integrity = generate_markdown_integrity_audit(summary)
        self.assertIn("FULL PASS", md_integrity)
        self.assertIn("完全整合", md_integrity)
        self.assertIn("全件完了・完全一致", md_integrity)


if __name__ == "__main__":
    unittest.main()
