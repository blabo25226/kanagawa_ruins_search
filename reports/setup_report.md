# Phase 0 環境セットアップ報告（Google Driveデータバンク対応版）

- 実行日時（JST）：2026-10-09 22:26:40 JST
- Git branch / commit：main / 856abecc6b6e7cf5d800ac0be5876b480718ded8
- Ubuntu / kernel / Python / Conda：Ubuntu Linux (Linux 7.0.0-34-generic x86_64, glibc 2.43) / Python 3.12.15 / Conda 26.5.3
- モデル・実行担当：Gemini 3.8 Flash（主担当エージェント）

---

## 1. 実行環境とストレージ構成

本プロジェクトでは、コードと大容量データを明確に分離管理する構成を採用しています。

- **ローカルリポジトリ**: `/home/blabo/kanagawa_ruins_search`
  - GitHub管理対象（ソースコード、設定、指示書、Markdownレポート、テストコード）
  - 一時データ容量制限: 原則1GB以内
- **Google Driveデータバンク**: `/home/blabo/gdrive/kanagawa_ruins_search_databank`
  - 生データ正規保存先: `/home/blabo/gdrive/kanagawa_ruins_search_databank/data`
  - 参照環境変数: `RUINS_DATA_ROOT`（`.env` およびシェル環境変数にて設定）
  - マウント形式: `fuse.rclone`（`gdrive: on /home/blabo/gdrive type fuse.rclone (rw,nosuid,nodev,relatime,user_id=1000,group_id=1000)`）

---

## 2. インストールしたツールと動作確認結果

| 項目 | 結果 PASS/FAIL/SKIP | バージョン | 備考 |
|---|---|---|---|
| Python | PASS | 3.12.15 | `/home/blabo/miniconda3/envs/kanagawa-ruins/bin/python` |
| GeoPandas / Shapely / PyProj | PASS | GeoPandas 1.2.0 / Shapely 2.2.0 / PyProj 3.8.0 | conda-forge 独立環境 |
| Rasterio / GDAL | PASS | Rasterio 1.5.2 / GDAL 3.13.3 | conda-forge 独立環境 |
| OpenCV (cv2) | PASS | 5.0.0 | コンピュータビジョン用 |
| Folium / Matplotlib | PASS | Folium 0.20.0 / Matplotlib 3.11.2 | 地図可視化・グラフ |
| gdalinfo / ogrinfo / gdalwarp | PASS | GDAL 3.13.3 "Iowa City", released 2026/08/13 | CLI実行確認 (exit code 0) |
| rclone | PASS | rclone v1.60.1-DEV (go1.26.0) | `/usr/bin/rclone` 動作確認 |
| qgis_process（任意） | OPTIONAL_MISSING | なし | QGIS Desktop GUIは使わず、CLIファースト構成で要件充足 |
| Google Drive マウント検証 | PASS | `gdrive: on /home/blabo/gdrive (fuse.rclone)` | パス階層厳密検証（前方一致排除） |
| Google Drive 読み書き検証 | PASS | UUID排他作成 (`O_CREAT \| O_EXCL`)・読込・削除成功 | 上書き事故防止・排他プローブ検証完了 |
| 合成GIS smoke tests | PASS | - | 合成ベクトルのCRS変換 (EPSG:4326 <-> 3857)、合成GTiff入出力、OpenCV GaussianBlur |
| unittest | PASS | - | `python -m unittest discover -s tests -v` (11/11 PASS、異常系・偽装拒否含む) |

---

## 3. ストレージ容量と利用状況

- **ローカルリポジトリ使用容量**: **約 904 KB**（一時データ 0 B、1GB以内制限を完全遵守）
  - ローカルストレージ全体: 233 GB 中 146 GB 使用（空き 76 GB, 66%）
- **Google Driveデータバンク使用容量**: **約 1.8 MB**
  - Google Driveストレージ全体: 5.0 TB 中 223 GB 使用（空き 4.8 TB, 5%）
- **ローカル重複保存の排除**:
  - 先行取得したローカル `data/raw/` の実ファイルをGoogle Drive側へ移行・集約し、ローカルには `.gitkeep` のみを保持。

---

## 4. エラーと対応、残課題

- **エラー発生**: なし。すべてのdoctorチェック・ユニットテスト・データダウンロードが正常終了。
- **qgis_process**: 未導入（`OPTIONAL_MISSING`）。GDAL CLIおよびPythonライブラリ群でPhase 0〜Phase 1のCLI要件を充足しているため問題なし。

---

## 5. 解析未着手の確認

- [x] 実地理データの解析・廃墟候補生成は一切実行していない
- [x] 地図記号・鳥居の画像認識、古地図自動位置合わせ、候補地ランキング、現地調査計画等は未着手
