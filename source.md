# 公式・歴史地理データソース台帳（2026-10-10 Phase 0.4更新）

目的: 入手先の検討・利用条件の記録。**出典の掲載≠自動収集の許可**。ここにあるURLを網羅的にスクレイピングしない。  
自動取得の対象は `config/sources.toml` で限定し、ダウンロードデータはすべて Google Drive 上の `$RUINS_DATA_ROOT`（`kanagawa_ruins_search_databank/data/`）へ保存する。

---

## データ保存場所とストレージ管理方針

生データ・地理空間データ・文献資料は、すべて Google Drive 上の正規ストレージ（環境変数 `RUINS_DATA_ROOT`）に以下のディレクトリ階層で安全に格納・管理する。ローカルリポジトリには一切の大容量データを保存・コミットしない（1GB以内厳守）。

```text
kanagawa_ruins_search_databank/
└── data/
    ├── raw/
    │   ├── administrative/        # 行政区域・住居表示（D01: 14151.zip, D03: 神奈川N03, D16: 東京N03, D17: 山梨N03, D18: 静岡N03）
    │   ├── historical_boundaries/ # 過去行政区域・変遷（D04: N03-2014, D05: CODH 津久井町/相模湖町/城山町/藤野町）
    │   ├── landuse/               # 土地利用細分メッシュ（D07/D08: L03-b 1976/2014/2021年 5338/5339メッシュ）
    │   ├── rivers/                # 河川・水系データ（D11: 神奈川W05, D19: 東京W05, D20: 山梨W05, D21: 静岡W05）
    │   ├── railways/              # 鉄道・交通データ（D10: N02 鉄道データ全国）
    │   ├── osm/                   # OpenStreetMap（D06: 津久井4地区個別XML, D23: 関東PBF, D24: 中部PBF）
    │   ├── cultural_properties/   # 文化財台帳（D02: 相模原CSV, D12: 県目録PDF, D22: 全国P32, D25-D27: 県別P32, D28: 都CSV, D30: 相模原埋文PDF）
    │   ├── aerial_photos/         # 昭和期空中写真（D29: 津久井4地区42件カタログJSON、1974年サンプル正射タイル）
    │   └── historical_maps/       # 旧版地形図・歴史地図（Phase 0.4は図歴・所蔵先・利用条件整理）
    │
    ├── literature/
    │   ├── papers/                # 関連研究論文 PDF（P02: 田林, P03: MapReader, P04: Berganzo, P05: Luft, P08: 金木, P09: 谷, P10: 藤田, P11: 小田）
    │   ├── historical_documents/  # 歴史史料（D15: NDL新編相模国風土記稿 第5輯 全324コマ IIIFマニフェスト）
    │   ├── catalogs/              # 公文書館・史料所在目録（D13: 津久井郡歴史資料所在目録, D14: 若柳村文書目録）
    │   └── bibliography/          # 書誌情報（P01〜P12 原典監査済 BibTeX / JSON / Review / Audit Report）
    │
    ├── processed/                 # Phase 1以降の中間成果・解析結果
    └── provenance.jsonl           # 取得全ファイルの完全来歴台帳（53件正規取得レコード、実ファイル計65件、SHA-256検証済）
```

---

## データソース一覧（D01〜D30）

