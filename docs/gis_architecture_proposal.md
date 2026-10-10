# GIS 解析基盤 アーキテクチャ提案

- 作成日: 2026-10-10 / 作成: Claude Sonnet 5.5
- ステータス: **設計提案（未実装）**。Phase 0 ゲートにより解析コードは実行していない。実装は GPT レビュー通過後（Phase 1 以降）。
- 凡例: 【事実】= 実機・実ファイルで確認済み、【提案】= 設計判断。

---

## 1. 現状（確認済みの事実）

### 1.1 データバンク

【事実】Google Drive（rclone FUSE マウント）`kanagawa_ruins_search_databank/data/` 総量 約 1.2GB、ファイル 70 個。GitHub には `data/` を含めず、コードと `config/sources.toml` のみ（`.gitignore`）。

| 区分 | 場所（`raw/` 配下） | 形式 | 規模・CRS 等（確認できたもの） |
|---|---|---|---|
| 行政区域（現行） | `administrative/N03-20260101_{13,14,19,22}_GML.zip` | Shapefile+GeoJSON（ZIP） | 神奈川 1,247 地物、EPSG:6668、UTF-8（`.cpg`）、無効ジオメトリ 0 |
| 行政区域（過去） | `historical_boundaries/N03-140401_14_GML.zip`, `codh_*.geojson` | 同上 / GeoJSON | CODH は旧津久井周辺 5 自治体の歴史的行政区域（CRS は取込時に要確認） |
| 住居表示 | `administrative/14151.zip`（相模原市緑区） | Shapefile 想定 | 津久井山間部は未提供 |
| OSM | `osm/kanto-latest.osm.pbf`(518MB), `chubu-latest.osm.pbf`(512MB), `tsukui_*_osm.osm`(5.8〜11.8MB ×5) | PBF / OSM-XML | EPSG:4326。Geofabrik 広域 + Overpass 抽出（旧津久井 5 区画） |
| 文化財（神社・寺院は専用データなし） | `cultural_properties/P32-14_{00,19,22}_GML.zip`, `bunkazai.csv`, PDF | 国土数値情報 P32（都道府県指定文化財）他 | 【事実】カタログ上 P32 は都道府県指定文化財で、寺社の網羅的台帳ではない。**神社・寺院の位置は OSM（`amenity=place_of_worship` 等）が主データ源**になる【提案】 |
| 道路・鉄道・河川 | `railways/N02-23_GML.zip`, `rivers/W05-08_{13,14,19,22}_GML.zip` | Shapefile ZIP | 道路は OSM 由来を想定 |
| 土地利用メッシュ | `landuse/L03-b-{76,14,21}_{5338,5339}…zip` | 国土数値情報 土地利用細分メッシュ（約 100m） | 1976/2014/2021 年、メッシュ 5338・5339 のみ（津久井を含む 2 枚） |
| DEM | （**未取得**） | — | 国土地理院 DEM5/DEM10 は未入手 |
| 歴史地図 | `historical_maps/README.md` のみ | — | **画像データなし**（取得条件の整理のみ） |
| 航空写真 | `aerial_photos/metadata/*.json`（カタログ 42 件）, `sample_ortho_1974/*.jpg` ×4 | JSON / JPEG | 【事実】JPEG は 256×256・3 バンド・**ジオリファレンスなし**（`rasterio` で CRS=None、アフィン=恒等）。ファイル名の `z15_{x}_{y}` から XYZ タイル位置を復元する設計が必要 |

【事実】Python 環境: `kanagawa-ruins`（Python 3.12.15, GeoPandas 1.2.0, Shapely 2.2.0, Rasterio 1.5.2, PyProj 3.8.0, GDAL 3.13.3, pyogrio, OpenCV 5.0.0）。DuckDB / PyOsmium / PyArrow は未導入。

### 1.2 既存コードの制約（詳細は `reports/claude_independent_code_review.md`）

