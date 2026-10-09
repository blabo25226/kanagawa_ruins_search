# 公式・歴史地理データソース台帳（2026-10-09確認）

目的: 入手先の検討・利用条件の記録。**出典の掲載≠自動収集の許可**。ここにあるURLを網羅的にスクレイピングしない。自動取得の対象は`config/sources.toml`で限定する。

| ID | データ・提供者 | URL | 取得・用途 | 注意 |
|---|---|---|---|---|
| MLIT-N03 | 国土交通省 国土数値情報 行政区域 N03（2026） | https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N03-2026.html | 神奈川県2026 ZIP（`N03-20260101_14_GML.zip`、約5.12 MB）、行政区画の基礎。GeoJSON等の形式あり | CC BY 4.0。Web画面から取得；リンクを憶測して組み立てない。2026版はJGD2011表記。 |
| GSI-JUSHO | 国土地理院 住居表示住所 相模原市緑区 | https://data.e-gov.go.jp/data/dataset/mlit_20140919_3060/resource/b79eca7e-b47f-4bf7-9fd3-bed540d4c6f1?inner_span=True | 公開ZIP（`https://saigai.gsi.go.jp/jusho/download/data/14151.zip`）を少量取得して検証 | e-Govカタログに政府標準利用規約2.0と記載。住所データは神社跡の実在証明ではない。 |
| SAGAMIHARA-CULTURAL | 相模原市オープンデータ 文化財一覧 | https://opendata.city.sagamihara.kanagawa.jp/ne/dataset/bunkazai | 公開CSVを基礎資料として取得（CKAN resource_showで正規URLを取得） | 市公式は原則 CC BY 4.0と説明。リソース別表記との相違は記録し再配布時再確認。収録対象は指定・登録等の文化財であり廃墟の網羅データではない。 |
| GSI-HISTORY | 国土地理院 地図・空中写真閲覧サービス | https://service.gsi.go.jp/map-photos/app/ | 旧版地形図の索引と過去航空写真の存在・年代を確認 | 高画質閲覧の画面キャプチャ禁止。必要な画像は正式な交付・提供手続き。登録・購入が必要な場合あり。 |
| GSI-OLDMAP | 国土地理院 旧版地図等の交付 | https://web1.gsi.go.jp/MAP/HISTORY/koufu.html | 旧版図の取得手順を確認 | 交付・閲覧条件を満たして入手。自動スクレイピング不可。 |
| GSI-FGD | 国土地理院 基盤地図情報 基本項目・DEM | https://service.gsi.go.jp/kiban/ | 境界・道路縁・数値標高モデル | 無料だが利用者登録必須。2026-07-31以降の提供はJGD2024へ移行。ユーザー側で取得。 |
| GSI-TILES | 国土地理院 地理院タイル | https://maps.gsi.go.jp/help/use.html | リアルタイム表示用の背景図、地形参考 | タイルごとに条件が異なる。広域連続DLをしない。測量成果に該当する場合は申請要否を確認。 |
| NARO-OLD | 農研機構 歴史的農業環境閲覧システム（迅速測図） | https://habs.rad.naro.go.jp/ | 明治の地図との比較。関東の一部のみ | 原則 CC BY 2.1 JPと案内。地域カバーと測量精度を要確認（100m程度の誤差例）。タイル一括取得はしない。 |
| NARO-FAQ | 農研機構 利用条件FAQ | https://habs.rad.naro.go.jp/habs_faq.html | 出典表記、精度、ダウンロード可能なデータの確認 | 必ず個別条件確認。 |
| KONJAKU | 今昔マップ on the web | https://ktgis.net/kjmapw/ | ブラウザでの歴史地形図比較 | **画像ファイル自体をPC・サーバに保存する使用は禁止**。自動DLしない。規約: https://ktgis.net/kjmapw/note.html |
| SAGAMIHARA-GIS | さがみはら地図情報（Web公開型GIS） | https://www.city.sagamihara.kanagawa.jp/shisei/1026823/1004480/1026832/1024999.html | 地形図・埋蔵文化財包蔵地の参考 | 津久井地域の一部でデータ提供対象外あり。閲覧サイトはDL APIとみなさない。 |
| SAGAMIHARA-OPEN | 相模原市オープンデータ案内 | https://www.city.sagamihara.kanagawa.jp/shisei/toukei/opendata/index.html | 市CSVの利用条件確認 | 市案内は CC BY 4.0、取得の際に最新規約を確認。 |

## Phase 0の取得優先度

1. **取得を自動化可能**: `GSI-JUSHO` ZIPおよび`SAGAMIHARA-CULTURAL` CSV（正規のAPIでURLを確認して取得）。
2. **ブラウザから利用者が取得**: `MLIT-N03` 神奈川県単位の2026版（行政境界・座標系の記録を重視）。
3. **登録・購入等を確認**: `GSI-FGD`、`GSI-HISTORY`。エージェントは登録・購入を代行しない。
4. **比較閲覧のみ**: `KONJAKU`、`NARO-OLD`、`SAGAMIHARA-GIS`。利用条件を守る。

## 記録する最低限のメタデータ

- dataset_id, organization, source_page, direct_url（該当時のみ）
- license_name, license_url, license_reviewed_at, attribution_text, redistribution_allowed (yes/no/unknown)
- geographic_coverage, years, format, data_crs, current_crs_assumption (記入不可: 推測禁止)
- downloaded_at_utc, downloaded_bytes, sha256, relative_path
- access_requirement (none/account/manual_application/purchase/unknown)
- remarks (検証状態と制約)

## 注意: 精度・調査倫理

- 古地図の鳥居記号不掲載だけでは廃社と断定できない。
- 大正以前の史料に現代の境界・地名をそのまま適用しない。
- 個人宅・私有地や危険施設の立ち入りを推奨する位置情報は公開しない。
- 素材に利用規約・第三者権利・測量法による制限がある場合、その条件を優先する。
