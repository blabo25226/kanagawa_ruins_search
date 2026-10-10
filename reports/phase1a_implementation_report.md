# Phase 1-A GISデータ統一処理基盤 実装報告

## 1. 開始状態と許可範囲

実行日: 2026-10-10。実装担当: Codex（モデル選択は実行クライアントで管理し、コードの挙動には使わない）。開始時に `git fetch origin main` を実行し、最新mainが `9c149f3b97668c133f93a9a3ef0a65ebbc165f6d` であること、作業ツリーに未コミット変更がないことを確認した。そこから `codex/phase1a-gis-foundation` を作成した。

指定順で既存指示・設計・レビュー・台帳・実装を読み、`docs/gis_architecture_proposal.md`、特に改訂§8を基礎にした。Phase 0完了状態は今回のフル監査でも確認した。53取得レコードのSHA-256を全再計算し一致、原本等65ファイル、未登録・欠落・サイズ不一致・ハッシュ不一致はいずれも0だった（`phase1a_baseline_audit.json`）。

ユーザーの明示的許可に従いAGENTS、README、GEMINIと関連ルールのフェーズゲートだけを最小限更新した。許可対象は既存GISの整備・変換・検索と品質検証。原本raw、取得台帳、Phase 0履歴レポート、`firstinstruction.md` は保存した。廃墟候補の推定・ランキング・実在判定・画像認識・候補公開は実装していない。GPU、QGIS GUI、新規GISデータ収集も使用していない。PR後に独立レビューを待ち、mainへのマージは行わない。

## 2. 実装機能と責務