| ID | データ名 | 提供元 | 対象地域・年代 | データ形式 | 推定容量 | ライセンス・利用条件 | 保存先パス | 実施状況 |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| **D01** | 住居表示住所（緑区） | 国土地理院 | 相模原市緑区 (2025年版) | ZIP (CSV + SHP) | 1.67 MB | 国土地理院利用規約（CC BY 4.0互換）。現代番地参照用。 | `raw/administrative/gsi_jusho_midori/14151.zip` | **取得済み** |
| **D02** | 文化財一覧 CSV | 相模原市 | 相模原市全域 (現代) | CSV (UTF-8) | 210 KB | 相模原市オープンデータ（CC BY 4.0）。指定文化財照合参考データ。 | `raw/cultural_properties/sagamihara_cultural_assets/bunkazai.csv` | **取得済み** |
| **D03** | 行政区域 N03 2026年 | 国土交通省 | 神奈川県全域 (2026年) | ZIP (GML/SHP) | 5.37 MB | 国土数値情報規約（CC BY 4.0互換）。最新市町村・区境界ポリゴン。 | `raw/administrative/N03-20260101_14_GML.zip` | **取得済み** |
| **D04** | 過去の行政区域 N03 | 国土交通省 | 神奈川県全域 (2014年版) | ZIP (GML/SHP) | 1.86 MB | 国土数値情報規約（CC BY 4.0互換）。大合併後境界対照用。 | `raw/historical_boundaries/N03-140401_14_GML.zip` | **取得済み** |
| **D05** | 歴史的行政区域データセット | CODH | 旧津久井郡全4町 | GeoJSON (5件) | 計 約470 KB | CODH利用規約（CC BY 4.0）。旧郡町村合併変遷ポリゴン。 | `raw/historical_boundaries/codh_*.geojson` | **取得済み** |
| **D06** | OpenStreetMap (4地区網羅) | OSM 貢献者 | 寸沢嵐・鳥屋・青山・青野原 | XML (.osm, 4件) + JSON | 計 約35.8 MB | ODbL 1.0。神社・寺院・建物・道路・水系等を完全抽出。 | `raw/osm/tsukui_*_osm.osm` | **取得済み** |
| **D07** | 土地利用細分メッシュ 1976年 | 国土交通省 | 5338・5339メッシュ (津久井・道志) | ZIP (GML) | 29.1 MB | 国土数値情報利用規約（CC BY 4.0互換）。最古デジタル土地利用。 | `raw/landuse/L03-b-76_5338_GML.zip`, `...5339...` | **取得済み** |
| **D08** | 土地利用細分メッシュ 2014/2021年 | 国土交通省 | 5338・5339メッシュ (津久井・相模原) | ZIP (GML) | 67.2 MB | 国土数値情報利用規約（CC BY 4.0互換）。中間期・現代メッシュ。 | `raw/landuse/L03-b-14_*.zip`, `L03-b-21_*.zip` | **取得済み** |
| **D09** | 土地利用細分メッシュ 1987/1997年 | 国土交通省 | 5338・5339メッシュ | ZIP (GML) | 各約14 MB | 国土数値情報利用規約（CC BY 4.0互換）。中間変遷補間用。 | `raw/landuse/` | **計画策定済** |
| **D10** | 鉄道データ N02 2023年 | 国土交通省 | 全国/神奈川県 (2023年) | ZIP (GML/SHP) | 17.5 MB | 国土数値情報利用規約（CC BY 4.0互換）。近世・近代交通路対照。 | `raw/railways/N02-23_GML.zip` | **取得済み** |
| **D11** | 河川データ W05 | 国土交通省 | 神奈川県全域 (2008年) | ZIP (GML/SHP) | 1.91 MB | 国土数値情報利用規約（CC BY 4.0互換）。相模川・道志川流路。 | `raw/rivers/W05-08_14_GML.zip` | **取得済み** |
| **D12** | 神奈川県指定等文化財目録 | 神奈川県 | 神奈川県全域 (令和7年3月) | PDF | 5.55 MB | 神奈川県オープンデータ（CC BY 4.0準拠）。県指定史跡公式台帳。 | `raw/cultural_properties/kanagawa_bunkazai_mokuroku_r07.pdf` | **取得済み** |
| **D13** | 歴史資料所在目録（旧津久井郡編） | 県立公文書館 | 旧津久井郡全域 (第14集) | PDF | 8.15 MB | 神奈川県立公文書館公開資料。古文書・神社資料所在調査。 | `literature/catalogs/rekishishiryoushozaimokuroku14-4-1.pdf` | **取得済み** |
| **D14** | 古文書・私文書資料群一覧 | 県立公文書館 | 相模原市緑区（若柳村等） | PDF | 54 KB | 神奈川県立公文書館公開目録。地域所蔵史料目録。 | `literature/catalogs/pdflist_wakayanagi.pdf` | **取得済み** |
| **D15** | 新編相模国風土記稿 第5輯 | NDL | 旧津久井郡各村 (明治21年) | JSON (IIIF 324コマ) | 190 KB | パブリックドメイン (NDL PID 763971)。全324コマ画像マニフェスト。 | `literature/historical_documents/Shinpen_Sagami_Fudokiko_Vol5_IIIF_manifest.json` | **取得済み** |
| **D16** | 行政区域 N03 2026年 東京都 | 国土交通省 | 東京都全域 (2026年) | ZIP (GML/SHP) | 13.15 MB | 国土数値情報利用規約（CC BY 4.0互換）。隣接9市区町村境界検証用。 | `raw/administrative/N03-20260101_13_GML.zip` | **取得済み** |
| **D17** | 行政区域 N03 2026年 山梨県 | 国土交通省 | 山梨県全域 (2026年) | ZIP (GML/SHP) | 3.64 MB | 国土数値情報利用規約（CC BY 4.0互換）。隣接3市村境界検証用。 | `raw/administrative/N03-20260101_19_GML.zip` | **取得済み** |
| **D18** | 行政区域 N03 2026年 静岡県 | 国土交通省 | 静岡県全域 (2026年) | ZIP (GML/SHP) | 13.59 MB | 国土数値情報利用規約（CC BY 4.0互換）。隣接6市町境界検証用。 | `raw/administrative/N03-20260101_22_GML.zip` | **取得済み** |
| **D19** | 河川データ W05 東京都 | 国土交通省 | 東京都全域 (2008年) | ZIP (GML/SHP) | 1.41 MB | 国土数値情報利用規約（CC BY 4.0互換）。多摩川水系流路ポリライン。 | `raw/rivers/W05-08_13_GML.zip` | **取得済み** |
| **D20** | 河川データ W05 山梨県 | 国土交通省 | 山梨県全域 (2008年) | ZIP (GML/SHP) | 3.91 MB | 国土数値情報利用規約（CC BY 4.0互換）。桂川・道志川上流流路。 | `raw/rivers/W05-08_19_GML.zip` | **取得済み** |
| **D21** | 河川データ W05 静岡県 | 国土交通省 | 静岡県全域 (2008年) | ZIP (GML/SHP) | 6.79 MB | 国土数値情報利用規約（CC BY 4.0互換）。酒匂川上流・狩野川水系。 | `raw/rivers/W05-08_22_GML.zip` | **取得済み** |
| **D22** | 都道府県指定文化財 P32 全国 | 国土交通省 | 全国44道府県 (※東京等除く) | ZIP (GML/SHP) | 2.03 MB | 国土数値情報利用規約（CC BY 4.0互換）。道府県指定文化財位置データ。 | `raw/cultural_properties/P32-14_00_GML.zip` | **取得済み** |
| **D23** | OpenStreetMap 関東地方最新PBF | Geofabrik | 関東全域（神奈川・東京等） | OSM PBF | 517.6 MB | ODbL 1.0。道路・水系・建物・宗教施設等の広域地物ベクタ。 | `raw/osm/kanto-latest.osm.pbf` | **取得済み** |
| **D24** | OpenStreetMap 中部地方最新PBF | Geofabrik | 中部全域（山梨・静岡等） | OSM PBF | 511.7 MB | ODbL 1.0。道路・山間歩道・水系・宗教施設等の広域地物ベクタ。 | `raw/osm/chubu-latest.osm.pbf` | **取得済み** |
| **D25** | 都道府県指定文化財 P32 神奈川県 | 国土交通省 | 神奈川県単独 | ZIP (GML/SHP) | 37.6 KB | 国土数値情報利用規約（CC BY 4.0互換）。神奈川県指定文化財位置。 | `raw/cultural_properties/P32-14_14_GML.zip` | **取得済み** |
| **D26** | 都道府県指定文化財 P32 山梨県 | 国土交通省 | 山梨県単独 | ZIP (GML/SHP) | 56.2 KB | 国土数値情報利用規約（CC BY 4.0互換）。山梨県指定文化財位置。 | `raw/cultural_properties/P32-14_19_GML.zip` | **取得済み** |
| **D27** | 都道府県指定文化財 P32 静岡県 | 国土交通省 | 静岡県単独 | ZIP (GML/SHP) | 44.7 KB | 国土数値情報利用規約（CC BY 4.0互換）。静岡県指定文化財位置。 | `raw/cultural_properties/P32-14_22_GML.zip` | **取得済み** |
| **D28** | 東京都指定史跡データ一覧 CSV | 東京都教育庁 | 東京都全域 | CSV (UTF-8) | 9.7 KB | 東京都オープンデータ（CC BY 4.0準拠）。P32未収録補完史跡データ。 | `raw/cultural_properties/130001culturalproperty.csv` | **取得済み** |
| **D29** | 昭和期空中写真カタログ・タイル | 国土地理院 | 旧津久井4地区 (1946〜1978年) | JSON + JPEG | 計 118 KB | 国土地理院利用規約。単写真42件詳細諸元および1974年カラーオルソ。 | `raw/aerial_photos/` | **取得済み** |
| **D30** | 相模原市内埋蔵文化財包蔵地一覧 | 相模原市教育委 | 相模原市全域 (令和8年2月版) | PDF | 110.7 KB | 相模原市教育委員会 文化財課公表資料。市域全遺跡台帳。 | `raw/cultural_properties/sagamihara_buried_cultural_properties_20260212.pdf` | **取得済み** |

