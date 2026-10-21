# Issue #13 — CLI診断と手順書の修正

PR #9 head `cc609d866a7c140d5b504ee1fe0b0afa5c88efb2`から、専用worktree `/tmp/kanagawa-cli-runbook-hardening` とブランチ `codex/phase1c-cli-runbook-hardening` を作成。stacked PRのbaseは `chatgpt/phase1c-coordination-20261021`。

## 修正と実測

- ユーザー作成手順書を保持し、確認済みのCLI引数と未検証の実行時挙動を分離。AGENTS.mdと新CLAUDE.mdには短い参考導線だけを追加し、自動委任を許可しないことを明記した。
- `agy 1.3.2 --help`には実際に`--mode`と`plan`/`accept-edits`が存在した。レビューの「未対応の疑い」をそのまま事実とせず、実測版の例を保持した。Cursor `--trust`は信頼確認の省略として説明し、read-onlyの例から除去した。
- 導入済み4 CLIで`--version`/`--help`、Codexで`exec --help`を確認した。最終診断の固定9コマンドは成功。完全なstdout/stderr、認証状態、APIキーはレポートへ保存しない。結果は `worker_cli_observed_20261021_r2.json`。最初の情報表示診断は `worker_cli_observed_20261021.json` に保持した。
- 診断の既定は存在確認のみ、直接起動0。`--probe-installed`でも情報表示以外の引数は呼ばない。直列・上限9・10秒/件・予算45秒・終了待ち2秒/件・出力128KiB・再帰拒否・最初の失敗で停止。`--plan-worker-ok`は候補と承認要件を表示するだけ。
- 認証付きWORKER_OKの実行器は今回実装していない。将来追加する場合は別の実行フラグ、ユーザーのローカル環境承認、OS/ネットワーク隔離が必要。今回のモデル呼出しは0、認証付き疎通は未実施。CLI間の全方向呼出しや自律オーケストレーションが実証されたとはしない。
- CIには既定の存在確認とmockテストだけを追加。stacked base名の`/`を既存scope guardが拒否していたため、`git check-ref-format`によるリテラルref検査へ置き換えた。revision式を受け入れる変更ではない。

## 検証

```bash
python -m unittest discover -s tests -p 'test_worker_cli.py' -v
# 18 tests OK
python -m unittest discover -s tests -p 'test_pr_scope.py' -v
# 8 tests OK
python -m compileall -q scripts/ci tests/test_worker_cli.py tests/test_pr_scope.py
python scripts/ci/check_worker_cli.py
# subprocess_count=0; inference_executed=false; authentication_checked=false
python scripts/ci/check_worker_cli.py --plan-worker-ok agy
# PREPARED_NOT_EXECUTED; WORKER_OK NOT_RUN
python scripts/ci/check_worker_cli.py --probe-installed --output reports/worker_cli_observed_20261021_r2.json
# PASS; fixed information commands only (既存report名を再実行で上書きしない)
git diff --check
```

mockによる診断テストと、無害なPython fixtureによるtimeout/出力超過/子プロセス停止テストを行った。実AIはテスト内で起動しない。GitHub Actionsの結果はPR作成後に別途確認し、GIS実データの検証結果として扱わない。

Drive、原本GIS、台帳、OAuth/rclone設定、PR #6/#7/#8のブランチ、他者の作業ツリーは変更していない。mainやbaseへの自動mergeはしない。
