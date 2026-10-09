# Phase 0 データ取得状況・ソース台帳

- 確認日時（JST）：2026-10-09 23:20:00 JST
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
  - 国土地理院 基盤地図情報: `https://service.gsi.go.jp/kiban/`
  - 今昔マップ on the web 利用上の注意: `https://ktgis.net/kjmapw/note.html`
  - 農研機構 歴史的農業環境閲覧システム FAQ: `https://habs.rad.naro.go.jp/habs_faq.html`
  - 国立国会図書館デジタルコレクション 利用規約: `https://www.ndl.go.jp/jp/use/reproduction/index.html`

---

## 1. 取得済みデータ一覧（Google Drive格納・検証済み）

| ID | ソース名・提供元 | 格納パス (Google Drive相対) | 容量 (bytes) | 形式 | SHA-256 ハッシュ値 | ライセンス・利用条件 | 備考 |
|:---|:---|:---|---:|:---|:---|:---|:---|
| **D01** | 住居表示住所（緑区）<br>国土地理院 | `raw/administrative/14151.zip` | 1,672,520 | ZIP | `a72352712494a1c598745fe87ee4a4c4f555849a86a2478725913964ebda531d` | 国土地理院利用規約<br>(CC BY 4.0互換) | 現代の字名・番地・集落参照用（神社現存判定には直接使用しない） |
| **D02** | 文化財一覧 CSV<br>相模原市 | `raw/cultural_properties/bunkazai.csv` | 210,799 | CSV | `dec1117a21869988457f1d06a578e6b891e85700b7efee4b52521b16e79b08b7` | 相模原市OD<br>(CC BY 4.0) | 指定文化財照合の参考データ（現存完全除外DBではない） |
| **D03** | 行政区域 N03 2026年<br>国土交通省 | `raw/administrative/N03-20260101_14_GML.zip` | 5,370,610 | ZIP | `27ab5aa2982fc6fe81e9c0b08ca75d18177e8228527b2e602ce803e681e7e561` | 国土数値情報規約<br>(CC BY 4.0互換) | 神奈川県全域の最新行政界ポリゴン（JGD2011） |
| **D04** | 過去行政区域 N03 2014年<br>国土交通省 | `raw/historical_boundaries/N03-140401_14_GML.zip` | 1,860,243 | ZIP | `b9f236d3512a9b96ed6525c4e7b1f898874fc7a45595a66cd2f150549d9daeca` | 国土数値情報規約<br>(CC BY 4.0互換) | 平成大合併前後の行政界対照用 |
| **D05-1** | 歴史的行政区域（津久井町1955）<br>CODH | `raw/historical_boundaries/codh_tsukui_19551001.geojson` | 137,132 | GeoJSON | `d2105725065d8b2f9cb04bb28829ddd651500a4566ac73d70f09e3a10fc389cf` | CODH利用規約<br>(CC BY 4.0) | 1955年津久井町発足時の町界ポリゴン |
| **D05-2** | 歴史的行政区域（津久井町2005）<br>CODH | `raw/historical_boundaries/codh_tsukui_20050101.geojson` | 136,875 | GeoJSON | `85b4f3ef11efd93602a40e930b441453112e183993b08f0ee303f3934c2b9ce6` | CODH利用規約<br>(CC BY 4.0) | 相模原市編入直前の旧津久井町境界ポリゴン |
| **D06** | OpenStreetMap (津久井コア)<br>OSM | `raw/osm/tsukui_core_osm.osm` | 5,834,482 | XML | `8bea6721aefe13b3e850c8d1a224e7433b1721135aff7d16d0a8a01a8e4bb671` | ODbL 1.0 | 青野原・青山・鳥屋・寸沢嵐のコア領域フィーチャ |
| **D08** | 土地利用細分メッシュ 2021年<br>国土交通省 | `raw/landuse/L03-b-14_5339-jgd_GML.zip` | 13,314,929 | ZIP | `b72e1446cb2ab067f28f7196099b09f473ed1650bdfa1b41f44b0d6bc44b1c44` | 国土数値情報規約<br>(CC BY 4.0互換) | 5339メッシュ（相模原・津久井地域）の森林・宅地等メッシュ |
| **D10** | 鉄道データ N02 2023年<br>国土交通省 | `raw/railways/N02-23_GML.zip` | 17,518,918 | ZIP | `e91ecdee90966877c6119ab94dc92ee6562eb9d89194f8a0a91f71b179c82a40` | 国土数値情報規約<br>(CC BY 4.0互換) | 鉄道網・駅データ（近世古道・交通路対照） |
| **D11** | 河川データ W05<br>国土交通省 | `raw/rivers/W05-08_14_GML.zip` | 1,908,537 | ZIP | `8a553d8c3aa3a43d5a4c8bc9067a971eb57967eb435168dfca823192b7ed431d` | 国土数値情報規約<br>(CC BY 4.0互換) | 相模川・道志川水系の流路ポリラインデータ |
| **D12** | 神奈川県指定文化財目録<br>神奈川県 | `raw/cultural_properties/kanagawa_bunkazai_mokuroku_r07.pdf` | 5,545,067 | PDF | `b7c5294ec088af0497d7ee4c8861225eba3bcd242fc0d3e3bceec0159eb86071` | 神奈川県OD<br>(CC BY 4.0準拠) | 県指定重要文化財・史跡等の最新台帳（令和7年版） |
| **D13** | 歴史資料所在目録（旧津久井郡編）<br>神奈川県立公文書館 | `literature/catalogs/rekishishiryoushozaimokuroku14-4-1.pdf` | 8,153,399 | PDF | `6c8f05077508427d1f2d574e325c95119aa141a0a6b91aa1525b933814916b78` | 公文書館公開刊行物<br>(調査・学術利用) | 旧津久井郡内の古文書・神社資料所在一覧（第14集第4分冊） |
| **D14** | 古文書資料群一覧（若柳村文書）<br>神奈川県立公文書館 | `literature/catalogs/pdflist_wakayanagi.pdf` | 53,950 | PDF | `e57f983037ed234623030ebf0548b0e2185b1cf67cac0730c4e012b8036d4672` | 公文書館公開刊行物<br>(調査・学術利用) | 相模原市緑区旧村（若柳村）所蔵古文書群目録 |
| **P03** | MapReader 論文 PDF<br>Wood et al. (2024) | `literature/papers/Wood2024_MapReader.pdf` | 447,699 | PDF | `e6ecce73e73152fa4651fb7a55a0309b7182d9752ee33963bce5f930673fd92d` | JOSS (CC BY 4.0) | 大規模地図ラスタ画像認識 OSS パイプライン論文 |