---

## 閲覧専用・手動確認・保留データソース一覧（規約遵守）

| ID | データ名 | 提供元 | URL | 利用規約上の重要制約 | Phase 0.4対応・Phase 1への申し送り |
|:---|:---|:---|:---|:---|:---|
| `GSI-FGD` | 基盤地図情報 (DEM・基本項目) | 国土地理院 | `https://service.gsi.go.jp/kiban/` | 無料だが**利用者登録（アカウント認証）が必須**。 | **手動手順策定済**：2次メッシュコード（533921, 533931等）およびFGDM/QGIS変換手順を `reports/phase0_4_manual_actions.md` に明記。 |
| `GSI-OLDMAP` | 旧版地形図等の交付 | 国土地理院 | `https://web1.gsi.go.jp/MAP/HISTORY/koufu.html` | **有料（測量法第28条に基づく謄本交付申請・手数料）**。 | **図歴調査済**：青野原（昭4測量・昭44改測）、相模湖（明39測量・昭42改測）等の図歴を整理。申請準備完了。 |
| `GSI-HISTORY` | 地図・空中写真閲覧サービス | 国土地理院 | `https://service.gsi.go.jp/map-photos/` | 国土地理院利用規約。400dpi高解像度ダウンロードは**無料ユーザーログイン必須**。 | **カタログ取得済・手順整理**：42件のメタデータを取得済。400dpi手動ダウンロード手順を整理。 |
| `KONJAKU` | 今昔マップ on the web | 埼玉大学 谷謙二研究室 | `https://ktgis.net/kjmapw/` | **「画像ファイル自体をPC・サーバ等に保存することは禁止」**と規約に明記。 | **閲覧専用（自動取得厳禁）**：PC保存禁止のためWebブラウザでの目視比較に限定。 |
| `NARO-OLD` | 歴史的農業環境閲覧システム (迅速測図) | 農研機構 | `https://habs.rad.naro.go.jp/` | タイル一括取得禁止。**旧津久井山間部は未作成区域（対象外）と判明**。 | **対象外確認済**：山間部には迅速測図が存在しないため、陸地測量部旧版地形図を最優先とする。 |
| `SAGAMIHARA-TOSHOKAN` | 『ふるさと津久井第3号』・『津久井町史』 | 相模原市立図書館 | 相模原市図書館所蔵 | 館内閲覧・郷土資料複写。 | **調査手順策定済**：津久井図書館・橋本図書館所蔵（請求記号 K1-21）。村絵図・字絵図54点の複写申請手順を整理。 |

