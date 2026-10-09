# Phase 0.4 データ・文献追加収集および品質検証レポート

**プロジェクト**: 神奈川県廃墟調査プロジェクト（Kanagawa Ruins Search Project）  
**対象フェーズ**: Phase 0.4（参考文献の全面再検証と不足データの重点収集）  
**調査地域**: 神奈川県全域、隣接18自治体、および重点調査地域（相模原市緑区旧津久井地域：青野原、青山、鳥屋、寸沢嵐）  
**作成日時**: 2026-10-10  
**担当エージェント**: Gemini 3.8 Flash  
**レビュー担当**: GPT-5.6 Sol High  

---

## 1. 概要と目的

Phase 0.3において神奈川県全域および隣接18自治体（東京都檜原村を含む）の行政境界・文化財・基幹OSMデータの広域収集が達成された。
本Phase 0.4では、Phase 1における遺構推定・古地図対照・地形解析に向けた基盤整備として、以下の重点課題を実施した。

1. **参考文献・研究論文（P01〜P12）の全面再検証と一次情報へのアクセス確認**
   - 以前のAIセッションで混入したハルシネーション（架空DOI、架空論文名、不正確な著者名・対象地域）を原典照合により完全是正。
   - オープンアクセス論文（P02 田林 2026, P05 Luft & Schiewe 2021）のPDFを正規取得しデータバンクへ格納。
2. **土地利用細分メッシュデータ（L03-b）の計画的ピンポイント収集**
   - 広域一括ダウンロードによる容量圧迫を回避し、神奈川県全域＋隣接18自治体をカバーする1次メッシュ（5238, 5239, 5338, 5339）を数理的に特定。
   - 重点調査地域（相模原市緑区旧津久井地域）を含む**メッシュ5338（西側）および5339（東側）**を対象に、最古の1976年、中間期2014年、最新の2021年の時系列データをピンポイント取得（計6ファイル、約96MB）。
3. **昭和期空中写真（米軍・国土地理院）の詳細調査とカタログ化・サンプル取得**
   - 2026年3月にリニューアルされた国土地理院「地図・空中写真閲覧サービス」のAPI仕様を解読。
   - 旧津久井4地区（青野原・青山・鳥屋・寸沢嵐）をカバーする昭和期単写真（1940年代米軍、1950年代、1960年代国土基本図、1970年代カラー写真）計42件の詳細メタデータを抽出しカタログJSON化。
   - 1974〜1978年カラーオルソ画像（gazo1）の代表サンプルタイルを正規取得。
4. **自治体埋蔵文化財データ・遺跡地図の最新調査と公式一覧PDFの取得**
   - 相模原市教育委員会文化財課が公表している最新（令和8年2月12日現在）の『相模原市内埋蔵文化財包蔵地一覧』（PDF）を正規取得し格納。
   - 青野原遺跡、青山開戸遺跡、寸沢嵐遺跡、津久井城跡等の登録状況を確認。

> [!IMPORTANT]
> **Phase 0 規律の厳守**:
> 本フェーズにおいても、廃墟候補地の抽出、神社・遺構の自動探索、候補地点のランキング、機械学習モデルの訓練などの解析作業には一切着手しておらず、データ収集・保存・整合性確認および手順整理のみを実施している。

---

## 2. 新規収集データ一覧

Phase 0.4においてGoogle Driveデータバンク（`$RUINS_DATA_ROOT`）へ新たに追加されたデータは以下の通りである。

