# Phase 1-B 実装報告

実施日：2026-10-11（JST）。実行日時のJSONはUTC。実装担当：Codex。独立レビュー待ち。

## 1. 開始状態と許可範囲

最新mainをfetchし、PR #3のマージコミット `71cb91da59b220f1e58918dd6baa4430d5f3dd74` から `codex/phase1b-historical-raster-foundation` を作成した。開始時に未コミット変更はなかった。Phase0・Phase1Aの履歴レポートは保存し、AGENTS/README/phase gateを今回の明示的許可に合わせて最小更新した。新規派生物は本物のrcloneマウントを確認した `processed/phase1b/` のみ。新規データ取得・認証・購入・検出・ランキングは行っていない。

## 2. 実装した機能

- `imaging/`：現有画像inventory、実キーに基づく写真カタログ正規化・検索、XYZ座標/ピクセル変換、GCPアフィン推定と独立誤差評価、GDAL幾何補正。
- `raster/`：window IO、DEFLATE COG、GDAL full validator、基底画素/マスク保持確認、Phase1B専用の安全なpublisherとmanifest、5つのCLI。
- `terrain/`：公式仕様を参照したbounded FGD XML/GML/ZIP、元SRS/mesh/NoData/標高保持、限定的な水平再投影、メートルDEMからのwindow傾斜・陰影。
- `qa/`：原本と取得台帳の一致、COG/XYZ/カタログ/manifest検証。監査は登録済みの完全な派生物だけ識別し、未登録・破損をFAILにする。

## 3. 環境・依存関係

実測：Python 3.12.15、GDAL 3.13.3（CLIとRasterioバックエンド）、Rasterio 1.5.2、NumPy 2.5.3、PyProj 3.8.0 / PROJ 9.9.0。既存Phase1AのDuckDB 1.4.3等は変更していない。`pyproject.toml`にRasterio/NumPyを明記し、environment.ymlのNumPy/Rasterio/GDAL条件を検証環境に合わせた。新しいライブラリのインストール、Conda solverによる環境再解決、lock生成は実施していない。既存環境で`pip check`は成功した。

## 4. 現有データの機械確認

[inventory](phase1b_inventory.json)でJPEG4枚、カタログ42件、旧版地図画像0件、DEM0件、Phase1A 107レイヤーを確認した。原本の出典・SHAは正規provenance.jsonlと照合した。

## 5. 実データで保存したCOGとカタログ

全COGは256×256、RGB uint8 3band、EPSG:3857、DEFLATE、overview [2]。基底画素とマスクは元JPEGのデコード値と一致。GDAL full COG構造検証・XYZ bbox照合・北向き配置・対象地域sanity checkに成功した。撮影日はnull、期間は取得台帳の1974–1978年。元写真の位置精度を保証した結果ではない。

|入力JPEG|asset_id|容量 bytes|bbox EPSG:3857|
|---|---|---:|---|
|aonohara_1974_z15_29054_12916.jpg|aerial__gazo1__z15_x29054_y12916_v1|207372|15495314.374, 4240114.833, 15496537.366, 4241337.825|
|aoyama_1974_z15_29058_12912.jpg|aerial__gazo1__z15_x29058_y12912_v1|199844|15500206.344, 4245006.803, 15501429.336, 4246229.795|
|toya_1974_z15_29055_12920.jpg|aerial__gazo1__z15_x29055_y12920_v1|216874|15496537.366, 4235222.863, 15497760.359, 4236445.856|
|suarashi_1974_z15_29054_12906.jpg|aerial__gazo1__z15_x29054_y12906_v1|180212|15495314.374, 4252344.758, 15496537.366, 4253567.750|

COG合計は804,302 bytes。正規化カタログ `aerial__photo_catalog__tsukui_v1.json` は42件、94,917 bytes、CRS null。各出力の完全な相対パス・source/output SHA・実行パラメータ・使用ライブラリは[aerial conversion](phase1b_aerial_conversion.json)と[catalog conversion](phase1b_catalog_conversion.json)に記録した。Driveには5成果物と5manifestを新規保存した。画像そのものはGitに含めていない。

初回manifestはその時点の実装SHAを保持する。最終コードで再生成したCOG4枚・カタログ1件は全て同じ出力SHAとなり、`already_present_reproduced`で既存成果物を変更しなかった。[画像再生成](phase1b_aerial_reproduction.json)、[カタログ再生成](phase1b_catalog_reproduction.json)を参照。

