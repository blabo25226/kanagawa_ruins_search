# Phase 1-C1 利用手順

これは基盤地図情報の**版間の記録差**を調べる研究用処理である。建設・解体年月、廃墟・廃道の判定には使わない。現時点の実行は部分検証であり、県全域分析の完成ではない。

## 準備と実行

専用Conda環境を有効化し、`RUINS_DATA_ROOT`を既存の実Driveマウントへ設定する。既存環境やマウント設定は変更しない。既存Phase 1-AのN03 2026神奈川県レイヤーを使う。

```bash
conda activate kanagawa-ruins
python scripts/check_environment.py --output reports/new_environment_check.json
python scripts/phase1c1_ingest.py --stage pilot --report reports/new_pilot.json
python scripts/phase1c1_ingest.py --stage all --pilot-report reports/new_pilot.json \
  --report reports/new_ingest.json
python scripts/phase1c1_analyze.py --ingest-report reports/new_ingest.json \
  --run-id unique_run_id --report reports/new_analysis.json
```

既存レポート、原本、派生物は上書きしない。途中から取り込みを再開するときは、保存済み出力のSHAを照合したうえで新しいレポートを指定する。

```bash
python scripts/phase1c1_ingest.py --stage all --pilot-report reports/new_pilot.json \
  --resume-report reports/phase1c1_ingest_r2.json --report reports/resumed_ingest.json
```

出力先は `processed/phase1c/codex/vectors/` と `manifests/`、解析成果は `analysis/<run-id>/`。Phase 1-AのGeoParquet writer、CRS検査、排他公開・SHA再読取、およびPhase 1-Bで再利用されているscratch管理を使う。一般解析はGeoParquet入力ハッシュも検証する。manifestとファイルがそろって初めて保存済みと扱う。マウントのreadback一致は、リモートへのupload完了の保証とは区別する。

2008年は補正グリッドがないためEPSG:4612のまま保存し、`analysis_ready=false`。2014年・2025年のEPSG:6677レイヤーへ推測で重ねない。後日、神奈川県に適用できる正式な補正操作を確認したら新処理版・新IDで出力する。

全域取り込みはBldAとRdEdgを変換する。BldLはpilotで読み取りを検証し、面とは別の線地物として保持する。BldLから自動的に面を作らない。現実データの非連続線分も架空の接続線を補わない。

## 取り込みと照合の条件

- 外部ZIPを丸ごとメモリ展開しない。内部ZIPを1件ずつジョブ専用一時領域へコピーし、XMLを逐次パースする。既定一時容量1,000,000,000 bytes。XML1件の受付上限512MB。終了・割込時に一時GISを削除する。
- UTF-8 / Shift_JISをXML宣言から厳格に読む。未知CRS、未知構造、開いた面リングや矛盾する同一fidは停止。不正なトポロジーは数を記録して除外し、判定不能を保持する。
- 版選択は同年代・同コードのファイル版日付の最大値。同日重複は内部ZIPのSHA一致が必要。`devDate`が示す地物整備日と、ファイル版の日付は別属性で保持する。
- 建物は候補距離1/5/10m。IoU≥0.2、または交差面積/小さい方の面積≥0.5、または重心距離≤許容距離かつ面積比≥0.5かつバッファIoU≥0.3。候補グラフの連結成分から分割・統合・多対多の曖昧さを分類する。単独対応のIoU≥0.5を`matched`とする。これらは未校正の対応仮説であり検出精度ではない。
- 情報レベル差は`ambiguous_survey_scale`、未対応のメッシュ境界付近は`indeterminate_partition_boundary`。地物完全性は保証しない。不正面がある比較区画の未対応地物は`indeterminate_geometry_quality`。
- 道路は相手道路縁のバッファ内にある延長比を双方向で計算する。0.9以上を空間的一致として集計する。道路中心線の生成・接続性解析は行わない。
- 地域集計は2026年N03市区町村コードとEPSG:6677の1km正方形グリッドへ**重心で全地物を帰属**させる。面積・延長は境界で切り分けていない。市区町村内に厳密に切り取った面積・延長や物理的建物数とは異なる。

## 台帳への追記案

`reports/phase1c1_registration_plan.json`の7レコードがレビュー対象。基本項目8原本のSHAとサイズを再確認済みで、完全重複1原本はそのまま保存する。取得日時・直接取得URLを推測で埋めない。提供元の配布ページと利用規約ページを記録し、個別成果の利用条件を別途保持する。

**実際の追記にはユーザーの明示承認が必要**。承認後の手順は以下。今回の実行では追記していない。

1. 承認したplanのSHA、既存台帳のSHAを確定する。
2. 既存`ProvenanceLock`で排他取得し、台帳がplanの`ledger_sha256_before`と一致することを確認する。不一致なら再レビューし、自動で追記しない。
3. 全7原本のSHA・サイズ、source_idとrelative_pathの非重複、必須フィールドを再検証する。同じレコードが既にある場合も二重追記しない。
4. 台帳末尾が改行済みであることを確認し、既存バイト列を保存する。7件をJSONLの新規行としてappendする。既存レコードをrewriteしない。
5. readbackした全体が「既存バイト列＋承認済み新規行」と完全一致することを確認する。ローカルロックが保証するのは同一ホストだけであり、別ホストの書込みがない運用条件を確認する。
6. 前後SHAと追記内容を監査記録に保存する。同期完了とリモート再読取も検証する。失敗時に既存台帳を自動truncateして戻さない。

未登録のまま許可済み解析を行う場合、入力の実SHAを保持し、manifestの`acquisition_registered=false`を維持する。解析の許可を台帳追記の承認と扱わない。

## Drive API障害時

今回、Drive APIのクォータ超過HTTP 403で全域保存が中断した。`phase1c1_ingest_r2.json`の正常保存済みペアを保全し、APIの回復後に再読取検証して再開する。未完了のmanifest/partialがないかを確認し、既存ファイルは自動削除・上書きしない。

`scripts/phase1c1_pilot_analysis.py`は、検査済み原本から2メッシュの2014/2025年を一時変換して比較する代替手順。小さな地域集計CSV・図のみローカルreportsへ残し、GeoParquetは一時領域の終了時に削除する。Drive保存できたと報告しない。既存pilot出力がある場合は新しい出力名へ変更して実行する。補助土地利用が読めない実行では森林代理区分・山間地域比較を未実施とする。

```bash
python scripts/phase1c1_pilot_analysis.py --report reports/reproduction_analysis.json \
  --artifact-dir reports/reproduction_figures --run-id reproduction \
  --ingest-report reports/reproduction_temporary_ingest.json
```

最新の表示範囲とゼロ中心の色尺度を明示した地図は`phase1c1_render_maps.py`で集計CSVから生成した。`phase1c1_plot_review.json`に図と入力集計のSHAを保持する。`phase1c1_report.py`は今回の実行JSONから指定6報告を生成する。既存の報告ファイルがある場合は停止し、上書きしない。

## テスト

```bash
python -m pytest tests/test_phase1c1.py -q
# 従来のPhase0実Drive監査を今回のオフライン回帰から除外する
RUINS_DATA_ROOT=/tmp/ruins_intentionally_unmounted python -m pytest -q \
  --ignore=tests/test_phase0_4_1.py
git diff --check
```

Conda環境のGDAL CLIをPATHで有効にする。合成試験は実地図精度を証明しない。正解ラベルがないため、p値や実測検出精度は生成しない。
