# Phase 0.3 収集結果レポート：神奈川県全域＋隣接市区町村地理データ一括収集

**プロジェクト**: 神奈川県廃墟調査プロジェクト  
**作成日**: 2026-10-10  
**担当エージェント**: Gemini 3.8 Flash  
**レビュー担当**: GPT-5.6 Sol High  
**フェーズ目標**: 将来的な神奈川県全域の歴史GIS解析に備え、無料で合法的に取得可能な地理データを広域で収集・保存・整合性確認する。  

---

## 1. 実施概要と遵守事項

本フェーズ（Phase 0.3）では、Phase 0.2までに確立した安全なGoogle Driveデータ保存基盤（rcloneマウント検証、ストリーミング直接保存、Zip Slip/Bomb/Symlink多層防御、チェックサム記録）に基づき、**神奈川県全域および隣接18市区町村を網羅する広域地理データの一括収集と境界検証**を実施した。

### 遵守した制約
- **本格解析の完全禁止**: 廃墟候補の探索、位置推定、画像認識、古地図自動位置合わせ、地物消失判定等の本格解析には一切着手していない。
- **データ管理原則**: 生データ（Shapefile, GeoJSON, OSM PBF, PDF等）はすべて Google Drive データバンク（`$RUINS_DATA_ROOT` = `/home/blabo/gdrive/kanagawa_ruins_search_databank/data/`）へ直接保存し、ローカルリポジトリ容量は **1.7 MB**（制限1GB以内）を厳守。
- **合法的取得**: 利用規約に準拠し、認証回避や有料データの不正取得を行わず、無料・公的に公開されているデータのみを取得。

---

## 2. ストレージ現状とデータ照合結果

### 2.1 データバンク全体規模
- **Google Drive内総ファイル数**: **52 ファイル**
- **Google Drive内総容量**: **1,153.35 MB**（約 1.126 GB）
- **ローカルリポジトリ総容量**: **1.7 MB**
- **取得来歴台帳**: `provenance.jsonl`（**40 レコード**、SHA-256および取得日時完全記録）

### 2.2 実ファイル（52件）と来歴台帳（40レコード）の完全照合
ディスク上の実ファイル52件の内訳と台帳の照合結果は以下の通りであり、不整合のない透明なデータ構成を確認した：

1. **正規ダウンロードデータ（40件）**:
   - `provenance.jsonl` の全40レコードと1対1で完全合致（ハッシュ・サイズ確認済）。
2. **来歴台帳原本（1件）**:
   - `provenance.jsonl`
3. **ドキュメント・メタデータ類（7件）**:
   - `literature/literature_review.md`
   - `literature/references.bib`
   - `literature/references.json`
   - `raw/administrative/README.md`
   - `raw/historical_maps/README.md`
   - `raw/osm/README.md`
   - `raw/osm/tsukui_4districts_metadata.json`
4. **初期重複データ（4件）**:
   - `raw/administrative/14151.zip`
   - `raw/administrative/gsi_jusho_midori/14151.zip`
   - `raw/cultural_properties/bunkazai.csv`
   - `raw/cultural_properties/sagamihara_cultural_assets/bunkazai.csv`

> [!NOTE]
> **中断ファイル2件の削除完了**:
> Phase 0.2実行時に通信切断等で生じた一時ファイル断片（`tsukui_aoyama_osm.osm.partial.interrupted_1791557033` および `tsukui_suarashi_osm.osm.partial.interrupted_1791556976`、各9.96MB）は、末尾がタグ途中で欠損している未完了断片であることを確認し、完全版（10.9MB / 11.7MB）が存在することを確認した上でGoogle Drive上から安全に削除完了した。

> [!TIP]
> **初期重複データ4件の整理方針**:
> Phase 0初期に配置された直下ファイル（`raw/administrative/14151.zip`, `raw/cultural_properties/bunkazai.csv`）と、その後の設定統一により配置されたサブディレクトリ付きファイル（`raw/administrative/gsi_jusho_midori/14151.zip`, `raw/cultural_properties/sagamihara_cultural_assets/bunkazai.csv`）は同一内容である。既存スクリプト等の後方互換性を損なわないため即時削除は行わず、正規参照先をサブディレクトリ付きパスとし、直下ファイルを「非推奨・レガシーファイル」と位置づけ、Phase 1移行時に整理・アーカイブする。

---

## 3. Phase 0.3 取得データ一覧

