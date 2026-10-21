"""No-Drive unit tests for GitHub PR file-scope guard."""
import unittest
from unittest.mock import patch
import subprocess

from scripts.ci.check_pr_scope import check_paths, is_c1, is_c2, changed_paths


class PrScopeTests(unittest.TestCase):
    def test_stacked_base_ref_with_slashes(self):
        with patch('scripts.ci.check_pr_scope.subprocess.run', side_effect=[
            subprocess.CompletedProcess([], 0),
            subprocess.CompletedProcess([], 0, stdout=b'AGENTS.md\0docs/runbook.md\0'),
        ]) as run:
            self.assertEqual(changed_paths('origin/chatgpt/phase1c-coordination-20261021'),
                             ['AGENTS.md', 'docs/runbook.md'])
            self.assertEqual(run.call_args_list[0].args[0],
                             ['git', 'check-ref-format', 'origin/chatgpt/phase1c-coordination-20261021'])

    def test_revision_expression_rejected_before_diff(self):
        with patch('scripts.ci.check_pr_scope.subprocess.run',
                   return_value=subprocess.CompletedProcess([], 1)) as run:
            with self.assertRaises(ValueError):
                changed_paths('origin/main...HEAD')
            self.assertEqual(run.call_count, 1)

    def test_non_remote_base_rejected(self):
        with patch('scripts.ci.check_pr_scope.subprocess.run') as run:
            with self.assertRaises(ValueError):
                changed_paths('--upload-pack=bad')
            run.assert_not_called()

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
