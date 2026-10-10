# Rule 50 — Agent Roles & Git

- Phase 1-A executor: Codex. Phase 0 executor: Gemini. モデル情報はログで管理しモデル依存コードは禁止。
- Reviewer: GPT-5.6 Sol High. Geminiはレビュー結果を捏造しない。
- Subagents: Cursor/ClaudeはPhase 0で呼び出さない。
- Push は指定済み`origin`へ通常のpushのみ。`git push --force` / `git reset --hard`は禁止。
- リモートが未設定ならpushに成功したと宣言しない。
- レビュー向け報告にcommit hashと実行結果を示す。環境のバージョンを固定と偽らない。
