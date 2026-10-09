# Phase 0.2 データ取得状況・ソース台帳

- 確認日時（JST）：2026-10-09 23:55 JST
- 生データ正規保存先：Google Drive上の `kanagawa_ruins_search_databank/data/`（環境変数 `RUINS_DATA_ROOT`）
- 参照した主な利用規約・案内URL：
  - 国土地理院コンテンツ利用規約: `https://www.gsi.go.jp/kikakuchousei/kikakuchousei40182.html`
  - 国土地理院 住居表示住所案内: `https://www.gsi.go.jp/kihonjohochousa/jukyo_jusho.html`
  - 相模原市オープンデータ利用規約: `https://www.city.sagamihara.kanagawa.jp/shisei/toukei/opendata/index.html`
  - 国土数値情報利用規約: `https://nlftp.mlit.go.jp/ksj/other/agreement.html`
  - 人文学オープンデータ共同利用センター (CODH) 利用規約: `https://geoshape.ex.nii.ac.jp/city/`
  - OpenStreetMap 利用規約 (ODbL): `https://www.openstreetmap.org/copyright`
  - 神奈川県オープンデータカタログ: `https://catalog.opendata.pref.kanagawa.jp/`
  - 神奈川県立公文書館 刊行物案内: `https://archives.pref.kanagawa.jp/`
  - 国立国会図書館デジタルコレクション 利用規約: `https://www.ndl.go.jp/jp/use/reproduction/index.html`
  - Nature Scientific Reports (CC BY 4.0): `https://www.nature.com/srep/`
  - J-STAGE 利用規約: `https://www.jstage.jst.go.jp/`

---

## 1. 取得済みデータ一覧（Google Drive格納・ハッシュ検証済み）

