# 古地図・航空写真 画像解析 ソフトウェア設計

- 作成日: 2026-10-10 / 作成: Claude Sonnet 5.5
- ステータス: **設計提案（未実装）**。現在は画像データが不足しているため、モデル学習・検出処理は行わない。Phase 0 ゲートにより、候補抽出・座標生成も行わない。
- 凡例: 【事実】= 確認済み、【提案】= 設計判断、【未検証】= 外部情報で本リポジトリ上では未確認。

---

## 1. 前提（確認済みの事実）

- 【事実】Drive 上の画像は `raw/aerial_photos/sample_ortho_1974/*.jpg` の 4 枚のみ。いずれも 256×256 px・3 バンド・**ジオリファレンスなし**（`rasterio` で CRS=None、アフィン=恒等）。ファイル名は `{地区}_1974_z15_{x}_{y}.jpg`（XYZ タイル）。
- 【事実】`raw/historical_maps/` は README のみで**古地図画像は 0 枚**。空中写真は `metadata/tsukui_aerial_photos_catalog.json`（42 件のカタログ）のみ。内容が Phase 0.4.1 で変更中（レビュー §1.4）。
- 【事実】環境: OpenCV 5.0.0 / Rasterio 1.5.2 / GDAL 3.13.3 / pyogrio あり。**PyTorch・MapReader・PyArrow・DuckDB は未導入**。GPU 有無は未確認（別環境 `llm-gpu` が存在するが本プロジェクト用ではない）。
- 【未検証・外部情報】MapReader（Living with Machines、Alan Turing Institute / British Library）は、地図画像を**パッチに分割して分類**するパイプラインと、事前学習済みモデルによる**テキスト検出・認識**パイプラインを提供する Python ライブラリ（[公式ドキュメント](https://mapreader.readthedocs.io/)、[JOSS 論文](https://joss.theoj.org/papers/10.21105/joss.06434.pdf)）。タイルサーバからの取得や geo 拡張もある。ただし、個別の記号（点）の検出や GCP による幾何補正を担う機能は確認できていない。また、英国 OS 図幅向けに作られており、日本の旧版地形図・迅速測図の記号への適用事例は今回の検索（1 回のみ・網羅的でない）では見つからなかった。
- 【未検証・外部情報】地形図の図式は明治初期以降 20 回以上改定されており、記号は版ごとに異なる（[NDL 関連資料](https://ndlsearch.ndl.go.jp/rnavi/maps/post_626) など）。迅速測図は関東の「迅速図」と関西の「仮製図」で方式が異なる。→ **検出器は版（時代・図式）ごとに定義する**必要がある。

---

## 2. 全体パイプライン【提案】

```
[1 取込]  古地図画像 + 取得メタ ──▶ ImageAsset（原画像は不変）
[2 前処理] 正規化・ノイズ除去・色/二値化・分割 ──▶ 派生画像（COG/PNG）+ 処理記録
[3 位置合わせ] GCP 選定 → 変換推定 → 誤差評価 → ジオリファレンス済みラスタ(COG)
[4 検出]  地図記号の検出（画像座標 px）           ← 学習データ不足の間は枠組みのみ
[5 変換]  px → 地理座標（EPSG:6668）→ GeoJSON/GeoParquet
[6 評価]  位置推定誤差・検出精度の算出、レポート
```
設計の核: **「位置合わせ」と「検出」を独立モジュールにし、どちらも不確かさ（誤差推定）を出力に持たせる**。検出結果の座標誤差 = 検出誤差（px）× 解像度 ⊕ 幾何補正の残差（RMSE）⊕ 地図自体の測量誤差。

### 2.1 パッケージ構成（`src/kanagawa_ruins/imaging/`）

```
imaging/
  assets.py        # ImageAsset(asset_id, path, sha256, kind=old_map|aerial, source_id, year, scale, dpi, license)
  io.py            # rasterio/GDAL で読込（大判 TIFF はウィンドウ読み）, JPEG/PNG/TIFF, 8/16bit
  tiles.py         # XYZ タイル→アフィン（Web Mercator）, タイル結合（モザイク）
  preprocess/
    normalize.py   # グレー/色空間, 白色点補正, コントラスト(CLAHE), 紙の黄ばみ補正
    denoise.py     # bilateral / non-local means（OpenCV）
    binarize.py    # Sauvola 等（記号が黒系の図式向け）, 色分離（HSV/Lab）
    tile_split.py  # スライディングウィンドウ（overlap）で検出用パッチ化, patch→元座標の逆写像
  georef/
    gcp.py         # GCP(px_x, px_y, lon, lat, source, confidence) の入出力（GeoJSON/CSV）
    candidates.py  # GCP 候補（経緯度グリッド交点, 三角点, 寺社, 橋, 河川合流点）の提示
    transform.py   # 変換推定: 相似/アフィン/多項式(2,3次)/TPS。GDAL の gdal_translate -gcp + gdalwarp
    residuals.py   # 残差・RMSE・LOO-CV（leave-one-out）, 外れ値除去(RANSAC)
    refine.py      # 現代GISとの自動微調整（道路・河川・海岸線への ECC/特徴点, 任意）
  detect/
    base.py        # Detector 抽象: detect(patch)->list[Detection(px, class, score, bbox)]
    template.py    # OpenCV matchTemplate（凡例記号1〜数枚で動く、学習不要）
    classical.py   # 色・形状・連結成分ベース
    cnn.py         # PyTorch 検出器（YOLO系/Faster R-CNN）。※学習は将来
    nms.py         # パッチ境界の重複除去（NMS, 座標逆写像後に実施）
  export/
    geojson.py     # Detection+変換 → GeoJSON/GeoParquet（§3.5）
  eval/
    geo_error.py   # §4
    detection.py   # P/R/F1, 距離許容での一致
  provenance.py    # 各ステップの入出力 SHA-256・パラメータ・コード版を provenance へ
```

---

## 3. 各処理の設計

### 3.1 古地図画像の読み込み（入力: 画像、出力: `ImageAsset`）

- 入力形式: TIFF（LZW/Deflate, 8/16 bit）、JPEG、PNG、タイル集合（XYZ）。
- 実装: `rasterio.open`（GDAL ドライバ経由）。大判（数千〜数万 px）はウィンドウ読み、または COG/VRT 化して部分読み。OpenCV の `imread` は大判・16bit・EXIF 方向で扱いに癖があるため、**入出力は rasterio、画像処理は NumPy 配列を OpenCV へ渡す**構成にする。
- 取り込み時に必ず記録: `sha256`、`width/height`、`dpi`（不明なら `None`）、`source_id`（`sources.toml`）、**元の入手条件・ライセンス**。**画像が公式サービスの閲覧専用で保存不可の場合は取り込まない**（`10-source-legality.md` に従う。タイルの連続取得・最高画質のスクレイピング禁止）。
- 【事実に基づく注意】現在の 256px JPEG は座標が無いので、**`tiles.py` で `z/x/y` から Web Mercator のアフィン（原点 = タイル左上、解像度 = 2π·R / (256·2^z)）を計算し EPSG:3857 のジオリファレンスを付与**して GeoTIFF/COG 化する（z=15 で約 4.77 m/px（赤道）、神奈川の緯度では約 3.9 m/px）。この画像は既に空中写真/地図のタイル化成果であり、GCP 作業は不要。

### 3.2 前処理（入力: `ImageAsset`、出力: 派生画像 + 処理記録）

目的: 検出・位置合わせの前段で、**原画像を変えずに**派生物を作る。

- 正規化: 色空間変換、グレー化、`CLAHE`、背景（紙色）推定と除去。
- ノイズ・折り目・汚れ: bilateral / non-local means。ただし**記号は小さい**ため、平滑化しすぎて記号を潰さない（パラメータは検出再現率で選ぶ）。
- 二値化: Sauvola 等の局所しきい値（旧版の黒/赤など色で図式が分かれる場合は **色分離（Lab/HSV）を先に**）。
- 傾き・歪み: 図郭（枠線）の検出 → 4 隅から射影補正（`cv2.getPerspectiveTransform`）。※これは位置合わせの初期値にもなる。
- 分割: `tile_split.py` で 512〜1024px・オーバーラップ 20% のパッチ化。**各パッチは元画像座標への逆写像（オフセット・スケール）を必ず保持**。
- すべての処理は `params.json` と入出力 SHA-256 を `provenance` に追記し、同一入力・同一パラメータで再現可能にする（乱数は固定）。

### 3.3 地図記号の検出（入力: パッチ、出力: `Detection`）

画像データが不足しているため、**学習なしで動く手法から段階的に**。

| 段階 | 手法 | 必要データ | 実装 | 備考 |
|---|---|---|---|---|
| S0 | **凡例テンプレート照合** | 図式の凡例記号 1〜数枚 | OpenCV `matchTemplate`（複数スケール・回転）、色フィルタ併用 | 学習不要。誤検出多、スコア閾値と NMS 必須 |
| S1 | 古典的特徴（連結成分・形状記述子） | なし（ルール） | OpenCV `findContours`、Hu モーメント | 神社記号（鳥居・卍等）のように形が単純な図式向け |
| S2 | 少数ショット/半自動 | 数十〜数百の人手アノテ | 人手ラベル → 小型 CNN の転移学習 | **将来**。アノテ UI（`labelme`/`CVAT`/QGIS 点レイヤ） |
| S3 | 物体検出モデル | 数千以上のラベル | PyTorch（Faster R-CNN / YOLO 系、torchvision） | **将来**。現時点で不要 |

- **MapReader の位置づけ**【未検証】: パッチ単位の分類（「この 100m 四方に寺社記号を含むか」等）や地図上の文字領域の抽出には有用な可能性がある。ただし (a) 点記号の座標精度は出ない（パッチ解像度）、(b) 日本語地図テキスト・日本の図式への適合は未検証、(c) PyTorch 等の重い依存が増える。**S0〜S1 は自前（OpenCV）で実装し、S2 以降のアノテーション・分割・学習管理のワークフロー部品として MapReader の採用可否を、実画像 10 枚程度でスパイク評価して決める**ことを提案する。
- 図式は時代で異なる（§1）。`Detector` は **`legend_id`（図式の版）をパラメータに持つ**設計にし、例えば `meiji_jinsoku_kanto` / `taisho_5man` / `showa_25000` ごとに別設定とする。
- 出力 `Detection`: `{asset_id, patch_id, px_x, px_y, bbox_px, class, score, detector, detector_version, legend_id}`。

### 3.4 現代 GIS データとの位置合わせ（入力: 画像 + 参照 GIS、出力: ジオリファレンス済みラスタ + 変換）

- **参照データ**（`docs/gis_architecture_proposal.md`）: N03（行政界）、OSM（道路・河川・橋・社寺）、W05（河川）、N02（鉄道）、DEM/陰影。経年変化に強い**河川合流点・山頂・橋・海岸線・古い神社の位置・寺院**を GCP 候補に使う。道路は付替えが多く、旧版では不利。
- 手順:
  1. **粗位置合わせ**: 図郭の経緯度（図幅番号から算出）で相似/アフィン変換。
  2. **GCP 選定**: 地図上の 10〜30 点（人手 + 候補提示）。分布は図郭全体に偏りなく、変換次数 +3 点以上。
  3. **変換推定**: 相似 → アフィン → 2 次多項式 → TPS の順に比較。**次数を上げる前に LOO-CV 誤差を見る**（過学習防止）。`gdal_translate -gcp … && gdalwarp -r bilinear -t_srs EPSG:6677 -order 2 | -tps`（コマンド全文を記録）。
  4. **精密化（任意）**: 河川・海岸線ベクトルを参照して `refine.py` で局所補正（ECC/相互相関）。
- 出力: GeoTIFF/COG（EPSG:6677 または 6668）+ `transform.json`（種別・係数・GCP・残差・コマンド・コード版）。
- **現地測量精度の限界**: 迅速測図は精度が高くない（簡易測量）ため、位置合わせ残差が小さくても、地図そのものの誤差は残る。誤差評価で分離して報告する（§4）。

### 3.5 検出結果の GeoJSON 出力（入力: `Detection` + 変換、出力: GeoJSON/GeoParquet）

- 座標変換順序: パッチ px → 画像 px（逆写像）→ 地理座標（変換モデル）→ EPSG:6668（RFC 7946 準拠の GeoJSON は WGS84 前提のため、GeoJSON 出力時は **EPSG:4326 の経度緯度**を既定とし、CRS 注記を `properties` と `provenance` に明記）。
- スキーマ案:

```json
{
  "type": "FeatureCollection",
  "properties": {
    "schema_version": 1,
    "asset_id": "…", "asset_sha256": "…",
    "transform_id": "…", "transform_type": "affine|poly2|tps",
    "gcp_rmse_m": 12.3, "loocv_rmse_m": 18.0,
    "detector": "template_v0", "detector_version": "…",
    "legend_id": "meiji_jinsoku_kanto",
    "code_commit": "…", "built_at": "…"
  },
  "features": [
    {"type": "Feature",
     "geometry": {"type": "Point", "coordinates": [139.2, 35.6]},
     "properties": {
       "det_id": "…", "class": "shrine_symbol", "score": 0.87,
       "px": [1234.5, 876.0], "patch_id": "…",
       "pos_sigma_m": 25.0, "pos_sigma_method": "see eval"
     }}
  ]
}
```
- **Phase 0/1 の倫理・公開制限**（`agent/rules/30-field-ethics.md`）: 検出結果は**内部作業データ**であり、実際の廃墟候補の公開・ランキングは行わない。出力先は `data/processed/`（gitignore）。GitHub へは合成サンプルのみ。

---

## 4. 位置推定誤差の評価【提案】（入力: 検出点・参照点、出力: 誤差統計）

**誤差の分解**（独立と仮定して合成。仮定の妥当性は検証対象）:

`σ_total² ≈ σ_det² + σ_georef² + σ_map²`

| 成分 | 内容 | 推定方法 |
|---|---|---|
| σ_det | 検出の px 位置誤差 × 地上解像度 | 人手ラベルとの差（ラベル付き部分集合） |
| σ_georef | 幾何補正の残差 | GCP RMSE と **LOO-CV RMSE**（独立検証点）。GCP の一部を最初から検証用に取り分ける |
| σ_map | 古地図自体の測量誤差・図式のずれ | **検証点（今も存在する不動の地物: 山頂・橋・社寺・水路交点）での旧版地図位置と現代位置の差**から推定 |

- **検証セット**: 時代を問わず存続している地物（例: 現存する神社の本殿位置、河川合流点）を現代 GIS から選び、古地図上の対応記号位置を人手で取得 → 変換後の座標との差を距離（m）で集計。
- 指標: 平均誤差、RMSE、中央値、90/95 パーセンタイル、最大誤差、**誤差の空間分布図**（図郭内で端ほど大きい等）。`pos_sigma_m` を各検出点に付与（局所残差補間）。
- 検出精度: 検出点と参照点の距離が許容半径 r（地図縮尺から決定。例: 25m / 50m）内なら一致として Precision/Recall/F1（r を変えた曲線も出力）。
- **再現性**: 検証点 ID・乱数シード・分割・変換パラメータをすべてレポートに記録。評価は Phase 0 の制約に従い、**探索目的の候補作成には使わない**（検証用の既知地物のみ）。
- 出力: `reports/georef_eval_{asset_id}.md` と `eval/*.json`（機械可読）。

## 5. 技術選定の比較

| ライブラリ | 用途 | 現状 | 判断【提案】 |
|---|---|---|---|
| **Rasterio / GDAL** | 画像 I/O、GCP 補正、COG、座標変換 | 導入済み | **必須**。位置合わせ（`gdalwarp -order/-tps`）の標準実装 |
| **OpenCV** | 前処理、テンプレート照合、輪郭、特徴点、射影補正 | 5.0.0 導入済み | **必須**。S0〜S1 検出と前処理の主力 |
| scikit-image | Sauvola 二値化、モルフォロジ、変換推定（`estimate_transform`） | 未導入 | 任意（OpenCV で足りない部分のみ） |
| **PyTorch + torchvision** | S2〜S3 の学習・推論 | 未導入 | **今は導入しない**（学習は不要の指示）。S2 開始時に追加、CPU 版でも検証可 |
| **MapReader** | パッチ分類・文字検出・アノテ補助 | 未導入、【未検証】 | **スパイク評価のみ**（実画像 10 枚）。採否は結果で決める。必須化しない |
| ultralytics/YOLO | 物体検出 | 未導入 | S3 で検討（ライセンス AGPL に注意）。torchvision の Faster R-CNN は BSD 系 |
| QGIS（GUI なしでも可） | GCP 作業・目視検証 | 任意 | GCP は QGIS ジオリファレンサまたは自前 CLI。**GUI は Phase 0 では起動しない** |

## 6. 必要となるデータとテスト【提案】

- **今すぐ可能（学習不要・小データ）**: (1) `tiles.py` の XYZ→アフィン変換の**単体テスト**（既知タイル 4 枚の外接矩形が N03 津久井域内に収まるかを確認）。(2) 合成画像（数 KB、コードで生成した模擬地図 + 既知記号）による、前処理・テンプレート照合・px→座標変換・誤差評価の**エンドツーエンドテスト**。(3) 変換推定の既知解テスト（既知アフィンで GCP を生成し係数復元）。
- **画像確保後**: 図幅ごとに 10〜30 GCP、検証点 10 点以上、凡例画像。
- **CI/回帰**: 画像本体は Git に入れず、合成データのみコミット。実画像の評価は手動実行（Drive 読み取りのみ）。

## 7. 実装順序【提案】

1. 合成データ・誤差評価・GeoJSON スキーマ（画像不要で完成度を担保）。
2. `tiles.py` + 現有 4 枚の航空写真のジオリファレンス化（派生物のみ、原本は不変）。
3. 前処理 + `template.py`（S0）。
4. `georef/*`（GCP・変換・LOO-CV）。実古地図入手後。
5. MapReader スパイク → S2 アノテーション。
6. S3（PyTorch）は十分なラベルが集まってから。

## 8. 未解決事項

- 古地図の入手可否・取得条件（国土地理院「地図・空中写真閲覧サービス」の保存可否、農研機構の歴史的農業環境閲覧システム、国立国会図書館等）。本設計は画像が保存可能な条件で取得できた場合のみ有効。
- 図式（凡例）の版の特定と、神社・寺院記号の時代別の形状定義。
- GPU 資源の有無（S3 以降）。
- 航空写真の 1974 年タイル（z15）の画素サイズ・撮影年・出典表示と利用条件の確認（カタログ内容は Gemini 作業中）。

Sources: [MapReader docs](https://mapreader.readthedocs.io/) / [JOSS paper](https://joss.theoj.org/papers/10.21105/joss.06434.pdf) / [NDL 旧版地図案内](https://ndlsearch.ndl.go.jp/rnavi/maps/post_626)
