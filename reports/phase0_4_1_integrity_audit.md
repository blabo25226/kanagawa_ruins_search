# Phase 0.4.1 データ整合性・実ファイル完全照合監査レポート

**プロジェクト**: 神奈川県廃墟調査プロジェクト（Kanagawa Ruins Search Project）  
**監査実施日時（UTC）**: 2026-10-10T06:33:00.341817+00:00  
**対象フェーズ**: Phase 0.4.1（データ整合性・文献情報の最終修正）  
**担当エージェント**: Gemini 3.8 Flash  
**レビュー担当**: GPT-5.6 Sol High  
**データ保存先**: `/home/blabo/gdrive/kanagawa_ruins_search_databank/data` (`$RUINS_DATA_ROOT`)  

---

## 1. 監査概要と総合判定

Phase 0.4におけるデータ収集成果に対して、Google Driveストレージ上の全実ファイルと来歴台帳（`provenance.jsonl`）の1対1照合およびSHA-256ハッシュ値の独立再計算による完全監査を実施した（監査モード: **FULL**）。

### 総合判定: **完全整合（PASS - 100% 整合確認済）**

- **台帳登録資産数**: 53件（全件ディスク上に実在、サイズ一致率 100%、ハッシュ一致率 100%）
- **サイズ不一致**: **0件**
- **ハッシュ値不一致**: **0件**
- **欠損ファイル**: **0件**
- **未登録・不明ファイル**: **0件**（台帳外ファイルは既知の初期重複ファイル4件、メタデータ/解題ファイル7件、台帳自身1件として完全に特定・分類）

---

## 2. ストレージ容量とファイル内訳の厳密な定義

ストレージ容量の単位解釈の齟齬を排除するため、十進数（Decimal: $10^6$）および二進数（Binary: $2^{20}$）の双方をバイト単位で正確に記録する。

| 項目 | 値 | 単位・基準 |
|:---|---:|:---|
| **総実ファイル数** | **65** | ファイル |
| **総データ容量（バイト）** | **1,279,520,259** | Bytes (厳密値) |
| **十進表記容量 (MB)** | **1279.52** | MB ($10^6$ Bytes) |
| **二進表記容量 (MiB / GiB)** | **1220.25** / **1.192** | MiB ($2^20$ Bytes) / GiB ($2^30$ Bytes) |
| **ローカルリポジトリ容量** | **約 2.2** | MB (1GB以内制限を完全に遵守) |

### 65実ファイルの内訳分類

```text
kanagawa_ruins_search_databank/data/ (合計 65 ファイル)
├── [53件] provenance.jsonl に記録された正規ダウンロード資産
├── [ 4件] Phase 0 初期ダウンロード時の重複保持ファイル（raw保存規約に基づき保持）
├── [ 7件] メタデータ・解題・文献レビュー・READMEファイル
└── [ 1件] 取得来歴台帳自身 (provenance.jsonl)
```

1. **正規ダウンロード資産（53件）**:
   - 行政境界データ（N03 2026年 神奈川/東京/山梨/静岡、2014年神奈川、CODH津久井郡旧4町GeoJSON等）
   - 土地利用細分メッシュ（L03-b 1976/2014/2021年 5338/5339メッシュ計6件）
   - 河川水系データ（W05 神奈川/東京/山梨/静岡）
   - 鉄道網データ（N02 全国）
   - OpenStreetMap（津久井4地区個別XML 4件、Geofabrik 関東PBF/中部PBF 2件）
   - 文化財・遺跡データ（相模原市文化財CSV、P32全国・県別4件、東京都史跡CSV、相模原市埋蔵文化財包蔵地一覧PDF）
   - 昭和期空中写真（津久井4地区42件カタログJSON、1974年オルソ画像タイル4件）
   - 学術研究論文（P02, P03, P04, P05, P08, P09, P10, P11 のPDF計8本）
   - 地域公文書・歴史資料目録（新編相模国風土記稿IIIFマニフェスト、津久井郡歴史資料所在目録PDF、若柳村文書目録PDF）
2. **初期重複保持ファイル（4件）**:
   - `raw/administrative/14151.zip` (正規ターゲット: `raw/gsi_jusho_midori/14151.zip` と同一内容)
   - `raw/administrative/gsi_jusho_midori/14151.zip` (正規ターゲット: `raw/gsi_jusho_midori/14151.zip` と同一内容)
   - `raw/cultural_properties/bunkazai.csv` (正規ターゲット: `raw/sagamihara_cultural_assets/bunkazai.csv` と同一内容)
   - `raw/cultural_properties/sagamihara_cultural_assets/bunkazai.csv` (正規ターゲット: `raw/sagamihara_cultural_assets/bunkazai.csv` と同一内容)
   - *方針*: プロジェクト基本規律「Google Drive上のrawデータの無断削除禁止」を遵守し、消去せず重複として監査台帳に記録。
