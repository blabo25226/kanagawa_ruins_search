"""Network-free tests of Phase 0 safety, project structure, and Google Drive mount verification."""
from __future__ import annotations
import importlib.util
import os
from pathlib import Path
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]

# Import fetch_sources
SPEC = importlib.util.spec_from_file_location("fetch_sources", ROOT / "scripts" / "fetch_sources.py")
assert SPEC is not None and SPEC.loader is not None
fetch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fetch)

# Import storage_utils
SPEC_STORAGE = importlib.util.spec_from_file_location("storage_utils", ROOT / "scripts" / "storage_utils.py")
assert SPEC_STORAGE is not None and SPEC_STORAGE.loader is not None
storage_utils = importlib.util.module_from_spec(SPEC_STORAGE)
SPEC_STORAGE.loader.exec_module(storage_utils)


class Phase0ConfigTests(unittest.TestCase):
    def test_required_entrypoints_present(self):
        for name in ("README.md", "firstinstruction.md", "source.md", "GEMINI.md", "AGENTS.md",
                     "environment.yml", ".env.example", "agent/rules/00-phase-gate.md"):
            with self.subTest(name=name):
                self.assertTrue((ROOT / name).is_file())

    def test_automatic_source_allowlist(self):
        with (ROOT / "config/sources.toml").open("rb") as f:
            sources = tomllib.load(f)["source"]
        ids = [s["id"] for s in sources]
        self.assertEqual(len(ids), len(set(ids)))
        for source in sources:
            if source["mode"] in fetch.DOWNLOADABLE_MODES:
                self.assertTrue(source["allowed_domains"])
                self.assertTrue(fetch.approved_url(source.get("url", source.get("api_url")),
                                                   source["allowed_domains"]))
                self.assertLessEqual(source["max_bytes"], 700_000_000)
                self.assertIn(source["expected_format"], ("csv", "zip", "geojson", "json", "xml", "pdf", "pbf"))
            else:
                self.assertIn(source["mode"], ("manual", "reference_only"))

    def test_rejects_unsafe_urls(self):
        hosts = ["saigai.gsi.go.jp"]
        for url in ("http://saigai.gsi.go.jp/data.zip",
                    "https://evil.test/data.zip",
                    "https://saigai.gsi.go.jp.evil.test/a",
                    "file:///tmp/file.zip",
                    "https://me:pwd@saigai.gsi.go.jp/a"):
            with self.subTest(url=url):
                self.assertFalse(fetch.approved_url(url, hosts))
        self.assertTrue(fetch.approved_url("https://saigai.gsi.go.jp/a.zip", hosts))

    def test_simple_format_check(self):
        self.assertTrue(fetch.looks_like_format(b"PK\x03\x04more", "zip"))
        self.assertTrue(fetch.looks_like_format("名称,区分\n寺,文化財".encode(), "csv"))
        self.assertTrue(fetch.looks_like_format(b'{"type": "FeatureCollection"}', "geojson"))
        self.assertTrue(fetch.looks_like_format(b'<?xml version="1.0"?><osm></osm>', "xml"))
        self.assertTrue(fetch.looks_like_format(b'%PDF-1.4 header', "pdf"))
        self.assertTrue(fetch.looks_like_format(b"\x00\x00\x00\r\n\tOSMHeader", "pbf"))
        self.assertFalse(fetch.looks_like_format(b"<html>login</html>", "csv"))
        self.assertFalse(fetch.looks_like_format(b"not a zip", "zip"))
        self.assertFalse(fetch.looks_like_format(b"not a pdf", "pdf"))
        self.assertFalse(fetch.looks_like_format(b"not a pbf", "pbf"))

    def test_gitignore_raw(self):
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("/data/raw/*", ignored)
        self.assertIn("/data/provenance.jsonl", ignored)