- provenance の正本が 2 つ（Drive 53 行 / ローカル 42 行）でスキーマ混在。
- CRS 変換先は EPSG:6677（JGD2011 / 平面直角 IX 系）と README に記載。
- Drive の FUSE は 500MB 級のファイルを何度も読むと遅い（実測: `unittest` 17 件で 48.6 秒。ほぼ Drive 上の PBF ヘッダ確認）。解析は**ローカルのキャッシュ領域**で行う前提にする。

---

## 2. 要求と設計原則【提案】

1. **再現性**: 原データ（不変）→ 派生データ（再生成可能）を厳密に分離。派生物はスクリプトとハッシュから常に再生成でき、Git に入れない。
2. **Drive は原本（`raw/`）の正規保存先で、原本は不変・読み取り専用**。ローカルは**ジョブ単位の一時作業領域のみ（原則 1GB 以内、処理後に削除）**。派生物の正規保存先は README 記載どおり Drive 側 `processed/`。（改訂 2026-10-10: 当初案の「ローカル `data/cache/` に恒久キャッシュ」は既存方針と矛盾するため撤回。詳細は §8）
3. **CRS を 1 か所で管理**: 保存は EPSG:6668（JGD2011 地理）または元 CRS のまま、**計算（距離・面積・バッファ）は EPSG:6677**。変換は取り込み層のみ。
4. **小さく始める**: 現データは合計 約 1.2GB、ベクタは数十万〜数百万地物規模。単一マシンで完結する構成を採る。
5. **拡張可能な型契約**: すべての空間レイヤーに `layer_id`, `source_id`（`sources.toml`）, `crs`, `acquired_at`, `sha256` を紐付ける（レイヤーカタログ）。

---

## 3. 技術比較

評価軸: 容量 / 速度 / 再現性 / 拡張性 / 運用コスト（学習・保守）。◎良 ○可 △難 ×不適。

| 技術 | 役割 | 容量 | 速度 | 再現性 | 拡張性 | 運用コスト | 本プロジェクトでの位置づけ |
|---|---|---|---|---|---|---|---|
| **GeoPandas** (+pyogrio) | ベクタの読込・結合・投影・簡易解析 | ○（数百万地物まで。メモリ依存） | ○（pyogrio で高速化。Shapely 2 でベクトル化済み） | ◎ | ◎ | ◎ | **中核**。小〜中規模の解析・可視化。導入済み |
| **Shapely 2** | ジオメトリ演算（STRtree, make_valid, buffer…） | ◎ | ◎（C 実装・ベクトル化） | ◎ | ◎ | ◎ | GeoPandas に内包。直接利用は座標・誤差計算 |
| **Rasterio** | ラスタ I/O、warp、window 読み、COG | ◎（ウィンドウ読み） | ○ | ◎ | ◎ | ○ | **中核（ラスタ）**。DEM・メッシュ・古地図・航空写真 |
| **GDAL / OGR**（CLI + osgeo） | 形式変換、`gdalwarp`、GCP 幾何補正、COG 生成、VRT | ◎ | ◎ | ◎（コマンド列を記録） | ◎ | △（API が低レベル） | **補助だが必須**。Rasterio/GeoPandas の下層。GCP 幾何補正・COG 化は CLI で記録 |
| **PyOsmium** | PBF のストリーム読み（ハンドラ）、範囲・タグ抽出、`osmium extract` | ◎（PBF 500MB を低メモリで） | ◎ | ◎ | ○ | ○ | **OSM 取込の標準**。現状 `ElementTree` 全読み込みは PBF に不向き |
| **DuckDB Spatial** | 組込み分析 DB、SQL での空間結合、Parquet 直読み | ◎（ディスク超過分も処理） | ◎（列指向・並列。空間結合は R-tree/最近傍） | ○（拡張のバージョン固定が必要） | ○ | ◎（サーバ不要、単一ファイル） | **推奨のクエリ層**。広域の結合・集計・カタログ検索 |
| **GeoParquet** | 派生データの保存形式 | ◎（圧縮・列指向、Shapefile の 2GB/列名10文字制限なし） | ◎ | ◎（スキーマ・CRS メタ内蔵、`sha256` 容易） | ◎ | ◎ | **推奨の派生データ形式**。要 `pyarrow`（導入） |
| **PostGIS** | サーバ型空間 DB | ◎ | ◎（GiST 索引） | △（DB 状態は dump 管理が必要） | ◎（多ユーザ・WMS 提供） | × （サーバ運用・認証・バックアップ） | **現時点では不要**。複数人同時編集・Web 配信が必要になった時点で再評価 |

