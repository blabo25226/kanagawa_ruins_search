# Issue #19: stacked CLI integration check

Review date: 2026-10-22 JST. Base remains `chatgpt/phase1c-coordination-20261021`.
Latest #9 base `f57d31a0a32e3e195dd63ff39d639e866fe36e3d` was incorporated by normal merge
`625be134bdf4261ee80b7db70fb2124784d9f5f8`; the new integration checkpoint was read.
Only base documentation changed; no conflicts occurred. No PR was merged and main was not changed.

## Verification

- `python scripts/ci/check_worker_cli.py`: PASS, zero CLI subprocesses, no authentication/inference.
- `python scripts/ci/check_worker_cli.py --probe-installed --output reports/worker_cli_observed_20261022.json`:
  PASS, nine fixed information commands, sequential, no retries. Codex 0.163.0, Claude 2.1.280,
  Cursor agent 2026.09.23, agy 1.4.4. Required mode/permission/print flags remain present.
- `python -m unittest discover -s tests -p test_worker_cli.py -v`: 18 PASS.
- `python -m unittest discover -s tests -p test_pr_scope.py -v`: 8 PASS.
- `python scripts/ci/check_pr_scope.py --base origin/chatgpt/phase1c-coordination-20261021`: PASS.
- `python -m compileall -q src scripts tests` and `git diff --check`: PASS.
- `AGENTS.md` and `CLAUDE.md` relative links resolve. They preserve firstinstruction/rules priority,
  and reference the runbook without authorizing delegation.
- Offline diagnostic source SHA is recorded in the observation JSON. Raw help/credentials are not stored.
- [Official Codex CLI reference](https://developers.openai.com/codex/cli/reference) was fetched again;
  installed help remains the version-specific evidence. No installer/login/update command was run.

The authenticated `WORKER_OK` test remains **NOT_RUN**. CLI help is not an authenticated service,
sandbox enforcement or independent Google Drive access test. No model, Drive, OAuth, mount or cache
operation was requested by this check. PR #18 proves only its separately documented FUSE read.
GitHub CI must be evaluated on the final pushed head; its URL and exact SHA are recorded in the
PR #16 review-request comment, rather than reusing the older green run.