| ソースID | 格納パス (Google Drive相対) | 容量 (bytes) | 形式 | SHA-256 (先頭16桁) | ライセンス・利用条件 | 概要・対象地域 |
|:---|:---|---:|:---|:---|:---|:---|
| `gsi_jusho_midori` | `raw/administrative/14151.zip` | 1,672,520 | ZIP | `a72352712494a1c5` | 国土地理院 (CC BY 4.0互換) | 相模原市緑区 住居表示住所（市街地番地参照用） |
| `mlit_n03_2026_kanagawa` | `raw/administrative/N03-20260101_14_GML.zip` | 5,370,610 | ZIP | `27ab5aa2982fc6fe` | 国土数値情報 (CC BY 4.0互換) | 神奈川県全域 最新行政区域ポリゴン (2026年) |
| `mlit_n03_2014_kanagawa` | `raw/historical_boundaries/N03-140401_14_GML.zip` | 1,860,243 | ZIP | `b9f236d3512a9b96` | 国土数値情報 (CC BY 4.0互換) | 神奈川県 過去行政区域ポリゴン (2014年) |
| `codh_tsukui_1955` | `raw/historical_boundaries/codh_tsukui_19551001.geojson` | 137,132 | GeoJSON | `d2105725065d8b2f` | CODH (CC BY 4.0) | 旧津久井町 1955年合併時境界ポリゴン |
| `codh_tsukui_2005` | `raw/historical_boundaries/codh_tsukui_20050101.geojson` | 136,875 | GeoJSON | `85b4f3ef11efd936` | CODH (CC BY 4.0) | 旧津久井町 2005年編入直前境界ポリゴン |
| `codh_sagamiko_2005` | `raw/historical_boundaries/codh_sagamiko_20050101.geojson` | 96,324 | GeoJSON | `8bf187d34be07ee3` | CODH (CC BY 4.0) | 旧相模湖町 2005年編入前境界（寸沢嵐が所属） |
| `codh_shiroyama_2005` | `raw/historical_boundaries/codh_shiroyama_20050101.geojson` | 51,611 | GeoJSON | `077da437650f0442` | CODH (CC BY 4.0) | 旧城山町 2005年編入前境界ポリゴン |
| `codh_fujino_2005` | `raw/historical_boundaries/codh_fujino_20050101.geojson` | 52,534 | GeoJSON | `027f60212dd1465a` | CODH (CC BY 4.0) | 旧藤野町 2005年編入前境界ポリゴン |
| `mlit_landuse_2021_5339` | `raw/landuse/L03-b-14_5339-jgd_GML.zip` | 13,314,929 | ZIP | `b72e1446cb2ab067` | 国土数値情報 (CC BY 4.0互換) | 5339メッシュ（相模原・津久井）土地利用細分 (2021) |
| `mlit_rivers_kanagawa` | `raw/rivers/W05-08_14_GML.zip` | 1,908,537 | ZIP | `8a553d8c3aa3a43d` | 国土数値情報 (CC BY 4.0互換) | 相模川・道志川水系 河川流路ポリライン (2008) |
| `mlit_railways_2023` | `raw/railways/N02-23_GML.zip` | 17,518,918 | ZIP | `e91ecdee90966877` | 国土数値情報 (CC BY 4.0互換) | 全国/神奈川 鉄道・路線・駅データ (2023) |
| `osm_tsukui_core` | `raw/osm/tsukui_core_osm.osm` | 5,834,482 | XML | `8bea6721aefe13b3` | ODbL 1.0 | 旧コア領域 OSMデータ (約2.5万ノード) |
| `osm_tsukui_suarashi` | `raw/osm/tsukui_suarashi_osm.osm` | 11,774,956 | XML | `753f3a4afea6312a` | ODbL 1.0 | 寸沢嵐地区網羅 OSMデータ (48,512ノード) |
| `osm_tsukui_toya` | `raw/osm/tsukui_toya_osm.osm` | 6,241,979 | XML | `b380bc65f6d8a2c8` | ODbL 1.0 | 鳥屋地区網羅 OSMデータ (27,354ノード) |
| `osm_tsukui_aoyama` | `raw/osm/tsukui_aoyama_osm.osm` | 10,936,667 | XML | `2cee8ec50206676e` | ODbL 1.0 | 青山地区網羅 OSMデータ (47,098ノード) |
| `osm_tsukui_aonohara` | `raw/osm/tsukui_aonohara_osm.osm` | 6,828,635 | XML | `ed6961c5a73313d5` | ODbL 1.0 | 青野原地区網羅 OSMデータ (29,698ノード) |
| `osm_4districts_meta` | `raw/osm/tsukui_4districts_metadata.json` | 3,075 | JSON | `b5cd347a34cf4fd6` | 学術調査メタデータ | 4地区のBBOX・地物数統計メタデータ |
| `sagamihara_cultural` | `raw/cultural_properties/bunkazai.csv` | 210,799 | CSV | `dec1117a21869988` | 相模原市 (CC BY 4.0) | 相模原市文化財一覧（参考データ） |
| `kanagawa_cultural` | `raw/cultural_properties/kanagawa_bunkazai_mokuroku_r07.pdf` | 5,545,067 | PDF | `b7c5294ec088af04` | 神奈川県 (CC BY 4.0準拠) | 神奈川県指定等文化財目録 令和7年3月版 |
| `kanagawa_archives_tsukui`| `literature/catalogs/rekishishiryoushozaimokuroku14-4-1.pdf`| 8,153,399 | PDF | `6c8f05077508427d` | 公文書館公開資料 | 歴史資料所在目録 旧津久井郡編 (第14集第4分冊) |
| `kanagawa_archives_waka` | `literature/catalogs/pdflist_wakayanagi.pdf` | 53,950 | PDF | `e57f983037ed2346` | 公文書館公開資料 | 相模原市若柳村文書 古文書資料群目録 |
| `ndl_shinpen_sagami_vol5` | `literature/historical_documents/Shinpen_Sagami_Fudokiko_Vol5_IIIF_manifest.json` | 190,030 | JSON | `1ecfb5457453b4ca` | パブリックドメイン (NDL) | 『新編相模国風土記稿 第5輯 三浦・津久井郡』全324コマ IIIFマニフェスト |
| `paper_wood2024` (P03) | `literature/papers/Wood2024_MapReader.pdf` | 447,699 | PDF | `e6ecce73e73152fa` | JOSS (CC BY 4.0) | MapReader 論文 PDF (歴史地図画像解析OSS) |
| `paper_berganzo2023` (P04)| `literature/papers/Berganzo2023_ArchaeologicalMounds.pdf` | 3,943,985 | PDF | `e64eca11c9c77e07` | Nature Sci Rep (CC BY 4.0) | 歴史地図からの考古学的遺構深層学習検出 |
| `paper_kanaki2003` (P08) | `literature/papers/Kanaki2003_AbandonedSettlements.pdf` | 1,606,333 | PDF | `a5bde654b76c2d1b` | 建築学会 (J-STAGE OA) | 消滅集落の分布について 論文 PDF |
| `paper_tani2017` (P09) | `literature/papers/Tani2017_KonjakuMap.pdf` | 4,689,607 | PDF | `64a1c2988d014024` | GIS理論と応用 (J-STAGE OA)| 今昔マップの開発と公開 論文 PDF |
| `paper_fujita2007` (P10) | `literature/papers/Fujita2007_ShrineLocationGIS.pdf` | 2,908,569 | PDF | `c2593cb87354b4a8` | 景観生態学 (J-STAGE OA) | 神社・寺院の立地環境GIS解析 論文 PDF |
| `paper_oda2015` (P11) | `literature/papers/Oda2015_ShrineMerger.pdf` | 176,791 | PDF | `cef264d5e4df26c1` | 日本地理学会 (J-STAGE OA)| 神社合祀と地域社会（三重県飯南・飯高）論文 PDF |

---

## 2. 先行研究書誌情報（Google Drive `literature/bibliography/`）

- `references.bib`: P01〜P12のファクトチェック済みBibTeX台帳
- `references.json`: 構造化メタデータ（研究対象地域・手法・注意点・PDF所蔵状況を含む）
- `literature_review.md`: 改訂版先行研究レビュー

---

## 3. ストレージ容量と重複管理実績

- **Google Drive正規保存先** (`$RUINS_DATA_ROOT`):
  - 有効データ容量: **約 125 MB**
  - 重複ファイル: 既存の重複ファイル（`gsi_jusho_midori/14151.zip`, `sagamihara_cultural_assets/bunkazai.csv` 等）は無断削除を避け、正規保存先へ集約した上で削除候補として記録。
- **ローカルリポジトリ** (`kanagawa_ruins_search`):
  - 使用容量: **約 1.5 MB**（大容量データ重複保存ゼロ、1GB以内制限完全遵守）
