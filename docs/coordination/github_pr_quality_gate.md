# GitHub reviews / Actions: lightweight guardrails

The proposed `.github/workflows/pr-safety.yml` will run on pull requests and via manual workflow_dispatch **after GitHub enables/accepts it**.

## What the workflow checks

1. **Static path check (stdlib Python)**: PRs with changes to both Phase 1-C1-only and Phase 1-C2-only paths fail. This catches PR #7's foreign `kari commit` while permitting one team to modify truly shared files with justification.
2. **Data guard**: modified repository paths may not contain binary/raw/processed GIS data (ZIP, GeoParquet, GeoTIFF, PBF, DuckDB). Figures and small Markdown/JSON summaries are allowed, subject to review.
3. **Syntax and whitespace**: `compileall` over `src/`, `scripts/`, `tests/`; `git diff --check` against base.
4. **Offline synthetic unit tests** for whichever known C1/C2/ledger test modules exist in the checkout. Requirements come from `pyproject.toml` plus test dependencies. These tests intentionally never use `RUINS_DATA_ROOT`.

CI must not use secrets or touch Google Drive, rclone, raw data, provenance, real-world locations, or application credentials. Actions only verifies the GitHub checkout; local live-test evidence remains required in scientific reports.

## Human merge order

- First review and (with the user's approval) merge PR #8.
- Remove PR #7's foreign commit, update it against main as appropriate, recheck diff/CI, then merge PR #7 **only with explicit user approval**.
- Leave PR #6 as Draft until remote upload/ledger/coverage blockers are resolved and independently reviewed.

If a CI run fails, link its run URL in the PR, give the exact command and error, and avoid bypassing protections. Do not set Actions auto-fix, auto-merge, or access to Drive secrets.
