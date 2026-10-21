# Codex handoff — PR #6 / Phase 1-C1

Reference: [PR #6](https://github.com/blabo25226/kanagawa_ruins_search/pull/6), [coordination plan](20261021_phase1c_plan.md).
Owner: Codex. Keep PR **Draft** until full coverage and remote integrity can be demonstrated. Do not move unrelated Claude Phase 1-C2 edits into this branch.

## Present blockers

- Google Drive API returns `403 RATE_LIMIT_EXCEEDED` even for one slow, nonrecursive read probe. This is a **shared project API quota**, not demonstrated disk exhaustion. **Stop requests while failure persists**; do not automatically poll/retry in a loop.
- `reports/phase1c1_review_continuation.json` lists nine 2008-derived vector/manifest pairs. Mount readback was seen, but remote upload completion **has not been verified**.
- Seven new acquisition-ledger entries have specific prior user approval, but actual appends are **zero** because remote preflight failed. Preserve approval and its plan hash; do not claim entry registration.
- 2014/2025 full-area building/road analysis remains undone. Small-area pilot covers 523867 and 533935 intersections (~0.644% of prefecture). Do not generalize its statistics.
- JGD2000-to-target for 2008 in Kanagawa lacks verified applicable correction; keep 2008 comparison stopped. A numeric roundtrip is not proof of datum correctness.

## Required next steps once *user explicitly authorizes* resumption and access is actually healthy

1. Read `docs/phase1c1_drive_operations.md`, `docs/phase1c1_usage.md`, and `reports/phase1c1_review_continuation.json` on PR #6. Preserve any pending rclone VFS writes.
2. Confirm a single conservatively rate-limited read-only remote probe. If 403 persists, stop with `BLOCKED` and precise evidence; do not brute-force retries or modify OAuth/mount configs.
3. Verify all nine remotely stored vector+manifest pairs by identity, size and streamed SHA-256 from remote, **not only mount cache**. Report absent/unpaired/partial files without deleting them.
4. Under existing provenance lock and user-approved exact 7-record plan, recheck existing ledger prefix/hash plus seven ZIP SHA/size; append only if all conditions match. Report remote readback; **never rewrite prior entries**.
5. Before running full ingestion, add and test an explicit year filter for 2014/2025 and fail-fast behavior for persistent remote failure; existing `--stage all` also includes 2008 and must not be run unmodified for this purpose.
6. Ingest with bounded scratch and verify building polygons (`BldA`) and road edges (`RdEdg`) separately for common-support areas. Document gaps, duplicates and source metadata. 2014 and 2025 archive availability is **not** proof of feature completeness.
7. Run correspondence sensitivity analyses and geographic summaries; publish immutable GeoParquet/CSV/maps and manifests to `processed/phase1c/codex/` with confirmed remote hashes. Record exact support area.
8. Update six Phase 1-C1 reports and tests; leave PR Draft if any key step is unfinished. Do not infer construction, demolition, abandonment or road-centerline connectivity.

## Deliverable and acceptance

- PR #6 remains the only implementation branch for C1; precise command/output in PR discussion.
- Offline tests + affected live checks only when data access permits, with explicit pass/fail/skip.
- Separate clear statuses: `remote_upload_verified`, `ledger_appended`, `analysis_scope_verified`, `geoparquet_published`, `overall_completion`.
- **Do not alter credentials/configuration or run new API probes under this document alone.**