### 3.1 行政区域・水系・広域OSMデータ
| データセットID | データ名 / 提供元 | 保存先（Google Drive） | ファイルサイズ | SHA-256 チェックサム | ライセンス |
|---|---|---|---|---|---|
| `mlit_n03_2026_tokyo` | 国土数値情報 行政区域 2026年 東京都 | `raw/administrative/N03-20260101_13_GML.zip` | 13,153,227 B | `94f10b26256566db970dd74b09d614f059c1e8a432f9244ac9c4add76c32ff16` | 国土数値情報 (CC BY 4.0互換) |
| `mlit_n03_2026_yamanashi` | 国土数値情報 行政区域 2026年 山梨県 | `raw/administrative/N03-20260101_19_GML.zip` | 3,642,283 B | `ecb815857ced4ef4c74795c46baa73c400208b7fa549e9583d564e7394e12ae9` | 国土数値情報 (CC BY 4.0互換) |
| `mlit_n03_2026_shizuoka` | 国土数値情報 行政区域 2026年 静岡県 | `raw/administrative/N03-20260101_22_GML.zip` | 13,592,970 B | `a10ed331f67a75f275c3e3a9ccc9c716a0d6249609b8cf218d7e4254a5a11a0d` | 国土数値情報 (CC BY 4.0互換) |
| `mlit_rivers_tokyo` | 国土数値情報 河川データ W05 東京都 | `raw/rivers/W05-08_13_GML.zip` | 1,406,220 B | `7e1d7907855e4560e72c45cf80469802084272da47b0e980139aa6c3da5c09ff` | 国土数値情報 (CC BY 4.0互換) |
| `mlit_rivers_yamanashi` | 国土数値情報 河川データ W05 山梨県 | `raw/rivers/W05-08_19_GML.zip` | 3,911,147 B | `d73f3fcf9e47dbc526420400a6fd272e25c462cf23e96ac9c3a28c0b78fdc29f` | 国土数値情報 (CC BY 4.0互換) |
| `mlit_rivers_shizuoka` | 国土数値情報 河川データ W05 静岡県 | `raw/rivers/W05-08_22_GML.zip` | 6,786,401 B | `c293f5ff4f183f13e5310fcc9d6beed7625f9c6c581944ab8119adba3710fa73` | 国土数値情報 (CC BY 4.0互換) |
| `geofabrik_kanto` | Geofabrik OpenStreetMap 関東最新PBF | `raw/osm/kanto-latest.osm.pbf` | 517,645,146 B | `d128943f6cebc6bc20c95a62d89ad9dbcde20c9b17747b1d46d338587ba01fad` | OpenStreetMap (ODbL 1.0) |
| `geofabrik_chubu` | Geofabrik OpenStreetMap 中部最新PBF | `raw/osm/chubu-latest.osm.pbf` | 511,655,965 B | `14056311e5086850abe09284b00feec25586222453a94b92c55808677acbe4cd` | OpenStreetMap (ODbL 1.0) |

### 3.2 文化財データの補完と取得（P32仕様調査に基づく対応）
国土交通省の国土数値情報 P32（都道府県指定文化財、平成26年版）を調査した結果、全国一括データ（`P32-14_00_GML.zip`）には全国44道府県のみが収録されており、**東京都(13)・奈良県(29)・大分県(44)の3都県は製品仕様上未収録**であることが判明した。
このため、東京都隣接市区町村（八王子市・町田市・檜原村等）の文化財情報を補完すべく、東京都教育庁の公式オープンデータを取得し、さらに神奈川・山梨・静岡の単独データも取得した：

| データセットID | データ名 / 提供元 | 保存先（Google Drive） | ファイルサイズ | SHA-256 チェックサム | 備考 |
|---|---|---|---|---|---|
| `mlit_cultural_properties_nationwide` | P32 文化財 全国44道府県一括 | `raw/cultural_properties/P32-14_00_GML.zip` | 2,032,153 B | `debc5f00123ab6080a2bce307d14b31f3b4fc1123beb1f231a68a11c259b16d7` | 全国広域照合用（44道府県） |
| `mlit_cultural_properties_kanagawa` | P32 文化財 神奈川県単独 | `raw/cultural_properties/P32-14_14_GML.zip` | 37,598 B | `032139919ca1fe523f8e93997dddffba902e94797b29b7de7c899d8f1c7cf016` | 神奈川県指定文化財 |
| `mlit_cultural_properties_yamanashi` | P32 文化財 山梨県単独 | `raw/cultural_properties/P32-14_19_GML.zip` | 56,165 B | `64a2859c35f61091d7d872a749e4549b5de76f4388b4b2a78167e350b0fc731b` | 山梨県指定文化財 |
| `mlit_cultural_properties_shizuoka` | P32 文化財 静岡県単独 | `raw/cultural_properties/P32-14_22_GML.zip` | 44,694 B | `7a3c26fe954a46a1968f7a8d034d691353e0a3c253701c6548ef1e5015cbd70b` | 静岡県指定文化財 |
| `tokyo_cultural_properties` | 東京都指定史跡データ一覧 CSV | `raw/cultural_properties/130001culturalproperty.csv` | 9,696 B | `be7d9aa6950801dde3cd7448a81052ed839f32bafd408c64b88126b095b9ac83` | 東京都教育庁オープンデータ |

