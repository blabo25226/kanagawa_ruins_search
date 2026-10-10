# Phase 0.4.1 データ取得状況・ソース台帳

- 監査実施日時（UTC）: 2026-10-10T05:25:39.966562+00:00
- 生データ正規保存先: `/home/blabo/gdrive/kanagawa_ruins_search_databank/data`
- 監査モード: **FAST**
- 参照した主な利用規約・案内URL:
  - 国土数値情報利用規約: `https://nlftp.mlit.go.jp/ksj/other/kiyaku.html`
  - 東京都オープンデータ利用規約: `https://catalog.data.metro.tokyo.lg.jp/`
  - OpenStreetMap 利用規約 (ODbL): `https://www.openstreetmap.org/copyright`
  - Geofabrik 利用案内: `https://download.geofabrik.de/`
  - 国土地理院コンテンツ利用規約: `https://www.gsi.go.jp/kikakuchousei/kikakuchousei40182.html`
  - 人文学オープンデータ共同利用センター (CODH) 利用規約: `https://geoshape.ex.nii.ac.jp/city/`
  - 神奈川県オープンデータカタログ: `https://catalog.opendata.pref.kanagawa.jp/`
  - 相模原市オープンデータ利用規約: `https://www.city.sagamihara.kanagawa.jp/shisei/toukei/opendata/index.html`
  - 神奈川県立公文書館 刊行物案内: `https://archives.pref.kanagawa.jp/`
  - 国立国会図書館デジタルコレクション 利用規約: `https://www.ndl.go.jp/jp/use/reproduction/index.html`
  - Nature Scientific Reports (CC BY 4.0): `https://www.nature.com/srep/`
  - J-STAGE 利用規約: `https://www.jstage.jst.go.jp/`

---

## 1. 取得済みデータ一覧（Google Drive実ファイル照合・ハッシュ検証済み）

