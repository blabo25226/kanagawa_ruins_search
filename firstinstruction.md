# 初回実行指示書 — Phase 0: Preparation Only

この文書は **Gemini 3.8 Flash（主担当）** に渡す初回指示書である。新モデルに切り替えた場合も同じ手順を踏む。完了後はGitHubにpushして**作業を停止**し、ユーザーがGPT-5.6 Sol Highにレビュー依頼するまで解析に進まないこと。

## 0. 先に読むファイル

1. `README.md`
2. `GEMINI.md`
3. `agent/rules/` 配下のすべてのMarkdown
4. `source.md` と `config/sources.toml`
5. `agent/skills/phase0-preparation/SKILL.md`

ルールが競合する場合は、ユーザーの明示的指示、Phase 0の停止条件、法令・利用規約を優先する。

## 1. 今回のゴール

A. VS Codeターミナルだけで扱えるPython/GIS処理環境を作成・点検する。
B. 公的なGIS・歴史資料の入手先、利用条件、地理的範囲、データ形式を整理する。
C. 公開条件が確認できた小規模な基礎データをダウンロードし、出典と検査結果を残す。
D. 運用用Markdownと再現可能なコマンドを整える。
E. pushし、レビュー待ちで終了する。

**禁止事項**：実際の廃墟候補の抽出、鳥居・建物等の画像認識、候補の座標生成、廃道推定、地図差分解析、ランキング、現地調査計画、情報公開用マップの作成。これらはPhase 1以降。

## 2. 実行手順（飛ばさない）

### Step 1: Gitと作業環境の確認

- `pwd`, `git status --short --branch`, `git remote -v`, `uname -a`, `which python`, `python --version`, `conda --version`を実行。
- ユーザーが既存リポジトリを提示した場合、破壊的な上書きは禁止。新規リポジトリなら`main`への初期コミット可。リモート未指定ならpushは保留し、必要事項だけ報告。
- 認証情報を表示・保存・コミットしない。GitHubへのpushはユーザーが接続済みの認証方法を使う。

### Step 2: GIS CLIの構築と動作確認

```bash
conda env create -f environment.yml
conda activate kanagawa-ruins
python scripts/check_environment.py --output reports/environment_check.json
python -m unittest discover -s tests -v
```

- `conda env create`で既存環境エラーなら、再作成で壊さず `conda env update -n kanagawa-ruins -f environment.yml --prune` を慎重に使う前に状態を報告する。
- `gdalinfo`, `ogrinfo`, `gdalwarp`, `python` とGeoPandas/Rasterio/PyProj/Shapely/OpenCVを検査する。`qgis_process`は**任意**。QGIS GUIは起動しない。
- 環境チェックがNGならログ・原因・再試行内容を`reports/setup_report.md`に残す。虚偽の成功報告は禁止。
- インストール済みの既存Conda環境には手を加えず、このプロジェクト用環境を独立させる。

### Step 3: データソース監査

- `source.md`にある国土地理院、国土数値情報、農研機構、相模原市の公式情報についてURL・公開年月日・認証要否・ライセンスを検査。
- 直接DLとブラウザでのみ利用可能なサービス、購入・交付が必要なデータを明確に分ける。
- 2026年版N03神奈川県（`N03-20260101_14_GML.zip`）は重要だが、**ダウンロード画面経由の配布であり直リンクを推測しない**。手動取得の可否を調べ、必要ならユーザーへの確認事項に記す。
- 相模原市の公開GISは津久井地域に未提供エリアがあり得るため、網羅性を保証しない。
- 各データに出典名・配布ページ・原典URL・測地系・取得日・再配布条件・範囲・フォーマット・サイズを記録する。

### Step 4: ホワイトリストの公開データだけを取得

```bash
python scripts/fetch_sources.py --list
python scripts/fetch_sources.py --dry-run --all-approved
python scripts/fetch_sources.py --execute --all-approved
```

- この取得対象は小さな公開資料に限定。ZIP/CSVのデータ本体はGitHubにpushしない。
- リダイレクト先、形式、サイズ、HTTP応答、SHA-256をチェック。失敗時は理由を報告して次へ。
- 申請、会員登録、ログイン、課金、CAPTCHA回避、タイルの連続取得、オンライン最高画質画像の保存・スクレイピングを行わない。
- 明示的に許可されていないURLをスクリプトに追加して自動取得しない。権利や取得条件に疑義がある場合は取得を保留する。
- ダウンロードした資料の中身の探索分析は行わない。検査は拡張子・ヘッダー・ファイル数・ハッシュ・容量・形式確認まで。

### Step 5: 報告とコミット

`reports/templates/`から以下を作成する。

1. `reports/setup_report.md`: OS/CLI/Pythonの版、PASS/FAIL、コマンド、環境構築状況、未解決問題。
2. `reports/data_inventory.md`: データの取得可否・取得物・出典・条件・ハッシュ・利用範囲。
3. `reports/review_request.md`: 変更ファイル、テスト結果、レビューしてほしい論点、次フェーズ提案（**実行はしない**）。

`git status --short`, `git diff --check`, `python -m unittest discover -s tests -v` を最後に再実行。`data/raw`・機密情報が追跡対象に混ざっていないことを確認。

```bash
git add README.md firstinstruction.md source.md GEMINI.md AGENTS.md   agent config scripts tests reports environment.yml Makefile .gitignore
# git commit -m "Initialize preparation-only geospatial research environment"
# git push -u origin main
```

`git add`はリポジトリの状態に合わせて調整。**リモート未設定ならpushしない**。pushに失敗したら正確に報告する。`--force`禁止。

## 3. 最終応答フォーマット

- 使用したGitHubリポジトリURLとコミットハッシュ（実際に取得できた場合のみ）。
- 準備フェーズのPASS/FAILと主なバージョン。
- ダウンロード済みデータ名／保留データ名と理由。
- 利用条件に関する懸念。
- GPTレビュー対象ファイル一覧。
- 最後に「Phase 1の解析は未着手。GPTレビュー待ち」と明記。

**この最後の報告を出したら停止する。**
