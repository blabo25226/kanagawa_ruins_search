# Skill: GIS CLI Doctor

```bash
conda activate kanagawa-ruins
python scripts/check_environment.py --output reports/environment_check.json
python -m unittest discover -s tests -v
```

環境チェックでは合成データのみで、Python GIS依存・GDAL CLI・CRS変換・小さなラスタ作成・OpenCVの稼働を確認する。実測地理データの操作・解析は禁止。`qgis_process`はoptionalと記載する。

問題が出た場合は`reports/setup_report.md`へ実際のエラーメッセージ、試した解決策、再試行結果を記録。成功の捏造禁止。
