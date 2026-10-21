# Agent Routing

このファイルは将来のCursor / Claude Code / Codexなどに向けた互換入口であり、現在これらのサブエージェントを動かす指示ではない。

最初に`firstinstruction.md`と`agent/rules/*.md`を必ず確認する。Phase 1-Bの許可範囲は`agent/rules/00-phase-gate.md`を正とする。Phase 0の履歴指示は保存し、今回の明示的ユーザー許可が優先する。

モデルの変更はコードの挙動に依存させず、実行ログ・レビュー資料で管理する。

CLIの確認と手動ワーカー運用は[CLI運用手順書](.ai/workers/CLI_SETUP_RUNBOOK.md)を参照する。
この導線は相互呼び出し・自動委任の許可ではない。今回のユーザー指示と既存のフェーズゲートを優先する。
診断の既定動作はCLIの存在確認のみ。認証付き実行には別の明示承認が必要であり、ログインは人間が行う。
