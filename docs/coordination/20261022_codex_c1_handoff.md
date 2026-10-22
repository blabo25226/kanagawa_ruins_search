# Codex 作業依頼：Phase 1-C1オフライン再開前監査と45メッシュ状態表

**担当**: Codex（次の独立作業）  
**ベース**: 最新`origin/main`、専用ブランチ `codex/phase-next-c1-offline-preflight`  
**作業場所**: 別worktree。既存作業ブランチ、C2ファイル、Drive、raw、provenance、認証・rclone設定を変更しない。

## まず読む資料
- `firstinstruction.md`, `AGENTS.md`, `agent/rules/*.md`（特に00, 30）
- `docs/coordination/20261022_next_cycle_roadmap.md`
- `docs/coordination/20261022_data_readiness.md`
- `docs/phase1c1_usage.md`, `docs/phase1c1_drive_operations.md`
- `reports/phase1b5_inventory.json`, `reports/phase1c1_validation.json`, `reports/phase1c1_review_20261021.json`
- `reports/phase1c1_registration_plan.json`, `reports/phase1c1_registration_execution.json`
- `scripts/phase1c1_ingest.py`, `scripts/phase1c1_verify_remote.py`, `scripts/phase1c1_analyze.py`
- [未解決Issue #12](https://github.com/blabo25226/kanagawa_ruins_search/issues/12)

## 目的
C1が2014/2025基本項目各45メッシュについて**何が証跡で確認済み、何が未処理、何がRemote未検証なのか**を、GitHubにある現存レポートだけから説明できるようにする。DriveのHTTP 403にアクセスして再試行するのではなく、**再開可能性の静的・オフライン検証**を実装／報告する。今後本実行する場合の条件をテスト可能にする。

## 必須タスク
1. 現在の実行スクリプト・QA・CLIオプションの実コードを読み、`--years` (既定2014/2025)、段階的停止、`--resume-report`、remote SHA照合の整合性をレビュー。推測でPASSにしない。
2. Git管理済みのB.5/C1レポートから、2014/2025各45の**アーカイブ存在**と、実際に比較済みの**2メッシュ**を区別する機械可読な集計ステータスを作成する。必要項目: `mesh2`, `year`, `source_provenance`, `archive_present_reported`, `converted`, `temporal_analyzed`, `remote_sha_verified`, `crs_source`, `status`, `limitation`. 未知値はnull/unknown。報告にない個別パーティションの実在を作り出さない。
3. ステータス表について、集計数の重複、重複アーカイブ、面積カバレッジ、2008除外、比較年差、保存済9ペアと未検証9ペアの区別を検証する**オフラインの合成／fixtureテスト**を追加する（Drive読取なし）。
4. `phase1c1_verify_remote.py`を実行**しない**で、再開時に何を比較し失敗時どこで止まるかをコードレビューし、抜けがあればmockに限ったテスト・修正を行う。9 remoteペア0/9、台帳7件の実追記0、2025/2014解析県域未完を維持する。
5. 戻り値・exit status・error報告・dry-run時副作用・input SHA・out-of-coverageを混同しない。改変するなら対象C1コードと専用テストだけ。
6. `reports/phase_next_c1_offline_preflight.md`と機械可読結果JSON（必要なら、**明確なGitHub証跡由来**の属性だけ）、テストログ、PR説明を作る。

## 受入基準
- GitHub上の過去監査と、新たなremote live検証の未実施を明記。`REMOTE_UNVERIFIED`を`VERIFIED`へ昇格させない。
- 原本ZIPを新しく開かず、Drive API・rclone/FUSE・Google Driveコネクタ・ネットワーク・OAuthの実操作は**行わない**。
- raw、`provenance.jsonl`、既存派生GIS、旧phaseレポート、`agent/rules/00-phase-gate.md`を上書きしない。
- オフラインpytest/unittest（既存C1重要テスト含む）と `python -m compileall -q ...` と `git diff --check`。通らないものは失敗・skip理由・環境制約を記録。
- PRの差分はC1と専用報告だけ。メッシュ別状態を機械判定できる形で残し、既知の2メッシュを代表標本と書かない。
- **PRを作って停止**、自分でmainへマージしない。他エージェントを自動起動しない。

## 今回やらないこと
- 403回復プローブ、7件の台帳追記、9件の実リモートSHA、45メッシュの実データ再解析、2008年の未確認CRS補正
- C2/Phase 1-DのGIS統合実行、廃墟・廃神社・廃道の候補抽出・ランキング・地点公開

## 報告フォーマット
`baseline_main_sha`, `analysis_scope`, `source_reports`, `archive_count`, `temporal_analyzed_meshes`, `remote_verified_pairs`, `tests_passed`, `tests_skipped`, `code_changes`, `blocked_items`, `needs_user_approval`を必ず示す。