### 3.1 要点（判断理由）

- **PostGIS を今は採用しない**理由: 単一利用者・約 1.2GB・バッチ解析中心で、サーバ運用コスト（インストール・接続情報の管理・バックアップ）が便益を上回る。Phase 0 は「VS Code ターミナルだけで扱える」環境が要件（`firstinstruction.md`）。DuckDB + GeoParquet で同等の SQL 空間結合ができる。
- **Shapefile を派生データに使わない**: 列名 10 文字・文字コード問題（本レビュー F1）・2GB 上限。派生は GeoParquet、人が QGIS で見る用途のみ GeoPackage（`.gpkg`）。
- **OSM は GeoPandas で直読みしない**: 500MB 級 PBF は `pyosmium`（または `osmium` CLI）で関心タグ（`amenity=place_of_worship`, `religion`, `historic`, `highway`, `waterway`, `landuse`, `ruins:*`, `abandoned:*` 等）と bbox で抽出してから GeoParquet 化する。

---

## 4. 推奨構成【提案】

**「GDAL/Rasterio（ラスタ）+ pyosmium（OSM）+ GeoPandas（整形）→ GeoParquet（保存）→ DuckDB Spatial（クエリ）」**。PostGIS は将来の選択肢として保留。

```
Google Drive (read-only, rclone)          ローカル一時作業領域（≤1GB・ジョブ後に削除）
┌──────────────────────────────┐         ┌──────────────────────────────────────┐
│ raw/ (不変)  provenance.jsonl │ ──copy──▶│ 一時 tmp（ZIP 展開等のみ。※改訂 §8）   │
└──────────────────────────────┘  +verify └───────────────┬──────────────────────┘
                                                          │ ingest（種別ごと）
                                                          ▼
                                      ┌─────────────────────────────────────────┐
                                      │ data/processed/ (再生成可能)            │
                                      │  vector/*.parquet  (GeoParquet, 6668/6677)│
                                      │  raster/*.tif      (COG, 軽量オーバビュー)  │
                                      │  catalog.duckdb    (レイヤーカタログ+VIEW)│
                                      └───────────────┬─────────────────────────┘
                                                      │ DuckDB Spatial / GeoPandas
                                                      ▼
                                      reports/, 小規模GeoJSON/PNG（GitHub可）
```

GitHub に入れるもの: コード、`config/*.toml`、設計文書、**数 KB の検証用ミニマルなサンプル（合成データ）**、レポート。入れないもの: 原データ、PBF、ZIP、COG、Parquet、DuckDB ファイル、古地図・航空写真画像（`.gitignore` 済み。`*.parquet`/`*.duckdb`/`*.tif` の追加を提案）。

### 4.1 ディレクトリ・モジュール案

```
src/kanagawa_ruins/                 # 新規パッケージ（pyproject.toml 追加）
  config.py          # RUINS_DATA_ROOT, キャッシュ/出力パス, CRS 定数
  storage/
    drive.py         # 既存 storage_utils.py を移設: マウント検証, 読取専用ヘルパ
    provenance.py    # スキーマ v1, append-only, verify(full/fast)
    scratch.py       # ジョブ単位の一時ディレクトリ（≤1GB 監視・終了時削除）。恒久キャッシュは作らない（§8）
  catalog/
    layers.py        # LayerSpec(layer_id, source_id, kind, crs, path, sha256, bbox, license)
    sources.py       # sources.toml のロードと静的検査
  ingest/
    admin.py         # N03 / CODH → GeoParquet（.cpg 優先の文字コード処理）
    osm.py           # pyosmium: PBF→タグ別 GeoParquet（寺社, 道路, 水系, 土地利用, 歴史）
    kokudo.py        # N02/W05/P32/L03 の共通ローダ（GML/Shapefile）
    landuse_mesh.py  # L03 メッシュ → ポリゴン GeoParquet + 年次比較用コード表
    dem.py           # DEM(GSI) → COG, hillshade/slope は都度計算
    raster.py        # 画像 + ジオリファレンス → COG（画像解析設計 §3 参照）
  geo/
    crs.py           # to_analysis(gdf)=EPSG:6677, to_storage(gdf)=EPSG:6668
    validate.py      # make_valid, 空/無効/重複ジオメトリ検査, bbox, CRS 検査
    spatial.py       # 最近傍・バッファ・結合の薄いラッパ（STRtree/DuckDB 切替）
  qa/
    verify.py        # SHA-256 再計算, 形式別完全性（osmium fileinfo, GDAL decode）
    report.py        # 検証結果から動的にレポート生成（結論は結果から導出）
scripts/              # 既存 CLI は維持し、新規は薄いエントリのみ
tests/                # 合成データ（数 KB）でのユニット + marker 付き統合テスト
```

