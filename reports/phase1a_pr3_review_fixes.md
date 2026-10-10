# PR #3 レビュー指摘への修正・検証

既存PRブランチ `codex/phase1a-gis-foundation` の `6a66d01e2ed188d9862b6106fcd65d4becd128f1` から修正。開始時にfetchし、mainは `9c149f3b97668c133f93a9a3ef0a65ebbc165f6d`、PR #3はOPEN・未マージと確認した。

## 修正

1. `qa/sql.py` の土地利用集計は、各ファイルから `source_vintage`・`landuse_code`・`landuse_label` の3属性だけを選択してから結合する。集計用 `landuse` と年次集計用別名 `layer` にgeometryを含めない。空間ビューのEPSG:6677制限は継続する。
2. `--area` のCLIヘルプ、dry-run/listの入力別JSON、利用ガイドに適用範囲を明記した。津久井bboxはOSM PBFだけの交差選択で、切り詰めは行わない。XML・他のGISは原本の収録範囲を保持する。`--area all` はPBFの範囲選択を解除する。

## 検証

既存6土地利用レイヤーに対し、インメモリDuckDB Spatialで上記属性ビューと保存済みSQLを実行した。分類別・年次別集計は従来の `phase1a_sql_validation.json` と一致し、年次件数はカタログとも一致した。両ビューの3列をDESCRIBEで確認した。

| 対象年 | レイヤー数 | 件数 | 保存CRS |
| --- | ---: | ---: | --- |
| 1976 | 2 | 1,270,000 | EPSG:4301 |
| 2014 | 2 | 1,270,000 | EPSG:6677 |
| 2021 | 2 | 1,270,000 | EPSG:6677 |

実台帳のdry-run（`--include-pbf` 指定）は32入力。`tsukui` はPBF 2入力だけにbboxを表示し、残りは `original_source_coverage` と表示した。`all` は全32入力で原本の収録範囲と表示した。

回帰テスト6件を追加した。混合CRSの合成GeoParquetでgeometry列の不在・空間演算の拒否・分類/年次件数・日本語・欠損値・入力バイト保持を確認する。CLIは既定dry-run・明示dry-run・list・all・helpを検査し、dry-run/listから取り込みが呼ばれないことも確認する。

```bash
RUINS_RUN_LIVE=1 conda run --no-capture-output -n kanagawa-ruins python -m pytest tests/ -v
conda run --no-capture-output -n kanagawa-ruins ruff check src/kanagawa_ruins/qa/sql.py src/kanagawa_ruins/cli.py tests/test_phase1a_review_fixes.py
conda run --no-capture-output -n kanagawa-ruins ruff format --check src/kanagawa_ruins/qa/sql.py src/kanagawa_ruins/cli.py tests/test_phase1a_review_fixes.py
git diff --check
```

Phase 0・既存Phase 1-A・実データ統合テストを含め **91 passed、26 subtests passed**（184.51秒）。既存合成GMLテストのXMLレイヤー名調整による警告2件。Ruffとdiffチェックも成功した。詳細は `phase1a_pr3_review_tests.log`（行末空白のみ除去）、実データ集計と整合性証跡は `phase1a_pr3_review_fixes.json` に記録した。

実データの再取り込み・再変換は行っていない。既存の実データ統合テストを含め、実データは読み取り専用で検証した。合成データの変換テストは専用の一時領域で実行した。raw/ 48ファイル・既存GeoParquet 107ファイル・manifest 107ファイル・取得台帳1ファイル、計263ファイルの2回のSHA-256/サイズ比較はすべて一致し、追加・削除・変更は0件。raw内の取得台帳登録済み42資産のSHA-256も台帳と一致した。元のPhase 0監査レポートと既存検証レポートは保持した。
