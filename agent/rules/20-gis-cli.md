# Rule 20 — GIS CLI Only

- 実行経路はVS CodeターミナルからのPython / GDAL CLIを中心とする。
- `gdalinfo`, `ogrinfo`, `gdalwarp`、および `rclone` 等は `--version`で存在・動作確認。
- Google Drive（FUSE / rclone）のマウント状態および読み書き可能性を必ず事前に確認する。マウントされていないローカルパスへの誤書き込みを禁止する。
- GeoPandas、Rasterio、PyProj、Shapely、OpenCVのスモークテストを実施。
- `qgis_process` は任意・不在でも構わない。QGIS Desktopの起動・GUI自動操作は禁止。
- CRSはファイルメタデータに基づく。EPSG:4326への勝手な置換やJGD2011/JGD2024の混同は禁止。
- Phase 1-Aでは既存GISの読み込み・CRS変換・SQL検索・品質検証を許可。距離・面積は原則EPSG:6677。元CRS宣言と変換履歴を保持し、不明CRSは推測しない。画像位置合わせ・候補探索は対象外。
