# Phase 1-C coordination plan (2026-10-21)

> Status at review time; verify GitHub's current state before taking action. This document is a coordination plan, **not** authorization to change protected Google Drive files, bypass access limits, or merge PRs.

## Baseline and current work

- Default branch `main` at review: `b24be1ee767b8668207e0187e03295878dc9a936` (Phase 1-B.5 merged). Earlier Phase 1-A/1-B are merged.
- [PR #6](https://github.com/blabo25226/kanagawa_ruins_search/pull/6): Codex Phase 1-C1 building/road-edge data, **Draft / blocked**. Partial 2014–2025 analysis covers ~0.644% of Kanagawa by area. Full 2014/2025 GIS ingestion, remote integrity checks, seven approved ledger appends and full-domain reports remain incomplete due to repeated Google Drive API HTTP 403 rate-limit responses. 2008 JGD2000 datum conversion is separately blocked.
- [PR #7](https://github.com/blabo25226/kanagawa_ruins_search/pull/7): Claude Code Phase 1-C2 2014–2021 land-use analysis, ~75.3% of Kanagawa by area (not prefecture-wide). Revision 0.2.0 corrects the connected-component definition; **the extra commit `b91ed71` ("kari commit", 2026-10-21) also introduces Phase 1-C1 files**. Do not merge before the unrelated changes are cleanly removed and rerun tests.
- [PR #8](https://github.com/blabo25226/kanagawa_ruins_search/pull/8): Phase 0 append-only ledger/test repairs. Includes `c52bb51` validating immutable original 53 lines and permitted future appends. Draft pending review.
- CI workflow on this coordination branch adds a **GitHub-only safety test**; no external Drive dataset, credentials, live integration tests, or large GIS data should be loaded in GitHub Actions.

## Sequence and owner

| Priority | Owner | Work | Done when |
|---|---|---|---|
| P0 | Claude Code | Remove `b91ed71`'s unrelated Phase 1-C1 changes from PR #7 **without force-push**, then verify diff and offline tests | PR #7 changes only Phase 1-C2 modules, reports, tests and agreed shared files; Phase 1-C1 stays in #6 |
| P0 | Reviewer / Claude | Review PR #8's append-only ledger semantics and regression tests (53 and 60 rows) | Tests prove immutable prefix and validated appends; no raw file mutation; PR #8 can be reviewed/merged separately |
| P1 | Reviewer | Merge #8 after review, then update/recheck #7 against main and merge #7 **only after explicit user go-ahead** | No conflicting branches, appropriate tests/checks green, claims and Drive-output status verified |
| P1 / BLOCKED | Codex | Recover read-only Drive access conservatively and resume Phase 1-C1 according to approved operations plan | Confirm remote upload integrity for previous nine layers, append approved seven ledger entries only under required controls, process actual 2014/2025 coverage and publish verified outputs |
| P2 / NOT YET AUTHORIZED | Future agent | Combine valid C1/C2 results with DEM when available; assess shared spatial/temporal support | New scoped issue, user approval, QA and separate branch before any new analysis |

## Shared non-negotiable rules

1. Original ZIPs, existing provenance/ledger records, previous derivatives and previous analysis versions are immutable. No unapproved deletions, cache resets, rclone config/OAuth changes, `git push --force`, or direct pushes to main.
2. Respect `AGENTS.md`, `firstinstruction.md`, and `agent/rules/*.md`; preserve their historical phase instructions. Scope extensions require explicit user authorization. This plan alone does **not** grant additional Phase 1-D research or data acquisition.
3. Keep agent branches and Google Drive derived subtrees separate: C1 under `processed/phase1c/codex/`, C2 under `processed/phase1c/claude/`. Do not commit ZIP, GeoParquet, rasters or sensitive coordinates.
4. Do not call recorded disappearance of a building or road evidence of demolition or abandonment. Differences in dates/CRS, survey scale and land-use classification matter.
5. For each PR, report tested commit, commands, real-vs-synthetic tests, failed/skipped checks, valid spatial coverage, input/output hashes, and blockers. **No success claims for unverified remote uploads or unfinished work.**
6. GitHub PR comments/issues are asynchronous instructions and do not automatically run Codex/Claude Code. Start or resume those agents explicitly in their connected environments.
7. CI is intentionally offline and cannot establish actual Google Drive or GIS-data completeness; local live integration requires separately verified access.

## Handoffs

- Codex: [Phase 1-C1](codex_phase1c1_handoff.md)
- Claude Code: [Phase 1-C2](claude_phase1c2_handoff.md)
- CI and review: [GitHub quality gate](github_pr_quality_gate.md)