---

## 先行研究一覧（P01〜P12 原典監査結果）

書誌データは Google Drive 側 `literature/bibliography/`（`references.bib`, `references.json`, `literature_review.md`）および `reports/bibliography_audit.md` に完全同期。

| ID | 著者・年 | 論文・研究題目 | 一次情報ファクトチェック結果 | DOI / URL | 本文PDF所蔵状況 |
|:---|:---|:---|:---|:---|:---|
| **P01** | 田林 雄（2021） | 畳み込みニューラルネットワークを用いた旧版地形図の地図記号の分類 | 旧版地形図の植生・土地利用記号のCNN画像パッチ分類 (*自然・人間・社会*, 69・70合併号, 43–65)。 | J-GLOBAL: `202102206775677894` | 機関リポジトリ非公開<br>(冊子体所蔵) |
| **P02** | 田林 雄（2026） | 生成AIを用いた旧版地形図の幾何補正 | 2026年春季日本地理学会発表要旨（2026s, 264）。迅速図ジオリファレンスAI。 | `10.14866/ajg.2026s.0_264` | **取得済**<br>(`Tabayashi2026_OldMapGeoreferencingAI.pdf`) |
| **P03** | Wood et al.（2024） | MapReader: Open software for the visual analysis of maps | 歴史地図ラスタの大規模パッチ分割・コンピュータビジョン分析ツール (*J. Open Source Softw.*, 9(98), 6434)。 | `10.21105/joss.06434` | **取得済**<br>(`Wood2024_MapReader.pdf`) |
| **P04** | Berganzo-Besga et al.（2023） | Curriculum learning-based strategy for low-density archaeological mound detection from historical maps in India and Pakistan | 歴史地図からの低密度考古学的遺構（塚・マウンド）自動検出 (*Sci. Rep.*, 13, 11295)。対象地域: インド・パキスタン。 | `10.1038/s41598-023-38190-x` | **取得済**<br>(`Berganzo2023_ArchaeologicalMounds.pdf`) |
| **P05** | Luft & Schiewe（2021） | Automatic content-based georeferencing of historical topographic maps | 道路網・水系網等の特徴量照合による19世紀歴史地図自動ジオリファレンス (*Trans. in GIS*, 25(6), 2888–2906)。 | `10.1111/tgis.12794` | **取得済**<br>(`Luft2021_HistoricalMapGeoreferencing.pdf`) |
| **P06** | Huang et al.（2023） | Leveraging Deep Convolutional Neural Network for Point Symbol Recognition in Scanned Topographic Maps | スキャン地形図上の点記号（鳥居・寺院・学校等）の深層畳み込み認識 (*ISPRS Int. J. Geo-Inf.*, 12(3), 128)。 | `10.3390/ijgi12030128` | オープンアクセス（WAF回避手動取得案内） |
| **P07** | 大倉・布施（2016） | 旧版地形図における地図記号の自動認識 | 近代旧版地形図特有のかすれ・歪み記号の幾何・輪郭特徴抽出（日本写真測量学会秋季学術講演会発表論文集, 99–102）。 | CiNii / JSPRS | 学会要旨（無料公開PDFなし） |
| **P08** | 金木 健（2003） | 消滅集落の分布について：戦後日本における消滅集落発生過程に関する研究 その1 | 日本全国を対象とし、過疎山間部における廃村・消滅集落の立地環境（標高・傾斜・アクセス）の定量的分析 (*日本建築学会計画系論文集*, 68(566), 25–32)。 | `10.3130/aija.68.25_4` | **取得済**<br>(`Kanaki2003_AbandonedSettlements.pdf`) |
| **P09** | 谷 謙二（2017） | 「今昔マップ旧版地形図タイル画像配信・閲覧サービス」の開発 | 旧版地形図のジオリファレンス・時系列タイル配信システム設計 (*GIS-理論と応用*, 25(1), 1–10, 2017-06-30公開)。 | `10.5638/thagis.25.1` | **取得済**<br>(`Tani2017_KonjakuMap.pdf`) |
| **P10** | 藤田 直子・熊谷 洋一（2007） | GIS解析による都市における神社・寺院・公園の立地地点の分布形態の差異に関する研究 | 東京都23区部を対象とし、神社・寺院の立地環境特性を点パターン・空間統計解析した基本論文 (*景観生態学*, 12(1), 9–21)。 | `10.5738/jale.12.9` | **取得済**<br>(`Fujita2007_ShrineLocationGIS.pdf`) |
| **P11** | 小田 匡保・柳光 里香（2015） | 神社合祀と地域社会―三重県松阪市飯南・飯高地区を事例に― | 三重県松阪市山間過疎地域における明治末期神社合祀・社地廃絶の空間的変容分析（日本地理学会発表要旨集, 2015s, 100229）。 | `10.14866/ajg.2015s.0_100229` | **取得済**<br>(`Oda2015_ShrineMerger.pdf`) |
| **P12** | （旧 Uhl et al. 2022） | 架空引用（DOI 10.1080/13658816.2022.2038751） | 以前のAI生成によるハルシネーション（存在しないDOI・論文）と判明。**書誌から除外・保留**。 | - | **除外**（架空文献排除） |
| **参考** | Buchi et al.（2024） | Georeferencing of historic maps using neural networks | 歴史地図自動ジオリファレンスの最新CNNフレームワーク (*ISPRS J. Photogramm. Remote Sens.*, 215, 237–251)。 | `10.1016/j.isprsjprs.2024.06.012` | 有料購読（将来候補） |

---

## 調査倫理・法令遵守の原則

1. **廃墟の断定禁止**: 古地図で神社・寺院・集落が存在し現代地図に見当たらない場合でも、直ちに「廃墟」と断定しない（合祀・移転・非公開文化財・個人所有地・祭祀継続の可能性）。
2. **私有地立入・危険箇所の非推奨**: 私有地への無断侵入、危険な廃建造物への立ち入りを助長する行為は厳禁。
3. **個人情報の保護**: 個人の住居・別荘を廃墟候補と誤認し、正確な番地や氏名を公開しない。
4. **測地系（CRS）の混同禁止**: JGD2000, JGD2011, WGS84, JGD2024 等の異なる測地成果を推測で統合せず、データごとにメタデータを完全記録する。