# CLI 運用手順書（Codex / Claude Code / Cursor Agent / Antigravity）

対象: 人間オペレーターと、4 CLI のいずれかで動くエージェント AI。
どの CLI も「呼び出し元（オーケストレータ）」にも「ワーカー」にもなれる。リポジトリ固有の事項は
`<REPO_URL>`（clone 元）と `<REPO_DIR>`（clone 先）で表す。

| CLI                   | コマンド                     | 認証方式                       | ログイン状態の確認            | 非対話実行                | 更新                     |
| --------------------- | ---------------------------- | ------------------------------ | ----------------------------- | ------------------------- | ------------------------ |
| Codex                 | `codex`                    | ChatGPT アカウント（ブラウザ） | `codex login status`        | `codex exec "<prompt>"` | 公式インストーラを再実行 |
| Claude Code           | `claude`                   | claude.ai アカウント           | `claude auth status`        | `claude -p "<prompt>"`  | `claude update`        |
| Cursor Agent          | `agent` / `cursor-agent` | Cursor アカウント（ブラウザ）  | `agent status`              | `agent -p "<prompt>"`   | `agent update`         |
| Antigravity（Gemini） | `agy`                      | Google アカウント（AI Pro 等） | `agy models` が成功すること | `agy -p "<prompt>"`     | `agy update`           |

Linux x86_64 / arm64 と macOS が対象（Windows は WSL2 の Ubuntu 内で Linux 手順を実施）。
手順は Linux (Ubuntu) で実測。macOS の `apt` は `brew` に読み替える。

## 0. 共通原則

- 認証は各公式 CLI が所有する。パスワード・トークン・API キーをリポジトリ、ログ、プロンプトに書かない。
  認証ファイル（例: `~/.codex/auth.json`）の中身を `cat` しない。
- **ログイン（ブラウザ操作）は人間だけが行う。** エージェントはログイン切れを検知したら自分で再ログインせず、
  リポジトリの人間介入キュー／ハードストップ規約に従って「どの CLI の再ログインが必要か」を記録し、
  ログイン不要の他タスクを続ける。
- API キーでの回避はしない（アカウント/チームシート運用の場合、認証方式を勝手に切り替えない）。
- 子 CLI を呼ぶときは既定を読み取り専用とし、書き込みは隔離ブランチ/worktree と書き込み範囲を宣言したタスクのみ。
  権限確認を丸ごと飛ばすフラグ（`--dangerously-skip-permissions`、`--dangerously-bypass-approvals-and-sandbox`、
  `--force`、`--yolo`）は使わない。

## 1. 新しい PC でのインストール（ダウンロード）— 人間が実施

インストーラはすべてユーザー領域（`~/.local/bin` や各 CLI のホーム）に入り、sudo は不要。

### 1-1. 前提ツール

```bash
sudo apt update && sudo apt install -y git curl gh      # macOS: brew install git gh
git --version && gh --version
echo "$PATH" | tr ':' '\n' | grep -x "$HOME/.local/bin" || echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
exec bash -l                                            # PATH を反映
```

Node.js は 4 CLI のどれにも不要（Codex の npm 版を使う場合のみ必要）。

### 1-2. GitHub とリポジトリ

```bash
gh auth login                                           # GitHub.com / HTTPS / ブラウザ。人間が実施
gh auth status
git clone <REPO_URL> <REPO_DIR>
cd <REPO_DIR>
git config user.name  "<name>"
git config user.email "<email>"
```

作業ブランチへ `git switch` してから進める。リポジトリ固有の追加セットアップ（言語環境など）は
リポジトリの README に従う。

### 1-3. 4 CLI のダウンロード

各インストーラは先にファイルへ保存して内容を確認してから実行するのが安全。下は公式の最短形。

```bash
# Codex
curl -fsSL https://chatgpt.com/codex/install.sh -o /tmp/codex_install.sh && CODEX_NON_INTERACTIVE=true sh /tmp/codex_install.sh
#   代替: npm install -g @openai/codex（Node が必要）

# Claude Code
curl -fsSL https://claude.ai/install.sh | bash

# Cursor Agent（コマンドは agent と cursor-agent の両方ができる）
curl https://cursor.com/install -fsS | bash

# Antigravity CLI（Gemini。コマンドは agy）
curl -fsSL https://antigravity.google/cli/install.sh | bash
```

PATH が書き換えられた場合は `exec bash -l` で反映する。

### 1-4. インストール確認（ログイン前）

```bash
codex --version && claude --version && agent --version && agy --version
command -v codex claude agent cursor-agent agy
```

すべてバージョンが出れば 2 章へ。`command not found` は 1-1 の PATH を確認する。

更新は表の「更新」列のコマンド。失敗したら 1-3 のインストーラを再実行する。

