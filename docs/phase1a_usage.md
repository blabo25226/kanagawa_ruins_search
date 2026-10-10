# Phase 1-A 利用ガイド

2026-10-10のユーザー許可によるGIS基盤。既存データの整備・変換・検索・品質検証に限定し、候補推定・ランキング・実在判定・画像認識・外部公開は行わない。設計の基礎は `gis_architecture_proposal.md`、ストレージは同§8を採用した。

## インストール

新規環境:

```bash
conda env create -f environment.yml
conda activate kanagawa-ruins
python -m pip install -e . --no-deps
```

既存の専用環境では環境を再作成せず、追加依存を導入する:

```bash
conda activate kanagawa-ruins
python -m pip install pyarrow==23.0.1 duckdb==1.4.3 osmium==4.2.0
python -m pip install -e . --no-deps
python -m pip check
```

`RUINS_DATA_ROOT` を実際のDriveデータディレクトリへ設定する。シェル環境変数を優先し、作業ディレクトリの `.env` を補助的に読む。コード内にユーザー固有のパスはない。Ubuntuの `/proc/mounts` から最深のマウントを確認し、通常のローカルディレクトリや別マウントへの誤書き込みを拒否する。マウント設定は変更しない。

## 保存構成

```text
$RUINS_DATA_ROOT/
  raw/                         # 不変、既存取得物のみ
  provenance.jsonl             # Phase 0取得台帳、読み取り専用
  processed/phase1a/
    vectors/<layer_id>.parquet
    manifests/<layer_id>.json  # 入出力SHA、CRS宣言、版、件数、処理条件
```

ローカルはコード・ログ・レポート・テストのみ。ZIP展開、OSM参照解決用ディスクインデックス、Parquetステージングは `tempfile` のジョブ専用領域を使い、例外終了時も削除する。原則1GB、処理中の例外上限25GB。展開前に容量と空きを確認し、処理中にも容量を点検する。標準rcloneキャッシュの実使用量を最大30秒間隔で確認し、観測できた場合はジョブとの合計25GBもガードする。カスタムcache-dirは自動検出しないため運用時に `du -sh ~/.cache/rclone` 等でも確認する（カスタムcache-dirの場合は実設定を参照）。

Driveへの保存は同一ホストの排他ロック下で新規partialへコピーし、SHA-256の再読取一致後にrename、公開後にも再照合する。最後にmanifestを公開する。これはマウント経由のreadback保証であり、rcloneのリモートupload完了を保証するものではない。リモート同期状態は既存rclone運用で確認する。異なるホストからの同時書き込みは運用対象外。

## CLI

```bash
python scripts/phase1a_ingest.py --list
python scripts/phase1a_ingest.py --dry-run --area tsukui
python scripts/phase1a_ingest.py --execute --area tsukui --layers admin,osm,landuse --report reports/phase1a_run.json
python scripts/phase1a_verify.py --report reports/phase1a_verification.json
python scripts/phase1a_sql_verify.py
```

省略時はdry-run。`--layers` は `admin,osm,railways,rivers,cultural,landuse`。`--source-id` は取得台帳の正確なIDを指定でき、繰り返し可。`--include-pbf` は小規模XMLの確認後に指定する:

```bash
python scripts/phase1a_ingest.py --execute --layers osm --include-pbf --area tsukui \
  --source-id geofabrik_kanto --source-id geofabrik_chubu --report reports/phase1a_pbf.json
```

`--area tsukui` はPBFをPhase 0の4区画の外接矩形で抽出する指定。大字境界ではなく、geometryとの交差による選択で、切り詰めは行わない。他のベクトルとXMLは入力の全範囲を保持する。全国・県別資産の出力範囲を津久井だけと解釈しない。`--area all` はPBFの範囲選択を解除する（全域での実データ実行は未検証）。

同一IDの再実行は入力から再生成し、既存成果物とSHA-256が一致した場合だけ `already_present_reproduced` を返す。出力・条件・入力ハッシュが違う場合は既存を上書きせず停止する。破損や台帳未登録の出力も停止する。失敗ソースは個別に記録しCLIは非ゼロ終了する。入力ファイルの形状不正は自動修復せず停止する。

## Python API