---

## 2. 先行研究書誌情報（Google Drive格納）

- 格納先: `literature/bibliography/`
  - `references.bib`: P01〜P11のBibTeX形式書誌情報
  - `references.json`: P01〜P11のJSON形式構造化メタデータ
  - `literature_review.md`: 各論文の研究概要・技術的意義・Phase 1以降の活用方針

---

## 3. 保留・閲覧専用データ（規約遵守状況）

- `GSI-FGD`（基盤地図情報）: 利用者登録必須のため自動取得保留。Phase 1にて必要なメッシュのみ手動取得。
- `KONJAKU`（今昔マップ on the web）: 利用規約により「画像ファイルのPC/サーバ保存禁止」が明記されているため、自動取得・保存を完全除外。Webブラウザでの目視比較に限定。
- `GSI-HISTORY` / `GSI-OLDMAP`: 高画質スクレイピング禁止。正式交付申請手順をPhase 1計画書に策定。
- `NARO-OLD`（歴史的農業環境閲覧システム）: タイル一括取得禁止。対象地域の目視確認に限定。

---

## 4. ストレージ容量実績

- **Google Drive正規保存先** (`$RUINS_DATA_ROOT`):
  - 取得ファイル数: 14データファイル + 書誌3ファイル + README 3ファイル + 来歴台帳1ファイル
  - 総容量: **約 62.0 MB**
- **ローカルリポジトリ** (`kanagawa_ruins_search`):
  - 使用容量: **約 1.1 MB**（ソースコード、設定、レポート、テストのみ）
  - 生データ実体: **0 B**（重複保存完全排除）
  - 一時データ容量制限（1GB以内）: 完全遵守