### 4.2 データ層の規約

- **レイヤー命名**: `{domain}__{source}__{vintage}`（例 `admin__n03__2026`, `osm__worship__20261010`, `landuse__l03__2021`）。
- **座標系**: Parquet は元の測地系を保持（N03=6668, OSM=4326）。解析ビュー `v_*_6677` を DuckDB に用意して距離・面積はこちらで計算。
- **属性**: 日本語列名はそのまま保持しつつ、解析で使う列は ASCII の別名列（`pref`, `muni`, `muni_code`）を追加。
- **GeoParquet メタデータ**: `geo` キーに CRS・エンコーディング、さらに独自キー（`provenance_sha256`, `source_id`, `built_by`, `built_at`）を Parquet の key-value に格納。
- **ジオメトリ品質**: 取り込み時に `shapely.make_valid` を適用し、修正件数をログ化（N03 神奈川は無効 0 件を確認済み。他は未確認）。
- **メッシュ土地利用**: 1976/2014/2021 のコード体系が年次で異なる（L03-b の年次差）。**コード対応表を明示的に持つ**（`config/landuse_codes.toml`）。

### 4.3 DuckDB 利用方針

- 解析クエリ用の読取専用 DB。`INSTALL spatial; LOAD spatial;` は拡張のバージョンを環境ファイルで固定（再現性）。
- 例: 「寺社（OSM）から最近傍の道路・河川への距離」「旧津久井 4 地区の大字ポリゴン内に含まれる神社点数」を SQL で記述し、クエリ自体を `queries/*.sql` として Git 管理。
- 注意【提案上の留意】: DuckDB Spatial は PROJ 変換や GEOS 関数の網羅性が GeoPandas より限定的。複雑な幾何演算は Shapely、広域結合・集計は DuckDB、と使い分ける。

### 4.4 ラスタの扱い

- DEM・古地図・航空写真は **COG（Cloud Optimized GeoTIFF）+ オーバビュー**へ正規化し、`rasterio` のウィンドウ読みで処理。
- 変換は `gdal_translate -of COG -co COMPRESS=DEFLATE`、再投影は `gdalwarp -t_srs EPSG:6677 -r bilinear`（コマンド全文を provenance の `processing` イベントに記録）。
- 現時点の航空写真 JPEG（256px タイル）は **XYZ タイル座標からアフィン変換を算出**して初めて GIS データになる（画像解析設計 §3.1）。

### 4.5 再現性

1. `environment.yml` に `pyarrow`, `duckdb`, `osmium`（pyosmium）を追加し、`conda-lock` 等で固定（現行 `environment.lock.yml` は再生成を提案）。
2. すべての派生物にビルドメタ（入力 SHA-256 の集合、コミットハッシュ、依存バージョン）を付与。
3. `make rebuild-processed` が `catalog.duckdb` まで決定的に再生成できること（`ORDER BY` を明示し、並列書き込みの順序依存を避ける）。
4. `provenance.jsonl` は単一正本・追記専用・スキーマ固定（レビュー提案 1）。

### 4.6 想定容量・性能（概算・未測定）