| ソースID | 格納パス (Google Drive相対) | 実ファイルサイズ (bytes) | 形式 | SHA-256 (先頭16桁) | ライセンス・利用条件 | 整合性状態 |
|:---|:---|---:|:---|:---|:---|:---:|
| `gsi_jusho_midori` | `raw/gsi_jusho_midori/14151.zip` | 1,672,520 | ZIP | `a72352712494a1c5` | 政府標準利用規約2.0とe-Govに記載; 取得直前に最新条件を確認 | **OK** |
| `sagamihara_cultural_assets` | `raw/sagamihara_cultural_assets/bunkazai.csv` | 210,799 | CSV | `dec1117a21869988` | 相模原市は原則CC BY 4.0; リソース個別のライセンス欄も確認 | **OK** |
| `mlit_n03_2026_kanagawa` | `raw/administrative/N03-20260101_14_GML.zip` | 5,370,610 | ZIP | `27ab5aa2982fc6fe` | 国土数値情報利用規約（CC BY 4.0互換）; 出典明記要 | **OK** |
| `mlit_n03_2014_kanagawa` | `raw/historical_boundaries/N03-140401_14_GML.zip` | 1,860,243 | ZIP | `b9f236d3512a9b96` | 国土数値情報利用規約（CC BY 4.0互換）; 出典明記要 | **OK** |
| `codh_tsukui_1955` | `raw/historical_boundaries/codh_tsukui_19551001.geojson` | 137,132 | GEOJSON | `d2105725065d8b2f` | CODH 歴史的行政区域データセット（CC BY 4.0） | **OK** |
| `codh_tsukui_2005` | `raw/historical_boundaries/codh_tsukui_20050101.geojson` | 136,875 | GEOJSON | `85b4f3ef11efd936` | CODH 歴史的行政区域データセット（CC BY 4.0） | **OK** |
| `osm_tsukui_core` | `raw/osm/tsukui_core_osm.osm` | 5,834,482 | OSM | `8bea6721aefe13b3` | OpenStreetMap 貢献者（ODbL 1.0） | **OK** |
| `mlit_landuse_2021_5339` | `raw/landuse/L03-b-14_5339-jgd_GML.zip` | 13,314,929 | ZIP | `b72e1446cb2ab067` | 国土数値情報利用規約（CC BY 4.0互換）; 出典明記要 | **OK** |
| `mlit_railways_2023` | `raw/railways/N02-23_GML.zip` | 17,518,918 | ZIP | `e91ecdee90966877` | 国土数値情報利用規約（CC BY 4.0互換）; 出典明記要 | **OK** |
| `mlit_rivers_kanagawa` | `raw/rivers/W05-08_14_GML.zip` | 1,908,537 | ZIP | `8a553d8c3aa3a43d` | 国土数値情報利用規約（CC BY 4.0互換）; 出典明記要 | **OK** |
| `kanagawa_cultural_properties_catalog` | `raw/cultural_properties/kanagawa_bunkazai_mokuroku_r07.pdf` | 5,545,067 | PDF | `b7c5294ec088af04` | 神奈川県オープンデータ（CC BY 4.0準拠） | **OK** |
| `kanagawa_archives_tsukui_catalog` | `literature/catalogs/rekishishiryoushozaimokuroku14-4-1.pdf` | 8,153,399 | PDF | `6c8f05077508427d` | 神奈川県立公文書館 刊行資料; 調査・学術利用 | **OK** |
| `kanagawa_archives_wakayanagi_list` | `literature/catalogs/pdflist_wakayanagi.pdf` | 53,950 | PDF | `e57f983037ed2346` | 神奈川県立公文書館 刊行資料; 調査・学術利用 | **OK** |
| `paper_wood2024_mapreader` | `literature/papers/Wood2024_MapReader.pdf` | 447,699 | PDF | `e6ecce73e73152fa` | JOSS (CC BY 4.0) | **OK** |
| `codh_sagamiko_2005` | `raw/historical_boundaries/codh_sagamiko_20050101.geojson` | 96,324 | GEOJSON | `8bf187d34be07ee3` | CODH 歴史的行政区域データセット（CC BY 4.0） | **OK** |
| `codh_shiroyama_2005` | `raw/historical_boundaries/codh_shiroyama_20050101.geojson` | 51,611 | GEOJSON | `077da437650f0442` | CODH 歴史的行政区域データセット（CC BY 4.0） | **OK** |
| `codh_fujino_2005` | `raw/historical_boundaries/codh_fujino_20050101.geojson` | 52,534 | GEOJSON | `027f60212dd1465a` | CODH 歴史的行政区域データセット（CC BY 4.0） | **OK** |
| `osm_tsukui_toya` | `raw/osm/tsukui_toya_osm.osm` | 6,241,979 | OSM | `b380bc65f6d8a2c8` | OpenStreetMap 貢献者（ODbL 1.0） | **OK** |
| `osm_tsukui_aonohara` | `raw/osm/tsukui_aonohara_osm.osm` | 6,828,635 | OSM | `ed6961c5a73313d5` | OpenStreetMap 貢献者（ODbL 1.0） | **OK** |
| `ndl_shinpen_sagami_vol5` | `literature/historical_documents/Shinpen_Sagami_Fudokiko_Vol5_IIIF_manifest.json` | 190,030 | JSON | `1ecfb5457453b4ca` | 著作権保護期間満了（パブリックドメイン）; NDL IIIF API | **OK** |
| `paper_kanaki2003_abandoned` | `literature/papers/Kanaki2003_AbandonedSettlements.pdf` | 1,606,333 | PDF | `a5bde654b76c2d1b` | 日本建築学会計画系論文集; 学術調査利用 (J-STAGE) | **OK** |
| `paper_tani2017_konjaku` | `literature/papers/Tani2017_KonjakuMap.pdf` | 4,689,607 | PDF | `64a1c2988d014024` | GIS-理論と応用; 学術調査利用 (J-STAGE) | **OK** |
| `paper_fujita2007_shrine_gis` | `literature/papers/Fujita2007_ShrineLocationGIS.pdf` | 2,908,569 | PDF | `c2593cb87354b4a8` | 景観生態学; 学術調査利用 (J-STAGE) | **OK** |
| `paper_oda2015_shrine_merger` | `literature/papers/Oda2015_ShrineMerger.pdf` | 176,791 | PDF | `cef264d5e4df26c1` | 日本地理学会発表要旨集; 学術調査利用 (J-STAGE) | **OK** |
| `osm_tsukui_suarashi` | `raw/osm/tsukui_suarashi_osm.osm` | 11,774,956 | OSM | `753f3a4afea6312a` | OpenStreetMap 貢献者（ODbL 1.0） | **OK** |
| `osm_tsukui_aoyama` | `raw/osm/tsukui_aoyama_osm.osm` | 10,936,667 | OSM | `2cee8ec50206676e` | OpenStreetMap 貢献者（ODbL 1.0） | **OK** |
| `paper_berganzo2023_mounds` | `literature/papers/Berganzo2023_ArchaeologicalMounds.pdf` | 3,943,985 | PDF | `e64eca11c9c77e07` | Nature Scientific Reports (CC BY 4.0) | **OK** |
| `mlit_n03_2026_tokyo` | `raw/administrative/N03-20260101_13_GML.zip` | 13,153,227 | ZIP | `94f10b26256566db` | 国土数値情報利用規約（CC BY 4.0互換）; 出典明記要 | **OK** |
| `mlit_n03_2026_yamanashi` | `raw/administrative/N03-20260101_19_GML.zip` | 3,642,283 | ZIP | `ecb815857ced4ef4` | 国土数値情報利用規約（CC BY 4.0互換）; 出典明記要 | **OK** |
| `mlit_n03_2026_shizuoka` | `raw/administrative/N03-20260101_22_GML.zip` | 13,592,970 | ZIP | `a10ed331f67a75f2` | 国土数値情報利用規約（CC BY 4.0互換）; 出典明記要 | **OK** |
| `mlit_rivers_tokyo` | `raw/rivers/W05-08_13_GML.zip` | 1,406,220 | ZIP | `7e1d7907855e4560` | 国土数値情報利用規約（CC BY 4.0互換）; 出典明記要 | **OK** |
| `mlit_rivers_yamanashi` | `raw/rivers/W05-08_19_GML.zip` | 3,911,147 | ZIP | `d73f3fcf9e47dbc5` | 国土数値情報利用規約（CC BY 4.0互換）; 出典明記要 | **OK** |
| `mlit_rivers_shizuoka` | `raw/rivers/W05-08_22_GML.zip` | 6,786,401 | ZIP | `c293f5ff4f183f13` | 国土数値情報利用規約（CC BY 4.0互換）; 出典明記要 | **OK** |
| `mlit_cultural_properties_nationwide` | `raw/cultural_properties/P32-14_00_GML.zip` | 2,032,153 | ZIP | `debc5f00123ab608` | 国土数値情報利用規約（CC BY 4.0互換）; 出典明記要 | **OK** |
| `geofabrik_kanto` | `raw/osm/kanto-latest.osm.pbf` | 517,645,146 | PBF | `d128943f6cebc6bc` | OpenStreetMap 貢献者（ODbL 1.0）; 出典明記要 | **OK** |
| `geofabrik_chubu` | `raw/osm/chubu-latest.osm.pbf` | 511,655,965 | PBF | `14056311e5086850` | OpenStreetMap 貢献者（ODbL 1.0）; 出典明記要 | **OK** |
| `mlit_cultural_properties_kanagawa` | `raw/cultural_properties/P32-14_14_GML.zip` | 37,598 | ZIP | `032139919ca1fe52` | 国土数値情報利用規約（CC BY 4.0互換） | **OK** |
| `mlit_cultural_properties_yamanashi` | `raw/cultural_properties/P32-14_19_GML.zip` | 56,165 | ZIP | `64a2859c35f61091` | 国土数値情報利用規約（CC BY 4.0互換） | **OK** |
| `mlit_cultural_properties_shizuoka` | `raw/cultural_properties/P32-14_22_GML.zip` | 44,694 | ZIP | `7a3c26fe954a46a1` | 国土数値情報利用規約（CC BY 4.0互換） | **OK** |
| `tokyo_cultural_properties` | `raw/cultural_properties/130001culturalproperty.csv` | 9,696 | CSV | `be7d9aa6950801dd` | 東京都オープンデータ（CC BY 4.0準拠）; P32未収録の東京都分補完 | **OK** |
| `paper_luft2021` | `literature/papers/Luft2021_HistoricalMapGeoreferencing.pdf` | 1,361,395 | PDF | `facca1e1394c0d0e` | - | **OK** |
| `paper_tabayashi2026` | `literature/papers/Tabayashi2026_OldMapGeoreferencingAI.pdf` | 1,083,965 | PDF | `e0cb29ac4caea02f` | - | **OK** |
| `mlit_l03_b_1976_5338` | `raw/landuse/L03-b-76_5338_GML.zip` | 14,630,483 | ZIP | `1071994099b4d79e` | 国土数値情報利用規約（CC BY 4.0互換）; 出典明記要 | **OK** |
| `mlit_l03_b_1976_5339` | `raw/landuse/L03-b-76_5339_GML.zip` | 14,450,493 | ZIP | `b2e5a7210f516b9e` | 国土数値情報利用規約（CC BY 4.0互換）; 出典明記要 | **OK** |
| `mlit_l03_b_2014_5338` | `raw/landuse/L03-b-14_5338-jgd_GML.zip` | 13,398,459 | ZIP | `09e03256f41a9ac6` | 国土数値情報利用規約（CC BY 4.0互換）; 出典明記要 | **OK** |
| `mlit_l03_b_2021_5338` | `raw/landuse/L03-b-21_5338-jgd2011_GML.zip` | 22,476,659 | ZIP | `3f9d82c098eb4693` | 国土数値情報利用規約（CC BY 4.0互換）; 出典明記要 | **OK** |
| `mlit_l03_b_2021_5339` | `raw/landuse/L03-b-21_5339-jgd2011_GML.zip` | 22,386,507 | ZIP | `f6bbebb3fa80cf5f` | 国土数値情報利用規約（CC BY 4.0互換）; 出典明記要 | **OK** |
| `gsi_aerial_photo_catalog_tsukui` | `raw/aerial_photos/metadata/tsukui_aerial_photos_catalog.json` | 59,394 | JSON | `205325245d13387c` | 国土地理院コンテンツ利用規約; 測量法第27条に基づく測量成果閲覧APIより抽出 | **OK** |
| `gsi_aerial_tile_1974_aonohara_1974` | `raw/aerial_photos/sample_ortho_1974/aonohara_1974_z15_29054_12916.jpg` | 20,452 | JPG | `5c8b6e2b80081aa6` | 国土地理院コンテンツ利用規約（CC BY 4.0互換）; 出典明記要 | **OK** |
| `gsi_aerial_tile_1974_aoyama_1974` | `raw/aerial_photos/sample_ortho_1974/aoyama_1974_z15_29058_12912.jpg` | 18,502 | JPG | `025d60d1e3d600a9` | 国土地理院コンテンツ利用規約（CC BY 4.0互換）; 出典明記要 | **OK** |
| `gsi_aerial_tile_1974_toya_1974` | `raw/aerial_photos/sample_ortho_1974/toya_1974_z15_29055_12920.jpg` | 22,088 | JPG | `b347e2a9705f5bbf` | 国土地理院コンテンツ利用規約（CC BY 4.0互換）; 出典明記要 | **OK** |
| `gsi_aerial_tile_1974_suarashi_1974` | `raw/aerial_photos/sample_ortho_1974/suarashi_1974_z15_29054_12906.jpg` | 17,121 | JPG | `6ae487f3296568a6` | 国土地理院コンテンツ利用規約（CC BY 4.0互換）; 出典明記要 | **OK** |
| `sagamihara_buried_cultural_properties_2026` | `raw/cultural_properties/sagamihara_buried_cultural_properties_20260212.pdf` | 110,726 | PDF | `de14000fe289fe57` | 相模原市公式ホームページ著作権規定; 公共情報・出典明記要 | **OK** |

