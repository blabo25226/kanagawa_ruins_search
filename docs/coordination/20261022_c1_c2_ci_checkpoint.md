# Combined Phase 1-C1/C2 and ledger offline integration QA

After merging PR #6 as **PARTIAL**, verify the current main with the actual Phase 1-C1 tests plus prior Phase 1-C2 and append-only ledger tests in GitHub Actions.

- Selected tests expected: `tests/test_phase1c1.py`, `tests/test_phase1c2_synthetic.py`, `tests/test_phase0_ledger_append.py`. Logs, not only workflow green state, must show actual collection/count.
- No remote Drive reads, uploads, source ZIP modifications or ledger appends; no CI credentials.
- Scientific coverage remains C1 ~0.644% vs C2 ~75.3%, shared 5.95km² only. C1 full-area state `overall_completion=false`; 2008 datum invalid as comparison, and 2014→2025 vs 2014→2021 cannot be treated as matching endpoints.
- This checkpoint is an offline code integration test, **not a validation of all-area GIS quality**.
- If checks fail, stop the remaining integrations pending review.