```python
from kanagawa_ruins.catalog import list_layers, load_layer

metadata = list_layers()  # 小さなmanifestのみ。GIS全件を読み込まない
admin = load_layer("admin__n03__2026_kanagawa")
roads = load_layer("osm__roads__2026_10_osm_tsukui_core",
                   columns=["osm_type", "osm_id", "highway", "geometry"],
                   bbox=(-65000, -50000, -55000, -40000), limit=1000)
```

名称は実際の対象年次を使う。土地利用の行属性 `source_vintage` は年とメッシュを含む版識別子（例 `2014_5338`）、カタログの `temporal_coverage` は対象年（`2014`）。年次集計SQLは検証済みの先頭4桁で両メッシュを集計する。OSM取得台帳の対象時点は `2026-10` のため、処理日を使って `20261010` と偽装しない。ファイル単位のsource_idや都県・メッシュを含めて衝突を防ぐ。`list_layers()` の結果を正としてIDを選ぶ。

`load_layer` は列選択可能。bboxは**各レイヤーの保存CRSのx/y単位**（通常EPSG:6677のメートル）。bboxまたはlimit指定時はDuckDBで絞ってからGeoDataFrameにする。指定しない場合は選択した列の全件をメモリへ読み込むので、大きいレイヤーはSQLを推奨する。空間インデックス付covering bboxによるParquet行群スキップは未実装。SQLの絞り込みは結果のメモリを減らすがgeometry列の走査は必要。

## DuckDB Spatial

初回だけ公式Spatial拡張をネットワークから導入する。通常の問い合わせはLOADだけで、暗黙のINSTALLは行わない:

```python
from kanagawa_ruins.geo.spatial import spatial_connection, register_layer

with spatial_connection(install=True) as con:  # 初回導入のみ
    print(con.sql("SELECT extension_name, extension_version FROM duckdb_extensions() WHERE extension_name='spatial'").fetchall())

with spatial_connection() as con:
    register_layer(con, "admin__n03__2026_kanagawa")
    print(con.sql('SELECT muni, count(*) FROM "admin__n03__2026_kanagawa" GROUP BY muni').fetchall())
```

DuckDBは必ずインメモリ。メモリ1GB、2 threads、ディスクspill無効のため、大きいクエリは無制限にローカルへ書かず失敗する。更新型DBはDriveに置かない。永続正規データはGeoParquet。実行環境はDuckDB 1.4.3、Spatial `2f2668d`。拡張はDuckDB版・プラットフォームに依存する。検証CLIが実際の拡張版を記録する。

`queries/` にbbox、行政区域による抽出、土地利用分類集計、年次件数集計を保存した。登録したビューをSQLに記載された `layer`, `roads`, `admin`, `landuse` として別名登録し、値はパラメータで渡す。全ビューのCRSを揃える責任は呼出側にある。`register_layer` はEPSG:6677以外を拒否する。

OSMの複数抽出の重複は `register_osm_union(con, layer_ids)` で調べる。同一ドメインのtype/idごとに、指定順で最初のソースを採用した `osm_unique` ビューと重複表を返す。タグ差・geometry差を報告し、欠損属性の補完はしない。道路と土地利用のような異なるドメインは混ぜない。単独ソースの完全同一重複は取り込み時に除去し、内容が矛盾する同一IDはエラー。

