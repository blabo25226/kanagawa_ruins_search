# Phase 0.2 データ・文献収集および品質改善完了レポート

- **プロジェクト名**: 神奈川県廃墟調査プロジェクト
- **フェーズ**: Phase 0.2（データ・文献の追加収集と品質改善）
- **実施日時**: 2026-10-09 23:55 JST
- **担当エージェント**: Gemini 3.8 Flash
- **レビュアー**: GPT-5.6 Sol High
- **正規データ保存先**: Google Drive `$RUINS_DATA_ROOT` (`/home/blabo/gdrive/kanagawa_ruins_search_databank/data/`)

---

## 1. 実施概要と達成状況

Phase 0.2では、将来のPhase 1本格解析（古地図と現代地図の照合、遺構抽出）に向け、無料で合法的に入手可能なGISデータ・歴史資料・学術論文を網羅的に収集し、既存データの問題修正と安全性の向上を実施した。

### 主な達成事項
1. **OSM取得範囲の根本修正と4地区完全網羅**:
   - 従来の狭小BBOXを廃止し、初期対象4地区（寸沢嵐・鳥屋・青山・青野原）の個別BBOXを特定。
   - 4地区のOSM XML（計3,578万bytes）を完全取得し、神社11件、寺院1件、歴史地物21件、道路・歩道・建物を抽出、`raw/osm/tsukui_4districts_metadata.json` を生成。
2. **CODH歴史的行政区域の旧津久井郡全町網羅**:
   - 既存の津久井町に加え、寸沢嵐が属していた旧相模湖町、旧城山町、旧藤野町の境界GeoJSONを完全取得。
3. **歴史史料のIIIFマニフェスト取得**:
   - NDLデジタルコレクションより、対象4地区の風土記・神社・小名を網羅する『新編相模国風土記稿 第5輯 三浦・津久井郡』（明治21年刊、パブリックドメイン、PID 763971）の全324コマ IIIFマニフェストを取得。
4. **学術論文オープンアクセスPDFの収集とファクトチェック**:
   - J-STAGEおよびNature Scientific Reportsより、P04（Berganzo 2023）、P08（金木 2003）、P09（谷 2017）、P10（藤田・熊谷 2007）、P11（小田・柳光 2015）のオープンアクセスPDFを取得（P03 MapReaderと合わせ計6件のPDFを保管）。
   - 田林（2021）[P01]の分類対象（鳥居ではなく植生・土地利用記号である点）、小田・柳光（2015）[P11]の対象地域（神奈川県ではなく三重県松阪市飯南・飯高地区である点）の誤りを完全に訂正。
5. **ダウンロード処理の安全性強化と単体テスト拡充**:
   - `scripts/fetch_sources.py` に厳格なファイル整合性検証（ZIP CRC、PDF EOF、JSON/XML構文チェック）、Zip Bomb/Zip Slip防止機能、中断 `.partial` ファイルの安全退避機能を実装。
   - 単体テスト14件全パスを確認。
6. **全データの品質・整合性検証**:
   - GeoPandas、Rasterio、GDALを用いた全GISレイヤの読み込み検査（`scripts/validate_databank.py`）を実施し、`reports/data_validation_report.md` を生成。欠損ジオメトリなしを確認。

---

## 2. Google Drive データバンク保存状況一覧

総ファイル数: **24データファイル + 3書誌ファイル + 4ドキュメント + 1来歴台帳**  
総データ容量: **約 125 MB**（Google Drive側） / ローカルリポジトリ使用量: **約 1.5 MB**（1GB以内厳守）

