# Skill: Phase 0 Preparation

## Purpose

分析を一切始めず、再現可能なGIS CLI環境、公式データソース台帳、監査可能な取得経路、レビュー資料を整える。

## Prerequisites

- `firstinstruction.md` と `agent/rules/*.md` を読了
- Ubuntu + VS Codeターミナル、Conda、Git
- ソースサイトの最新利用条件を確認

## Procedure

1. `git status --short --branch` と `git remote -v`で環境とブランチ確認。
2. `conda env create -f environment.yml`、有効化、doctorとテストを実行。
3. `python scripts/fetch_sources.py --list` でソースを点検。
4. `source.md` の公式ページを閲覧し条件・更新日を確認。
5. `--dry-run --all-approved` で取得対象確認後、問題なければ`--execute --all-approved`を実行。
6. データの原本とメタデータを照合し、取得失敗は保留と記録。
7. `reports/templates/` を使って3種のレビュー資料を作成。
8. `git diff --check` / tests / セキュリティチェック後にcommit/push、そこで終了。

## Success criteria

- 指示書で要求された3レポートが存在
- 各コマンドの実行結果が記録
- 取得対象のライセンスレビュー完了（不明は保留）
- 生データはGit管理対象外
- Phase 1のコードも実行もなし
