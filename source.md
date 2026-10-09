# 公式・歴史地理データソース台帳（2026-10-09更新）

目的: 入手先の検討・利用条件の記録。**出典の掲載≠自動収集の許可**。ここにあるURLを網羅的にスクレイピングしない。  
自動取得の対象は `config/sources.toml` で限定し、ダウンロードデータはすべて Google Drive 上の `$RUINS_DATA_ROOT`（`kanagawa_ruins_search_databank/data/`）へ保存する。

---

## データ保存場所とストレージ管理方針

生データ・地理空間データ・文献資料は、すべて Google Drive 上の正規ストレージ（環境変数 `RUINS_DATA_ROOT`）に以下のディレクトリ階層で安全に格納・管理する。ローカルリポジトリには一切の大容量データを保存・コミットしない（1GB以内厳守）。

```text
kanagawa_ruins_search_databank/
└── data/
    ├── raw/
    │   ├── administrative/        # 行政区域・住居表示（D01, D03）
    │   ├── historical_boundaries/ # 過去行政区域・自治体境界変遷（D04, D05）
    │   ├── landuse/               # 土地利用メッシュデータ（D07, D08, D09）
    │   ├── rivers/                # 河川・水系データ（D11）
    │   ├── railways/              # 鉄道・交通データ（D10）
    │   ├── osm/                   # OpenStreetMap 抽出データ（D06）
    │   ├── cultural_properties/   # 文化財・史跡台帳（D02, D12）
    │   └── historical_maps/       # 旧版地形図・歴史地図（Phase 0は閲覧・規約整理のみ）
    │
    ├── literature/
    │   ├── papers/                # 関連研究論文 PDF（P03等 オープンアクセス）
    │   ├── historical_documents/  # 歴史史料・地誌文献（NDLデジタル等）
    │   ├── catalogs/              # 公文書館・史料所在目録（D13, D14）
    │   └── bibliography/          # 書誌情報（P01〜P11 BibTeX / JSON / Review）
    │
    ├── processed/                 # Phase 1以降の中間成果・解析結果
    └── provenance.jsonl           # 取得全ファイルの完全来歴台帳（SHA-256）
```

---

## データソース一覧（D01〜D15）

