# Claude 独立コードレビュー（Phase 0.4.1 時点）

- 作成日: 2026-10-10
- 対象: `main` @ `5069867`（Gemini 作業中の未コミット変更は対象外）
- レビュー担当: Claude Sonnet 5.5（Gemini とは別系統の独立監査）
- 方針: **「確認済みの事実」**（コードを読む・実際に実行して再現したもの）と **「提案」**（未実装の設計判断）を分けて記載する。Geminiの報告は前提とせず、コードと Google Drive 上の実ファイルで検証した。
- 制約遵守: Google Drive は読み取りのみ（書き込み・削除なし）。Gemini が編集中のファイルは変更していない。解析・廃墟候補の抽出は行っていない（Phase 0 ゲート維持）。

---

## 0. 要約

| # | 重大度 | 内容 | 状態 |
|---|---|---|---|
| F1 | 高 | `validate_databank.py` が UTF-8 の Shapefile を `cp932` で「成功」読み込みし文字化けを返す | 再現済み |
| F2 | 高 | 整合性検証が「ヘッダのみ」。切り詰められた OSM/PBF/CSV/JPEG が `Valid` になる | 再現済み |
| F3 | 高 | `validate_databank.py` が provenance の SHA-256 を**再計算せず信用**する（検証が循環） | コード確認 + 実測（F4 と併せ） |
| F4 | 中 | Drive 上の実ファイルと provenance の不一致（SHA 1件、未記録ファイル 17件） | 実測済み |
| F5 | 中 | `already_present` 経路が provenance に記録を残さない／`expected_sha256` が全 56 ソースで未設定（TOFU） | 再現済み |
| F6 | 中 | provenance のキー構成が 4 種混在、ローカル(42行)とDrive(53行)が乖離、同一内容ファイルが 3 重配置 | 実測済み |
| F7 | 中 | `validate_databank.py` のレポート結論・日時がハードコード（検証結果に依存しない） | コード確認 |
| F8 | 低 | PROJ パス・ユーザー名のハードコード、環境非再現性 | コード確認 |
| F9 | 中 | テスト網羅性: 主要スクリプトの大半が未テスト、ライブテストが外部状態に依存 | 実測済み |

Geminiの「全ファイル正常・欠損なし」という趣旨の報告（`reports/data_validation_report.md` 第3節）は、**上記 F1〜F3・F7 の理由により、現状のコードでは裏付けられない**。

---

## 1. 確認済みの事実

### 1.1 実行環境・テスト

- conda 環境 `kanagawa-ruins`: Python 3.12.15 / GeoPandas 1.2.0 / Shapely 2.2.0 / Rasterio 1.5.2 / PyProj 3.8.0 / OpenCV 5.0.0 / GDAL(osgeo) 3.13.3 / pyogrio あり。
- 未導入: DuckDB, PyOsmium, PyArrow, PyTorch, MapReader, Fiona, rioxarray（`environment.yml` にも未記載）。
- `python -m unittest discover -s tests` → **17 tests OK（48.6 秒）**。遅い原因は Drive 上の PBF を開く `test_databank_osm_pbf_live_header`（FUSE 越しの実ファイル読み）。
- ベース環境の `python` は 3.14.6 で、プロジェクト環境ではない。`make test` は `python` を呼ぶため、**conda 環境を有効化しないと別のインタプリタで動く**（`Makefile`）。

### 1.2 データ取得（`scripts/fetch_sources.py`）

良い点（コードで確認）:
- HTTPS・ホスト許可リスト・ユーザー名/ポートの拒否（`approved_url`）、リダイレクト先の再検査（`RedirectGuard`）、`max_bytes` 上限（Content-Length とストリーム双方）、`.partial` への書き込み後に検証して rename、既存ファイルを上書きしない（`xb` モード）、Zip Slip / ZIP bomb / symlink の拒否（`safe_extract_zip`）。
- `RUINS_DATA_ROOT` が `fuse.rclone` マウント配下かを `/proc/mounts` の親子関係で検査（文字列前方一致を回避）。

問題点:

**F5a. `already_present` が provenance を残さない**（`fetch_sources.py:230-251`）。既存ファイルがある場合、レコードを返すだけで `provenance.jsonl` へ追記しない。ダウンロード直後にプロセスが落ちて provenance 追記前に止まった場合、次回以降は永久に「記録なしのファイル」になる。

