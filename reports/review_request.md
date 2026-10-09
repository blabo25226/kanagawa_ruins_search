# GPTレビュー依頼 — Phase 0 完了審査（Google Driveデータバンク対応版）

## Git情報

- リポジトリURL：`https://github.com/blabo25226/kanagawa_ruins_search.git`
- branch / commit hash：main / 856abecc6b6e7cf5d800ac0be5876b480718ded8
- 直近のpush成否：push実行（成功確認済み）

## Phase 0で実際に完了した作業

1. **ストレージアーキテクチャの確立とGoogle Driveデータバンク接続**:
   - コードリポジトリ（ローカルPC: `kanagawa_ruins_search`）と大容量データ（Google Drive: `kanagawa_ruins_search_databank`）を分離管理する構成を確立。
   - 生データ正規保存先をGoogle Drive側の `data/` とし、環境変数 `RUINS_DATA_ROOT`（`/home/blabo/gdrive/kanagawa_ruins_search_databank/data`）による動的解決を実装（パスの直接ハードコードを完全排除）。
   - `.env` および `.env.example` の設定環境を整備。
   - `fuse.rclone` によるGoogle Driveマウント状態および読み書き権限を自動検証。
   - ローカルPCのストレージ容量制限（一時データ1GB以内）を遵守し、ローカル生データの重複保存を排除（ローカル使用量: 約904KB、Google Drive使用量: 約1.8MB）。
2. **GIS CLI・Python実行環境の構築と検証**:
   - `conda-forge` による独立仮想環境 `kanagawa-ruins` を構築（Python 3.12, GDAL 3.13.3, GeoPandas 1.2.0, Shapely 2.2.0, PyProj 3.8.0, Rasterio 1.5.2, OpenCV 5.0.0, rclone v1.60.1-DEV）。
   - `scripts/check_environment.py` による doctor スモークテストを実施し、全項目 PASS（`reports/environment_check.json` 出力）。
   - QGIS Desktop GUIは一切起動せず、CLIファースト要件を遵守。
3. **ユニットテストの実施**:
   - `python -m unittest discover -s tests -v` を実行し、全5件合格。
4. **データソース利用条件・規約の包括的監査**:
   - 国土地理院（住居表示、基盤地図情報、空中写真・旧版図、地理院タイル）、国土交通省（国土数値情報N03）、相模原市オープンデータ（文化財一覧、WebGIS）、神奈川県オープンデータカタログ、農研機構（迅速測図）、今昔マップ（画像保存禁止規定）、国立国会図書館デジタルコレクションの利用条件・ライセンス・容量・取得方法を調査・整理（[`source.md`](file:///home/blabo/kanagawa_ruins_search/source.md) および [`reports/data_inventory.md`](file:///home/blabo/kanagawa_ruins_search/reports/data_inventory.md)）。
5. **ホワイトリスト承認済みデータのGoogle Driveへの正規取得**:
   - `scripts/fetch_sources.py` を改修し、Google Drive側の `$RUINS_DATA_ROOT/raw/` 配下に直接取得・整合性検査（SHA-256、ヘッダー、サイズ）を実施。
   - `gsi_jusho_midori` (1.67MB ZIP) および `sagamihara_cultural_assets` (210KB CSV) を保存し、来歴を `$RUINS_DATA_ROOT/provenance.jsonl` に記録。
6. **レポート類の整備**:
   - [`reports/setup_report.md`](file:///home/blabo/kanagawa_ruins_search/reports/setup_report.md)
   - [`reports/data_inventory.md`](file:///home/blabo/kanagawa_ruins_search/reports/data_inventory.md)
   - [`reports/environment_check.json`](file:///home/blabo/kanagawa_ruins_search/reports/environment_check.json)
   - [`reports/review_request.md`](file:///home/blabo/kanagawa_ruins_search/reports/review_request.md)

## 検証結果

- doctor：PASS (`PHASE 0 GIS DOCTOR: PASS` / GDAL CLI, rclone, Google Driveマウント/読み書き, 合成CRS変換・ラスターI/O・OpenCVすべて正常)
- unittest：PASS (`Ran 5 tests in 0.001s OK`)
- git diff --check：PASS（余計な空白・改行エラーなし）
- セキュリティ / 生データの追跡確認：PASS（生データ実体、Google Drive大容量データ、および認証情報の混入なし）

## 読んでほしいファイル

- [`README.md`](file:///home/blabo/kanagawa_ruins_search/README.md)
- [`firstinstruction.md`](file:///home/blabo/kanagawa_ruins_search/firstinstruction.md)
- [`source.md`](file:///home/blabo/kanagawa_ruins_search/source.md)
- [`.env.example`](file:///home/blabo/kanagawa_ruins_search/.env.example)
- [`config/sources.toml`](file:///home/blabo/kanagawa_ruins_search/config/sources.toml)
- [`reports/setup_report.md`](file:///home/blabo/kanagawa_ruins_search/reports/setup_report.md)
- [`reports/data_inventory.md`](file:///home/blabo/kanagawa_ruins_search/reports/data_inventory.md)
- [`reports/environment_check.json`](file:///home/blabo/kanagawa_ruins_search/reports/environment_check.json)
- [`scripts/check_environment.py`](file:///home/blabo/kanagawa_ruins_search/scripts/check_environment.py)
- [`scripts/fetch_sources.py`](file:///home/blabo/kanagawa_ruins_search/scripts/fetch_sources.py)
- [`tests/test_phase0.py`](file:///home/blabo/kanagawa_ruins_search/tests/test_phase0.py)
- [`agent/rules/10-source-legality.md`](file:///home/blabo/kanagawa_ruins_search/agent/rules/10-source-legality.md)
- [`agent/rules/20-gis-cli.md`](file:///home/blabo/kanagawa_ruins_search/agent/rules/20-gis-cli.md)

## GPTに判断してほしいこと

1. **ストレージ構成とデータ管理方針**:
   - Google Drive上の `kanagawa_ruins_search_databank/data/` を環境変数 `RUINS_DATA_ROOT` で参照し、ローカルPCに生データ・大容量データを置かない（1GB制限）設計が適切か。
   - rclone FUSEマウントの検出・読み書き検証ロジックおよび上書き防止機構の安全性。
2. **公式データの選定と利用条件**:
   - 住居表示住所（国土地理院）および文化財一覧（相模原市）を既知史跡・現役建造物の除外マスクとして使用する方針の妥当性。
   - 今昔マップ（画像PC保存禁止）の閲覧専用方針、国土地理院基盤地図情報（アカウント必須/JGD2024移行）の保留判断の妥当性。
   - 神奈川県オープンデータカタログおよび国立国会図書館デジタルコレクション（津久井郡誌等の地誌史料）のPhase 1での活用順序。
3. **GIS環境とCRS設計**:
   - JGD2000/2011/2024が混在する複数データに対し、相模原市緑区を対象とした分析統一CRSとして平面直角座標系第IX系（JGD2011 / EPSG:6677）を採用する設計方針の妥当性。
4. **Phase 1の最小実験範囲と判定指標**:
   - 初期対象地域（相模原市緑区 旧津久井地域: 青野原・青山・鳥屋・寸沢嵐）における小規模PoCの進め方。
   - 廃神社 → 廃寺 → 廃村・集落跡 → 廃道 → 放置建造物の順に進める調査順序と倫理的配慮。

## 未実施・保留事項

- **Phase 1の実解析（廃墟候補抽出、地図記号認識、自動位置合わせ、座標生成、ランキング、現地調査計画等）は一切着手していない。**
- レビュー結果と次フェーズ承認を待ってから作業を再開する。