## 6. 航空写真カタログ

実キーは`specification_id`、`planning_organization`、`center_pos`、`geom_image_*_pos`等。`specId`は正規化時の別名である。撮影日不明6件、範囲状態は `{'footprint_approximate': 34, 'center_only': 8}`。座標datum・高度・個別ライセンス確認は未確認。元の`verification_status=verified`は位置精度の独立保証とは扱わない。

現有単写真は0件で、XYZ4枚を42件の単写真取得と取り違えず全件not_acquiredとした。年代・native bbox・近似footprint・未取得の検索を実装。メートル近傍検索には確認済み地理CRSの明示を要求し、実カタログのdatumを推測設定しない。中心のみ8件はfootprint検索から除外する。

## 7. 合成GCPの精度評価

既知Affine `(5,0,-60000,0,-5,-40000)` を持つ32×32合成画像と学習4点・独立検証1点を用いた。学習RMSEは1.150429910983213e-11 m、独立検証RMSEは0.0 m。検証座標だけに3m/4mのずれを与えるとRMSEは5.0 mとなり、学習残差と独立誤差を区別できた。GDAL補正後のbboxは[-60000.0, -40160.0, -59840.0, -40000.0]、EPSG:6677で画素一致した。

[合成検証JSON](phase1b_synthetic_verification.json)に実コマンド・係数・点別残差・SHAを保存した。テストでは誤った既存GeoTIFF geotransformをGCPで置き換えること、点不足・退化・混合/未定義CRS・検証点使い回しの拒否を確認した。実在する旧版地図の位置合わせ結果ではない。

## 8. DEM合成検証

FGD仕様形状の合成UTF-8 XMLとZIPから、緯度経度軸、北西0,0のセル順序、startPointによる省略、NoData -9999、正当な負標高、mesh/SRSを確認した。投影済み合成平面DEMで理論傾斜12.6043826484度と照合した。

|出力|有効セル|NoDataセル|最小|最大|
|---|---:|---:|---:|---:|
|slope|3844|252|12.604382514953613|12.604382514953613|
|hillshade|3844|252|188.40943908691406|188.40943908691406|

平坦DEMの傾斜0と陰影255/√2、異なるx/y解像度の平面、512px window境界、NoData伝播、geographic/未定義/回転CRSの拒否、COGと傾斜/陰影の再現性もテストした。合成画像/DEMはジョブ専用一時領域で削除しDriveへ保存していない。標高値の基準変換は実装していない。実DEMを検証した結果ではない。

## 9. 取得準備と公式資料調査

[手動取得ガイド](../docs/phase1b_manual_acquisition.md)に公式リンク、DEM候補メッシュ533921/533931、写真ID、図幅照合、TIFF提供と費用・申請方法・条件をまとめた。[取得候補JSON](phase1b_acquisition_candidates.json)は現有JSONから機械集計した写真を示す。希望年次の旧版図が実在するか、津久井の5m DEM製品の範囲は手動確認事項。ログイン・購入・データ取得は行っていない。

## 10. 1976年土地利用の測地変換調査