3. **メタデータ・解題ファイル（7件）**:
   - `literature/bibliography/literature_review.md`
   - `literature/bibliography/references.bib`
   - `literature/bibliography/references.json`
   - `literature/historical_documents/README.md`
   - `processed/README.md`
   - `raw/historical_maps/README.md`
   - `raw/osm/tsukui_4districts_metadata.json`
4. **取得来歴台帳自身（1件）**:
   - `provenance.jsonl` (各資産のSHA-256、サイズ、URL、取得時刻、ライセンスの来歴記録)

---

## 3. SHA-256 ハッシュ値独立検証結果（全53件）

全53件の登録資産について、Google Driveマウント上の実ファイルからSHA-256を独立再計算し、`provenance.jsonl`の記録値と完全に一致することを確認した。

| No. | 管理識別子 | 相対パス | 実ファイルサイズ (Bytes) | 算出SHA-256 (先頭16桁) | 検証結果 |
|:---:|:---|:---|---:|:---|:---:|
| 1 | `gsi_jusho_midori` | `raw/gsi_jusho_midori/14151.zip` | 1,672,520 | `a72352712494a1c5` | 一致 (PASS) |
| 2 | `sagamihara_cultural_assets` | `raw/sagamihara_cultural_assets/bunkazai.csv` | 210,799 | `dec1117a21869988` | 一致 (PASS) |
| 3 | `mlit_n03_2026_kanagawa` | `raw/administrative/N03-20260101_14_GML.zip` | 5,370,610 | `27ab5aa2982fc6fe` | 一致 (PASS) |
| 4 | `mlit_n03_2014_kanagawa` | `raw/historical_boundaries/N03-140401_14_GML.zip` | 1,860,243 | `b9f236d3512a9b96` | 一致 (PASS) |
| 5 | `codh_tsukui_1955` | `raw/historical_boundaries/codh_tsukui_19551001.geojson` | 137,132 | `d2105725065d8b2f` | 一致 (PASS) |
| 6 | `codh_tsukui_2005` | `raw/historical_boundaries/codh_tsukui_20050101.geojson` | 136,875 | `85b4f3ef11efd936` | 一致 (PASS) |
| 7 | `osm_tsukui_core` | `raw/osm/tsukui_core_osm.osm` | 5,834,482 | `8bea6721aefe13b3` | 一致 (PASS) |
| 8 | `mlit_landuse_2021_5339` | `raw/landuse/L03-b-14_5339-jgd_GML.zip` | 13,314,929 | `b72e1446cb2ab067` | 一致 (PASS) |
| 9 | `mlit_railways_2023` | `raw/railways/N02-23_GML.zip` | 17,518,918 | `e91ecdee90966877` | 一致 (PASS) |
| 10 | `mlit_rivers_kanagawa` | `raw/rivers/W05-08_14_GML.zip` | 1,908,537 | `8a553d8c3aa3a43d` | 一致 (PASS) |
| 11 | `kanagawa_cultural_properties_catalog` | `raw/cultural_properties/kanagawa_bunkazai_mokuroku_r07.pdf` | 5,545,067 | `b7c5294ec088af04` | 一致 (PASS) |
| 12 | `kanagawa_archives_tsukui_catalog` | `literature/catalogs/rekishishiryoushozaimokuroku14-4-1.pdf` | 8,153,399 | `6c8f05077508427d` | 一致 (PASS) |
| 13 | `kanagawa_archives_wakayanagi_list` | `literature/catalogs/pdflist_wakayanagi.pdf` | 53,950 | `e57f983037ed2346` | 一致 (PASS) |
| 14 | `paper_wood2024_mapreader` | `literature/papers/Wood2024_MapReader.pdf` | 447,699 | `e6ecce73e73152fa` | 一致 (PASS) |
| 15 | `codh_sagamiko_2005` | `raw/historical_boundaries/codh_sagamiko_20050101.geojson` | 96,324 | `8bf187d34be07ee3` | 一致 (PASS) |
| 16 | `codh_shiroyama_2005` | `raw/historical_boundaries/codh_shiroyama_20050101.geojson` | 51,611 | `077da437650f0442` | 一致 (PASS) |
| 17 | `codh_fujino_2005` | `raw/historical_boundaries/codh_fujino_20050101.geojson` | 52,534 | `027f60212dd1465a` | 一致 (PASS) |
| 18 | `osm_tsukui_toya` | `raw/osm/tsukui_toya_osm.osm` | 6,241,979 | `b380bc65f6d8a2c8` | 一致 (PASS) |
| 19 | `osm_tsukui_aonohara` | `raw/osm/tsukui_aonohara_osm.osm` | 6,828,635 | `ed6961c5a73313d5` | 一致 (PASS) |
| 20 | `ndl_shinpen_sagami_vol5` | `literature/historical_documents/Shinpen_Sagami_Fudokiko_Vol5_IIIF_manifest.json` | 190,030 | `1ecfb5457453b4ca` | 一致 (PASS) |
| 21 | `paper_kanaki2003_abandoned` | `literature/papers/Kanaki2003_AbandonedSettlements.pdf` | 1,606,333 | `a5bde654b76c2d1b` | 一致 (PASS) |
| 22 | `paper_tani2017_konjaku` | `literature/papers/Tani2017_KonjakuMap.pdf` | 4,689,607 | `64a1c2988d014024` | 一致 (PASS) |
| 23 | `paper_fujita2007_shrine_gis` | `literature/papers/Fujita2007_ShrineLocationGIS.pdf` | 2,908,569 | `c2593cb87354b4a8` | 一致 (PASS) |
| 24 | `paper_oda2015_shrine_merger` | `literature/papers/Oda2015_ShrineMerger.pdf` | 176,791 | `cef264d5e4df26c1` | 一致 (PASS) |
| 25 | `osm_tsukui_suarashi` | `raw/osm/tsukui_suarashi_osm.osm` | 11,774,956 | `753f3a4afea6312a` | 一致 (PASS) |
| 26 | `osm_tsukui_aoyama` | `raw/osm/tsukui_aoyama_osm.osm` | 10,936,667 | `2cee8ec50206676e` | 一致 (PASS) |
| 27 | `paper_berganzo2023_mounds` | `literature/papers/Berganzo2023_ArchaeologicalMounds.pdf` | 3,943,985 | `e64eca11c9c77e07` | 一致 (PASS) |
| 28 | `mlit_n03_2026_tokyo` | `raw/administrative/N03-20260101_13_GML.zip` | 13,153,227 | `94f10b26256566db` | 一致 (PASS) |
| 29 | `mlit_n03_2026_yamanashi` | `raw/administrative/N03-20260101_19_GML.zip` | 3,642,283 | `ecb815857ced4ef4` | 一致 (PASS) |
| 30 | `mlit_n03_2026_shizuoka` | `raw/administrative/N03-20260101_22_GML.zip` | 13,592,970 | `a10ed331f67a75f2` | 一致 (PASS) |
| 31 | `mlit_rivers_tokyo` | `raw/rivers/W05-08_13_GML.zip` | 1,406,220 | `7e1d7907855e4560` | 一致 (PASS) |
| 32 | `mlit_rivers_yamanashi` | `raw/rivers/W05-08_19_GML.zip` | 3,911,147 | `d73f3fcf9e47dbc5` | 一致 (PASS) |
| 33 | `mlit_rivers_shizuoka` | `raw/rivers/W05-08_22_GML.zip` | 6,786,401 | `c293f5ff4f183f13` | 一致 (PASS) |
| 34 | `mlit_cultural_properties_nationwide` | `raw/cultural_properties/P32-14_00_GML.zip` | 2,032,153 | `debc5f00123ab608` | 一致 (PASS) |
| 35 | `geofabrik_kanto` | `raw/osm/kanto-latest.osm.pbf` | 517,645,146 | `d128943f6cebc6bc` | 一致 (PASS) |
| 36 | `geofabrik_chubu` | `raw/osm/chubu-latest.osm.pbf` | 511,655,965 | `14056311e5086850` | 一致 (PASS) |
| 37 | `mlit_cultural_properties_kanagawa` | `raw/cultural_properties/P32-14_14_GML.zip` | 37,598 | `032139919ca1fe52` | 一致 (PASS) |
| 38 | `mlit_cultural_properties_yamanashi` | `raw/cultural_properties/P32-14_19_GML.zip` | 56,165 | `64a2859c35f61091` | 一致 (PASS) |
| 39 | `mlit_cultural_properties_shizuoka` | `raw/cultural_properties/P32-14_22_GML.zip` | 44,694 | `7a3c26fe954a46a1` | 一致 (PASS) |
| 40 | `tokyo_cultural_properties` | `raw/cultural_properties/130001culturalproperty.csv` | 9,696 | `be7d9aa6950801dd` | 一致 (PASS) |
| 41 | `paper_luft2021` | `literature/papers/Luft2021_HistoricalMapGeoreferencing.pdf` | 1,361,395 | `facca1e1394c0d0e` | 一致 (PASS) |
| 42 | `paper_tabayashi2026` | `literature/papers/Tabayashi2026_OldMapGeoreferencingAI.pdf` | 1,083,965 | `e0cb29ac4caea02f` | 一致 (PASS) |
| 43 | `mlit_l03_b_1976_5338` | `raw/landuse/L03-b-76_5338_GML.zip` | 14,630,483 | `1071994099b4d79e` | 一致 (PASS) |
| 44 | `mlit_l03_b_1976_5339` | `raw/landuse/L03-b-76_5339_GML.zip` | 14,450,493 | `b2e5a7210f516b9e` | 一致 (PASS) |
| 45 | `mlit_l03_b_2014_5338` | `raw/landuse/L03-b-14_5338-jgd_GML.zip` | 13,398,459 | `09e03256f41a9ac6` | 一致 (PASS) |
| 46 | `mlit_l03_b_2021_5338` | `raw/landuse/L03-b-21_5338-jgd2011_GML.zip` | 22,476,659 | `3f9d82c098eb4693` | 一致 (PASS) |
| 47 | `mlit_l03_b_2021_5339` | `raw/landuse/L03-b-21_5339-jgd2011_GML.zip` | 22,386,507 | `f6bbebb3fa80cf5f` | 一致 (PASS) |
| 48 | `gsi_aerial_photo_catalog_tsukui` | `raw/aerial_photos/metadata/tsukui_aerial_photos_catalog.json` | 59,394 | `205325245d13387c` | 一致 (PASS) |
| 49 | `gsi_aerial_tile_1974_aonohara_1974` | `raw/aerial_photos/sample_ortho_1974/aonohara_1974_z15_29054_12916.jpg` | 20,452 | `5c8b6e2b80081aa6` | 一致 (PASS) |
| 50 | `gsi_aerial_tile_1974_aoyama_1974` | `raw/aerial_photos/sample_ortho_1974/aoyama_1974_z15_29058_12912.jpg` | 18,502 | `025d60d1e3d600a9` | 一致 (PASS) |
| 51 | `gsi_aerial_tile_1974_toya_1974` | `raw/aerial_photos/sample_ortho_1974/toya_1974_z15_29055_12920.jpg` | 22,088 | `b347e2a9705f5bbf` | 一致 (PASS) |
| 52 | `gsi_aerial_tile_1974_suarashi_1974` | `raw/aerial_photos/sample_ortho_1974/suarashi_1974_z15_29054_12906.jpg` | 17,121 | `6ae487f3296568a6` | 一致 (PASS) |
| 53 | `sagamihara_buried_cultural_properties_2026` | `raw/cultural_properties/sagamihara_buried_cultural_properties_20260212.pdf` | 110,726 | `de14000fe289fe57` | 一致 (PASS) |