再現手順:
```python
import fetch_sources as fs, tempfile
from pathlib import Path
t = Path(tempfile.mkdtemp())
src = dict(id='x', filename='x.csv', expected_format='csv', max_bytes=1000,
           allowed_domains=['example.com'], dest_dir='raw/x')
(t/'raw/x').mkdir(parents=True); (t/'raw/x/x.csv').write_bytes(b'id,name\n1,tampered\n')
rec = fs.download(src, 'https://example.com/x.csv', data_root=t)
# -> status='already_present', (t/'provenance.jsonl').exists() == False
```
結果: `status already_present sha 647d91e3179e provenance written? False`（実行確認済み）。

**F5b. SHA-256 の固定がない（Trust On First Use）**。`config/sources.toml` の 56 ソース中 `expected_sha256` を持つものは **0 件**。既存ファイルは「形式が妥当なら信用」される。再取得時に上流データが変わっても検出できない。

**F5c. 非アトミックな二重書き込み**。provenance は Drive 側とローカル側の 2 ファイルへ別々に追記され、排他ロックも `fsync` もない。FUSE 上の `a` モード追記は rclone の VFS キャッシュ設定により部分書き込み・競合の可能性がある（挙動は rclone 設定依存で未検証）。

**F5d. `Content-Length` 検査の穴**。`int(response.headers.get('Content-Length') or '0')` は数値でない値で `ValueError` を出す（`main()` 側で捕捉されるため致命的ではない）。HTTP エラー本文を `looks_like_format` で弾く設計は妥当。

### 1.3 整合性検証（`validate_file_integrity` ほか）

**F2. ヘッダのみの検査**（再現済み）:

```
truncated .osm   -> (True, 'Valid XML/OSM format confirmed')
header-only pbf  -> (True, 'Valid OSM PBF format confirmed')
stub jpeg        -> (True, 'Valid JPEG format confirmed')
truncated csv    -> (True, 'Valid CSV format confirmed')
```
- XML/OSM は先頭 2KB が `<?xml` / `<osm` で始まれば OK（`ET` を import するが使っていない）。途中で切れた `.osm` が合格する。
- PBF は先頭 2KB に文字列 `OSMHeader` があるだけで合格。完全性の根拠にならない（Drive 上の約 500MB × 2 の PBF は SHA-256 が provenance と一致したことのみ確認。構造的完全性は未検証）。
- JPEG は先頭 3 バイトのみ。EOI(`FFD9`)も画素デコードも見ない。
- ZIP（`testzip` による CRC 全走査）と PDF（`%%EOF`）は比較的妥当。

**F3. `validate_databank.py` の SHA-256 が循環**（`load_provenance_map` → `if rel in prov_map: sha = prov_map[rel]`）。provenance に記録があるファイルは**ハッシュを再計算せず記録値を表示**する。コメントは「FUSE のレイテンシ回避」。結果として「ハッシュ検証結果」の表の大半は、ファイルが壊れていても常に一致して見える。

実測（今回 Drive 上の 53 レコード全件のファイルを読み直して SHA-256 を計算）:
- 52/53 件一致、**1 件不一致**（F4）。`validate_databank.py` が出力するはずの表では検出できない構造。

### 1.4 provenance と Drive 実態（F4, F6）

実測（`provenance.jsonl` 53 行 vs Drive `data/` 配下 70 ファイル）:

- JSON 不正行: 0。重複パスのレコード: 0。レコードにあるがファイルがない: 0。
- **キー構成が 4 系統混在**: `relative_path` + `status`（38）、`relative_path` + `status` + `metadata`（11）、`status` なしの `relative_path` 形式（2）、`relative_path` を持たず `dest_path`/`fetched_at`/`id`/`url` を持つ旧形式（2）。`validate_databank.py` は `dest_path or relative_path` の二重対応で吸収している。
- **SHA 不一致 1 件**: `raw/aerial_photos/metadata/tsukui_aerial_photos_catalog.json`。記録 76,317 bytes / `0ffa71e1…` に対し、現ファイルは 59,394 bytes / `20532524…`。`backups/phase0_4_pre_fix/` のコピーは記録値 `0ffa71e1…` と一致 → **Phase 0.4.1 の修正で内容が変わり、provenance は未更新**（Gemini 作業中の可能性が高い。完了後に再記録されるべき）。
- **provenance 未記録のファイル 17 件**（うち実データ 7）:
  - `raw/administrative/14151.zip`、`raw/administrative/gsi_jusho_midori/14151.zip`（記録されているのは `raw/gsi_jusho_midori/14151.zip`）。
  - `raw/cultural_properties/bunkazai.csv`、`raw/cultural_properties/sagamihara_cultural_assets/bunkazai.csv`（記録されているのは `raw/sagamihara_cultural_assets/bunkazai.csv`）。
  - `raw/osm/tsukui_4districts_metadata.json`。
  - ほか README・書誌（`literature/…`）・バックアップ。