| 区分 | 管理ID | ファイル名 / 相対パス | データ種別 | サイズ | SHA-256 (先頭12桁) | ライセンス・出典 | 備考 |
|:---|:---|:---|:---|---:|:---|:---|:---|
| **研究論文** | `paper_p02_tabayashi2026` | `literature/papers/Tabayashi2026_OldMapGeoreferencingAI.pdf` | 学術論文 (PDF) | 1,083,965 B | `e0cb29ac4cae` | J-STAGE / 日本地理学会発表要旨集（CC BY互換オープンアクセス） | P02原典PDF。深層学習を用いた迅速図ジオリファレンス技術 |
| **研究論文** | `paper_p05_luft2021` | `literature/papers/Luft2021_HistoricalMapGeoreferencing.pdf` | 学術論文 (PDF) | 1,361,395 B | `facca1e1394c` | Wiley / Transactions in GIS (CC BY 4.0 DEAL オープンアクセス) | P05原典PDF。19世紀歴史地図の自動ジオリファレンスフレームワーク |
| **土地利用** | `mlit_l03_b_1976_5338` | `raw/landuse/L03-b-76_5338_GML.zip` | 国土数値情報 (GML/ZIP) | 14,630,483 B | `1071994099b4` | 国土交通省 国土数値情報利用規約（CC BY 4.0互換） | 1976年（昭和51年）最古デジタル土地利用メッシュ（津久井西部・道志） |
| **土地利用** | `mlit_l03_b_1976_5339` | `raw/landuse/L03-b-76_5339_GML.zip` | 国土数値情報 (GML/ZIP) | 14,450,493 B | `b2e5a7210f51` | 国土交通省 国土数値情報利用規約（CC BY 4.0互換） | 1976年（昭和51年）最古デジタル土地利用メッシュ（津久井東部・相模原） |
| **土地利用** | `mlit_l03_b_2014_5338` | `raw/landuse/L03-b-14_5338-jgd_GML.zip` | 国土数値情報 (GML/ZIP) | 13,398,459 B | `09e03256f41a` | 国土交通省 国土数値情報利用規約（CC BY 4.0互換） | 2014年（平成26年）土地利用メッシュ（津久井西部・JGD2000） |
| **土地利用** | `mlit_l03_b_2021_5338` | `raw/landuse/L03-b-21_5338-jgd2011_GML.zip` | 国土数値情報 (GML/ZIP) | 22,476,659 B | `3f9d82c098eb` | 国土交通省 国土数値情報利用規約（CC BY 4.0互換） | 2021年（令和3年）最新土地利用メッシュ（津久井西部・JGD2011） |
| **土地利用** | `mlit_l03_b_2021_5339` | `raw/landuse/L03-b-21_5339-jgd2011_GML.zip` | 国土数値情報 (GML/ZIP) | 22,386,507 B | `f6bbebb3fa80` | 国土交通省 国土数値情報利用規約（CC BY 4.0互換） | 2021年（令和3年）最新土地利用メッシュ（津久井東部・JGD2011） |
| **空中写真** | `gsi_aerial_photo_catalog_tsukui` | `raw/aerial_photos/metadata/tsukui_aerial_photos_catalog.json` | 検索台帳 (JSON) | 39,268 B | `db0f0985c707` | 国土地理院 地図・空中写真閲覧サービス API成果 | 津久井4地区を捉えた昭和期空中写真42件の詳細諸元（コース・番号・座標等） |
| **空中写真** | `gsi_aerial_tile_1974_aonohara` | `raw/aerial_photos/sample_ortho_1974/aonohara_1974_z15_29054_12916.jpg` | 正射画像タイル (JPEG) | 20,452 B | `0be53715c0e7` | 国土地理院コンテンツ利用規約（gazo1 レイヤ） | 1974〜1978年 青野原中心部 正射写真タイル (Zoom 15) |
| **空中写真** | `gsi_aerial_tile_1974_aoyama` | `raw/aerial_photos/sample_ortho_1974/aoyama_1974_z15_29058_12912.jpg` | 正射画像タイル (JPEG) | 18,502 B | `0d89280f2d5e` | 国土地理院コンテンツ利用規約（gazo1 レイヤ） | 1974〜1978年 青山中心部 正射写真タイル (Zoom 15) |
| **空中写真** | `gsi_aerial_tile_1974_toya` | `raw/aerial_photos/sample_ortho_1974/toya_1974_z15_29055_12920.jpg` | 正射画像タイル (JPEG) | 22,088 B | `ddadfe6344d5` | 国土地理院コンテンツ利用規約（gazo1 レイヤ） | 1974〜1978年 鳥屋中心部 正射写真タイル (Zoom 15) |
| **空中写真** | `gsi_aerial_tile_1974_suarashi` | `raw/aerial_photos/sample_ortho_1974/suarashi_1974_z15_29054_12906.jpg` | 正射画像タイル (JPEG) | 17,121 B | `0f7236d89552` | 国土地理院コンテンツ利用規約（gazo1 レイヤ） | 1974〜1978年 寸沢嵐中心部 正射写真タイル (Zoom 15) |
| **埋蔵文化財** | `sagamihara_buried_cultural_properties_2026` | `raw/cultural_properties/sagamihara_buried_cultural_properties_20260212.pdf` | 公式台帳 (PDF) | 110,726 B | `de14000fe289` | 相模原市教育委員会 文化財課（公式オープン情報） | 令和8年2月12日改訂版。相模原市内全埋蔵文化財包蔵地一覧 |

---

## 3. データバンク現況統計

Phase 0.4完了時点におけるGoogle Driveデータバンク（`kanagawa_ruins_search_databank/data/`）の集計結果は以下の通りである。