公式TKY2JGDパラメータ`.par`とPROJが必要とする`tky2jgd.gsb`は別形式。現環境ではballpark禁止の4301→6677操作は利用可能0件、必要グリッド未配置だった。候補には2011地殻変動グリッドも含まれ、公式パラメータの正規利用・変換形式・検証点照合が未完了である。[環境実測JSON](phase1b_datum_research.json)と[公式資料を付した取得ガイド](../docs/phase1b_manual_acquisition.md#1976年土地利用の測地変換は保留)を参照。変換を実行せず、1976年GeoParquetはEPSG:4301のまま保存した。

PROJ 9.9.0では既存EPSGコードにJGD2024の名称が現れる。コード名だけで2011/2024の標高を同一視せず、入力SRS宣言・horizontal_datum・vertical_datumを別々に保持する。

## 11. テストと実行コマンド

開始時の既存テスト：91 passed / 26 subtests passed。Phase1Bには34テスト（うち実データ専用2件）と9サブテストを追加した。最終結果は[テストログ](phase1b_test_results.txt)を参照。最終実行は125 passed / 35 subtests passed。Ruffと`git diff --check`、`pip check`、wheel buildも成功。wheelに新規モジュールが含まれ、GISデータが含まれないことも確認した。警告は合成GML名の補正と意図的な未ジオリファレンス画像の読込であり、位置情報を推測補完していない。

```bash
git fetch origin
git switch -c codex/phase1b-historical-raster-foundation origin/main
RUINS_RUN_LIVE=1 conda run --no-capture-output -n kanagawa-ruins python -m pytest tests/ -q
conda run --no-capture-output -n kanagawa-ruins python scripts/phase1b_imaging.py --execute --report reports/phase1b_aerial_conversion.json
conda run --no-capture-output -n kanagawa-ruins python scripts/phase1b_imaging.py --mode catalog --execute --report reports/phase1b_catalog_conversion.json
conda run --no-capture-output -n kanagawa-ruins python scripts/phase1b_verify.py --execute --report reports/phase1b_verification.json
conda run --no-capture-output -n kanagawa-ruins python scripts/phase1b_georef.py --dry-run --report reports/phase1b_georef_plan.json
conda run --no-capture-output -n kanagawa-ruins python scripts/phase1b_dem.py --dry-run --report reports/phase1b_dem_plan.json
conda run --no-capture-output -n kanagawa-ruins python scripts/audit_databank.py --mode full --check-all-hashes --json-output reports/phase1b_final_audit.json
```

画像/カタログの再実行は同じ引数で別のローカルreport名を指定した。inventory・baseline照合・合成数値・PROJ調査はPython APIで機械集計した。合成検証の再現は`python -m pytest tests/test_phase1b_georef_terrain.py -q`、実データは`RUINS_RUN_LIVE=1 python -m pytest tests/test_phase1b_live.py -q`で行える。

## 12. 原本・Phase1A整合性とストレージ

[開始前baseline](phase1b_baseline_integrity.json)と[作業後照合](phase1b_original_integrity.json)で既存279ファイルのサイズ・SHAが全件一致した。うちPhase1Aは214ファイル（107 GeoParquet + 107manifest）。raw・provenance.jsonl・既存メタデータ/文献も変更していない。

フル監査は`FULL_PASS`、台帳53件のハッシュを全件再計算一致、全289ファイル、未登録0件、破損/サイズ不一致/欠落0件。Phase1B登録済み派生物は10ファイル（5成果物+5manifest）。

合成検証時のjob scratch実測peakは32,760 bytes、標準rcloneキャッシュのbest-effort実測は2,468,216,832 bytes。ジョブとキャッシュの合計上限25GB、既定ジョブ1GB、空き容量を確認する。共有マウント設定は変更していない。これは合成検証ジョブの測定値であり、全処理を通じたOSメモリ/全キャッシュの最大値を保証するものではない。

## 13. 判明した品質問題

- 過去の航空写真監査Markdownに記載されたカタログSHAは、現在の原本・正規台帳のSHA `205325245d13387c31ec29eb47bb3e2240f010dfd0064de276ab872fc6163327` と異なる。原本と台帳は一致しており、過去レポートを上書きせず本報告に差異を記録した。
- 過去の図幅表で533931=相模湖、533932=城山、533911=中津川とされた対応は、現行公式対照表の与瀬・八王子・大山とは異なる。旧版での図名変更は未確認であり、図歴照合が必要。記載された測量/修正年も確認済み扱いにしない。
- JPEG名の1974は正確な撮影日を示さず、gazo1期間は1974–1978。42写真には撮影日欠損6件、中心のみ8件、datum/高度/ライセンス未確認がある。
- 400dpiダウンロードと高解像度オンライン閲覧のログイン条件を区別する必要がある。現在の公式ヘルプから400dpi自体が一律ログイン必須とは確認できない。

## 14. 制約と次のフェーズ

実旧版図の位置合わせ・実DEMの適合性/標高精度、現行JGD2024 DEMの確認済み投影/標高変換、モザイク、高次/TPS、自動GCP、カタログの確定CRS、個別画像取得対応表のCLI公開は未完了。GML readerは限定仕様のUTF-8/GML3.2・単一DEM/明示startPointに対応し、全面的なXSD適合検証器ではない。

次は利用者が少量の公式DEM・旧版TIFF・単写真を正式取得し、出典/標高成果/CRSを登録した後、既存の合成検証に加えて実配布形式と独立参照点で検証する。1976年の変換は別の処理版で実装する。今回の基盤実装は実データと合成データを区別してレビューに提出し、新規PR作成後に停止する。候補検出・廃墟判定への移行は今回の成果に含めない。