- **同一内容の 3 重配置**: `14151.zip`（SHA `a7235271…`）と `bunkazai.csv`（SHA `dec1117a…`）は、各 3 か所に**バイト同一**のコピーがある。`sources.toml` の `dest_dir` は再編後の `raw/administrative` / `raw/cultural_properties` だが、provenance は旧パスのまま。
- ローカル `data/provenance.jsonl`（42 行）は Drive 側（53 行）と一致しない（ローカルは gitignore 済みで「便宜用」の位置づけだが、2 つの正本候補が存在する）。

### 1.5 GIS 読み込み（F1）

`validate_databank.py` は Shapefile を `for enc in ['cp932', 'utf-8']` の順で読み、**最初に例外が出なかった結果を採用**する。しかし 2026 年版 N03 には `.cpg`（UTF-8）が同梱されており、`cp932` 指定でも例外は出ず、文字化けした属性が返る。

再現手順（Drive の ZIP をローカルへコピー・展開して実行。Drive には書き込まない）:
```python
import geopandas as gpd
gpd.read_file('N03-20260101_14.shp')                    # 1247行, EPSG:6668, N03_001='神奈川県'
gpd.read_file('N03-20260101_14.shp', encoding='cp932')  # 1247行, 例外なし, N03_001='逾槫･亥ｷ晉恁'
```
GDAL は `RuntimeWarning: One or several characters couldn't be converted correctly from cp932 to UTF-8`（1 度のみ表示）を出すだけで例外にならない。→ `validate_databank.py` のレポートに載る「カラム一覧・件数」は正しくても、属性値を使う後続処理（市区町村名での絞り込み等）が静かに壊れる設計。`verify_adjacency.py` は encoding 指定なし（`.cpg` 任せ）なので現状は正しく読めている。

そのほか実測: N03 神奈川（2026）は 1,247 フィーチャ、CRS EPSG:6668（JGD2011）、無効ジオメトリ 0、欠損 0、外接矩形 経度 138.916–139.836 / 緯度 35.128–35.673。

### 1.6 その他

- **F7**: `validate_databank.py` は `検証実施日時: 2026-10-10 01:55 JST` を文字列リテラルで埋め込み、第 3 節の「すべて…欠損なく正常にロード・ヘッダー検証可能であることを確認」等も**検証結果に関係なく固定出力**される。実行のたびに結論が変わらないレポートは証跡にならない。また `status = "ERROR: …"` になっても表に出るだけで、終了コードは常に 0。
- **F8**: `os.environ['PROJ_DATA'] = '/home/blabo/miniconda3/envs/kanagawa-ruins/share/proj'` がハードコード（`validate_databank.py:23-24` は無条件に上書き、`verify_adjacency.py:24` は存在時のみ）。他ユーザー・他マシンで壊れる。実機の pyproj は同じパスを自動解決している（`pyproj.datadir.get_data_dir()` で確認）ため、上書き自体が不要。なお、pyogrio での読込時に `ERROR 1: PROJ: proj_create_from_database: Open of …/share/proj failed` が出力される現象を観測した（原因は未特定。GDAL 同梱の PROJ と環境の PROJ が別バージョンの可能性。要調査）。
- `validate_databank.py` は `.osm` を `ET.parse` で全読み込み（最大 11.8MB で現状は許容、PBF/大型 OSM には不向き）、ZIP は最初の `.shp` 1 枚しか見ない。
- `.zip`/`.csv`/`.pdf` の検査は拡張子ベースで、`sources.toml` の `expected_format` と突き合わせない。
- **F9 テスト網羅性**（`tests/test_phase0.py` の grep と実行）:
  - テスト済み: `approved_url`、`looks_like_format`、`validate_file_integrity`、`safe_extract_zip`（Zip Slip/bomb/symlink）、`is_rclone_mounted`、`get_verified_data_root`、`safe_probe_write`。
  - **未テスト**: `download()`（本体）、`resolve_download_url`（CKAN 経路）、`RedirectGuard`、`load_provenance_map`、`validate_databank`、`verify_adjacency` 全体、`check_environment`、カタログ（`sources.toml`）の ID・パス・重複検査。
  - ライブテストが Drive の実ファイルに依存し、未マウント時は skip（CI で常時 skip される）。モックのマウントテーブルを使うテストは良い設計。
  - カバレッジ数値は計測していない（`coverage` 未導入）。上記は関数名の grep と読解による。