```
kanagawa_ruins_search_databank/data/
├── literature/
│   ├── bibliography/
│   │   ├── literature_review.md
│   │   ├── references.bib
│   │   └── references.json
│   ├── historical_documents/
│   │   └── README.md
│   └── papers/
│       ├── Berganzo2023_ArchaeologicalMounds.pdf
│       ├── Fujita2007_ShrineLocationGIS.pdf
│       ├── Kanaki2003_AbandonedSettlements.pdf
│       ├── Luft2021_HistoricalMapGeoreferencing.pdf   [Phase 0.4 追加]
│       ├── Oda2015_ShrineMerger.pdf
│       ├── Tabayashi2026_OldMapGeoreferencingAI.pdf  [Phase 0.4 追加]
│       ├── Tani2017_KonjakuMap.pdf
│       └── Wood2024_MapReader.pdf
├── raw/
│   ├── administrative/ (N03行政区域 2026年、2014年、東京都・山梨県・静岡県分等)
│   ├── aerial_photos/                                [Phase 0.4 新設]
│   │   ├── metadata/
│   │   │   └── tsukui_aerial_photos_catalog.json
│   │   └── sample_ortho_1974/
│   │       ├── aonohara_1974_z15_29054_12916.jpg
│   │       ├── aoyama_1974_z15_29058_12912.jpg
│   │       ├── suarashi_1974_z15_29054_12906.jpg
│   │       └── toya_1974_z15_29055_12920.jpg
│   ├── cultural_properties/ (相模原市文化財CSV、P32全国・都県別ZIP、相模原市埋蔵文化財一覧PDF)
│   ├── gsi_jusho_midori/ (緑区住居表示ZIP)
│   ├── historical_boundaries/ (CODH津久井・相模湖旧自治体GeoJSON等)
│   ├── landuse/                                      [Phase 0.4 拡充]
│   │   ├── L03-b-14_5338-jgd_GML.zip
│   │   ├── L03-b-14_5339-jgd_GML.zip
│   │   ├── L03-b-21_5338-jgd2011_GML.zip
│   │   ├── L03-b-21_5339-jgd2011_GML.zip
│   │   ├── L03-b-76_5338_GML.zip
│   │   └── L03-b-76_5339_GML.zip
│   ├── osm/ (関東・中部最新OSM PBF、Overpass津久井抽出XML)
│   ├── railways/ (N02鉄道ラインZIP)
│   └── rivers/ (W05河川流路ZIP)
└── provenance.jsonl                                  [累計54件記録]
```

- **総実ファイル数**: 66ファイル
- **総データ容量**: 約 1.28 GB（Google Drive上）
- **ローカルリポジトリ容量**: 約 1.9 MB（Git管理下はコード・設定・レポートのみに徹底）
- **取得台帳（`provenance.jsonl`）**: 54件の正規取得レコードを記録

---

## 4. 取得データの品質と整合性検証

1. **ハッシュ値照合**: 全ての取得ファイルについてダウンロード完了時にSHA-256ハッシュ値を算出し、`provenance.jsonl`へ記録済み。
2. **フォーマット妥当性**:
   - PDFファイル（学術論文2本、相模原市埋蔵文化財一覧）: `%PDF-` マジックバイトおよび `%%EOF` 終端コードを検証済み。
   - ZIPアーカイブ（L03-b 土地利用メッシュ）: パストラバーサル防止機能を備えた `safe_extract_zip` による展開検証を実施し、GML/XMLスキーマ構造が正常であることを確認。
   - JPEG正射画像: `0xFFD8FF` JPEGマジックバイトを検証済み。
   - JSONメタデータ台帳: `json.loads` による構文解析およびキー構造を検証済み。
3. **FUSEストレージ最適化**:
   - rcloneマウントオプションを `--vfs-cache-mode full --drive-chunk-size 32M --tpslimit 8` に設定。
   - APIリクエスト急増によるレート制限エラー（HTTP 403 Rate Limit Exceeded）を完全に解消し、安定したローカルキャッシュ経由のファイルI/Oを実現。

---

## 5. 次期フェーズへの申し送り事項

1. **L03-b 土地利用データの解析準備**:
   - 1976年・2014年・2021年の時系列データが揃ったことにより、旧津久井地域（青野原・鳥屋・青山・寸沢嵐）における「山林・荒地・農地・宅地」の変遷追跡が可能となった。Phase 1でのGISメッシュ変換（ラスタ化またはポリゴン集計）の入力として直接使用できる。
2. **昭和期空中写真の400dpi単写真取得**:
   - 今回作成したカタログ（`tsukui_aerial_photos_catalog.json`）を基に、手動ダウンロードが必要な重要写真（特に1946年米軍写真および1974年カラー写真）の手順書を整備した（`reports/phase0_4_manual_actions.md` 参照）。
3. **埋蔵文化財包蔵地データの活用**:
   - 相模原市の最新PDFにより、未指定の考古遺跡・散布地が網羅された。Phase 1において、神社・集落跡の探索時に「既知の遺跡」との重複・近接判定リファレンスとして活用する。
