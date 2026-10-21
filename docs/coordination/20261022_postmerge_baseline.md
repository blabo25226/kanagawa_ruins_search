# Phase 1-C post-merge baseline (2026-10-22 JST)

## Purpose and authority

Record the `main` baseline after the user-authorized review/merge sequence. This document is a *status and handoff*, not authorization to resume blocked Drive operations, acquire datasets, run Phase 1-D, infer abandoned properties, rank locations, or publish precise locations. Existing phase gates and data-handling rules remain in force.

- Repository: `blabo25226/kanagawa_ruins_search`.
- Baseline main commit immediately after merges: `ce7637bc0349eb1acafe6df5ed5d97b65d8d09f6`.
- Merged sequence: #16 into #9; #9, #8, #7, #21 (combined C2/ledger CI), #6, #22 (combined C1/C2/ledger CI), #18, #15 into main.
- No open PR remained at the time of the baseline inventory.
- #22 GitHub Actions run [39638011056](https://github.com/blabo25226/kanagawa_ruins_search/actions/runs/39638011056) succeeded on its PR merge/test checkout: 52 pytest tests and 11 subtests, plus scope/syntax/worker job. It did **not** cover the newly merged agy-specific suite; this follow-up PR includes `tests/test_agy_drive_trace.py` in the workflow selection. The corresponding new CI must be checked separately. A green offline CI does **not** prove real-data correctness, live Drive connectivity, or nationwide processing.

## Observational status and limits

| Stream | Verified scope | Explicitly not established |
|---|---|---|
| C1 buildings and road edges (#6) | Pilot analyses of 2014/2025 in two second-order mesh areas, Kanagawa overlap 15.57 km² / ~0.6445% of prefecture land | Full 2014/2025 prefecture comparison, completed remote derivative upload, construction/demolition/abandonment labels |
| C2 land-use (#7) | 2014/2021 descriptive transition within 1,818.4 km² / ~75.3% of prefecture land; methodological/imagery interpretation changes matter | Coverage of omitted southern/western regions; causal attribution or abandonment labels |
| C1/C2 support intersection (#15) | Only second-order mesh 533935; 5.95 km² / ~0.246% of prefecture land | Meaningful prefecture-wide B/L/R integration |
| agy/FUSE access (#18) | One 2,842-byte manifest read through the existing rclone/FUSE path with matching expected SHA-256 | Independent Google Drive connection, 403 quota recovery, remote upload, large binary transfers |

Both the observation periods (C1 2014→2025; C2 2014→2021) and the nominal “1 km” grid conventions differ. C1 uses projected 1,000-m squares (EPSG:6677); C2 uses JIS geographic standard meshes. Do **not** join their reported grid IDs directly, and do not mistake missing coverage for zero change.

## Known blockers / work to retain

1. **Issue #12, C1 remote processing:** Drive API HTTP 403 rate limits blocked full analysis. Nine pre-existing derivative pairs still need independent remote readback verification. The approved seven proposed ledger additions were **not executed (0 actual appends; ledger remained 53)**. A controlled resumption requires an explicit new operational go-ahead and healthy Drive access. Keep existing mount/cache/config/data immutable meanwhile. The 2008 datum-transform issue is separate.
2. **C2 coverage:** L03-b first-order meshes 5238/5239 are not in current input. Decide whether to seek new approved acquisition before treating any area as a comparable support.
3. **Phase 1-D design only:** `docs/phase1d_integration_design.md` proposes a non-ranked, aggregated B/L/R observation table, with unknown/coverage masks, common-grid choice, aligned time comparison, synthetic injection tests, spatial dependence controls, and preregistered thresholds. It is not an execution authorization.
4. **Documentation hygiene:** earlier runbook/README/Issue comments may still describe the pre-merge state; preserve historical evidence, but use this checkpoint and live GitHub status for current PR state.

## Recommended next stage (requires scope review before actual data work)

1. Establish this consolidated code/documentation baseline with a CI run that includes the #18 offline unit tests. Confirm check job results and test counts from logs, not merely the workflow badge.
2. Separately plan a quota-safe **read-only** Drive health/remote SHA verification procedure, with stop conditions, before attempting the remaining seven acquisition-ledger additions or national-scope conversion. Do not start it based only on a successful cached FUSE read.
3. Decide whether C2 geographic completeness or C1 full-area coverage should be prioritized; record a versioned input coverage mask and a common-grid convention before Phase 1-D implementation.
4. Keep field-site confirmation, location publication, and historical interpretations separate from automated spatial change detection and its uncertainty.

## CI acceptance criteria

- Both offline Actions jobs green on a PR based on post-merge `main`.
- Synthetic test selection includes C1, C2, ledger, and agy trace verifier (12 known agy unit tests on its original branch). Missing files or skipped suites must not be silently interpreted as success.
- Scope/syntax gate still blocks raw/binary GIS assets, unexpected cross-agent code mixing, and Python syntax errors.
- No Google Drive access, downloads, OAuth/rclone changes, or GIS binary outputs are required to validate this checkpoint.