| 項目 | 原データ | 派生（概算） | 備考 |
|---|---|---|---|
| OSM（関東+中部 PBF） | 約 1.0GB | 絞り込み後 数十〜数百 MB（Parquet） | タグ・bbox（神奈川+周辺）で抽出。**未測定の推定** |
| N03/W05/N02/P32 | 約 80MB | 〜100MB | |
| L03 メッシュ（3 年次×2 枚） | 約 120MB | 〜200MB | |
| DEM（5m, 神奈川+周辺） | 未取得 | COG 数百 MB 規模（推定） | 取得時に確認 |
| 古地図・航空写真 | 未取得 | 画像は数 GB 規模になり得る | Drive 保管（COG/オーバビュー含む）。ローカルは一時のみ（§8） |

~~ローカルのキャッシュ領域は 10〜20GB を見込む（推定）。~~ **撤回**: 根拠のない未測定の数字で、既存方針（ローカル原則 1GB 以内）と矛盾していた。改訂方針は §8。

---

## 5. 段階的ロードマップ【提案】

| 段階 | 内容 | 前提 |
|---|---|---|
| 5-A（Phase 0 内可） | provenance 正本化、`expected_sha256`、検証強化、テスト追加（レビュー提案 1〜8） | Gemini の 0.4.1 完了後 |
| 5-B（Phase 1 前半） | `ingest/admin, osm, kokudo`、GeoParquet + `catalog.duckdb`、CRS 方針の実装 | GPT レビュー通過 |
| 5-C | `ingest/dem, landuse_mesh`、DEM 取得（国土地理院、規約確認） | 取得承認 |
| 5-D | `raster.py`: 航空写真タグ→ジオリファレンス、古地図取込（画像設計） | 画像データ確保 |
| 5-E | PostGIS 再評価（多人数・配信が必要になれば） | 要件発生時 |

## 6. provenance v1 スキーマ案

```json
{
  "schema_version": 1,
  "event": "downloaded | verified | copied | moved | derived | superseded",
  "ts_utc": "2026-10-10T12:34:56Z",
  "source_id": "mlit_n03_2026_kanagawa",
  "path": "raw/administrative/N03-20260101_14_GML.zip",
  "sha256": "…", "bytes": 5370610,
  "format": "zip",
  "origin_url": "https://…", "license_url": "…", "license_note": "…",
  "from_path": null, "tool": {"name": "fetch_sources.py", "git": "<commit>"},
  "inputs": [{"path": "…", "sha256": "…"}], "params": {"cmd": "gdalwarp …"}
}
```
`derived` イベントで入力 SHA-256 と実行コマンドを記録し、「どの原データ・どのコードから作られたか」を追跡できるようにする。

## 7. リスクと未解決事項

- ライセンス: OSM（ODbL: 派生データベースの帰属・共有義務）、国土数値情報、国土地理院（測量法第 29 条等）の再配布条件は用途（公開時）で再確認が必要。本提案は内部解析を想定。
- DuckDB Spatial の拡張・GeoParquet のバージョンは変化が速い。バージョンを固定し、更新時にゴールデンデータで回帰テスト。
- N03 は市区町村単位の同名・境界変更に注意（過去の N03-140401 と現行 2026 は別レイヤーとして扱う）。
- DEM・歴史地図は未取得。取得手続きの有無により工程が変わる。

## 8. ローカルキャッシュとストレージ方針の整合性（2026-10-10 改訂）

### 8.1 確認済みの事実（`origin/main` @ `96707a4`）

- `README.md`「ストレージ構成」: ローカルは「原則 **1GB 以内**」。Drive データバンクは「古地図、航空写真、標高、地理空間データ、歴史資料、GIS 解析用大容量ファイル、**中間生成物**」の保存先で、正規保存先は Drive 側 `data/`（`raw/`, `processed/`, `provenance.jsonl`）。
- `agent/rules/10-source-legality.md` 7〜8: 生データの正規保存先は Drive、「ローカル PC に大容量データを保存しない。一時データは原則 1GB 以内、処理後に不要ファイルを残さない」。
- 実測: Drive の現データは 65 ファイル / 1,279,520,207 B（約 1.19GiB、Gemini の 0.4.1 監査値。私の再計算でも provenance の 53 件は全件一致）。ローカル SSD は 233GB 中 73GB 空き（容量の問題ではなく**方針**の問題）。
- 実測: rclone は `--vfs-cache-mode full --vfs-cache-max-size 10G` で動作している（`ps` で確認）。つまり**Drive 読み取りは既に最大 10GB の透過的ローカルキャッシュを経由**しており、プロジェクト管理外のホームディレクトリ配下に置かれる。

