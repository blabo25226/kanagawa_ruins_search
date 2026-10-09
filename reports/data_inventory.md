# Phase 0 データ取得状況

- 確認日時（JST）：2026-10-09 21:58:25 JST
- 参照した利用条件のURL：
  - 国土地理院コンテンツ利用規約: `https://www.gsi.go.jp/kikakuchousei/kikakuchousei40182.html`
  - 国土地理院 電子国土基本図（地名情報）「住居表示住所」案内: `https://www.gsi.go.jp/kihonjohochousa/jukyo_jusho.html`
  - 相模原市オープンデータ利用規約: `https://www.city.sagamihara.kanagawa.jp/shisei/toukei/opendata/index.html`
  - 国土交通省 国土数値情報利用規約: `https://nlftp.mlit.go.jp/ksj/other/agreement.html`
  - 国土地理院 地図・空中写真閲覧サービス: `https://service.gsi.go.jp/map-photos/app/`
  - 国土地理院 基盤地図情報: `https://service.gsi.go.jp/kiban/`
  - 今昔マップ on the web 利用上の注意: `https://ktgis.net/kjmapw/note.html`
  - 農研機構 歴史的農業環境閲覧システム FAQ: `https://habs.rad.naro.go.jp/habs_faq.html`

## データ台帳

| ソースID | 状態（取得済み/保留/失敗） | 形式/容量 | 配布条件 | 保留理由・備考 |
|---|---|---|---|---|
| `gsi_jusho_midori` | 取得済み | ZIP (1,672,520 bytes, 展開後26.2MB, 6ファイル) | 国土地理院コンテンツ利用規約（公共データ利用規約1.0 / 政府標準利用規約2.0準拠, CC BY 4.0互換）。出典明記・加工内容の表示が必要。 | 直リンク（`saigai.gsi.go.jp`）より正常取得。展開検査でCSVおよびシェープファイル（shp, shx, dbf, prj, cpg）を確認。なおe-Gov掲載URLは404となっていたため国土地理院一次情報ページを参照。 |
| `sagamihara_cultural_assets` | 取得済み | CSV (210,799 bytes, 218行) | 相模原市オープンデータ利用規約（CC BY 4.0）。商用・非商用問わず二次利用可能、出典表記必要。 | 市公式CKAN API（`resource_show`）経由で最新リソースURLを動的解決して取得。ヘッダーおよび文字コード（UTF-8 with BOM）の正常性を確認。 |
| `mlit_n03_2026_kanagawa` | 保留 | ZIP (予定: 約5.12MB, `N03-20260101_14_GML.zip`) | 国土数値情報利用規約（CC BY 4.0）。出典明記必要。 | Webダウンロード画面上のJavaScript（`DownLd`関数）を経由する仕様であり、直リンク推測が禁止されているため自動取得から除外。手動取得または人間による取得案内として保留。 |
| `gsi_historical_maps` | 保留 | Web地図 / 画像交付 | 国土地理院コンテンツ利用規約等。画面キャプチャ・一括取得禁止。 | 旧版地形図および過去空中写真の高画質データはオンライン一括取得不可。研究に必要な対象地点が絞られた段階で正式な交付手続き・購入等を検討。 |
| `gsi_fgd_dem` | 保留 | 基盤地図情報 (XML/GML/DEM) | 国土地理院 基盤地図情報利用規約。無料だがアカウント登録が必須。 | エージェントによる無断アカウント登録や認証バイパスは規約違反となるため保留。また2026年7月31日以降提供データはJGD2024へ移行しているためCRS統一時の注意が必要。 |
| `konjaku_view_only` | 閲覧のみ | Webブラウザ表示 | 今昔マップ利用規約: **「画像ファイル自体をPC・サーバ等に保存することは禁止」**。 | 自動スクレイピング・ローカルキャッシュ保存は厳禁。Phase 1以降の比較検証においてもブラウザでの手動目視対照のみに限定する。 |

## 保管・来歴管理状況

- 原本保存先: `data/raw/`（`.gitignore` によりGit管理から除外済み）
  - `data/raw/gsi_jusho_midori/14151.zip` (1,672,520 bytes)
  - `data/raw/sagamihara_cultural_assets/bunkazai.csv` (210,799 bytes)
- 来歴管理ファイル: `data/provenance.jsonl`（`.gitignore` によりGit管理から除外済み）
  - 記録項目: `source_id`, `source_page`, `download_url`, `license_url`, `license_note`, `phase`, `downloaded_at_utc`, `relative_path`, `bytes`, `sha256`, `format`
- ハッシュ値確認（SHA-256）:
  - `14151.zip`: `a72352712494a1c598745fe87ee4a4c4f555849a86a2478725913964ebda531d`
  - `bunkazai.csv`: `dec1117a21869988457f1d06a578e6b891e85700b7efee4b52521b16e79b08b7`
- 内容の探索的分析・廃墟候補抽出: **一切未実施（原本の形式・サイズ・ハッシュ・ヘッダー検査のみ完了）**