| ID | データ名 | 提供元 | 対象地域・年代 | データ形式 | 推定容量 | ライセンス・利用条件 | 保存先パス | 実施状況 |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| **D01** | 住居表示住所（緑区） | 国土地理院 | 相模原市緑区<br>(2025年版) | ZIP (CSV + Shapefile) | 1.67 MB | 国土地理院利用規約（CC BY 4.0互換）。現代の字名・番地・集落位置の参考。神社の現存判定には直接使用しない。 | `raw/administrative/14151.zip` | **取得済み**<br>(SHA-256検証済) |
| **D02** | 文化財一覧 CSV | 相模原市 | 相模原市全域<br>(現代) | CSV (UTF-8) | 210 KB | 相模原市オープンデータ（CC BY 4.0）。指定文化財照合の参考データ。現存神社完全除外DBではない。 | `raw/cultural_properties/bunkazai.csv` | **取得済み**<br>(SHA-256検証済) |
| **D03** | 行政区域 N03 2026年 | 国土交通省 | 神奈川県全域<br>(2026年) | ZIP (GML/Shapefile) | 5.37 MB | 国土数値情報利用規約（CC BY 4.0互換）。出典明記要。最新の市町村・区境界。 | `raw/administrative/N03-20260101_14_GML.zip` | **取得済み**<br>(自動取得検証済) |
| **D04** | 過去の行政区域 N03 | 国土交通省 | 神奈川県全域<br>(2014年版) | ZIP (GML/Shapefile) | 1.86 MB | 国土数値情報利用規約（CC BY 4.0互換）。合併前後の自治体境界対照。 | `raw/historical_boundaries/N03-140401_14_GML.zip` | **取得済み**<br>(自動取得検証済) |
| **D05** | 歴史的行政区域データセット | 人文学オープンデータ共同利用センター (CODH) | 旧津久井町<br>(1955年/2005年) | GeoJSON | 各約137 KB | CODH利用規約（CC BY 4.0）。町村合併変遷のポリゴンデータ。 | `raw/historical_boundaries/codh_tsukui_*.geojson` | **取得済み**<br>(自動取得検証済) |
| **D06** | OpenStreetMap (津久井コア) | OpenStreetMap 貢献者 | 青野原・青山・鳥屋・寸沢嵐<br>(現代) | XML (.osm) | 約1.5 MB | ODbL 1.0（OpenStreetMap 貢献者）。現代の道路・水系・ランドマーク。 | `raw/osm/tsukui_core_osm.osm` | **取得済み**<br>(自動取得検証済) |
| **D07** | 土地利用細分メッシュ（過去） | 国土交通省 | 神奈川県・首都圏<br>(昭和50年代等) | ZIP (GML/SHP) | 数十MB | 国土数値情報利用規約（CC BY 4.0互換）。過去の山林・集落の境界変遷。 | `raw/landuse/` | **保留（選定中）**<br>年代精査後取得 |
| **D08** | 土地利用細分メッシュ 2021年 | 国土交通省 | 5339メッシュ<br>(相模原・津久井地域) | ZIP (GML/Shapefile) | 13.3 MB | 国土数値情報利用規約（CC BY 4.0互換）。現代の森林・宅地・農地メッシュ。 | `raw/landuse/L03-b-14_5339-jgd_GML.zip` | **取得済み**<br>(自動取得検証済) |
| **D09** | 土地利用詳細メッシュ | 国土交通省 | 首都圏・神奈川県 | ZIP | 数十MB | 国土数値情報利用規約（CC BY 4.0互換）。山間部のカバー状況要確認。 | `raw/landuse/` | **要カバー確認**<br>山間部精査 |
| **D10** | 鉄道データ N02 2023年 | 国土交通省 | 全国/神奈川県<br>(2023年) | ZIP (GML/Shapefile) | 17.5 MB | 国土数値情報利用規約（CC BY 4.0互換）。近世・近代交通路との対照。 | `raw/railways/N02-23_GML.zip` | **取得済み**<br>(自動取得検証済) |
| **D11** | 河川データ W05 | 国土交通省 | 神奈川県全域<br>(2008年) | ZIP (GML/Shapefile) | 1.91 MB | 国土数値情報利用規約（CC BY 4.0互換）。相模川・道志川水系の流路ポリライン。 | `raw/rivers/W05-08_14_GML.zip` | **取得済み**<br>(自動取得検証済) |
| **D12** | 神奈川県指定等文化財目録 | 神奈川県 | 神奈川県全域<br>(令和7年3月版) | PDF | 5.55 MB | 神奈川県オープンデータ（CC BY 4.0準拠）。県指定史跡・有形文化財等の公式一覧。 | `raw/cultural_properties/kanagawa_bunkazai_mokuroku_r07.pdf` | **取得済み**<br>(自動取得検証済) |
| **D13** | 歴史資料所在目録（旧津久井郡編） | 神奈川県立公文書館 | 旧津久井郡全域<br>(第14集第4分冊) | PDF | 8.15 MB | 神奈川県立公文書館 公開資料。旧津久井郡地域の古文書・神社資料所在調査。 | `literature/catalogs/rekishishiryoushozaimokuroku14-4-1.pdf` | **取得済み**<br>(学術調査利用) |
| **D14** | 古文書・私文書資料群一覧 | 神奈川県立公文書館 | 相模原市緑区（若柳村等） | PDF | 54 KB | 神奈川県立公文書館 公開目録。地域所蔵史料（村方文書・神社関連等）。 | `literature/catalogs/pdflist_wakayanagi.pdf` | **取得済み**<br>(学術調査利用) |
| **D15** | 次世代デジタルライブラリー OCR | 国立国会図書館 (NDL) | 神奈川県・旧津久井郡関連文献 | JSON / API | 資料毎 | 著作権保護期間満了資料（パブリックドメイン）。NDL Lab OCR テキスト API。 | `literature/historical_documents/` | **調査済み**<br>Phase 1資料選定 |

---

## 閲覧専用・手動確認データソース一覧（規約遵守）

| ID | データ名 | 提供元 | URL | 利用規約上の重要制約 | Phase 0対応方針 |
|:---|:---|:---|:---|:---|:---|
| `GSI-FGD` | 基盤地図情報 (DEM・基本項目) | 国土地理院 | `https://service.gsi.go.jp/kiban/` | 無料だが**利用者登録（アカウント認証）が必須**。JGD2024移行に留意。 | **保留（未取得）**：エージェントによる無断登録・認証回避は厳禁。手動取得待ち。 |
| `GSI-HISTORY` | 地図・空中写真閲覧サービス | 国土地理院 | `https://service.gsi.go.jp/map-photos/app/` | 国土地理院利用規約。**高画質閲覧画面のキャプチャ保存・一括スクレイピングは厳禁**。 | **保留（Web閲覧のみ）**：調査対象地絞り込み後に必要図幅の正式交付申請を検討。 |
| `GSI-OLDMAP` | 旧版地図等の交付 | 国土地理院 | `https://web1.gsi.go.jp/MAP/HISTORY/koufu.html` | 測量成果の交付手続き・規約。申請・謄本交付手続きが必要。 | **保留（未取得）**：Phase 0では手続きを行わない。 |
| `GSI-TILES` | 地理院タイル（標準・淡色・陰影） | 国土地理院 | `https://maps.gsi.go.jp/help/use.html` | 地理院タイル利用規約。広域一括・連続ダウンロード禁止。 | **オンライン参照のみ**：一括ダウンロードは行わない。 |
| `NARO-OLD` | 歴史的農業環境閲覧システム (迅速測図) | 農研機構 | `https://habs.rad.naro.go.jp/` | 原則 CC BY 2.1 JP。**タイル一括取得禁止**。約100mの測量誤差留意。 | **保留（Web閲覧のみ）**：相模原市緑区山間部のカバー状況を事前確認。 |
| `KONJAKU` | 今昔マップ on the web | 埼玉大学 谷謙二研究室 | `https://ktgis.net/kjmapw/` | **「画像ファイル自体をPC・サーバ等に保存することは禁止」**と規約に明記。 | **閲覧専用（自動取得厳禁）**：PC保存禁止のためWebブラウザでの目視比較に限定。 |
| `SAGAMIHARA-GIS` | さがみはら地図情報 | 相模原市 | `https://www.city.sagamihara.kanagawa.jp/` | 閲覧用WebGISサービス。一括ダウンロードAPIなし。津久井地域の一部未提供エリアあり。 | **閲覧のみ**：埋蔵文化財包蔵地の参考。 |