class StorageSecurityTests(unittest.TestCase):
    """Abnormal and boundary condition tests for rclone mount security and storage safety."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.mounts_file = Path(self.temp_dir.name) / "mock_mounts"
        # Create a mock mount table
        mock_content = (
            "/dev/sda1 / ext4 rw 0 0\n"
            "gdrive: /mock/gdrive fuse.rclone rw,user_id=1000 0 0\n"
            "/dev/sdb1 /mock/gdrive_local ext4 rw 0 0\n"
        )
        self.mounts_file.write_text(mock_content, encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_is_rclone_mounted_valid_hierarchy(self):
        # Descendant of rclone mount point
        valid_path = Path("/mock/gdrive/kanagawa/data")
        mounted, info = storage_utils.is_rclone_mounted(valid_path, mounts_path=self.mounts_file)
        self.assertTrue(mounted)
        self.assertIn("fuse.rclone", info)

        # Exact mount point match
        mounted, _ = storage_utils.is_rclone_mounted(Path("/mock/gdrive"), mounts_path=self.mounts_file)
        self.assertTrue(mounted)

    def test_is_rclone_mounted_rejects_string_prefix_spoof(self):
        """Ensure /mock/gdrive_local or /mock/gdrive_fake does NOT match /mock/gdrive."""
        fake_paths = [
            Path("/mock/gdrive_local/data"),
            Path("/mock/gdrive_fake"),
            Path("/mock/gdrive2/databank"),
            Path("/mock/gdrive.bak"),
        ]
        for p in fake_paths:
            with self.subTest(path=p):
                mounted, info = storage_utils.is_rclone_mounted(p, mounts_path=self.mounts_file)
                # Must be False, or recognized as non-rclone ext4
                self.assertFalse(mounted, f"Path {p} was incorrectly accepted as rclone mount: {info}")

    def test_is_rclone_mounted_rejects_unmounted_path(self):
        unmounted = Path("/some/random/unmounted/path")
        mounted, info = storage_utils.is_rclone_mounted(unmounted, mounts_path=self.mounts_file)
        self.assertFalse(mounted)
        self.assertIn("non-rclone filesystem", info)

    def test_get_verified_data_root_fails_when_unmounted(self):
        """Ensure get_verified_data_root raises StorageError when path is not an rclone mount."""
        local_dir = Path(self.temp_dir.name) / "local_unmounted"
        local_dir.mkdir()

        # Temporarily mock RUINS_DATA_ROOT
        orig_env = os.environ.get("RUINS_DATA_ROOT")
        try:
            os.environ["RUINS_DATA_ROOT"] = str(local_dir)
            with self.assertRaises(storage_utils.StorageError) as ctx:
                storage_utils.get_verified_data_root(mounts_path=self.mounts_file)
            self.assertIn("mount verification failed", str(ctx.exception))
        finally:
            if orig_env is not None:
                os.environ["RUINS_DATA_ROOT"] = orig_env
            else:
                os.environ.pop("RUINS_DATA_ROOT", None)

    def test_fetch_sources_stops_when_not_mounted(self):
        """Ensure fetch_sources.get_data_root raises DownloadError on unmounted storage."""
        local_dir = Path(self.temp_dir.name) / "local_test"
        local_dir.mkdir()

        orig_env = os.environ.get("RUINS_DATA_ROOT")
        try:
            os.environ["RUINS_DATA_ROOT"] = str(local_dir)
            with self.assertRaises(fetch.DownloadError) as ctx:
                fetch.get_data_root(mounts_path=self.mounts_file)
            self.assertIn("Storage mount security verification failed", str(ctx.exception))
        finally:
            if orig_env is not None:
                os.environ["RUINS_DATA_ROOT"] = orig_env
            else:
                os.environ.pop("RUINS_DATA_ROOT", None)

    def test_safe_probe_write_exclusive(self):
        probe_target = Path(self.temp_dir.name) / "probe_dir"
        probe_target.mkdir()
        # Should succeed without leaving temporary files behind
        storage_utils.safe_probe_write(probe_target)
        self.assertEqual(len(list(probe_target.iterdir())), 0)


class DownloadSecurityTests(unittest.TestCase):
    """Safety and integrity tests for download and archive handling."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_validate_file_integrity(self):
        # 1. Valid JSON
        valid_json = self.dir_path / "test.json"
        valid_json.write_text('{"name": "test"}', encoding="utf-8")
        ok, _ = fetch.validate_file_integrity(valid_json, "json")
        self.assertTrue(ok)

        # Corrupted JSON
        corrupted_json = self.dir_path / "bad.json"
        corrupted_json.write_text('{broken json', encoding="utf-8")
        ok, msg = fetch.validate_file_integrity(corrupted_json, "json")
        self.assertFalse(ok)
        self.assertIn("Integrity check failed", msg)

        # 2. Valid PDF
        valid_pdf = self.dir_path / "doc.pdf"
        valid_pdf.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\nstartxref\n10\n%%EOF\n")
        ok, _ = fetch.validate_file_integrity(valid_pdf, "pdf")
        self.assertTrue(ok)

        # Invalid PDF (missing EOF)
        bad_pdf = self.dir_path / "bad.pdf"
        bad_pdf.write_bytes(b"%PDF-1.4 truncated without eof")
        ok, msg = fetch.validate_file_integrity(bad_pdf, "pdf")
        self.assertFalse(ok)
        self.assertIn("%%EOF", msg)

        # 3. File too small
        empty_file = self.dir_path / "empty.bin"
        empty_file.write_bytes(b"")
        ok, msg = fetch.validate_file_integrity(empty_file, "zip")
        self.assertFalse(ok)
        self.assertIn("too small", msg)

        # 4. Valid and invalid PBF
        valid_pbf = self.dir_path / "test.pbf"
        valid_pbf.write_bytes(b"\x00\x00\x00\r\n\tOSMHeader\x08\x00" + b"\x00" * 50)
        ok, _ = fetch.validate_file_integrity(valid_pbf, "pbf")
        self.assertTrue(ok)

        bad_pbf = self.dir_path / "bad.pbf"
        bad_pbf.write_bytes(b"garbage without header" + b"\x00" * 50)
        ok, msg = fetch.validate_file_integrity(bad_pbf, "pbf")
        self.assertFalse(ok)
        self.assertIn("OSMHeader", msg)

    def test_safe_extract_zip_zip_slip_rejection(self):
        import zipfile
        evil_zip_path = self.dir_path / "evil.zip"
        with zipfile.ZipFile(evil_zip_path, 'w') as zf:
            zf.writestr('../../escaped.txt', 'evil content')

        dest_dir = self.dir_path / "extract_dest"
        with self.assertRaises(fetch.DownloadError) as ctx:
            fetch.safe_extract_zip(evil_zip_path, dest_dir)
        self.assertIn("Zip Slip detected", str(ctx.exception))

    def test_safe_extract_zip_zip_bomb_rejection(self):
        import zipfile
        bomb_zip_path = self.dir_path / "bomb.zip"
        with zipfile.ZipFile(bomb_zip_path, 'w') as zf:
            zf.writestr('large.bin', b'0' * 2000)

        dest_dir = self.dir_path / "bomb_dest"
        with self.assertRaises(fetch.DownloadError) as ctx:
            # Set max limit lower than 2000
            fetch.safe_extract_zip(bomb_zip_path, dest_dir, max_bytes=1000)
        self.assertIn("Zip Bomb protection", str(ctx.exception))

    def test_safe_extract_zip_symlink_rejection(self):
        import zipfile
        symlink_zip_path = self.dir_path / "symlink.zip"
        with zipfile.ZipFile(symlink_zip_path, 'w') as zf:
            zi = zipfile.ZipInfo("symlink_entry")
            zi.external_attr = 0o120777 << 16  # S_IFLNK
            zf.writestr(zi, "/etc/passwd")

        dest_dir = self.dir_path / "symlink_dest"
        with self.assertRaises(fetch.DownloadError) as ctx:
            fetch.safe_extract_zip(symlink_zip_path, dest_dir)
        self.assertIn("Symlink rejected", str(ctx.exception))

    def test_osm_pbf_structure_and_header_reading(self):
        """Test low-overhead OSM PBF header validation and binary block parsing."""
        import struct
        header_type = b"OSMHeader"
        blob_header = b"\n\t" + header_type + b"\x18\x20"
        header_len = len(blob_header)
        blob_content = b"\x78\x9c" + b"\x00" * 30
        pbf_data = struct.pack(">I", header_len) + blob_header + blob_content

        pbf_path = self.dir_path / "synthetic.osm.pbf"
        pbf_path.write_bytes(pbf_data)

        # 1. Format integrity validation
        ok, msg = fetch.validate_file_integrity(pbf_path, "pbf")
        self.assertTrue(ok, msg)

        # 2. Block header verification
        with pbf_path.open("rb") as f:
            h_len = struct.unpack(">I", f.read(4))[0]
            self.assertEqual(h_len, header_len)
            b_hdr = f.read(h_len)
            self.assertIn(b"OSMHeader", b_hdr)

    def test_databank_osm_pbf_live_header(self):
        """Verify actual databank PBF header structure without full-file read latency."""
        import struct
        try:
            root = storage_utils.get_verified_data_root()
        except Exception:
            self.skipTest("Data root is not mounted or verified")

        pbf_path = root / "raw/osm/kanto-latest.osm.pbf"
        if not pbf_path.exists():
            self.skipTest("kanto-latest.osm.pbf not yet present in databank")

        with pbf_path.open("rb") as f:
            h_len = struct.unpack(">I", f.read(4))[0]
            self.assertTrue(10 <= h_len <= 1024, f"Unexpected header len {h_len}")
            b_hdr = f.read(h_len)
            self.assertIn(b"OSMHeader", b_hdr)


if __name__ == "__main__":
    unittest.main()
