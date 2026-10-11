# Phase 1-C1: Drive制限の調査と再開条件

## 2026-10-11 レビュー後の実測

`reports/phase1c1_drive_resume_probe.json`に、再試行なし・非再帰・0.5 transaction/s・burst 1の読取専用確認を保存した。既知のdataフォルダIDを起点にし、ルートからのパス探索も省いたが、最初の一覧取得でHTTP 403 `RATE_LIMIT_EXCEEDED`となった。この実行による追加のDriveアクセスを停止した。stderrに同じエラーが二度表示されるのはエラーの伝播であり、実行したrcloneコマンドは1回だけである。

応答は`defaultPerMinutePerProject`、`Previous quota: Requests per minute`、consumer project `202264815644`を示した。これは保存容量不足を示すエラーではない。自身のリクエスト総数や他利用者の利用量は取得できず、このPCが上限を使い切ったとは断定できない。

認証情報を出力せず設定を調べたところ、`gdrive`は独自`client_id`未設定、`root_folder_id`未設定だった。既存mountは`--tpslimit 8`で稼働中。rcloneは空のclient_idで共有クライアントを使うため、共有プロジェクトの負荷が影響している可能性がある。[rclone Drive公式資料](https://rclone.org/drive/#making-your-own-client-id)

共有クライアントの制限は、このジョブの速度制限だけで解消する保証がない。Googleは403/429時の上限付き指数バックオフを案内するが、今回の明示指示に従って継続再試行は行わない。[Google公式の制限・バックオフ説明](https://developers.google.com/workspace/drive/api/guides/limits)

## API負荷を抑える運用案

- 再開時は下記の単一プローブを先に実行し、失敗したら原本ハッシュ・FUSE探索・変換を始めない。空の一覧や途中のJSONを成功として読まない。
- APIを使うジョブを直列化し、最初は0.5 transaction/s、burst 1とする。`--tpslimit`はプロセスごとの制限であり、既存mountや別プロセスと合算した全体制御にはならない。[rclone速度制限](https://rclone.org/docs/#tpslimit-float)
- 確認済みフォルダIDと対象リストを再利用し、Drive全体への再帰的ls、各工程での再inventory、各地物でのstatを避ける。SHA検査は必要な境界で1回ずつストリーミングする。ファイル名、サイズ、mtimeだけでSHA検査を代替しない。
- mountのdirectory cache/pollingを見直す案はある。長いdirectory cacheは外部変更の検出を遅らせ、poll停止は変更検知を止めるため、台帳・公開直前にはリモート再読取が必要。今回mount設定は変更していない。[mount cache/polling](https://rclone.org/commands/rclone_mount/#directory-cache)
- 独自OAuth client IDへの移行は共有制限を切り離す選択肢である。Google Cloudのプロジェクト設定と対話認証が必要であり、今回それらを作成・変更していない。秘密鍵やトークンをPRへ載せない。
- VFSの未送信ファイルを保全する。mountの強制終了、キャッシュ削除、`sync`による整理、partialの自動削除は行わない。full cache内の読取一致はリモート保存完了の証拠ではない。[VFS full/write cache](https://rclone.org/commands/rclone_mount/#vfs-file-caching)

回復後に手動で1回だけ行う確認（設定ファイルの変更なし、失敗時は停止）:

```bash
timeout 25 rclone lsjson gdrive: \
  --drive-root-folder-id 1XqQEuapdFd5dms0xa3I8reLGyenzc8gf \
  --files-only --max-depth 1 --tpslimit 0.5 --tpslimit-burst 1 \
  --retries 1 --low-level-retries 1 --contimeout 5s --timeout 10s
```

## 整合性確認と再開順序

1. `reports/phase1c1_review_continuation.json`に既存9レイヤーの相対パス・期待SHA・期待サイズ・manifestパスを保持した。これは初回レポートから作ったチェックリストであり、今回リモートを再検証した結果ではない。
2. 回復後、各vector/manifestを直列にリモート取得する。vectorは一時ファイルへ丸ごと保存せずSHA-256を逐次計算する。manifestのlayer_id、入力SHA、処理版、parameters、出力SHA、bytes、CRSを初回記録と照合する。9ペアの欠落・不一致は停止し、原物を保全する。残留partialや未対応vectorがあれば削除せず別に報告する。mount/cacheを介したreadbackだけでupload完了としない。
3. 承認済み7件は`docs/phase1c1_usage.md`の台帳手順を使う。承認plan SHA、台帳の事前SHA、全原本SHA/sizeを再検査する。**不一致は停止**する。追記後のリモート全バイトが旧台帳＋7新規行に一致することを確認する。取得日時・直接URLはnullを保持する。重複原本1件は保持し追記しない。
4. 既存派生物の`acquisition_registered=false`を後から書き換えない。登録後に作る派生物は登録済みとして新しいmanifestを作る。
5. 次回の全域変換は2014/2025年だけを明示選択する。現行`phase1c1_ingest.py --stage all`は2008年も選ぶため、そのまま再実行しない。年代フィルタと保存失敗時の即時停止を実装・検証してから実行する。既存のcatch-and-continueで全区画への失敗アクセスを繰り返さない。
6. 両年代45区画ずつを対象とするが、ZIPの存在と地物の完全性は別である。BldA/RdEdg別の収録状態・欠損・重複・県内共通範囲を確認し、県全域の照合・地域集計・感度分析へ進む。2008年は検証済み測地変換が得られるまで保留する。
7. GeoParquet・CSV・地図と計算入力・manifestを新IDでDriveへ保存し、リモートSHAを確認する。全域完了を確認してから6報告とvalidationを更新する。PR #6はDraftを維持し、mainへmergeしない。

現状は上記2以降を実行できていない。新しい解析・GeoParquet・CSV・地図の生成は0件で、全域解析は未完了。
