# Phase 1-B 利用ガイド

既存画像のGIS化、航空写真メタデータ検索、GCP位置合わせ、DEM処理の基盤です。廃墟判定・記号検出・新規資料の取得は含みません。歴史地図とDEMは現時点では合成データでの検証です。

## 環境と保存先

```bash
conda env create -f environment.yml  # 新規環境の場合
conda activate kanagawa-ruins
python -m pip install --no-deps -e .
export RUINS_DATA_ROOT="利用者が確認したDrive上のdataディレクトリ"
```

既存環境ではまず依存関係を確認してください。検証環境はPython 3.12.15 / GDAL 3.13.3 / Rasterio 1.5.2 / NumPy 2.5.3 / PyProj 3.8.0です。GDALのCLI、Pythonバインディング、`osgeo_utils.samples.validate_cloud_optimized_geotiff`が必要です。PyPIの宣言だけではGDAL CLIは導入されません。Condaの既存lockは再生成していません。

`RUINS_DATA_ROOT`は環境変数を優先し、既存の`.env`読込方式も引き継ぎます。CLIは本物のrcloneマウントを検証します。単に同名ディレクトリが存在するだけでは実行できません。

```text
processed/phase1b/
  aerial/georeferenced/    # 既存XYZ JPEGからのCOG
  aerial/catalog/          # 元属性を保持した正規化JSON
  historical_maps/georeferenced/
  terrain/dem/
  terrain/slope/
  terrain/hillshade/
  manifests/              # 各asset_idにつき1ファイル
```

`raw/`、`provenance.jsonl`、`processed/phase1a/`は読み取り専用として扱います。低水準の出力関数はローカル一時領域にのみ書き、Driveへの保存は台帳照合付きpublisherを経由します。派生物とmanifestのSHA-256を保存後に再読込確認します。既存出力は上書きしません。

## CLI

5つのCLIは全て`--list / --dry-run / --execute / --report`に対応し、省略時はdry-runです。`inventory`は`--execute`でも読取専用です。`verify --execute`も読取専用の検証です。`--report`は新しいローカルJSONファイルの保存先であり、既存レポートとDriveへの書込を拒否します。

```bash
python scripts/phase1b_inventory.py --list --report reports/my_inventory.json
python scripts/phase1b_imaging.py --dry-run
python scripts/phase1b_imaging.py --execute --report reports/my_tiles.json
python scripts/phase1b_imaging.py --mode catalog --execute
python scripts/phase1b_verify.py --execute --report reports/my_verification.json
python scripts/phase1b_georef.py --list
python scripts/phase1b_dem.py --dry-run
```

`--source-id`は正規取得台帳のIDです。imagingでは複数指定できます。georef/demの実行は、明示した1件のsource_id、固有asset_id、追加メタデータを必須とし、意図しない全域処理を防ぎます。未取得の地図・DEMのdry-runは`manual_action_required: true`を返します。取得処理はありません。

一時容量は`--scratch-limit`で指定し、既定1GB、上限25GBです。ジョブ専用TemporaryDirectory、空き容量1GBの余裕、可能な範囲のrcloneキャッシュ容量を確認し、例外・割込時も一時領域を削除します。GDAL warpはVRTで出力サイズを見積もってから実行します。マウント設定は変更しません。バッチ全体のトランザクションではなく、artifact/manifestの組を単位として公開します。途中失敗時も既に正常保存した組は保持します。

## XYZタイルとラスタAPI