---

## 先行研究一覧（P01〜P11）

書誌データは Google Drive 側 `literature/bibliography/`（`references.bib`, `references.json`, `literature_review.md`）に整備・保管。

| ID | 著者・年 | 論文・研究題目 | 今回の用途・技術的意義 | DOI / URL | 配布・保存状況 |
|:---|:---|:---|:---|:---|:---|
| **P01** | 田林（2021） | 旧版地形図におけるCNN記号分類 | 旧版地形図における畳み込みニューラルネットワークを用いた地図記号分類アルゴリズム | `https://cir.nii.ac.jp/crid/1050287297266629376` | 書誌記録 (`references.bib`) |
| **P02** | 田林（2026） | 生成AIを用いた旧版地形図の幾何補正 | 生成AI / マルチモーダルモデルを用いた古地図と現代地図の高精度自動アライメント | `10.14866/ajg.2026s.0_264` | 書誌記録 (`references.bib`) |
| **P03** | Wood et al.（2024） | MapReader: A Python package for inspecting large geospatial raster maps | 歴史地図ラスタの大規模パッチ分割・画像認識・CVパイプライン構築（OSS） | `10.21105/joss.06434` | **論文PDF取得済**<br>(`literature/papers/`) |
| **P04** | Berganzo-Besga et al.（2023） | Deep learning for historical map analysis: Automated detection of archaeological mounds | 歴史地図からの考古学的遺構・塚の深層学習自動検出（Nature Scientific Reports） | `10.1038/s41598-023-38190-x` | 書誌記録 (`references.bib`) |
| **P05** | Luft & Schiewe（2021） | Automatic content-based georeferencing of historical maps using computer vision | 道路網・水系網の特徴照合に基づく古地図の自動ジオリファレンス | `10.1111/tgis.12794` | 書誌記録 (`references.bib`) |
| **P06** | Huang et al.（2023） | Point Symbol Recognition in Scanned Topographic Maps Based on YOLOv5 | スキャン地形図上の点記号（鳥居・寺院・学校等）の物体検出と特徴抽出 | `10.3390/ijgi12030128` | 書誌記録 (`references.bib`) |
| **P07** | 大倉・布施（2016） | 旧版地形図における機械学習を用いた地図記号の自動認識 | 日本の旧版地形図特有の図式・手書きフォント・かすれ記号の抽出処理 | `https://jglobal.jst.go.jp/detail?JGLOBAL_ID=201602214144038318` | 書誌記録 (`references.bib`) |
| **P08** | 金木（2003） | 消滅集落の分布について：山間過疎地域における集落の空間構造と変容 | 旧津久井郡山間部における廃村・消滅集落の立地環境（標高・水系・傾斜）分析 | `10.3130/aija.68.25_4` | 書誌記録 (`references.bib`) |
| **P09** | 谷（2017） | 時系列地形図閲覧システム「今昔マップ on the web」の開発と公開 | 迅速測図・時系列地形図の幾何補正・タイル座標系設計の知見 | `10.5638/thagis.25.1` | 書誌記録 (`references.bib`) |
| **P10** | 藤田・熊谷（2007） | GISを用いた神社・寺院の立地環境と地域景観構造の定量的解析 | 神社・寺院の立地環境（標高・尾根・谷・集落中心距離）の空間統計モデル | `10.5738/jale.12.9` | 書誌記録 (`references.bib`) |
| **P11** | 小田・柳光（2015） | 明治期神社合祀令と地域社会の変容：神奈川県下の事例を中心に | 神奈川県下における明治末期の神社合祀・社地廃絶の歴史的背景と旧社地の特定手法 | `10.14866/ajg.2015s.0_100229` | 書誌記録 (`references.bib`) |

---

## 調査倫理・法令遵守の原則

1. **廃墟の断定禁止**: 古地図で神社・寺院・集落が存在し現代地図に見当たらない場合でも、直ちに「廃墟」と断定しない（合祀・移転・非公開文化財・個人所有地・祭祀継続の可能性）。
2. **私有地立入・危険箇所の非推奨**: 私有地への無断侵入、危険な廃建造物への立ち入りを助長する行為は厳禁。
3. **個人情報の保護**: 個人の住居・別荘を廃墟候補と誤認し、正確な番地や氏名を公開しない。
4. **測地系（CRS）の混同禁止**: JGD2000, JGD2011, JGD2024 等の異なる測地成果を推測で統合せず、データごとにメタデータを完全記録する。