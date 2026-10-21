"""No-Drive unit tests for GitHub PR file-scope guard."""
import unittest

from scripts.ci.check_pr_scope import check_paths, is_c1, is_c2


class PrScopeTests(unittest.TestCase):
    def test_codex_only(self):
        self.assertEqual([], check_paths(["src/kanagawa_ruins/ingest/fgd.py", "reports/phase1c1_report.md"]))
        self.assertTrue(is_c1("scripts/phase1c1_ingest.py"))

    def test_claude_only(self):
        self.assertEqual([], check_paths(["src/kanagawa_ruins/landuse_change/transition.py", "reports/phase1c2_results.json"]))
        self.assertTrue(is_c2("scripts/phase1c2_analyze.py"))

    def test_foreign_commit_is_rejected(self):
        failures = check_paths(["scripts/phase1c1_analyze.py", "src/kanagawa_ruins/landuse_change/analysis.py"])
        self.assertTrue(any("Cross-agent scope collision" in e for e in failures))

    def test_prohibit_raw_and_gis_artifacts(self):
        failures = check_paths(["data/raw/a.csv", "outputs/a.parquet", "maps/demo.tif"])
        self.assertEqual(3, len(failures))

    def test_allow_small_reports_and_gitkeep(self):
        self.assertEqual([], check_paths(["reports/figures/phase1c2/sample.png", "docs/plan.md", "data/raw/.gitkeep"]))


if __name__ == "__main__":
    unittest.main()