---

## 2. 初期重複ファイル（互換性維持のため残置）

以下のファイルは初期フェーズにおける保存パス互換性維持のため残置されており、正規台帳レコードとは独立して存在を確認済みです（無断削除禁止方針を遵守）。

- `raw/administrative/14151.zip` (正規ターゲット: `raw/gsi_jusho_midori/14151.zip` と同一内容)
- `raw/administrative/gsi_jusho_midori/14151.zip` (正規ターゲット: `raw/gsi_jusho_midori/14151.zip` と同一内容)
- `raw/cultural_properties/bunkazai.csv` (正規ターゲット: `raw/sagamihara_cultural_assets/bunkazai.csv` と同一内容)
- `raw/cultural_properties/sagamihara_cultural_assets/bunkazai.csv` (正規ターゲット: `raw/sagamihara_cultural_assets/bunkazai.csv` と同一内容)

---

## 3. メタデータ・書誌・文書ファイル一覧（Google Drive）

- `literature/bibliography/literature_review.md`
- `literature/bibliography/references.bib`
- `literature/bibliography/references.json`
- `literature/historical_documents/README.md`
- `processed/README.md`
- `raw/historical_maps/README.md`
- `raw/osm/tsukui_4districts_metadata.json`

---

## 4. ストレージ容量と管理状況（正確な実測メトリクス）

- **実ファイル総数**: **65 件**
  - 取得台帳記録ダウンロード実体: **53 件**
  - 互換性残置重複ファイル: **4 件**
  - メタデータ・文献データベース・文書: **7 件**
  - 取得台帳自身 (`provenance.jsonl`): **1 件**
  - 未登録ファイル: **0 件**
- **実ファイル総容量**: **1,279,520,207 Bytes**
  - **MB換算 (10^6 B)**: **1279.52 MB**
  - **MiB換算 (2^20 B)**: **1220.25 MiB (約 1.192 GiB)**
- **サイズ不一致件数**: **0 件**
- **ハッシュ不一致件数**: **0 件**
- **欠損ファイル件数**: **0 件**
- **ローカルリポジトリ容量**: **約 2.2 MB**（1GB制限完全遵守）