- `pyproject.toml` と `src/kanagawa_ruins/`: インストール可能なPythonパッケージ。設定、Drive安全確認、一時領域、出典台帳、レイヤーカタログ、CRS、geometry品質、取り込み、SQL、検証を分離。
- 既存 `scripts/storage_utils.py` の実装をパッケージ内に移し、旧スクリプトは互換入口とした。Phase 0取得ロジックは重複して作らず、既存取得台帳を読み取り専用で利用。
- 単独GMLもジョブへコピーしてからGDALで開き、読込時の.gfs生成が原本配下へ及ばないようにする。[GDAL公式仕様](https://gdal.org/en/stable/drivers/vector/gml.html)。ZIPのパストラバーサル・シンボリックリンク・重複メンバー・CRC・展開容量を検査。Shapefileを優先し、GMLも共通ローダで扱う。`.cpg`、明示された文字コード、DBF全テキストの厳格デコードを順に利用する。
- N03は元属性を保持し、存在する県名・市町村名・行政コードのみ共通属性へコピー。CODHは旧市町村境界として保存。
- OSM XML/PBFはPyOsmiumでストリーミング処理。全ノードをPythonへ渡す方式からネイティブのタグ事前フィルタへ改善した。参照解決はフィルタ前に実行される。ノード位置はジョブ専用ディスクインデックスへ置き、巨大PBF全体をGeoPandasへ読み込まない。node/way、対象タグ、全タグJSON、ID・型・版を保存。対象relationと参照不足wayは明示的に除外計上。
- N02/W05/P32は異なる属性構造を保持し、ZIP内部レイヤーごとに衝突しないIDで保存。UTF-8/Shift-JISの二重収録はUTF-8版を選び、同じ地物を二重出力しない。
- L03-bは内部KS-METAの年次と台帳・ファイルの年次を照合。1976/2014/2021のコード表を独立管理し、未確認コードはunknown、元コードは保持。
- GeoParquet 1.1/WKB/明示的PROJJSON、zstd圧縮。バッチ書き込み、元属性・欠損保持、入力SHA、行source_id、bbox、geometry型、出典・処理版を記録。処理日時を取得日時に流用しない。
- `list_layers()` はmanifestだけを読み、`load_layer()` は列選択とSQLによるbbox/limit抽出を提供。空間インデックスによるParquet行群スキップは未実装で、bbox指定でもgeometry走査は必要。
- DuckDBはインメモリ、メモリ1GB、2スレッド、ディスクspill無効。GeoParquetを正規データとし、更新型DBをDriveに作らない。OSM同一ドメインの重複をtype/idで報告し、指定順の最初を採用するビューを提供する。欠損補完はしない。
- CLIは既定dry-run。`--execute --area --layers --source-id --include-pbf --report` を実装。検証CLIは入力・出力SHA、全バッチgeometry、CRS、schema、bbox、件数、日本語の破損マーカー、SQL参照を照合する。

## 3. 依存関係と再現環境

専用Conda環境 `kanagawa-ruins` に `pyarrow==23.0.1`、`duckdb==1.4.3`、`osmium==4.2.0` をpipで導入し、editable packageをインストールした。`environment.yml` にこれらとpyogrio/pipを追加した。`pip check` は依存関係不整合なし。既存GIS環境のチェックもPASS（`phase1a_environment_check.json`）。

Python 3.12.15、GeoPandas 1.2.0、Shapely 2.2.0、PyProj 3.8.0、GDAL 3.13.3。その他の実インストール版は `phase1a_environment_export.yml` と各manifestに記録した。exportは実際の `conda env export` から生成し、ホスト固有prefixとeditableローカルパスだけを除いたインストール状態の記録であり、依存解決済みの新しいlockではない。既存 `environment.lock.yml` は変更していない。検査用ruff 0.14.0は開発ツールとして別途使用した。

DuckDB Spatialは公式coreから初回INSTALLが必要で、今回は導入・LOADとも成功した。DuckDB 1.4.3 / Spatial `2f2668d`。以後の通常実行で暗黙のダウンロードはしない。拡張はDuckDB版とプラットフォームに依存する。[公式拡張説明](https://duckdb.org/docs/lts/core_extensions/spatial/overview)。

## 4. 実際に変換したデータセット

全成果物は環境変数（補助的に既存.env）から解決した実rcloneマウントの `$RUINS_DATA_ROOT/processed/phase1a/{vectors,manifests}/` に保存した。ユーザー固有データパスは実装にハードコードしていない。ジョブ専用一時領域を使い、Driveコピー・SHA再読取・rename・公開後再読取を経てmanifestを最後に登録する。既存IDは上書きしない。同一入力・条件・出力SHAの再実行だけを冪等な成功とする。107レイヤーの再生成照合後に加えた単独GMLの副作用保護は、今回の実データ経路（ZIP、GeoJSON、OSM）を変更しない。再生成を行った実装fingerprintは `phase1a_reproducibility.json` に記録する。

N03 2026の神奈川・東京・山梨・静岡、N03 2014神奈川、CODH旧行政区域5件、OSM XML5件、N02、W05の4都県、P32全国と3県別、L03-bの6ファイルを実際に処理した。土地利用は各年5338=640,000行、5339=630,000行を保持した。PBF以外の97レイヤーは全再生成でも出力SHAが一致した（`phase1a_reproduction.json`）。PBFの結果は下の機械集計を参照。OSM roadsはhighwayタグ付きnodeも含む地物数であり、道路区間数や延長ではない。

最終集計: **32ソース / 107レイヤー / 3,913,158格納行 / 120,181,419 bytes（GeoParquetのみ）**。全107レイヤーの独立読戻し検証はPASS、全107レイヤーの独立再生成SHA-256一致はPASS（`phase1a_verification.json`、`phase1a_reproducibility.json`）。

| PBFソース | 対象タグ地物（全域） | 未対応relation（全域） | 参照不足way（全域） | 範囲外 | 出力地物 | 一時容量最大観測bytes |
|---|---:|---:|---:|---:|---:|---:|
| geofabrik_chubu | 3,109,912 | 3,247 | 0 | 3,106,038 | 627 | 1,040,406,789 |
| geofabrik_kanto | 3,257,803 | 6,238 | 0 | 3,247,297 | 4,268 | 1,057,999,455 |


## 5. 生成GeoParquetの一覧

各レイヤーのID・件数・容量・元CRS・保存CRSは `phase1a_layers.md`、入出力SHA・元パス・品質注意は `phase1a_layers.json`、Drive上の完全manifestに記録する。格納行数にはソース間の重複や複数タグによるドメイン重複が含まれ、ユニークな地物総数ではない。

## 6. 件数・容量・CRS

全レイヤーの件数・容量・元CRS・保存CRSは上記機械生成一覧を参照する。1976年の2レイヤーはEPSG:4301保持で解析未準備、その他はEPSG:6677。以下はカタログのグループ別合計。

| 種別 | レイヤー数 | 格納行数 | GeoParquet bytes |
|---|---:|---:|---:|
| admin | 10 | 10,618 | 21,317,301 |
| cultural | 47 | 20,541 | 1,353,695 |
| landuse | 6 | 3,810,000 | 77,243,476 |
| osm | 34 | 8,674 | 2,591,047 |
| railways | 2 | 32,189 | 6,603,549 |
| rivers | 8 | 31,136 | 11,072,351 |

## 7. DuckDB Spatialの実データ検証

`phase1a_sql_validation.json` はPASS。矩形道路検索はSQL 76件 = Shapely 76件、行政区域抽出はSQL 358件 = Shapely 358件。GeoParquet全件数、geometry妥当性、全bbox抽出も検証CLIで一致した。

土地利用は元CRSの異なる1976を含め、空間演算をせず属性だけをSQL集計した。年次別は1976年 1,270,000件、2014年 1,270,000件、2021年 1,270,000件でカタログと一致。分類別の全件数・名称もJSONに収録し、今回の実ファイルではunknown分類は0件だった。

全国P32の実属性P32_002は44都道府県コード。含まれないコードは 13, 29, 44。ファイル名だけで全国47都道府県の完全収録と解釈しない。

以下はXMLとPBFを含む全OSMソースの同一ドメイン内重複。採用順はカタログID順で明示し、重複除去ビューだけに適用する。各正規レイヤーは元ソースの地物を保持する。関東・中部だけの直接比較は `phase1a_pbf_overlap.json` に分けて記録した。

| OSMドメイン | 入力レイヤー | 重複ID | 除去可能な重複行 | タグ差のあるID | geometry差のあるID | 採用後行数 |
|---|---:|---:|---:|---:|---:|---:|
| roads | 7 | 2781 | 3515 | 0 | 0 | 3679 |
| waterways | 7 | 327 | 478 | 0 | 0 | 392 |
| worship | 7 | 17 | 18 | 0 | 0 | 21 |
| historic | 6 | 34 | 35 | 0 | 0 | 39 |
| landuse | 7 | 197 | 278 | 0 | 0 | 219 |

## 8. 実行コマンド

主要な実行（すべて専用Conda環境内）。PBFはソース別ジョブで実行し、個別JSONのlayer_id/SHAを照合して `phase1a_pbf.json`、`phase1a_pbf_reproduction.json` と全107レイヤーの `phase1a_reproducibility.json` を機械生成した:

```bash
git fetch origin main
git switch -c codex/phase1a-gis-foundation origin/main
python -m unittest discover -s tests -v
python scripts/audit_databank.py --mode full --check-all-hashes --json-output reports/phase1a_baseline_audit.json
python -m pip install pyarrow==23.0.1 duckdb==1.4.3 osmium==4.2.0
python -m pip install -e . --no-deps
python -m pip check
python scripts/check_environment.py --output reports/phase1a_environment_check.json
python scripts/phase1a_ingest.py --list
python scripts/phase1a_ingest.py --dry-run --area tsukui
python scripts/phase1a_ingest.py --execute --layers admin,osm --report reports/phase1a_admin_osm.json
python scripts/phase1a_ingest.py --execute --layers railways,rivers,cultural,landuse --report reports/phase1a_kokudo_landuse.json
python scripts/phase1a_ingest.py --execute --layers landuse --source-id mlit_l03_b_2014_5338 --source-id mlit_landuse_2021_5339 --report reports/phase1a_landuse_fixed.json
python scripts/phase1a_ingest.py --execute --report reports/phase1a_reproduction.json
python scripts/phase1a_ingest.py --execute --layers osm --include-pbf --source-id geofabrik_kanto --report reports/phase1a_pbf_kanto.json
python scripts/phase1a_ingest.py --execute --layers osm --include-pbf --source-id geofabrik_chubu --report reports/phase1a_pbf_chubu.json
python scripts/phase1a_ingest.py --execute --layers osm --include-pbf --source-id geofabrik_kanto --report reports/phase1a_pbf_kanto_reproduction.json
python scripts/phase1a_ingest.py --execute --layers osm --include-pbf --source-id geofabrik_chubu --report reports/phase1a_pbf_chubu_reproduction.json
RUINS_RUN_LIVE=1 python -m pytest tests/ -v
python scripts/phase1a_verify.py --report reports/phase1a_verification.json
python scripts/phase1a_sql_verify.py
python scripts/audit_databank.py --mode full --check-all-hashes --json-output reports/phase1a_final_audit.json
```

## 9. テスト結果

自動テストの最終実行は **85 passed、17 subtests passed**。Phase 0の既存テストをすべて含む。`unittest` は70件成功、初期ベースライン37件成功。ログは `phase1a_pytest.log`、`phase1a_unittest.log`、`phase1a_baseline_tests.log`。実データ3統合テストも有効化して実行した。2件の警告はいずれも合成GMLのレイヤー名をGDALが正規化する旨のもの。テスト無効化は行っていない。

Phase 0の65ファイル判定は、完全なmanifest/GeoParquetペアだけを別会計し、従来の65ファイルと53取得台帳の整合性を引き続き検証するよう拡張した。未登録ファイルを一律に無視する変更ではない。派生物の内容・SHA照合は専用検証CLIが担当する。外部データ不要の34新規テストは合成ZIP/Shapefile/GML/XML/PBFを使い、CRS、元属性と日本語、保存読込、件数、SQL、冪等性、未マウント、出力失敗時の原本保護、ZIP危険入力、容量、年次コードを確認した。

大規模PBF初回のPython側全オブジェクト走査は時間がかかったため停止し、一時領域の削除と未公開を確認した。ネイティブ事前フィルタへ変更後、合成XML/PBF回帰テストを実施して再処理した。この停止を変換成功とは計上していない。さらにPBF初回の公開時に、処理条件のtupleがJSON読戻しでlistとなるmanifest比較の不一致を検出した。安全停止・その出力のrollbackを確認し、JSONで表現する条件をlistへ統一した。合成PBFテストを実運用と同じtsukui範囲条件に拡張し、再実行の冪等性も確認した上で実データを再処理した（`phase1a_pbf_failed_attempt.log`、修正後33テスト成功は `phase1a_pbf_fix_tests.log`）。

## 10. ストレージ安全性・原本整合性

真正rclone FUSEマウントを `/proc/mounts` で確認し、通常ディレクトリ、出力配下の別マウント、シンボリックリンクによる逸脱を拒否する。マウント設定は変更していない。原則1GBに対し、PBFでは処理中だけ例外を利用し、25GB以内のジョブ専用領域、空き1GB以上の予約、標準rclone VFS実使用量との合計監視を行った。ジョブ終了時は例外・割込を含め一時ファイルを削除する。カスタムcache-dirの自動検出は未実装。

出力とmanifestには原本SHA-256があり、取得台帳との対応を確認している。原本ハッシュは処理前後、さらに開始・終了時のフル監査で再計算する。取得台帳へderivedイベントは追記しない。原本変更・削除は行っていない。マウント経由のSHA読戻しとリモートupload確認は異なるため、リモート検証結果は機械集計に別記する。

## 11. 未完成機能

本PRは動作するGIS基盤と実データ検証を提供するが、次の残件があり、Phase 1-Aの全機能完了とは報告しない。

- 1976土地利用の正確な測地変換: 正規グリッドの入手・利用条件・適用範囲を別途確認して、新処理版で投影する。現在は元CRS保持の要確認レイヤー。
- OSM relationのmultipolygon等の組立て、type別area解釈の拡張。現状の除外統計を基準にして、対応時は元IDと地物数の変化を検証する。
- 全関東・中部を出力する `--area all` の大規模実処理、実国土GML各スキーマの網羅確認。今回の国土実データはShapefileを優先した。GMLの共通経路は合成統合テストで確認した。
- 正確な大字境界は未取得・未確定。市町村ポリゴンや矩形で代用して確定扱いにしない。
- Parquetの空間covering/bbox行群スキップ、カタログの版切替・マイグレーション、複数ホストの同時書込制御。現状は同一ホスト排他と既存ID不変。
- CODHライセンス台帳の矛盾解消とデータソースID命名の整備は、原台帳を保全した別作業で行う。

## 12. 判明したデータ品質上の問題

1. 基本出力はEPSG:6677、GeoDataFrameのx/y順を使用する。元CRS、原本.prj、明示メタデータ宣言、元WKT・datum名を別途保持した。未定義・不正・非有限・3次元/高さを拒否し、座標値によるCRS推測やballpark変換は行わない。軸逆転は明白な範囲違反を検知するが、両軸が有効範囲に入る誤順序まで自動判別するものではない。
2. 現行EPSGではJGD2011の水平系EPSG:6668/6677がJGD2024と表示される。[国土地理院の説明](https://www.gsi.go.jp/sokuchikijun/datum-main.html)に従い、水平の定義・数値が変わらない名称改定と原本宣言を区別した。高さの変換は対象外。全国P32等をEPSG:6677へ保存しても、全国の距離・面積精度を保証しない。
3. 1976土地利用の内部宣言は `TD / (B, L)`。Tokyo Datum EPSG:4301であり、正確な変換に必要な `tky2jgd.gsb` が環境にない。推測変換を避け、2レイヤーは元CRSのGeoParquetにして `analysis_ready=false` とした。EPSG:6677との空間結合・距離計算は未許可状態で、属性別件数集計のみを行った。全レイヤーの解析CRS統一はこの点で未完了。
4. `mlit_landuse_2021_5339` はIDに2021とあるが実ファイル `L03-b-14_5339.zip`、台帳temporal_coverage、内部メタデータはいずれも2014。2014として出力し、元IDは出典としてそのまま保持した。年次をIDに合わせて偽装していない。
5. 2014土地利用は `.cpg` がなく、DBFの日本語フィールド名 `土地利用種` をGDAL任せにすると破損した。初回は必要属性不在として停止した。未宣言DBF全体の厳格なUTF-8/CP932検査を実装して、正しいCP932で読み直した結果、2ファイルとも成功・再生成一致した。失敗を `phase1a_kokudo_landuse.json` と `phase1a_landuse_retry.json`、修正後を `phase1a_landuse_fixed.json` に残した。
6. 年次別の分類名称は[1976公式表](https://nlftp.mlit.go.jp/ksj/gml/codelist/LandUseCd-77.html)と[2014/2021公式表](https://nlftp.mlit.go.jp/ksj/gml/codelist/LandUseCd-09.html)から採用した。年次間の対応表は推測していない。2014の日本語列名と別年のL03b_002を吸収するが元列は保持する。
7. CODHに埋め込まれた `cc:license` はBY-SA 4.0、一方で取得台帳はBY 4.0と記録している。双方を保持して矛盾を明記した。再配布時は原提供元の適用条件を要確認。
8. N03/CODHは行政界・旧市町村界であり、青野原・青山・鳥屋・寸沢嵐の正確な大字ポリゴンを新たに確定していない。PBFのtsukuiはPhase 0で用いた4矩形の外接矩形との交差選択で、正確な大字抽出でもgeometryの切り詰めでもない。
9. OSMの対象relationはgeometryを組み立てていない。閉じたwayを無条件にPolygon化せず、明示area=yesまたはarea=noでないlanduseだけを面にする。未対応relation、参照不足、範囲外、重複を保存統計に計上する。PBFのrelation件数は範囲判定前の対象タグ付きrelationであり、津久井内の件数を意味しない。ネイティブフィルタ後の件数を全PBFオブジェクト数と呼ばない。
10. OSM place_of_worshipは宗教施設の完全台帳ではなく、historicも廃絶の根拠ではない。P32も神社・寺院の網羅データではない。全国P32の掲載県は実ファイル・属性で確認した値をSQL集計に記録した。

## 13. 次段階への提案

まず独立レビューでCRS例外、原本保護、SQLと再生成の証跡を確認する。候補推定・土地利用変化からの廃墟判定は本実装に含めず、次段階でも別の明示的許可を要する。


## 終了時の機械確認

フル監査はFULL_PASS。取得台帳53件のサイズ・SHA-256が開始時と一致し、Phase 0原本等65ファイルを保全した。派生登録214ファイル、未登録0。リモートrclone checkもexit 0（`phase1a_remote_check.log`）。監視期間の一時ジョブ＋標準VFS最大観測値は6,657,602,909 bytes、tmp空き最小観測値は27,836,370,944 bytes。終了時ジョブディレクトリは0。既存VFSキャッシュは2,463,363,072 bytesで、設定の変更や無断消去は行っていない。観測は30秒間隔で、開始前の全履歴の最大値を意味しない。`phase1a_resources.jsonl`、`phase1a_integrity_summary.json` を参照。