[地理院タイル仕様](https://maps.gsi.go.jp/development/siyou.html)のXYZ方式を使います。北西原点でxは東、yは南です。Web Mercatorの半周長を`H=π×6378137`、タイル幅を`D=2H/2**z`とすると、左上は`(-H+xD, H-yD)`です。実画像を256×256・RGB uint8と照合し、AffineのY解像度を負にします。

```python
from kanagawa_ruins.imaging.tiles import XYZ, pixel_to_ground, ground_to_pixel
tile = XYZ.from_filename("aonohara_1974_z15_29054_12916.jpg")
mercator_bbox = tile.bounds()
lonlat_bbox = tile.lonlat_bounds()
x, y = pixel_to_ground(tile, 10, 20, crs="EPSG:6677")
column, row = ground_to_pixel(tile, x, y, crs="EPSG:6677")
```

ピクセル変換は既定で画素中心（column+.5,row+.5）、`center=False`で画素角です。EPSG:3857・4326・6677の間は常にx/y順を使い、ballparkを許可しません。タイルが指定地域のsanity bboxを外れれば停止します。このbboxは大字境界ではありません。

```python
from kanagawa_ruins.raster.config import RasterSettings
from kanagawa_ruins.raster.storage import list_artifacts
from kanagawa_ruins.raster.io import open_image, read_windows
settings = RasterSettings.from_env()
assets = list_artifacts(settings)
tile_asset = next(m for m in assets if m["kind"] == "xyz_tile")
path = settings.data_root / tile_asset["processed_path"]
with open_image(path) as ds:
    print(ds.crs, ds.bounds, ds.overviews(1))
for window, pixels in read_windows(path, size=512):
    pass  # pixelsだけを順次処理
```

`raster.cog.to_cog(source, local_output, job=job)`はDEFLATE、128pxブロック、NEARESTオーバービューを使います。GDALのfull COG validatorとRasterioのCRS・transform・bboxを照合します。JPEGをデコードした基底画素値は完全一致し、新たなJPEG再圧縮をしません。gazo1の対象期間は1974–1978年であり、ファイル名から1974年の撮影日や位置精度を確定しません。

## 航空写真カタログ

正規化JSONは42件程度の小規模カタログとして扱います。実キー`specification_id`から`specId`を作り、全ての元属性は`original`に保持します。撮影日不明はnull、撮影高度と座標CRS、個別ライセンス確認は資料にない限りunknown/nullです。

```python
import json
from kanagawa_ruins.imaging.catalog import search_catalog, nearby_photos
catalog_asset = next(m for m in assets if m["kind"] == "photo_catalog")
records = json.loads((settings.data_root / catalog_asset["processed_path"]).read_text())
selected = search_catalog(records, decade="1960s", bbox_native=[139.1,35.5,139.3,35.7],
                          footprints_only=True, unacquired_only=True)
```

```bash
python scripts/phase1b_imaging.py --mode catalog --dry-run \
  --bbox-native 139.1 35.5 139.3 35.7 --decade 1960s \
  --footprints-only --unacquired-only
```

検索結果にも`footprint_verified / footprint_approximate / center_only / footprint_unknown`を残します。中心点のみの写真を撮影範囲の包含判定には使いません。現有データは近似範囲34件、中心のみ8件です。元の`verification_status=verified`は独立した位置精度保証と解釈しません。

`bbox_native`は保存された数値座標の交差検索で、CRSを推定しません。現在は座標CRSが未確認のためメートル検索を既定では拒否します。確認済みの地理CRSを利用者が明示した場合に限り、`nearby_photos(records, lon, lat, radius_m, coordinate_crs="EPSG:4326")`で中心点距離を検索できます。混合CRSは拒否します。実カタログのdatum確認は未完了です。カタログ検索フィルタは読取専用で、`--execute`と併用できません。

## 古地図GCP

対応画像はTIFF/GeoTIFF/JPEG/PNGです。GCP JSONは`training`と独立した`validation`の配列を持ち、各点は次の構造です。以下の値は説明用であり実在参照点ではありません。

```json
{"point_id":"SYNTHETIC001","pixel_x":100.0,"pixel_y":200.0,
 "ground_x":-60000.0,"ground_y":-40000.0,"ground_crs":"EPSG:6677",
 "source":"synthetic example only","confidence":"high","selection_method":"analytical fixture"}
```

GDALと同じ連続ピクセル座標（左上角0,0、画素中心.5,.5）を使います。同一の投影メートルCRS、非共線の学習点3点以上、独立検証点1点以上を要求します。重複ID・同一画素位置による学習/検証の使い回し、CRS不足、退化配置は拒否します。

```bash
python scripts/phase1b_georef.py --execute --source-id 正規登録済み画像ID \
  --asset-id historical__official_sheet__v1 --gcps config/reviewed_gcps.json
```

最小二乗アフィン推定、学習/検証それぞれのRMSE・点別残差、`gdal_translate -gcp`と`gdalwarp -order 1 -r near`の実コマンドを記録します。GCP設定は既存GeoTIFFのgeotransformに優先します。出力CRS・パラメータ・追加JSONの内容とSHA・画像SHA・ライブラリ/コード版をmanifestに保存します。高次多項式/TPS、画像内容による自動GCP選定、検出モデルは実装していません。

## DEM

FGDのUTF-8 GML3.2 XML/GML/ZIPと、既に地理座標を持つ単バンドGeoTIFFに対応します。公式仕様を参照した合成XMLで検証しました。実配布ZIPへの適合確認は未実施です。1 XMLにつき1 DEM、Linear `+x-y`、明示的startPoint、lat/lon envelopeに限定し、未知形式を黙って処理しません。ZIPの危険パス・重複・CRC、XML128MB・グリッド400万セル上限を検証します。

北西セル番号0,0から東へ、次に南へ並べ、startPointによる先頭省略と末尾省略はNoDataとして扱います。`データなし,-9999.`と正当な負標高を区別します。mesh・元のSRS宣言・測地系名を保持します。

`--reference`には`crs / horizontal_datum / vertical_datum / unit / evidence`を持つ、提供資料から確認したJSONを指定してください。`unit`は`metre`です。未確認値を埋めて実行することは認めません。

```bash
python scripts/phase1b_dem.py --execute --source-id 正規登録済みDEM_ID \
  --asset-id terrain__official_mesh__v1 --reference config/reviewed_dem_reference.json
# JGD2011地理CRSについて確認済みの場合のみ、水平投影と地形処理
python scripts/phase1b_dem.py --execute --source-id 正規登録済みDEM_ID \
  --asset-id terrain__official_mesh_projected__v1 \
  --reference config/reviewed_dem_reference.json --target-crs EPSG:6677 --terrain
```

JGD2000/JGD2011/JGD2024の宣言を別フィールドで保持します。現行PROJのEPSG名がJGD2024と表示される場合も、入力宣言や標高基準を置き換えません。鉛直変換は実装していません。水平再投影はJGD2011→6677の確認可能な操作に限定し、グリッド不足・他datumは停止します。現在配布のJGD2024 DEMはnative COG生成までを想定し、未確認の投影・標高変換は実施しません。

傾斜/陰影は北向き・非回転・メートル投影DEMでのみ実行します。512px windowと1px halo、中央差分を使い、中央/上下左右のNoDataを伝播させます。外周1pxはNoData。傾斜は度、陰影はfloat32の0–255（太陽方位315°、高度45°）です。モザイクは未実装であり、離れたJPEG4枚を連結していません。

## 更新と検証

新規資料の取得・登録は[手動取得ガイド](phase1b_manual_acquisition.md)に従い、別の取得承認を得てPhase 0方式の台帳登録を行ってください。Phase1B CLI自体は原本・取得台帳を変更しません。rawの差替えや既存派生物上書きで更新せず、新しいsource_idとasset_id/版を用います。

```bash
RUINS_RUN_LIVE=1 python -m pytest tests/ -q
python scripts/phase1b_verify.py --execute
python scripts/audit_databank.py --mode full --check-all-hashes \
  --json-output reports/new_full_audit.json
```

監査は完全なPhase1B artifact/manifest組だけを登録済みと認識し、取得台帳のsource_id・原本SHAとも照合します。未登録・破損出力はFAILになります。Phase0履歴レポートを上書きするMarkdown出力引数は、このフェーズでは使いません。再実行は一時領域で再生成してSHAを比較し、一致すれば`already_present_reproduced`を返してDriveは変更しません。