### 8.2 判定

当初案（§2-2 の `data/cache/` に 10〜20GB を恒久配置）は、README と Rule 10-8 の **1GB 制限・処理後削除**に**違反する**。また「中間生成物は Drive」という README とも逆向きだった。10〜20GB という数字は未測定の推定で、根拠が弱い。**撤回する。**

### 8.3 改訂方針【提案】

| 用途 | 置き場所 | 容量方針 |
|---|---|---|
| 原データ | Drive `raw/`（不変） | 既存どおり |
| 大判ラスタ（COG）・Parquet の読み取り | **Drive から直接**読む。rclone VFS の透過キャッシュ（既存 10GB 上限）に任せる | COG のウィンドウ読み・Parquet のカラム/行グループ読みは部分読みに向く。プロジェクト側で追加キャッシュを作らない |
| ZIP 展開・PBF 抽出などの一時物 | ローカル `tempfile` のジョブ単位ディレクトリ | **≤1GB・終了時削除**（`validate_databank.py` が既にこの方式） |
| 派生物（GeoParquet / COG / `catalog` 用 Parquet） | Drive `processed/`（README 準拠） | 書き込みは**ユーザーが明示承認した処理のみ**（本セッションの私は Drive 書き込み不可）。原子的書き込み（`.partial`→rename）と provenance の `derived` イベント必須 |
| DuckDB データベース | **永続 `.duckdb` を FUSE 上に置かない**（単一ライターで FUSE 上のロック・fsync 挙動が不確実。rclone VFS の write-back 挙動は未検証）。Parquet を正とし、DuckDB は起動時に VIEW を張るインメモリ/一時 DB にする | 一時 DB は 1GB 以内 |
| 一時物が 1GB を超えるジョブ（DEM モザイク、高解像度古地図の幾何補正など） | ローカル一時領域 | **ユーザー決定（2026-10-10）: 処理中の一時的な 1GB 超過は可。条件は、(1) 最終成果物が Drive に保存され、(2) 終了時にローカルが 1GB 以内へ戻ること。** 運用ガード【提案】: ジョブ専用の一時ディレクトリのみ使う／終了時（異常終了含む）に削除し、削除後のローカル使用量をログに記録／Drive への書き込み後に SHA-256 を検証してから削除／ディスク空きに上限（暫定 25GB。決定済み）を設ける |

### 8.4 影響と未確認事項

- 影響: `src/…/storage/cache.py`（Drive→ローカルコピー）は廃止し `scratch.py`（一時領域の容量監視と掃除）に置換。§4.1/§4.2 のうち「ローカル `data/processed/`」前提の記述は「Drive `processed/`」と読み替える。
- 未確認: (a) FUSE 越しに Parquet/COG を部分読みしたときの実測性能（500MB 級 PBF でヘッダ検査に数十秒かかった事実から、ランダムアクセスは遅い可能性）。実測してから「直接読み」か「ジョブ単位の一時コピー（承認付き例外）」かを決める。(b) PBF→GeoParquet 抽出の出力サイズ（未測定）。(c) DuckDB の `spatial` 拡張は初回に拡張ファイルをダウンロードする（ネットワーク取得が発生）。許可・固定の扱いはユーザー判断。
- 決定済み（ユーザー, 2026-10-10）: 恒久的な 1GB 制限は維持し、処理中の一時的な超過のみ許可する（上表）。README / Rule 10-8 の文言は変更しない。「原則 1GB 以内」の例外として、必要なら注記を追加するかはユーザー判断。
- 決定済み（ユーザー, 2026-10-10）: 一時領域の絶対上限は**暫定 25GB**（見直し可）。ジョブ開始時に空き容量を確認し、上限到達前に中断・掃除する。