DuckDB 1.4ではgeometryのCRSをカタログで別管理する。`ST_Transform` は `always_xy := true` を使用する。PyProjとDuckDBのPROJデータベースは別であり、数値の一致をテストしている。[DuckDB Spatial公式](https://duckdb.org/docs/lts/core_extensions/spatial/overview)、[関数仕様](https://duckdb.org/docs/stable/core_extensions/spatial/functions.html)。

## CRS・品質方針

原本の `.prj`、同梱メタデータのCRS宣言、読み取り時のWKT・測地系名をmanifestに保持する。`.prj` 不在の場合は同梱 `referenceSystemInfo` の一意で既知の宣言だけを採用し、座標値から推測しない。`.cpg` 優先、UTF-8/Shift-JISフォルダの宣言を次に利用し、未宣言DBFは全テキストフィールドをUTF-8、CP932の順で厳格検査する。

解析用の基本はEPSG:6677。地理座標の緯度経度範囲・非有限値・軸順序の明白な逆転・投影逆変換・geometry妥当性を検査する。ただし両軸が有効範囲に収まる誤順序を完全自動判定することはできない。変換は `TransformerGroup(..., always_xy=True, allow_ballpark=False)` の利用可能な変換に限定する。

現行EPSG/PROJではEPSG:6668/6677の名称がJGD2024となる。[国土地理院](https://www.gsi.go.jp/sokuchikijun/datum-main.html)はJGD2011から水平の定義・数値が変わらない名称改定と説明している。原本のJGD2011宣言と現行ライブラリ名を区別して保持する。3次元座標・高さ・垂直CRSは拒否し、標高変換は扱わない。JGD2000との区別も保持する。全国・離島のデータは全件保持するが、EPSG:6677の距離・面積精度を全国で保証しない。計測は対象範囲に適した投影を選ぶこと。

1976年土地利用は同梱メタデータが `TD / (B, L)`（Tokyo Datum、EPSG:4301）。必須 `tky2jgd.gsb` が環境にないため、**元CRSのGeoParquetとして保存し `analysis_ready=false`** とする。推測変換やballpark変換を行わない。このレイヤーのbboxは度単位であり、EPSG:6677レイヤーとの空間結合・距離計算は禁止。正規のグリッドを別途確認・導入した後に新しい処理版で投影する。

OSMはnodeと参照解決できたwayを扱う。閉じたhighwayはLineStringを保持。area=yes、またはarea=noでないlanduseの閉じたwayだけをPolygonとする。他の閉じたwayを自動的に面としない。relationのgeometry組立ては未実装で、対象タグのrelation件数を明示する。参照不足のwayも件数を記録して除外する。宗教施設・historic・P32から現存／廃絶を判断しない。

`roads` はhighwayタグを持つnode（道路関連の点地物）も含む。道路線だけが必要な場合はgeometry型で選択する。件数を道路区間数や道路延長と解釈しない。

土地利用のコード表は `config/landuse_codes.toml`（パッケージ資源への同一実体リンク）。年度別公式表の名称だけを付け、年次間対応は推測しない。未知コードは `unknown`、元コードの欠損はそのまま。[1976公式表](https://nlftp.mlit.go.jp/ksj/gml/codelist/LandUseCd-77.html)、[2014/2021公式表](https://nlftp.mlit.go.jp/ksj/gml/codelist/LandUseCd-09.html)。

## 更新・検証

新しい原本の取得は今回のCLIの責務外。承認されたPhase 0取得手順で新しい資産として登録し、現行のrawを上書きしない。新しい年次・処理方式は一意のレイヤー名を付ける。処理内容を変える場合は処理版とIDを明示的に改版する（既存IDの自動置換や最新版ポインタは未実装）。Phase 0取得台帳にderivedイベントは追記しない。

```bash
python -m unittest discover -s tests -v
python -m pytest tests/ -v
RUINS_RUN_LIVE=1 python -m pytest tests/test_phase1a_live.py -v
python scripts/phase1a_verify.py --report reports/phase1a_verification.json
```

検証CLIは入力・出力SHA、CRS、全batchのgeometry、件数、列、日本語の代表的な破損マーカー、bbox、行ごとのsource_id、DuckDBでの件数・形状・全bbox検索を照合する。任意の文字化けを完全検出できるものではない。真の再現性は再実行でのバイト一致により確認する。`reports/phase1a_environment_export.yml` は実際のCondaインストール状態のexportであり、cross-platform lockではない。既存 `environment.lock.yml` はPhase 0スナップショットのまま保持している。

`phase1a_sql_verify.py` は本リポジトリの実データIDを使う統合検証であり、先に対象ソースを変換しておく。矩形・行政区域抽出をShapelyと照合し、年次件数・OSM重複・P32掲載県を機械集計する。ローカルの `reports/phase1a_sql_validation.json`、`phase1a_layers.json`、`phase1a_layers.md` を生成する。任意の別データバンクにそのまま適用する汎用検証ではない。

原本台帳の再監査は `make phase1a-audit` を使う。既存 `make audit` はPhase 0履歴レポートの再生成用なので、今回の新規検証には使わない。Phase 1-Aの登録済み派生ペアは原本65ファイルとは別会計とし、派生内容のSHA・geometry検査は `phase1a_verify.py` で実行する。
