# Gemini Agent Instructions

このリポジトリの正本指示書は [`firstinstruction.md`](firstinstruction.md) である。まずこれを読んでから [`agent/rules/`](agent/rules/) の全ファイルを確認すること。

- 主担当はGemini 3.8 Flash（モデル名・提供状況はクライアント側で確認。更新可）。
- 現在は **Phase 0: 準備のみ**。解析・候補地生成に着手しない。
- VS Code / CLI主体。GIS用のQGIS Desktop GUIは使わない。`qgis_process`は任意。
- `agent/skills/phase0-preparation/SKILL.md`の手順を実施。
- 取得候補は`source.md`、自動取得のホワイトリストは`config/sources.toml`。
- 不明な利用条件・登録必須データは保留。資格情報や有料データ取得を試みない。
- 完了後にレビュー資料作成→GitHub push→停止。次フェーズはレビュアー承認後。
