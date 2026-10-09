# GPTレビュー依頼 — Phase 0 完了審査

## Git情報

- リポジトリURL：https://github.com/blabo25226/kanagawa_ruins_search.git
- branch / commit hash：main / 83ae1d72578e36491e87205c84a4e2df97cf539f
- 直近のpush成否：push実行（成功確認済み）

## Phase 0で実際に完了した作業

1. **GIS CLIおよびPython実行環境の構築**:
   - `conda-forge` による独立仮想環境 `kanagawa-ruins` を構築（Python 3.12, GDAL 3.13.3, GeoPandas 1.2.0, Shapely 2.2.0, PyProj 3.8.0, Rasterio 1.5.2, OpenCV 5.0.0）。
   - `scripts/check_environment.py` による doctor テストを実施し、全17項目 PASS（`reports/environment_check.json` 出力）。
   - `qgis_process` は指示書規定に基づき任意（OPTIONAL_MISSING）としてスキップ。QGIS Desktop GUIは一切起動せず。
2. **ユニットテストの実施**:
   - `python -m unittest discover -s tests -v` を実行し、設定整合性・URL検証・フォーマット検査・gitignoreルールの全5件がPASS。
3. **データソース利用条件・規約の監査**:
   - `source.md` および `config/sources.toml` に基づき、国土地理院・相模原市・国土数値情報・今昔マップ等の利用条件を監査。
   - 今昔マップのローカル保存禁止規定、基盤地図情報のアカウント必須/JGD2024移行、国土数値情報の動的ダウンロード画面（直リンク推測不可）を明確に整理。
4. **ホワイトリストに基づく承認済み基礎データのダウンロード**:
   - `scripts/fetch_sources.py` を使用して `gsi_jusho_midori`（ZIP）および `sagamihara_cultural_assets`（CSV）を取得。
   - ファイルサイズ、SHA-256ハッシュ、基本ヘッダーの整合性を検証し、来歴を `data/provenance.jsonl` に記録。
5. **セキュリティおよびGit管理外の徹底**:
   - `data/raw/*` および `data/provenance.jsonl` が `.gitignore` により追跡除外されていることを確認。
6. **レポート類の整備**:
   - `reports/setup_report.md`
   - `reports/data_inventory.md`
   - `reports/review_request.md`
   - `reports/environment_check.json`

## 検証結果

- doctor：PASS (`PHASE 0 GIS DOCTOR: PASS` / 合成CRS変換・ラスターI/O・OpenCVすべて正常)
- unittest：PASS (`Ran 5 tests in 0.001s OK`)
- git diff --check：PASS（余計な空白・改行エラーなし）
- セキュリティ / 生データの追跡確認：PASS（`git status` にて `data/raw` およびバイナリ、認証情報の混入がないことを確認）

## 読んでほしいファイル

- `README.md`
- `firstinstruction.md`
- `source.md`
- `config/sources.toml`
- `reports/setup_report.md`
- `reports/data_inventory.md`
- `reports/environment_check.json`
- `scripts/check_environment.py`
- `scripts/fetch_sources.py`
- `tests/test_phase0.py`

## GPTに判断してほしいこと

1. **公開データの信頼性・利用条件の漏れ**:
   - 国土地理院住居表示住所（相模原市緑区）のe-GovカタログURLが404となっており、国土地理院本サイト（公共データ利用規約1.0/CC BY 4.0互換）を参照した点について妥当か。
   - 相模原市文化財一覧CSV（CC BY 4.0）および住居表示住所データを用いて、Phase 1以降の既知史跡除外マスクや地名参照を行う方針に問題はないか。
2. **GIS環境の過不足とCRS設計**:
   - 今後扱う国土数値情報（JGD2011）、国土地理院基盤地図情報（2026年移行分はJGD2024）、住居表示データ（JGD2000/2011）の混在に対し、分析時の統一CRS（例: 平面直角座標系第IX系 JGD2011 / EPSG:6677）への変換パイプラインの設計方針。
3. **Phase 1の最小実験範囲と判定指標**:
   - パイロット対象地域として「相模原市緑区（旧津久井町・青野原・青山等）」を選定し、明治期の迅速測図や旧版地形図と現代地図の差分から廃神社・廃寺・廃道候補の小規模PoCを行う手順の妥当性。
   - 誤検出（現役神社、一般民家、現役林道等）を最小化するための除外ルール（文化財台帳、住居表示、現役道路網等との照合）の十分性。
4. **廃神社以外への拡張の順番**:
   - 廃神社 → 廃寺 → 廃村・集落跡 → 廃道 → 放置建造物の順で進める検討順序の妥当性。
   - 宗教施設・脆弱な文化財・私有地・危険箇所に対する安全・倫理配慮（座標公開時の一般化等）の運用方針。

## 未実施・保留事項

- **Phase 1の実解析（差分抽出、画像認識、座標算出、ランキング、現地調査計画等）は一切着手していない。**
- レビュー結果と次フェーズ承認を待ってから作業を再開する。