## 2. 初回ログイン — 人間が実施

ブラウザが開ける端末で行う（SSH 先ならログイン用 URL を手元 PC のブラウザで開く）。

```bash
# Codex: 対話 UI を起動し "Sign in with ChatGPT" を選ぶ
codex
codex login status

# Claude Code
claude auth login               # 利用するアカウント種別（claude.ai）を選ぶ
claude auth status

# Cursor Agent（ブラウザが開けない場合は NO_OPEN_BROWSER=1 を付け、表示された URL を手動で開く）
agent login
agent status

# Antigravity CLI: 初回起動時の Google ログイン案内に従う
agy
agy models                      # モデル一覧が出ればログイン成功
```

注意:

- `agy` には専用の status/login サブコマンドが無い（`agy --help` で確認）。初回の画面表示は未検証のため、
  実際のログイン時に確認し、本書へ反映すること。
- Gemini 単体 CLI（`gemini`）は Google AI Pro 等の個人アカウントログインが非対応のため、`agy` を使う。

### 2-1. リポジトリ側のワーカー連携設定（リポジトリが提供している場合のみ）

リポジトリに CLI 呼び出し用ラッパー（例: `.ai/workers/*.sh`）や許可ルールがある場合は、その README に従う。
一般に必要な作業:

1. 呼び出し元 CLI でリポジトリを「信頼する」設定にする（Codex は `~/.codex/config.toml` の
   `[projects."<REPO_DIR>"] trust_level = "trusted"`、Claude/Cursor は初回起動時の信頼確認）。
2. 許可ルールファイルを追加・変更した後は、呼び出し元 CLI を再起動する。
3. 全ワーカーに読み取り専用の疎通確認をする:

```bash
<各ワーカーの呼び出し> "Reply with exactly: WORKER_OK"
```

すべて応答すれば完了。認証エラーが出た CLI は 2 章に戻ってログインする。

## 3. 2 回目以降（ログイン済みの日常運用）

### 3-1. 人間: セッション開始時チェック（約 1 分）

```bash
codex login status && claude auth status && agent status && agy models | head -3
```

- すべて成功 → ログイン不要でそのまま作業開始（トークンは各 CLI が自動更新する）。
- 失敗した CLI だけ 2 章の該当コマンドで再ログイン。

人間が直接使う（リポジトリルートで）:

```bash
cd <REPO_DIR>
codex      /  claude      /  agent      /  agy                       # 対話
codex exec "<task>"  /  claude -p "<task>"  /  agent -p "<task>"  /  agy -p "<task>"   # 非対話
```

### 3-2. エージェント AI: 他の CLI を呼ぶとき（ログイン操作はしない）

どの CLI が呼び出し元でも手順は同じ。

1. 自分と同じ CLI は呼ばない（別 CLI を独立した第 2 の視点として使う）。
2. リポジトリにラッパーがあればそれを優先する。ラッパーが無い CLI は、下の読み取り専用の直接呼び出しを使う。
3. 既定は読み取り専用。書き込みは隔離ブランチ/worktree と書き込み範囲を宣言したタスクだけ。
4. 成功判定は終了コード 0 だけで行わない。期待成果物、受け入れテスト、必要なコミットを確認する。

読み取り専用の直接呼び出し:

```bash
codex exec --sandbox read-only "<prompt>"
claude -p --permission-mode plan --tools Read,Glob,Grep "<prompt>"
agent -p --trust --mode=ask "<prompt>"
agy -p --mode plan --sandbox "<prompt>"
```

書き込みを許す場合の例（隔離ブランチ上でのみ）:

```bash
codex exec --sandbox workspace-write "<prompt>"
claude -p --permission-mode acceptEdits "<prompt>"
agent -p --trust "<prompt>"          # --force/--yolo は使わない
agy -p --mode accept-edits "<prompt>"
```

`agy` の非対話モードは、書き込みが拒否されても終了コード 0 を返すことがある。
`agy` に成果物を残させたいときは、標準出力を呼び出し元のシェルがファイルへ保存し、
保存後に内容を検証する方式にする。

### 3-3. 認証エラー時のエージェントの動き

| 症状                               | 動き                                                                                    |
| ---------------------------------- | --------------------------------------------------------------------------------------- |
| 子 CLI が認証/ログインエラーを返す | 1 回だけ再試行。同じなら別の CLI へフォールバック                                       |
| フォールバック先もない             | 人間介入キューに「どの CLI の再ログインが必要か」を記録し、ログイン不要の他タスクを続行 |
| 容量/レート制限                    | リポジトリのリトライ/フォールバック規約に従う                                           |

人間は通知を受けたら 2 章の該当コマンドだけ実行し、キューの項目を閉じる。
