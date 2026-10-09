# 神奈川県廃墟調査プロジェクト

**Kanagawa Ruins Research Project** | フェーズ: **0 / 準備のみ** | 作成日: 2026-10-09

神奈川県の歴史地図・行政資料・地理空間データを収集・整理し、将来的に廃神社、廃村、廃道、廃寺、廃施設等の歴史的変遷を調査するための、再現可能なCLI主体の研究基盤。

> **現在は準備フェーズ。候補地点の検出・照合・ランキング・探索地図の生成・現地調査はしない。**

## 対象と体制

- 長期対象: 神奈川県全域。最初の注目地域: 相模原市緑区／旧津久井地域（青野原・青山・鳥屋・寸沢嵐など）。
- 主担当: Gemini 3.8 Flash（利用可能性・名称を実行時に確認。新モデルへの変更は設定と記録のみでよい）。
- レビュアー: GPT-5.6 Sol High（ユーザーがレビューを依頼した段階で確認）。
- 予備: Cursor / Claude（準備フェーズでは呼び出さない）。
- 開発: VS Code / Ubuntu / Python / GIS CLI。QGIS Desktop は**不要**。
- 指示書の起点: [`firstinstruction.md`](firstinstruction.md)。ツール側の入口は [`GEMINI.md`](GEMINI.md)。

## リポジトリ構成

```text
.
├── firstinstruction.md          # 初回実行時の指示書（最優先）
├── GEMINI.md                    # Gemini向けルーティング
├── AGENTS.md                    # 他エージェントとの互換入口
├── source.md                    # 公式・研究データのソース台帳
├── environment.yml              # conda-forge 依存管理
├── Makefile                     # CLIコマンドの短縮
├── agent/
│   ├── rules/                   # スコープ/収集/安全/検証/Git
│   ├── skills/                  # 実行手順（MDのみ）
│   └── commands/                # よく使う定型作業
├── config/sources.toml          # 取得対象ホワイトリスト
├── scripts/
│   ├── check_environment.py     # CLI・GIS Pythonのsmoke test
│   └── fetch_sources.py         # 公開資料のみ取得・ハッシュ記録
├── tests/                       # ネットワーク不要の構造テスト
├── data/raw/                    # バイナリはGit管理対象外
├── data/processed/              # フェーズ0では使用しない
└── reports/
    └── templates/               # レビュー提出用テンプレート
```

## ローカルで開始（Ubuntu + Conda）

```bash
# 1. 空のGitHubリポジトリを作成後、このZIPの内容を配置
cd kanagawa-ruins-research

# 2. conda-forge によるGIS環境作成
conda env create -f environment.yml
conda activate kanagawa-ruins

# 3. 環境テスト: 環境とCLIの状態をレポート出力
python scripts/check_environment.py --output reports/environment_check.json

# 4. 外部通信なしのファイル/ルールテスト
python -m unittest discover -s tests -v

# 5. 公式取得ソースの一覧と取得予定確認（ネットワーク不要）
python scripts/fetch_sources.py --list
python scripts/fetch_sources.py --dry-run --all-approved

# 6. firstinstruction.md に従い、利用条件を確認したのち取得を実行
# python scripts/fetch_sources.py --execute --all-approved
```

`conda`未導入なら環境構築は停止し、導入方法を報告すること。QGISは任意。`qgis_process`の未導入は失敗と扱わない。

## データ取得の設計

`config/sources.toml`に登録済みの**明示的に許可したデータ資源**のみ自動取得。初期登録は、国土地理院の「住居表示住所（相模原市緑区）」ZIPと、相模原市オープンデータ「文化財一覧」CSV。これらは廃墟候補そのものではなく、取得・出典管理の仕組みを検証するための基礎資料。

- 取得物: `data/raw/<source_id>/`
- 来歴: `data/provenance.jsonl`（取得日時、URL、SHA-256、バイト数、利用条件参照先等）
- 別途手続きが必要な旧版地形図・基盤地図情報等は**自動取得しない**。
- 今昔マップの画像をローカル保存する行為は禁止されているため、自動収集しない。
- Gitには通常データ本体を含めない。出典と検査結果のみ共有する。

## フェーズ0の完了条件（すべて確認）

1. OS / Python / パッケージ / GDAL CLI のチェック結果が保存されている。
2. ネットワーク不要のテストが実行され、結果が記録されている。
3. `source.md` の主要公式リンクを確認し、公開条件・認証の要否を整理している。
4. 取得可能なホワイトリスト資料を取得するか、失敗理由を記録している。
5. `reports/setup_report.md`、`reports/data_inventory.md`、`reports/review_request.md` を作成している。
6. Gitの状態を確認してpush。**push後は停止し、ユーザーによるGPTレビューを待つ。**
7. **解析・探索は未実施**である。

## 注意事項

調査候補は現地の安全・立入権限を意味しない。私有地・立入禁止区域には入らない。危険な廃建築物や脆弱な文化財の正確な位置を安易に公開しない。取得データを再配布する場合は個別の利用条件に従う。

使う座標系はデータ単位で記録。2026年更新の国土地理院基盤地図情報ではJGD2024への移行があり、国土数値情報 N03（2026版）ではJGD2011と明記されるため、**CRSを推測して統合しない**。

## ドキュメント

- [初回指示書](firstinstruction.md)
- [公式データソース一覧](source.md)
- [初期ルール](agent/rules/00-phase-gate.md)
- [レビュー時の確認項目](agent/commands/submit-review.md)
