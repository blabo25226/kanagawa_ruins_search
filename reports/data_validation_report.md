# Phase 0.2 データ品質・整合性検証レポート

- 検証実施日時: 2026-10-09 23:50 JST
- 検証対象ストレージ: Google Drive `/home/blabo/gdrive/kanagawa_ruins_search_databank/data`

---

## 1. ファイル整合性・ハッシュ検証結果一覧

| ファイルパス (相対) | 種別 | サイズ (bytes) | SHA-256 (先頭12桁) | 整合性検証結果 | CRS / 空間仕様 | レコード数 |
|:---|:---|---:|:---|:---|:---|---:|
| `literature/bibliography/literature_review.md` | .MD | 3,865 | `e8d907aacaad` | OK | - | - |
| `literature/bibliography/references.bib` | .BIB | 5,065 | `2005d8e0ed83` | OK | - | - |
| `literature/bibliography/references.json` | .JSON | 6,654 | `87f460d129d3` | OK | - | Items:12 |
| `literature/catalogs/pdflist_wakayanagi.pdf` | .PDF | 53,950 | `e57f983037ed` | Valid PDF | - | - |
| `literature/catalogs/rekishishiryoushozaimokuroku14-4-1.pdf` | .PDF | 8,153,399 | `6c8f05077508` | Valid PDF | - | - |
| `literature/historical_documents/README.md` | .MD | 479 | `9044b15cb004` | OK | - | - |
| `literature/historical_documents/Shinpen_Sagami_Fudokiko_Vol5_IIIF_manifest.json` | .JSON | 190,030 | `1ecfb5457453` | OK | - | Keys:11 |
| `literature/papers/Berganzo2023_ArchaeologicalMounds.pdf` | .PDF | 3,943,985 | `e64eca11c9c7` | Valid PDF | - | - |
| `literature/papers/Fujita2007_ShrineLocationGIS.pdf` | .PDF | 2,908,569 | `c2593cb87354` | Valid PDF | - | - |
| `literature/papers/Kanaki2003_AbandonedSettlements.pdf` | .PDF | 1,606,333 | `a5bde654b76c` | Valid PDF | - | - |
| `literature/papers/Oda2015_ShrineMerger.pdf` | .PDF | 176,791 | `cef264d5e4df` | Valid PDF | - | - |
| `literature/papers/Tani2017_KonjakuMap.pdf` | .PDF | 4,689,607 | `64a1c2988d01` | Valid PDF | - | - |
| `literature/papers/Wood2024_MapReader.pdf` | .PDF | 447,699 | `e6ecce73e731` | Valid PDF | - | - |
| `processed/README.md` | .MD | 390 | `aebc704e5e25` | OK | - | - |
| `provenance.jsonl` | .JSONL | 16,642 | `8bd9ff19dd0b` | OK | - | - |
| `raw/administrative/14151.zip` | .ZIP | 1,672,520 | `a72352712494` | OK | EPSG:6668 | 30420 |
| `raw/administrative/N03-20260101_14_GML.zip` | .ZIP | 5,370,610 | `27ab5aa2982f` | OK | EPSG:6668 | 1247 |
| `raw/administrative/gsi_jusho_midori/14151.zip` | .ZIP | 1,672,520 | `a72352712494` | OK | EPSG:6668 | 30420 |
| `raw/cultural_properties/bunkazai.csv` | .CSV | 210,799 | `dec1117a2186` | OK | - | CSV parsed |
| `raw/cultural_properties/kanagawa_bunkazai_mokuroku_r07.pdf` | .PDF | 5,545,067 | `b7c5294ec088` | Valid PDF | - | - |
| `raw/cultural_properties/sagamihara_cultural_assets/bunkazai.csv` | .CSV | 210,799 | `dec1117a2186` | OK | - | CSV parsed |
| `raw/gsi_jusho_midori/14151.zip` | .ZIP | 1,672,520 | `a72352712494` | OK | EPSG:6668 | 30420 |
| `raw/historical_boundaries/N03-140401_14_GML.zip` | .ZIP | 1,860,243 | `b9f236d3512a` | OK | EPSG:4612 | 606 |
| `raw/historical_boundaries/codh_fujino_20050101.geojson` | .GEOJSON | 52,534 | `027f60212dd1` | OK | EPSG:4326 | 1 |
| `raw/historical_boundaries/codh_sagamiko_20050101.geojson` | .GEOJSON | 96,324 | `8bf187d34be0` | OK | EPSG:4326 | 1 |
| `raw/historical_boundaries/codh_shiroyama_20050101.geojson` | .GEOJSON | 51,611 | `077da437650f` | OK | EPSG:4326 | 1 |
| `raw/historical_boundaries/codh_tsukui_19551001.geojson` | .GEOJSON | 137,132 | `d2105725065d` | OK | EPSG:4326 | 1 |
| `raw/historical_boundaries/codh_tsukui_20050101.geojson` | .GEOJSON | 136,875 | `85b4f3ef11ef` | OK | EPSG:4326 | 1 |
| `raw/historical_maps/README.md` | .MD | 774 | `46ea40fdccb6` | OK | - | - |
| `raw/landuse/L03-b-14_5339-jgd_GML.zip` | .ZIP | 13,314,929 | `b72e1446cb2a` | OK | EPSG:4612 | 630000 |
| `raw/osm/tsukui_4districts_metadata.json` | .JSON | 3,075 | `b5cd347a34cf` | OK | - | Keys:4 |
| `raw/osm/tsukui_aonohara_osm.osm` | .OSM | 6,828,635 | `ed6961c5a733` | OK | EPSG:4326 (WGS84) | Nodes:29698, Ways:2887 |
| `raw/osm/tsukui_aoyama_osm.osm` | .OSM | 10,936,667 | `2cee8ec50206` | OK | EPSG:4326 (WGS84) | Nodes:47098, Ways:6514 |
| `raw/osm/tsukui_core_osm.osm` | .OSM | 5,834,482 | `8bea6721aefe` | OK | EPSG:4326 (WGS84) | Nodes:25052, Ways:3212 |
| `raw/osm/tsukui_suarashi_osm.osm` | .OSM | 11,774,956 | `753f3a4afea6` | OK | EPSG:4326 (WGS84) | Nodes:48512, Ways:6899 |
| `raw/osm/tsukui_toya_osm.osm` | .OSM | 6,241,979 | `b380bc65f6d8` | OK | EPSG:4326 (WGS84) | Nodes:27354, Ways:2583 |
| `raw/railways/N02-23_GML.zip` | .ZIP | 17,518,918 | `e91ecdee9096` | OK | EPSG:4326 | 21949 |
| `raw/rivers/W05-08_14_GML.zip` | .ZIP | 1,908,537 | `8a553d8c3aa3` | OK | None | 2439 |
| `raw/sagamihara_cultural_assets/bunkazai.csv` | .CSV | 210,799 | `dec1117a2186` | OK | - | CSV parsed |

