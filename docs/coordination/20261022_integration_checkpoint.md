# Phase 1-C integration checkpoint / main baseline proposal
**Review date:** 2026-10-22 · **status:** PROPOSED, NO MERGES AUTHORISED BY THIS DOCUMENT

This plan coordinates a single, reproducible `main` baseline containing Phase 1-C implementation, analysis reports and shared `.ai/`/CI instructions **without claiming that unfinished science is complete**. Review the latest heads and CI before each operation; all SHA/status values below are snapshots only.

## Scope and status at checkpoint

| PR | Content | Dependency | Scientific / execution status |
|---|---|---|---|
| [#16](https://github.com/blabo25226/kanagawa_ruins_search/pull/16) | Codex CLI runbook repair, `AGENTS.md` + `CLAUDE.md`, worker diagnostics | **stacked on #9**; target is #9 branch | Offline/mock testing successful per PR; authenticated model-to-model delegation NOT tested |
| [#9](https://github.com/blabo25226/kanagawa_ruins_search/pull/9) | `.ai/` instructions, CI scope guard, work coordination | #16 first, then #9 → main | GitHub CI green; C1/C2 tests not on this branch |
| [#8](https://github.com/blabo25226/kanagawa_ruins_search/pull/8) | append-only provenance/Phase 0 snapshot tests | after #9; independent | Original 53-record prefix and 60-record *synthetic* append checked; no actual 7-item append |
| [#7](https://github.com/blabo25226/kanagawa_ruins_search/pull/7) | Claude 2014→2021 land use; reports version 0.2.0 | after #8/#9 | 31 synthetic and 5 live tests reported locally; 75.3% **coverage**, not prefecture-wide. Cross-agent contamination reverted |
| [#6](https://github.com/blabo25226/kanagawa_ruins_search/pull/6) | Codex building and road-edge ingestion, temporal matching and reports | after #7/#9 (retest with integrated main) | **Partial** pilot ~0.644% of Kanagawa. Remote 9 pairs unverified, 7 ledger appends not performed, full-area run blocked by rclone API 403 |
| [#18](https://github.com/blabo25226/kanagawa_ruins_search/pull/18) | `agy` read-only Drive experiment | after #6/#9; documentation can integrate independently of successful Drive access | 2842-byte manifest SHA checked over **rclone/FUSE**, not independent Google Drive access. No large ZIP/remote persistence evidence |
| [#15](https://github.com/blabo25226/kanagawa_ruins_search/pull/15) | Claude Phase 1-D integration **design only** | after #6 and #7 for working links | No Phase 1-D execution authorized. C1/C2 common pilot support is extremely small |

**Research gate:** Merging PR #6 means **code and documented partial findings are accepted as a baseline**, not that the 2014–2025 all-Kanagawa analysis is done. Keep Issue #12 open and tests that prove data incompleteness. Similarly #18 does NOT resolve 403; do not silently replace rclone with agy for bulk transfers.

## Proposed merge order and roles

1. **Codex + reviewer:** finish PR #16, verify `AGENTS.md`/ `CLAUDE.md` links and CLI flags against installed `--help`; the `WORKER_OK` actual multi-CLI test is optional and separate, not a prerequisite for documentation integration. Reviewer merges #16 into its **base branch #9**, *not main*.
2. **Reviewer:** run CI on the updated PR #9 head, check that new shared files (.ai and GitHub Actions) are present and safe, merge #9 into `main`.
3. **Claude + reviewer:** check PR #8's 53- and 60-record scenarios, immutable prefix and negative cases; update to latest main without force-push or rewriting unrelated agent branches; reviewer merges #8.
4. **Claude + reviewer:** verify PR #7's v0.2.0 PR description, C2-only scope and recorded live evidence, rerun available offline CI with latest main, then merge #7. Do not relabel 75.3% as total-prefecture.
5. **Codex + reviewer:** review PR #6 against new main with **offline-only tests**, ensure C1 code can be imported with C2 and new QA tests. Explicitly preserve a `PARTIAL / REMOTE_BLOCKED` result; if critical test/regression is blocking, leave Draft and document exceptions instead of rushing the merge. If safely accepted as partial, merge #6; keep all unresolved science in Issue #12.
6. **Reviewer:** merge #18 after assessing that it adds scoped read-only experiment reports/tests only. Keep Issue #17's independent Drive route unresolved; **no evidence** that full C1 run can resume.
7. **Claude + reviewer:** verify PR #15 is design-only and references resolved, then merge #15.
8. **Post-merge cross-check:** run full eligible offline suite and real-data checks **only where access and explicit scope permit**, update project route/phase gate to accurately state both completed and blocked areas (without retroactive edits to immutable historical reports), produce an integrated QA/decision report and create immutable tag **only after QA**. New agent branches must start from this reviewed `main`.

**Do not merge automatically.** User approval and human review are required at the actual merge stage. Be prepared to reorder independent PRs if CI compatibility requires it, but **#16→#9** must be honored.

## Integration QA: explicit acceptance matrix

| Layer | Evidence | Pass / Block condition |
|---|---|---|
| Git/branch hygiene | main SHA before/after, exact merged PR commits, no force-push | No missing `.ai`, no C1 changes inside C2 or C2 changes inside C1 |
| CI offline | PR scope guard + Python compile + `pytest` with explicitly recorded selected/skipped tests | Exit 0 and no reported regression; **a green job with zero selected Phase 1-C tests is not scientific evidence** |
| Provenance | immutable Phase0 53 prefix; synthetic 60 append; actual ledger count | New 7 rows **not** treated as appended until verified via Drive; preserve source ZIP and historical records |
| GIS basic | BldA vs road edges; 2008 datum; 2014/2025 2-mesh pilot vs coverage | Unknown coverage, dates, CRS are marked; **do not** claim all-area completion |
| Land-use | 2014/2021; v0.2.0 connected-component 57.1/19.6/12.0/11.3%; reference 75.3% support | No old '82% isolated' claim; mismatch in temporal endpoints documented |
| `agy` probe | actual tool path + 2842-byte SHA; FUSE vs independent channel | `independent_drive_access=false`, `large_binary_transfer_verified=false`, `can_resume_c1_full_run=false` remain |
| Worker CLI | runbook, `AGENTS.md`, `CLAUDE.md`, mock tests; installed version checks | No implied automatic launching, CLI bypass flags, secret printing, paid recursive agents or hard-coded credentials |
| New phase | `docs/phase1d_integration_design.md` | **Design only**. No site coordinates, ranking, unsanctioned Drive writes, or new data downloads |

## When ready: integrated review deliverables

Create a **new review-only PR from the new main**, not an isolated copy of old branches:

- `reports/phase1c_integration_review.md`: per-PR commit audit, full test logs, live-test provenance, exact spatial/temporal support and unresolved risks.
- `reports/phase1c_release_manifest.json`: merged commits, datasets referenced (no raw data), test commands, check states, explicit booleans `c1_full_area_complete=false` and `agy_independent_drive_access=false` until verified.
- `docs/phase1d_readiness.md`: dependency on C1 area expansion, missing DEM, possible missing L03-b regions and human decision requests.
- Create a baseline tag such as `phase1c-baseline` **after** verified merged SHA and sign-off; do not invent/create the tag prematurely.

## Deferred / stopped work

- **User decision:** independent Google OAuth client configuration is deferred. Neither Codex nor Claude should implement/rotate it or modify rclone/FUSE configuration in this integration cycle.
- Optional: Codex can investigate actual independent `agy` Google Drive access through existing authorizations, **only as an explicitly scoped read-only experiment**, not a new login, arbitrary tool permissions or large transfer. If remote bytes cannot be independently verified, stop with `UNVERIFIED`.
- PR #6 broad ingestion, registration of seven ZIPs, DEM analyses and candidate creation are NOT authorized by this checklist.
- CLI-to-CLI orchestration can be tested later in the user's approved environment with limited, opt-in time/expense and isolation; no Github Actions secrets or background workers.
