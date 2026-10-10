# 神奈川県廃墟調査プロジェクト

**Kanagawa Ruins Research Project** | フェーズ: **1-A / GISデータ統一処理基盤** | 作成日: 2026-10-09

神奈川県の歴史地図・行政資料・地理空間データを収集・整理し、将来的に廃神社、廃村、廃道、廃寺、廃施設等の歴史的変遷を調査するための、再現可能なCLI主体の研究基盤。

> **2026-10-10のユーザー指示によりPhase 1-Aを開始。既存GISの読み込み・検証・CRS変換・GeoParquet化・SQL検索のみ許可。候補地点の検出・ランキング・実在判定・外部公開・画像認識・現地調査はしない。**

実行方法: [Phase 1-A利用ガイド](docs/phase1a_usage.md)。派生物は `$RUINS_DATA_ROOT/processed/phase1a/`、取得台帳とrawは不変。下記Phase 0手順・完了条件は履歴として保持する。

## 対象と体制

- 長期対象: 神奈川県全域。最初の注目地域: 相模原市緑区／旧津久井地域（青野原・青山・鳥屋・寸沢嵐など）。
- Phase 1-A実装: Codex。過去のPhase 0主担当: Gemini。モデル情報は実行記録で管理。
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

## ストレージ構成とデータ保存ルール

本プロジェクトでは、コードと大容量データを分離管理します。

1. **ローカルPC (`kanagawa_ruins_search`)**:
   - 保存対象: ソースコード、設定ファイル、エージェント指示書、Markdownレポート、テストコード、小容量ログ
   - 一時データ容量制限: 原則 **1GB以内**。処理中のみジョブ専用一時領域の暫定25GB上限まで許可。開始前に空きを確認し、Drive保存・SHA-256照合後、異常終了時を含め削除する。rclone VFS容量も監視し、既存設定は変更しない。
2. **Google Driveデータバンク (`kanagawa_ruins_search_databank`)**:
   - 保存対象: 古地図、航空写真、標高データ、地理空間データ、歴史資料、GIS解析用大容量ファイル、中間生成物
   - 正規保存先: Google Drive側の `data/` 配下（`raw/`, `processed/`, `provenance.jsonl` など）

### 環境変数 `RUINS_DATA_ROOT` の設定

Google Drive側のデータディレクトリを環境変数 `RUINS_DATA_ROOT` で参照します。パスをコードに直接ハードコードしないでください。

```bash
# .env ファイルの作成（プロジェクトルート、.gitignore対象）
cp .env.example .env
# .env 内にGoogle Driveマウント先を設定
# 例: RUINS_DATA_ROOT=/home/blabo/gdrive/kanagawa_ruins_search_databank/data

# またはシェルの環境変数としてエクスポート
export RUINS_DATA_ROOT=/home/blabo/gdrive/kanagawa_ruins_search_databank/data
```

※Google Driveのマウント状態（`fuse.rclone`等）や読み書き可能性は `python scripts/check_environment.py` で自動検証されます。

## ローカルで開始（Ubuntu + Conda）

```bash
# 1. 仮想環境の構築 (conda-forge)
conda env create -f environment.yml
conda activate kanagawa-ruins

# 2. 環境変数設定 (.env作成)
cp .env.example .env

# 3. 環境テスト: GISライブラリ・CLI・rclone・ストレージマウントの検証
python scripts/check_environment.py --output reports/environment_check.json

# 4. ユニットテスト
python -m unittest discover -s tests -v

# 5. 公式取得ソースの一覧と取得予定確認（ドライラン）
python scripts/fetch_sources.py --list
python scripts/fetch_sources.py --dry-run --all-approved

# 6. 承認済み公式データのGoogle Drive側への取得
python scripts/fetch_sources.py --execute --all-approved
```

`conda`未導入なら環境構築は停止し、導入方法を報告すること。QGISは任意。`qgis_process`の未導入は失敗と扱わない。

## データ取得の設計と役割の位置付け

`config/sources.toml`に登録済みの**明示的に許可したデータ資源**のみ自動取得。初期登録は、国土地理院の「住居表示住所（相模原市緑区）」ZIPと、相模原市オープンデータ「文化財一覧」CSV。これらは廃墟候補そのものではなく、取得・出典管理の仕組みを検証するための基礎資料。

### データの役割と制約に関する注意（GPTレビュー反映）
- **相模原市 文化財一覧**: 現存神社や史跡を自動的に除外・判定するための完全なデータベースではありません。指定・登録文化財の名称・位置・保護状況を照合するための**参考データ**として位置付けます。
- **国土地理院 住居表示住所**: 現代の字名・番地や集落位置を参照するための空間データであり、**神社の現存判定には直接使用しません**（神社境内に住居表示が付番されていないケースや、字名のみ残存しているケースがあるため）。

- 取得物: `$RUINS_DATA_ROOT/raw/<source_id>/`（Google Drive上）
- 来歴: `$RUINS_DATA_ROOT/provenance.jsonl`（取得日時、URL、SHA-256、バイト数、利用条件参照先等）
- 別途手続きが必要な旧版地形図・基盤地図情報等は**自動取得しない**。
- 今昔マップの画像をローカル/サーバ保存する行為は禁止されているため、自動収集しない。
- Gitにはデータ本体を含めない。出典と検査結果のみ共有する。

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