---

## 2. 提案（未実装・設計判断）

優先度順。いずれもコードを変更していない。実装は Gemini の作業完了・レビュー後を推奨。

1. **provenance を単一正本へ**（F4, F5, F6）
   - Drive 側 `provenance.jsonl` を唯一の正本とし、ローカル版は廃止または派生物にする。
   - スキーマを `schema_version` で固定（`docs/gis_architecture_proposal.md` §6 の案）。追記専用 + イベント種別（`downloaded` / `verified` / `moved` / `superseded`）。
   - 移動・再編・上書きも `moved` / `superseded` イベントとして記録し、パス変更で SHA 履歴が切れないようにする。
2. **`expected_sha256` の導入**（F5b）。初回取得後にレビューを経て `sources.toml` に固定。更新があった場合は別 ID（`…_v2`）で追加。
3. **検証関数を共通化し「再計算」を既定に**（F3）。`verify --mode full|fast`（`fast` はサイズ + mtime、`full` は SHA-256 再計算）。`validate_databank.py` は provenance 値を表示せず、必ず「再計算値 vs 記録値」を比較して不一致で終了コード 1。
4. **形式別の完全性検査を強化**（F2）: OSM-XML は `iterparse` で最後まで、PBF は `osmium fileinfo` / `pyosmium` で全ブロック、画像は GDAL/Pillow でデコード、CSV は `csv` モジュールで全行。
5. **Shapefile 文字コードは `.cpg` 優先**（F1）: `.cpg` があればそれに従い、無ければ UTF-8 を試し、失敗時のみ cp932。文字化け検出（置換文字 `U+FFFD`・典型的な `逾`・`ｷ` の混入）を検査に追加。
6. **レポートの動的生成**（F7）: 日時は実行時刻、結論は検査結果から機械的に生成。失敗があれば非ゼロ終了。
7. **ハードコード除去**（F8）: PROJ 上書きを削除し、`check_environment.py` で `pyproj.datadir` の整合を検査。
8. **テスト追加**（F9）: `download()` をローカル HTTPS 相当のモック（`http.server` + 許可リスト差し替え、または `opener` の差し替え）で、(a) 通常 (b) 超過サイズ (c) オフドメイン redirect (d) 切り詰め (e) 既存ファイル再実行 を検証。`sources.toml` の静的検査（ID 重複・`dest_dir` が許可ツリー内・`expected_format` が既知）。ライブテストは `@unittest.skipUnless(env)` で明示的に分離。
9. **`environment.yml` の更新案**: `pyogrio`, `pyarrow`, `duckdb`, `osmium`（pyosmium）の追加を検討（根拠は `docs/gis_architecture_proposal.md`）。`environment.lock.yml` は Python 3.12 のものが存在するが、`conda env export` の再生成と固定を提案。
10. **Makefile**: `PY ?= conda run -n kanagawa-ruins python` を使い、ベース環境（3.14）での誤実行を防ぐ。

---

## 3. 確認していないこと（限界）

- インターネット上の各データの出典・ライセンス条件の現在の正当性（今回は再検証していない）。
- PBF の全ブロック完全性、`.osm`（Overpass 抽出）の網羅性、OSM 抽出の bbox 妥当性。
- 書誌（`reports/bibliography_audit.md`）の事実確認。
- Gemini が現在編集中の `scripts/audit_databank.py` / `generate_bibliography.py` / `validate_bibliography.py` / `reports/phase0_4_manual_actions.md`（未コミット。レビュー対象外）。
- rclone VFS キャッシュ設定下での追記の安全性。

