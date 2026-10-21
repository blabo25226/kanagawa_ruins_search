# Phase 1-C combined offline CI checkpoint (2026-10-22)

## Purpose
This small review-only PR deliberately triggers GitHub's `PR safety (offline)` Actions against **the actual combined main after PR #9, #8, and #7 were merged**. It does not touch Google Drive, provenance, existing derivatives, site coordinates, or real-data analysis.

- Baseline at creation: main with merged #16 → #9 → #8 → #7.
- Expect focused `tests/test_phase0_ledger_append.py` and `tests/test_phase1c2_synthetic.py` to be discovered, selected and truly run. **A green job with 0 tests selected is not evidence of analytic integration.**
- Review `Scope, data and syntax guard` and `C1/C2/ledger offline synthetic tests`; obtain exact test counts from job logs, not only job status.
- Live 6 tests reported by Claude Code are local only; CI uses no live Drive credentials, remote API, raw GIS or mount.
- Later Codex PR #6 remains PARTIAL and full-area C1 is not complete. PR #18 only verified a small manifest through FUSE; independent Drive path unverified. This checkpoint authorizes neither ingestion nor Phase 1-D execution.

If this PR's CI fails, do not merge or proceed with #6 until failure is explained and corrected in a reviewable PR. Final phase-wide QA and tagging belong after all selected PRs are merged.