---

## 2. 空間データ（GIS）の詳細検証結果

### `raw/administrative/14151.zip`
- **種別**: ZIP-Spatial
- **CRS（測地系）**: `EPSG:6668`
- **レコード件数**: 30,420
- **外接矩形 (Bounds)**: `Lon: [139.28204, 139.36137], Lat: [35.58019, 35.60639]`
- **欠損ジオメトリ数**: 0
- **属性カラム一覧**: `city_code, jusho1, jusho2, jusho3, jcode1, jcode2, lon, lat`...

### `raw/administrative/N03-20260101_14_GML.zip`
- **種別**: ZIP-Spatial
- **CRS（測地系）**: `EPSG:6668`
- **レコード件数**: 1,247
- **外接矩形 (Bounds)**: `Lon: [138.91577, 139.83584], Lat: [35.12849, 35.6729]`
- **欠損ジオメトリ数**: 0
- **属性カラム一覧**: `N03_001, N03_002, N03_003, N03_004, N03_005, N03_007, geometry`

### `raw/administrative/gsi_jusho_midori/14151.zip`
- **種別**: ZIP-Spatial
- **CRS（測地系）**: `EPSG:6668`
- **レコード件数**: 30,420
- **外接矩形 (Bounds)**: `Lon: [139.28204, 139.36137], Lat: [35.58019, 35.60639]`
- **欠損ジオメトリ数**: 0
- **属性カラム一覧**: `city_code, jusho1, jusho2, jusho3, jcode1, jcode2, lon, lat`...

### `raw/gsi_jusho_midori/14151.zip`
- **種別**: ZIP-Spatial
- **CRS（測地系）**: `EPSG:6668`
- **レコード件数**: 30,420
- **外接矩形 (Bounds)**: `Lon: [139.28204, 139.36137], Lat: [35.58019, 35.60639]`
- **欠損ジオメトリ数**: 0
- **属性カラム一覧**: `city_code, jusho1, jusho2, jusho3, jcode1, jcode2, lon, lat`...

### `raw/historical_boundaries/N03-140401_14_GML.zip`
- **種別**: ZIP-Spatial
- **CRS（測地系）**: `EPSG:4612`
- **レコード件数**: 606
- **外接矩形 (Bounds)**: `Lon: [138.91577, 139.83584], Lat: [35.1285, 35.6729]`
- **欠損ジオメトリ数**: 0
- **属性カラム一覧**: `N03_001, N03_002, N03_003, N03_004, N03_007, geometry`

