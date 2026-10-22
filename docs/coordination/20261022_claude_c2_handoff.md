# Claude Code 作業依頼：Phase 1-C2品質監査と欠損4 ZIPの安全な拡張設計

**担当**: Claude Code（次の独立作業）
**ベース**: 最新`origin/main`、専用ブランチ `claude/phase-next-c2-coverage-qa`
**作業場所**: 別worktree。C1変更・既存派生GISの上書き・Driveアクセス・新規取得・CLI間自動委任は禁止。

## まず読む資料
- `firstinstruction.md`, `CLAUDE.md`, `AGENTS.md`, `agent/rules/*.md`
- `docs/coordination/20261022_next_cycle_roadmap.md`
- `docs/coordination/20261022_data_readiness.md`
- `reports/phase1c2_results.json`, `reports/phase1c2_landuse_change.md`, `reports/phase1c2_transition_matrix.md`, `reports/phase1c2_data_limitations.md`, `reports/phase1c2_regional_analysis.md`
- `src/kanagawa_ruins/landuse_change/`, `scripts/phase1c2_analyze.py`, `tests/test_phase1c2_*.py`
- `docs/phase1d_integration_design.md`（**設計のみ**）
- [公式の土地利用細分メッシュ配布](https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-L03-b-2021.html)

## 背景と目的
C2はL03-bの2014/2021年における県土1,818.4 km² / 75.3%について v0.2.0 を公表済みと記録。県南部・県西部の不足（597.8 km²）は、1次メッシュ`5238`/`5239`の原本が未取得であることが主因。**公式公開を確認した4 ZIPはまだ取得せず、分析版の偽陽性・地理的欠落・年次ずれ・再現性をオフラインで調べる。**

## 必須タスク
1. v0.2.0 `results.json` と関連Markdownの数値（県内解析面積、4.58%/83.2 km²、成分比57.1/19.6/12.0/11.3%、境界76.8%、農地・建物の純増減等）を**GitHubに存在するファイル同士で**照合。整合／不整合／丸め／未立証を区別した表を作成。**旧版「82%が単独セル」を復活させない**。
2. 公開ページに実在する4 ZIPの名前を固定した**取得前計画案（実取得なし）**：`L03-b-14_5238-jgd_GML.zip`、`L03-b-21_5238-jgd2011_GML.zip`、`L03-b-14_5239-jgd_GML.zip`、`L03-b-21_5239-jgd2011_GML.zip`。公式表示の概算容量とworld/Tokyo datumの違い、同意・ライセンス・配布URLの検証事項を記載する。実byte/SHAを捏造しない。
3. **オフライン合成テスト**を用い、既存コードが4メッシュ分の新しい年度別パッケージへ拡張できるかを点検する。対象はメッシュ集合、一意コード、年次source_idと内包メタデータの不一致、unknown/NoData/海域、県界・観測可能性、1976 Tokyo Datum、CODH藤野/相模湖の内容逆転、原本ハッシュとimmutable publication。必要ならC2限定の小さな修正を提案／実装する。
4. `analysis_scope`を既存75.3%から更新するための**受入条件**を決める（受入前は75.3%固定）。市区町村単位は被覆率に応じてcomparable/reference_partial/excludedを継続。ゼロ・未観測の区別ができるschemaを明示する。
5. 将来C1と結合する場合のJIS 1 km基準とC1の投影1 km格子の違い、2014→2021 vs 2014→2025の時間差を**実統合せず**検証可能な合成QA仕様にまとめる。空間依存性（Moran's I、空間ブロック）と変化の判読差を残す。
6. `reports/phase_next_c2_offline_qa.md`、`docs/coordination/phase_next_c2_acquisition_plan.md`（**承認前・未実施**）、必要ならC2限定のテスト・コード、検査ログをPRに提出する。

## 受入基準
- 過去に実解析済み範囲と、まだ取得していない4 ZIPを分ける。取得前に成果を「100%」へ更新しない。
- 実Drive/GIS原本の読取・新規ダウンロード・Webスクレイピング・OAuth/rclone調整・遠隔書込み・外部地点公開を行わない。公的URLの既知情報とGitHubの保存済みコード・報告のみ使用（追加の公式ページ確認ができなければ未確認と記載）。
- 合成fixtureテストの件数／skipを記録。`python -m compileall -q ...`、`git diff --check`、既存C2の合成テストを実行し、結果と実Drive live testを明確に区別。
- C2専用ファイルのみ変更し、PRで停止。mainには自分でマージしない。
- Phase 1-Dの実データ統合・複合ランキング・地点抽出／公開は行わない。

## 報告フォーマット
`baseline_main_sha`, `source_manifest_version`, `scope_before`, `new_files_acquired=0`, `scope_after=unchanged`, `metadata_checks`, `consistency_table`, `tests_passed`, `tests_skipped`, `open_questions`, `requires_user_approval`を明示する。
