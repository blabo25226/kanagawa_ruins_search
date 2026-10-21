# Claude Code handoff — PR #7 / Phase 1-C2

Reference: [PR #7](https://github.com/blabo25226/kanagawa_ruins_search/pull/7), [PR #8](https://github.com/blabo25226/kanagawa_ruins_search/pull/8), [coordination plan](20261021_phase1c_plan.md).
Owner: Claude Code. Keep Phase 1-C2 independent from Codex's Phase 1-C1 branch.

## Immediate review blocker: foreign commit

As of 2026-10-21, PR #7 head is `b91ed71c1be93d40609b4fb5f8027798f6e1df74` ("kari commit"). It adds about 19 Phase 1-C1 paths that belong in PR #6, including `agent/rules/00-phase-gate.md`, `scripts/phase1c1_*.py`, `src/kanagawa_ruins/geo/temporal*.py`, `src/kanagawa_ruins/temporal_pipeline.py`, `src/kanagawa_ruins/ingest/fgd.py`, `tests/test_phase1c1.py`, and `reports/phase1c1_*`. The claim that the PR is independent is currently not true.

**Safe resolution requested:**

1. First `git status` and fetch PR #7 head in an isolated worktree; preserve unrelated uncommitted work.
2. Inspect `git show b91ed71 --stat` and PR diff against latest main. If it is safe and exactly the undesired addition, make a **normal non-force revert commit** of `b91ed71`. Do not reset, delete branches, or force-push. If other work depends on that commit, explain the blocker instead of blindly reverting.
3. Confirm PR #7 contains no C1-only files or `agent/rules/00-phase-gate.md` C1 changes. Diff must contain only land-use/Phase 1-C2 work, reports, tests and justified shared files.
4. Keep version `phase1c2-claude-0.2.0` on Drive untouched. The earlier 0.1.0 results also remain immutable.
5. Verify the connected-component 1/2/3–4/5+ classification and reported shares (57.1/19.6/12.0/11.3%), coverage labels, CODH swapped-name audit, and relevant synthetic/live test records. Preserve the 75.3% area limitation and uncertainty from classification changes.
6. PR #8 maintains the common append-only ledger test; **do not duplicate its changes in #7**. Rebase/update #7 onto main only after #8 is reviewed/merged, and avoid force pushes or touching Codex's worktree.
7. Post verification commands and changed-file summary to PR #7; stop for review. Do not merge main.

## Acceptance checks

- No `phase1c1`-only files in PR #7; CI scope guard passes.
- Dataset analysis remains limited to confirmed L03-b coverage and never described as 100% Kanagawa.
- C2 analysis results and 0.2.0 manifest remain referenced correctly.
- Report direct evidence for tests; do not call a recorded 403 a successful live integration.