### `raw/historical_boundaries/codh_fujino_20050101.geojson`
- **種別**: GeoJSON
- **CRS（測地系）**: `EPSG:4326`
- **レコード件数**: 1
- **外接矩形 (Bounds)**: `Lon: [139.16926, 139.23604], Lat: [35.56577, 35.65302]`
- **欠損ジオメトリ数**: 0
- **属性カラム一覧**: `N03_001, N03_002, N03_003, N03_004, N03_005, N03_006, N03_007, id`...

### `raw/historical_boundaries/codh_sagamiko_20050101.geojson`
- **種別**: GeoJSON
- **CRS（測地系）**: `EPSG:4326`
- **レコード件数**: 1
- **外接矩形 (Bounds)**: `Lon: [139.11166, 139.20246], Lat: [35.54102, 35.6729]`
- **欠損ジオメトリ数**: 0
- **属性カラム一覧**: `N03_001, N03_002, N03_003, N03_004, N03_005, N03_006, N03_007, id`...

### `raw/historical_boundaries/codh_shiroyama_20050101.geojson`
- **種別**: GeoJSON
- **CRS（測地系）**: `EPSG:4326`
- **レコード件数**: 1
- **外接矩形 (Bounds)**: `Lon: [139.26477, 139.32634], Lat: [35.53815, 35.61316]`
- **欠損ジオメトリ数**: 0
- **属性カラム一覧**: `N03_001, N03_002, N03_003, N03_004, N03_005, N03_006, N03_007, id`...

### `raw/historical_boundaries/codh_tsukui_19551001.geojson`
- **種別**: GeoJSON
- **CRS（測地系）**: `EPSG:4326`
- **レコード件数**: 1
- **外接矩形 (Bounds)**: `Lon: [139.06604, 139.29599], Lat: [35.47455, 35.61028]`
- **欠損ジオメトリ数**: 0
- **属性カラム一覧**: `N03_001, N03_002, N03_003, N03_004, N03_005, N03_006, N03_007, id`...

### `raw/historical_boundaries/codh_tsukui_20050101.geojson`
- **種別**: GeoJSON
- **CRS（測地系）**: `EPSG:4326`
- **レコード件数**: 1
- **外接矩形 (Bounds)**: `Lon: [139.06604, 139.29599], Lat: [35.47455, 35.61028]`
- **欠損ジオメトリ数**: 0
- **属性カラム一覧**: `N03_001, N03_002, N03_003, N03_004, N03_005, N03_006, N03_007, id`...

### `raw/landuse/L03-b-14_5339-jgd_GML.zip`
- **種別**: ZIP-Spatial
- **CRS（測地系）**: `EPSG:4612`
- **レコード件数**: 630,000
- **外接矩形 (Bounds)**: `Lon: [139.0, 140.0], Lat: [35.33333, 36.0]`
- **欠損ジオメトリ数**: 0
- **属性カラム一覧**: `メッシュ, 土地利用種, geometry`

### `raw/railways/N02-23_GML.zip`
- **種別**: ZIP-Spatial
- **CRS（測地系）**: `EPSG:4326`
- **レコード件数**: 21,949
- **外接矩形 (Bounds)**: `Lon: [127.65228, 145.59801], Lat: [26.19315, 45.41688]`
- **欠損ジオメトリ数**: 0
- **属性カラム一覧**: `N02_001, N02_002, N02_003, N02_004, geometry`

### `raw/rivers/W05-08_14_GML.zip`
- **種別**: ZIP-Spatial
- **CRS（測地系）**: `None`
- **レコード件数**: 2,439
- **外接矩形 (Bounds)**: `Lon: [138.91759, 139.77249], Lat: [35.14025, 35.6675]`
- **欠損ジオメトリ数**: 0
- **属性カラム一覧**: `W05_001, W05_011, W05_000, geometry`

---

## 3. 品質評価サマリーとPhase 1への申し送り事項

1. **空間データの完全性**: すべてのGeoJSON、Shapefile、OSM XMLが欠損ジオメトリなく正常にロード可能であることを確認。
2. **CRS統一の必要性**: 行政区域データ（JGD2011/EPSG:6668）、住居表示（JGD2000/JGD2011）、CODH・OSM（WGS84/EPSG:4326）の測地系が混在しているため、Phase 1の実解析前に**平面直角座標系 第IX系（JGD2011 / EPSG:6677）**へ統一変換するパイプラインを必須とする。
3. **大字・地番境界の補完**: 住居表示未実施地域（旧津久井郡山間部）は大字レベルの行政界（CODHおよびN03）を参照することを確認。