```text
kanagawa_ruins_search_databank/data/
├── raw/
│   ├── administrative/
│   │   ├── 14151.zip                     (国土地理院 住居表示 緑区, 1.67MB)
│   │   └── N03-20260101_14_GML.zip       (国土数値情報 行政区域 2026年, 5.37MB)
│   ├── historical_boundaries/
│   │   ├── N03-140401_14_GML.zip         (国土数値情報 過去行政区域 2014年, 1.86MB)
│   │   ├── codh_tsukui_19551001.geojson  (CODH 津久井町 1955年合併時, 137KB)
│   │   ├── codh_tsukui_20050101.geojson  (CODH 津久井町 2005年編入直前, 137KB)
│   │   ├── codh_sagamiko_20050101.geojson(CODH 相模湖町 2005年編入前 [寸沢嵐], 96KB)
│   │   ├── codh_shiroyama_20050101.geojson(CODH 城山町 2005年編入前, 52KB)
│   │   └── codh_fujino_20050101.geojson  (CODH 藤野町 2005年編入前, 53KB)
│   ├── landuse/
│   │   └── L03-b-14_5339-jgd_GML.zip     (国土数値情報 土地利用 2021年 5339メッシュ, 13.3MB)
│   ├── rivers/
│   │   └── W05-08_14_GML.zip             (国土数値情報 河川データ 神奈川県, 1.91MB)
│   ├── railways/
│   │   └── N02-23_GML.zip                (国土数値情報 鉄道データ 2023年, 17.5MB)
│   ├── osm/
│   │   ├── tsukui_core_osm.osm           (旧コア抽出, 5.83MB)
│   │   ├── tsukui_suarashi_osm.osm       (寸沢嵐地区網羅, 11.77MB)
│   │   ├── tsukui_toya_osm.osm           (鳥屋地区網羅, 6.24MB)
│   │   ├── tsukui_aoyama_osm.osm         (青山地区網羅, 10.94MB)
│   │   ├── tsukui_aonohara_osm.osm       (青野原地区網羅, 6.83MB)
│   │   └── tsukui_4districts_metadata.json(4地区地物統計メタデータ, 3KB)
│   ├── cultural_properties/
│   │   ├── bunkazai.csv                  (相模原市文化財一覧 CSV, 210KB)
│   │   └── kanagawa_bunkazai_mokuroku_r07.pdf (神奈川県指定文化財目録 令和7年版, 5.55MB)
│   └── historical_maps/
│       └── README.md                     (旧版地図・迅速測図・今昔マップ規約方針)
│
├── literature/
│   ├── papers/
│   │   ├── Wood2024_MapReader.pdf        (P03: MapReader JOSS OA論文, 448KB)
│   │   ├── Berganzo2023_ArchaeologicalMounds.pdf (P04: Nature Sci Rep OA論文, 3.94MB)
│   │   ├── Kanaki2003_AbandonedSettlements.pdf   (P08: 建築学会 消滅集落 OA論文, 1.61MB)
│   │   ├── Tani2017_KonjakuMap.pdf       (P09: GIS理論と応用 今昔マップ OA論文, 4.69MB)
│   │   ├── Fujita2007_ShrineLocationGIS.pdf (P10: 景観生態学 神社GIS OA論文, 2.91MB)
│   │   └── Oda2015_ShrineMerger.pdf      (P11: 日本地理学会 神社合祀 OA論文, 177KB)
│   ├── historical_documents/
│   │   ├── Shinpen_Sagami_Fudokiko_Vol5_IIIF_manifest.json (新編相模国風土記稿 第5輯 全324コマ, 190KB)
│   │   └── README.md                     (風土記稿 津久井各村収録巻・コマ対照表)
│   ├── catalogs/
│   │   ├── rekishishiryoushozaimokuroku14-4-1.pdf (公文書館 津久井郡歴史資料所在目録, 8.15MB)
│   │   └── pdflist_wakayanagi.pdf        (公文書館 若柳村文書目録, 54KB)
│   └── bibliography/
│       ├── references.bib                (ファクトチェック済 BibTeX)
│       ├── references.json               (ファクトチェック済 JSONメタデータ)
│       └── literature_review.md          (先行研究レビュー改訂版)
│
├── processed/
│   └── README.md                         (Phase 1以降の中間成果保存用)
└── provenance.jsonl                      (完全来歴台帳)
```

---

## 3. 重複データ確認結果（削除候補の提示）

Google Drive内のハッシュ照合（SHA-256）の結果、以下の同一ファイル重複を確認した。  
ユーザー指示に基づき今回は削除せず、正規保存先を定義した上で削除候補として記録する。

1. **`14151.zip` (SHA256: `a72352712494...`)**:
   - **正規保存先**: `raw/administrative/14151.zip`
   - **削除候補**: `raw/administrative/gsi_jusho_midori/14151.zip`, `raw/gsi_jusho_midori/14151.zip`
2. **`bunkazai.csv` (SHA256: `dec1117a2186...`)**:
   - **正規保存先**: `raw/cultural_properties/bunkazai.csv`
   - **削除候補**: `raw/cultural_properties/sagamihara_cultural_assets/bunkazai.csv`, `raw/sagamihara_cultural_assets/bunkazai.csv`

---

## 4. Phase 1に向けた今後必要なデータとアクション

1. **国土地理院 旧版地形図の正規交付申請（人間による実施）**:
   - 謄本交付（TIFF画像）にて、対象4地区の図幅（「青野原」「八王子」「五日市」等）の交付申請を行う。
2. **基盤地図情報 DEMの取得（人間による実施）**:
   - 無料利用者登録の上、相模原市緑区の5m/10mメッシュDEMをダウンロードし `raw/dem/` へ配置。
3. **GIS解析パイプラインの座標系統一（Phase 1開発）**:
   - JGD2011/2000およびWGS84から**平面直角座標系 第IX系（JGD2011 / EPSG:6677）**への自動投影変換パイプラインを実装する。