## 4. 運用上の注意（共有ワークツリー）

作業開始時に `claude_20261010_prepare_data` を共有ワークツリー上で作成したため、Gemini の未コミット変更が一時的に私のブランチ上に見える状態になった。直ちに `main` に戻し、私のブランチは別ワークツリー `../kanagawa_ruins_search_claude` に分離した。Gemini の未コミット変更（`.gitignore` ほか）は変更・コミットしていない。今後も並行作業は worktree を分けることを推奨する。

---

# 追補 A: 最新 `main`（`96707a4`）との照合（2026-10-10）

上記 §0〜§4 は `main` @ `5069867` を対象とした**当時の監査結果であり、履歴として改変していない**。その後 `main` は `96707a4`（Gemini: Phase 0.4.1）へ進んだため、F1〜F9 を最新コードと Drive 実体で再確認した。

## A.1 照合方法

- `git diff 5069867 96707a4`: 変更は `scripts/validate_databank.py`、新規 `audit_databank.py` / `migrate_provenance_schema.py` / `generate_bibliography.py` / `validate_bibliography.py`、`tests/test_phase0_4_1.py`、各種レポート。**`scripts/fetch_sources.py`・`storage_utils.py`・`verify_adjacency.py`・`tests/test_phase0.py`・`config/sources.toml`・`Makefile`・`environment.yml` は無変更**。
- `origin/main` を detached worktree で展開し、`unittest discover`（17 件 OK）、`pytest tests/test_phase0_4_1.py`（11 件 passed）を実行。
- Drive の `provenance.jsonl` 53 件の対象ファイルを**再度すべて SHA-256 再計算**（読み取りのみ）。
- 既存コードは変更していない。`validate_databank.py` 自体は実行していない（レポートをリポジトリに書き出すため。コード読解で判定）。

## A.2 F1〜F9 の現状

| # | 当時の指摘 | 現状 | 根拠 |
|---|---|---|---|
| F1 | Shapefile を `cp932` 優先で読み文字化け | **未修正** | `validate_databank.py:139` が `["cp932", "utf-8"]` のまま（差分は引用符の統一のみ）。当時の再現手順は同一コードに対し有効。CSV は `utf-8` 優先（従来どおり） |
| F2 | 整合性検査がヘッダのみ（切断ファイルが Valid） | **未修正** | `fetch_sources.py` 無変更。`validate_databank.py` の `.osm`/`.pbf`/`.jpg` 判定も従来と同等 |
| F3 | provenance のハッシュを再計算せず信用 | **一部修正** | `--mode fast|full` を導入。`full` は SHA-256 を再計算し台帳と照合（不一致を `MISMATCH` 表示）。`fast` は「未再計算 (台帳参照)」と明示し、誤認は防止。**残り**: (a) 既定が `fast`、(b) `full` でも 100MB 超の PBF は既定で再計算を省略（`--check-all-hashes` で有効）、(c) 不一致でも終了コードは 0（`main()` は戻り値なし）、(d) 形式検査は F2 のまま |
| F4 | 実体と provenance の不一致（SHA 1 件・未記録 17 件） | **修正済み（SHA）/ 一部修正（未記録）** | 再計算で **53/53 件一致、不一致 0**（航空写真カタログは新ハッシュ `20532524…`・59,394 B に更新、旧値は `audit_history` に保持）。未記録ファイルは 17 件のまま（変化なし）だが、`audit_databank.py` が「重複 4・メタデータ 7・台帳自身 1（＋`backups/` 5）」として**分類・文書化**した。分類はコードに固定された許可リスト（`KNOWN_LEGACY_DUPLICATES` ほか）に依存 |
| F5 | `already_present` が provenance 未記録 / `expected_sha256` 未設定 / 非原子的追記 | **未修正** | `fetch_sources.py` 無変更。`sources.toml` も無変更（`expected_sha256` は 0 件） |
| F6 | スキーマ混在 / ローカル 42 行 vs Drive 53 行 / 3 重配置 | **一部修正** | Drive 側は `migrate_provenance_schema.py` で**統一キー**へ移行（53 件とも同一キー構成。うち 1 件のみ `audit_history` 付き）。**残り**: (a) 旧キーを別名として併記（`bytes`/`size_bytes`、`download_url`/`source_url` 等）しており冗長、(b) ローカル `data/provenance.jsonl` は 42 行のまま未移行で Drive と乖離（gitignore のためコミット対象外）、(c) 同一内容 3 重配置は「後方互換のため保持」として温存、(d) 移行スクリプトは航空写真カタログのハッシュを**リテラルで埋め込む**特例を持つ |
| F7 | レポートの日時・結論がハードコード | **一部修正** | 日時は実行時刻（UTC）に、モード表示も動的化。**残り**: 第 3 節の結論文は固定出力。特に `fast` モードでも「全登録ファイルの…SHA-256 の整合性を実測確認完了」「すべて…欠損なく正常にロード・ヘッダー検証可能」と出力される（`fast` はハッシュ未再計算）。これは再計算していない事項を確認済みと書く不整合 |
| F8 | PROJ パスのハードコード | **一部修正** | `validate_databank.py` からは削除。`verify_adjacency.py:24-27` は `/home/blabo/miniconda3/envs/kanagawa-ruins/share/proj` を（存在時のみ）設定する従来のまま |
| F9 | テスト網羅性 | **一部修正** | `tests/test_phase0_4_1.py`（11 件、pytest 形式）を追加し、`pytest` で 11 件 pass を確認。**残り**: (a) pytest 形式のため **`make test` / `unittest discover` では収集されない**（実行件数は 17 のまま。実測）、(b) 内容は書誌・Drive 実体・航空写真メタデータの検査で、件数が固定（53 / 65 / 12）のため**データ追加のたびに壊れる**、(c) Drive 未マウント時は skip でなく fixture エラー、(d) `download()`・`resolve_download_url`・`RedirectGuard`・`audit_databank`・`validate_databank`・`verify_adjacency` の単体テストは依然なし |