---

## 4. 自動検証スクリプトの整備と検証モードの分離

大規模な地理データ（OSM PBFファイル等、計約1.03 GB）に対する都度の全件ハッシュ計算は、FUSE/rcloneキャッシュ環境においてI/O負荷と実行時間を増大させるため、目的に応じて2段階の検証モードを整備した。

### 4.1 高速検証モード（Fast Mode: `--mode fast`）
- **対象**: 日常的な動作確認、CIテスト実行時
- **検証項目**: 実ファイルの存在確認、バイトサイズの一致確認、台帳JSON構文チェック
- **実行時間**: 約0.1〜0.5秒
- **実行コマンド**:
  ```bash
  python3 scripts/validate_databank.py --mode fast
  python3 scripts/audit_databank.py --mode fast
  ```

### 4.2 完全整合性検証モード（Full Mode: `--mode full`）
- **対象**: フェーズ完了時の納品前監査、定期的なデータ破損検出
- **検証項目**: 全実ファイルのSHA-256ハッシュ再計算および台帳値との完全一致照合
- **実行時間**: 約10〜15秒（ローカルVFSキャッシュ有効時）
- **実行コマンド**:
  ```bash
  python3 scripts/validate_databank.py --mode full
  python3 scripts/audit_databank.py --mode full --check-all-hashes
  ```

### 4.3 レポート・台帳の自動同期メカニズム
従来の「人間によるMarkdown手作業入力」による数字の転記ミスや幻覚を根絶するため、`scripts/audit_databank.py` によりディスク実測値と台帳値から `reports/databank_audit.json`、`reports/data_inventory.md`、および `reports/phase0_4_1_integrity_audit.md` を機械的に同期して同一実行から一括生成するパイプラインを確立した。

---

## 5. 結論と次期フェーズへの提言

1. Google Drive上の全データおよび台帳は1バイトの狂いもなく完全な整合状態にある。
2. 重複ファイル4件およびメタデータ7件は台帳システム内で明確に定義され、未追跡ファイルは0件である。
3. 幻覚された架空論文参照等の手作業ノイズは監査パイプラインの機械的生成により完全排除された。
4. 今後のデータ追加・更新時にも本監査スクリプトをCI/テストに組み込むことで、データの健全性と再現性を恒久的に担保できる。

