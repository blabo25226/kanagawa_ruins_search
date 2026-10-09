"""Network-free tests of Phase 0 safety and project structure."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("fetch_sources", ROOT / "scripts" / "fetch_sources.py")
assert SPEC is not None and SPEC.loader is not None
fetch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fetch)


class Phase0ConfigTests(unittest.TestCase):
    def test_required_entrypoints_present(self):
        for name in ("README.md", "firstinstruction.md", "source.md", "GEMINI.md", "AGENTS.md",
                     "environment.yml", "agent/rules/00-phase-gate.md"):
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
                self.assertLessEqual(source["max_bytes"], 20_000_000)
                self.assertIn(source["expected_format"], ("csv", "zip"))
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
        self.assertFalse(fetch.looks_like_format(b"<html>login</html>", "csv"))
        self.assertFalse(fetch.looks_like_format(b"not a zip", "zip"))

    def test_gitignore_raw(self):
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("/data/raw/*", ignored)
        self.assertIn("/data/provenance.jsonl", ignored)


if __name__ == "__main__":
    unittest.main()