集計: 修正済み 0 / 一部修正 6（F3, F4, F6, F7, F8, F9）/ 未修正 3（F1, F2, F5）/ 未確認 0。F4 の SHA 不一致という中核の事実誤りは解消されたが、F4 全体は未記録ファイルが残るため「一部修正」とした。

## A.3 Gemini の 0.4.1 報告に対する検証

- 「台帳 53 件・ハッシュ一致率 100%・不一致 0」: **再現できた**（私の独立した再計算と一致）。
- 「総実ファイル 65 件」: 私の列挙では `backups/` を含め 70 ファイル、`backups/` を除くと 65 で一致。
- 「完全整合（PASS）」という総合判定: PBF 2 本の構造的完全性（F2）と文字コード（F1）は検証範囲外で、判定は**ハッシュ・サイズ・存在**に限られる。

## A.4 今後の優先順位（提案）

1. F5（`already_present` の記録、`expected_sha256` 固定）と F2（形式別の完全検査）。取得・検証の信頼性に直結。
2. F1（`.cpg` 優先の文字コード処理）。属性値を使う Phase 1 以降で静かに壊れる。
3. F3(c) と F7: 不一致時に非ゼロ終了、結論文をモードと結果から生成。
4. F9(a): テストを `unittest` 形式へ揃えるか `Makefile` を `pytest` に変更。
5. F6(b): ローカル `data/provenance.jsonl` の扱い（廃止 or Drive からの派生物）を決める。

---

# 追補 B: ローカルキャッシュ方針の整合性

GIS 設計案（`docs/gis_architecture_proposal.md` 当初版）の「ローカルキャッシュ 10〜20GB」は、`README.md` の「ローカルは原則 1GB 以内・中間生成物は Drive」および `agent/rules/10-source-legality.md` 8「処理後に不要ファイルを残さない」と**矛盾する**ことを確認した。数値自体も未測定の推定だった。設計案側を改訂済み（同文書 §8）。要点: 恒久キャッシュは設けず、大判ラスタ/Parquet は Drive から直接部分読み（rclone は既に `--vfs-cache-mode full --vfs-cache-max-size 10G` で動作）、一時物はジョブ単位で 1GB 以内・終了時削除、派生物は Drive `processed/`、永続 `.duckdb` を FUSE 上に置かない。1GB を超えるジョブはユーザー承認つきの例外とする。FUSE 越しの部分読み性能は**未測定**で、採用前に実測が必要。
