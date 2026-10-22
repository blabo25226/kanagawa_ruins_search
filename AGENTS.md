# Agent Routing

このファイルは将来のCursor / Claude Code / Codexなどに向けた互換入口であり、現在これらのサブエージェントを動かす指示ではない。

最初に`firstinstruction.md`と`agent/rules/*.md`を必ず確認する。既存の作業許可・停止条件は`agent/rules/00-phase-gate.md`を正とする。過去のPhase 1-B/C1専用指示を他フェーズの包括許可として拡張しない。Phase 0の履歴指示は保存し、今回の明示的ユーザー許可が優先する。

モデルの変更はコードの挙動に依存させず、実行ログ・レビュー資料で管理する。

CLIの確認と手動ワーカー運用は[CLI運用手順書](.ai/workers/CLI_SETUP_RUNBOOK.md)を参照する。
この導線は相互呼び出し・自動委任の許可ではない。今回のユーザー指示と既存のフェーズゲートを優先する。
診断の既定動作はCLIの存在確認のみ。認証付き実行には別の明示承認が必要であり、ログインは人間が行う。

2026-10-22の次サイクル（**オフライン調査・QA準備に限る**）は、[roadmap](docs/coordination/20261022_next_cycle_roadmap.md)、[Codex C1作業指示](docs/coordination/20261022_codex_c1_handoff.md)、[Claude Code C2作業指示](docs/coordination/20261022_claude_c2_handoff.md)を参照する。これらは新規取得・Drive復旧試行・台帳追記・Phase 1-D実解析を許可しない。Issue作成によってCLIが自動実行されたとは扱わない。