---

## 4. 隣接自治体の幾何学的検証結果（GIS検証レポート）

国土数値情報 N03-2026 の最新行政区域ポリゴンを用い、平面直角座標系第IX系（EPSG:6677）にて厳密な幾何学的交差演算（`shapely` / `geopandas`）を実施した（`scripts/verify_adjacency.py`）。

### 4.1 東京都檜原村の正式追加と18自治体照合
当初の17自治体リストに加え、**東京都西多摩郡檜原村を正式な18番目の隣接自治体として追加**し検証を実施した結果、全18自治体が神奈川県と実境界線（Line Contact）を共有していることが完全立証された：

| No | 自治体名 | 都県 | 共有境界長 (km) | 接する神奈川県内市町村 | 判定 |
|---|---|---|---|---|---|
| 1 | 八王子市 | 東京都 | 17.275 km | 相模原市 | 一致（線共有） |
| 2 | 町田市 | 東京都 | 62.666 km | 相模原市, 川崎市, 横浜市, 大和市 | 一致（線共有） |
| 3 | 多摩市 | 東京都 | 2.354 km | 川崎市 | 一致（線共有） |
| 4 | 稲城市 | 東京都 | 11.935 km | 川崎市 | 一致（線共有） |
| 5 | 調布市 | 東京都 | 3.669 km | 川崎市 | 一致（線共有） |
| 6 | 狛江市 | 東京都 | 3.345 km | 川崎市 | 一致（線共有） |
| 7 | 世田谷区 | 東京都 | 7.300 km | 川崎市 | 一致（線共有） |
| 8 | 大田区 | 東京都 | 16.566 km | 川崎市 | 一致（線共有） |
| 9 | **檜原村** | **東京都** | **3.133 km** | **相模原市（緑区）** | **一致（線共有）** |
| 10 | 上野原市 | 山梨県 | 19.032 km | 相模原市 | 一致（線共有） |
| 11 | 道志村 | 山梨県 | 24.101 km | 相模原市, 山北町 | 一致（線共有） |
| 12 | 山中湖村 | 山梨県 | 6.717 km | 山北町 | 一致（線共有） |
| 13 | 小山町 | 静岡県 | 24.437 km | 山北町, 南足柄市, 箱根町 | 一致（線共有） |
| 14 | 御殿場市 | 静岡県 | 6.501 km | 箱根町 | 一致（線共有） |
| 15 | 裾野市 | 静岡県 | 6.441 km | 箱根町 | 一致（線共有） |
| 16 | 三島市 | 静岡県 | 1.467 km | 箱根町 | 一致（線共有） |
| 17 | 函南町 | 静岡県 | 5.575 km | 箱根町, 湯河原町 | 一致（線共有） |
| 18 | 熱海市 | 静岡県 | 8.047 km | 湯河原町 | 一致（線共有） |

### 4.2 境界検証の総括
- **検証済みCRS**: JGD2011 / 平面直角座標系第IX系（EPSG:6677）
- **対象18自治体の検出率**: **18 / 18 (100%)**
- **リスト外の接触自治体**: **0件**
- **リスト内で未接触の自治体**: **0件**
- **点接触（Point Contact）のみの自治体**: **0件**
- **結論**: 神奈川県に陸上境界で接する外部自治体は上記18自治体で完全に網羅されており、過不足はゼロである。

---

## 5. セキュリティ・信頼性向上策

1. **ZIP展開処理の多層防御 (`safe_extract_zip`)**:
   - `member.file_size` の累積チェックによるZip Bomb防御（デフォルト上限200MB）。
   - `Path.parents` による親ディレクトリ境界の厳密検証によるZip Slip防御。
   - `stat.S_ISLNK` によるシンボリックリンク属性の検出・拒否（サンドボックス脱出防止）。
2. **OSM PBFの低負荷完全性検証**:
   - 500MB超の巨大PBFストリームに対し、先頭ブロック構造（BlobHeader長プレフィックス、`OSMHeader` タイプ、`OsmSchema-V0.6` シグネチャ）をメモリゼロ負荷で高速検査するユニットテストを導入（全17テスト合格）。

---

## 6. 成果物一覧

1. `reports/phase0_3_collection_report.md`（本資料）
2. `reports/phase0_3_coverage_matrix.md`（18自治体対応カバレッジ表、航空写真未取得訂正）
3. `reports/phase0_3_unavailable_sources.md`（未取得・保留データ一覧、航空写真入手手順調査）
4. `reports/phase0_3_adjacency_verification.json`（幾何学的境界検証JSONデータ原本）
5. `scripts/verify_adjacency.py`（幾何学的境界検証スクリプト：TARGET_18対応）
6. `config/sources.toml`（P32単独および東京都文化財データ追加）
7. `reports/data_inventory.md`（全52ファイル最新台帳）
8. `source.md`（最新データ収集状況・書式整形）
