# CLI 運用手順書（Codex / Claude Code / Cursor Agent / Antigravity）

対象: 人間オペレーターと、4 CLI のいずれかで動くエージェント AI。
どの CLI も手動の設計上は「呼び出し元（オーケストレータ）」にも「ワーカー」にもなれるが、
本書の存在は自動委任の許可でも、認証済み相互呼び出しの実証でもない。既存のフェーズゲートと明示的ユーザー指示を優先する。リポジトリ固有の事項は
`<REPO_URL>`（clone 元）と `<REPO_DIR>`（clone 先）で表す。

| CLI                   | コマンド                     | 認証方式                       | ログイン状態の確認            | 非対話実行                | 更新                     |
| --------------------- | ---------------------------- | ------------------------------ | ----------------------------- | ------------------------- | ------------------------ |
| Codex                 | `codex`                    | ChatGPT アカウント（ブラウザ） | `codex login status`        | `codex exec "<prompt>"` | 公式インストーラを再実行 |
| Claude Code           | `claude`                   | claude.ai アカウント           | `claude auth status`        | `claude -p "<prompt>"`  | `claude update`        |
| Cursor Agent          | `agent` / `cursor-agent` | Cursor アカウント（ブラウザ）  | `agent status`              | `agent -p "<prompt>"`   | `agent update`         |
| Antigravity（Gemini） | `agy`                      | Google アカウント（AI Pro 等） | `agy models` が成功すること | `agy -p "<prompt>"`     | `agy update`           |

この表の認証・更新・導入は人間向け手順であり、今回実行していない。`agy models`の成功だけで
認証済み推論ができると判定しない。対応プランは各サービスの現行仕様を人間が確認する。

Linux x86_64 / arm64 と macOS が対象（Windows は WSL2 の Ubuntu 内で Linux 手順を実施）。
2026-10-21のLinux実測は、導入済み4 CLIの`--version` / `--help`のみ。
インストール・ログイン・macOS動作・認証付き`WORKER_OK`は今回未検証。macOSの導入は対応する公式手順を確認する。

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
- `gemini`と`agy`は別CLI。本書の対象は`agy`であり、`gemini`の対応アカウントやプランはここでは断定しない。

### 2-1. リポジトリ側のワーカー連携設定（リポジトリが提供している場合のみ）

リポジトリに CLI 呼び出し用ラッパー（例: `.ai/workers/*.sh`）や許可ルールがある場合は、その README に従う。
一般に必要な作業:

1. 人間が実行対象worktreeと信頼設定を確認する。診断のために信頼設定を自動変更しない。
   特にCursorの`--trust`は信頼確認の省略であって、read-onlyやsandboxの指定ではない。
2. 許可ルールファイルを追加・変更した後は、呼び出し元 CLI を再起動する。
3. 認証付き疎通は別途の明示的なローカル環境承認がある場合だけ、後述の実行契約に従って1ワーカーずつ手動実行する:

```bash
<各ワーカーの呼び出し> "Reply with exactly: WORKER_OK"
```

期待する完全一致応答を確認しても、個別疎通を確認しただけであり、安全な多段委任やGIS処理の動作確認にはならない。
認証エラーなら停止し、人間だけが2章のログインを行う。今回このテストは未実施。

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
2. 明示許可されたタスクだけを委任する。現時点の診断スクリプトは実行ラッパーではない。
   下の例を自動実行せず、実機help・承認・OS隔離を確認してから手動実行する。
3. 既定は読み取り専用。書き込みは隔離ブランチ/worktree と書き込み範囲を宣言したタスクだけ。
4. 成功判定は終了コード 0 だけで行わない。期待成果物、受け入れテスト、必要なコミットを確認する。

以下は承認後の候補コマンド。認証済み動作・外部サービスの無変更を保証する例ではない。
CLIモードやプロンプトだけでOS/ネットワークのread-only制約を代替しない。
`--trust`を既定で付けず、必要な信頼確認は人間が行う。

```bash
codex exec --sandbox read-only "<prompt>"
claude -p --permission-mode plan --tools Read,Glob,Grep "<prompt>"
agent -p --mode=ask "<prompt>"
agy -p --mode plan --sandbox "<prompt>"
```

書き込みを許す場合の例（隔離ブランチ上でのみ）:

```bash
codex exec --sandbox workspace-write "<prompt>"
claude -p --permission-mode acceptEdits "<prompt>"
agent -p "<prompt>"                 # 信頼設定は人間が確認。--force/--yolo は使わない
agy -p --mode accept-edits "<prompt>"
```

`agy` の非対話モードは、書き込みが拒否されても終了コード 0 を返すことがある。
これは運用上の注意であり、本Issueで再現・検証した挙動ではない。
`agy` に成果物を残させたいときは、標準出力を呼び出し元のシェルがファイルへ保存し、
保存後に内容を検証する方式にする。

### 3-3. 認証エラー時のエージェントの動き

| 症状                               | 動き                                                                                    |
| ---------------------------------- | --------------------------------------------------------------------------------------- |
| 子 CLI が認証/ログインエラーを返す | 即時停止。自動再試行・別CLIへの自動フォールバックはしない                               |
| フォールバック先もない             | 人間介入キューに「どの CLI の再ログインが必要か」を記録し、ログイン不要の他タスクを続行 |
| 容量/レート制限                    | リポジトリのリトライ/フォールバック規約に従う                                           |

人間は通知を受けたら 2 章の該当コマンドだけ実行し、キューの項目を閉じる。

## 4. 検証済みの範囲と診断（Issue #13）

`scripts/ci/check_worker_cli.py`は標準ライブラリのみを使う。既定はPATH上の存在確認だけで、
CLIプロセスやモデルを起動しない。見つからないものは`NOT_INSTALLED`とし、自動導入しない。
`--probe-installed`を明示した場合だけ、固定された`--version` / `--help`（Codexは`exec --help`も）を読む。
プロンプト、login/status/models/update、任意コマンドは実行しない。これは認証状態の確認ではない。

```bash
# 既定: CLI起動なし。GitHub Actionsでも認証不要
python scripts/ci/check_worker_cli.py
# 導入済みCLIの情報表示だけ。既存report名は再利用しない
python scripts/ci/check_worker_cli.py --probe-installed --output reports/new_worker_cli.json
# 疎通テスト候補をJSONへ準備するだけ。これもモデル実行なし
python scripts/ci/check_worker_cli.py --plan-worker-ok agy
```

2026-10-21の実測（生help/認証情報は保存せず、固定した引数名・版・出力SHAのみ記録）:

| CLI / version | helpで確認した引数・値 | 確認していないこと |
| --- | --- | --- |
| Codex 0.163.0 | `exec --help`、`--sandbox`。`read-only`は公式referenceにも記載 | 認証付きexec、実機sandboxの強制範囲 |
| Claude 2.1.280 | `--print`、`--permission-mode`、`--tools`、plan/acceptEdits | 認証付きprint、MCP/hooksを含む外部書込みの防止 |
| Cursor agent 2026.09.23（build 86fc751） | `--print`、`--mode`、ask/plan、`--sandbox`、`--trust` | Askモードと外部サービスを含む厳密な隔離 |
| Antigravity agy 1.3.2 | `--print`、`--mode`のplan/accept-edits、`--sandbox` | 認証付きprint、sandboxで実際に禁止される操作 |

**agyの訂正:** レビュー時に`--mode`未対応の疑いがあったが、導入済み1.3.2のhelpには実在した。
そのため上の候補例は保持する。古い版にも使えるとは主張しない。公式codelabと実機helpが異なる場合は、
版と観測結果を明記する。モード名の存在と、実際のread-only強制は別の検証項目である。

2026-10-22（JST）の統合前再確認では、Codex 0.163.0、Claude 2.1.280、Cursor agent 2026.09.23、
`agy 1.4.4`の固定9情報表示コマンドが成功した。`agy`の`--mode`とplan/accept-edits、`--sandbox`は
新版helpにも存在する。結果は`reports/worker_cli_observed_20261022.json`に保持し、旧版の観測は変更しない。
認証付き`WORKER_OK`と独立したDriveアクセスは未検証のまま。別PR #18のFUSE読取成功は独立API経路の証明ではない。

診断は直列・再試行なし・直接起動最大9プロセス・1プロセス10秒・起動/読取予算45秒、出力128KiB上限。
プロセス群の終了待ちは別枠で最大2秒/件。直接起動数の上限はCLI内部の補助プロセス数を保証するものではない。
最初の失敗/timeout/出力超過で停止する。子プロセス群を終了し、生stdout/stderrや環境変数はログへ出さない。
子には認証用環境変数を渡さず、APIキーの読出しも行わない。CLIの情報表示自体はOS sandboxではなく、
CLI内部の起動時telemetry/cache等を禁止した保証はない。作業cwdは空の一時領域とする。
ヘルプ診断は既存インストールを前提にする。CIでは実CLIを導入せず、既定の存在確認とmockテストだけを行う。

一次資料（2026-10-21照合）:

- [OpenAI CLI reference](https://developers.openai.com/codex/cli/reference)
- [Claude CLI reference](https://code.claude.com/docs/en/cli-reference)
- [Cursor CLI overview](https://prod.cursor.com/docs/cli/overview)
- [Google Antigravity CLI codelab](https://codelabs.developers.google.com/sdd-agy-cli?hl=ja)

## 5. 委任の実行契約と未実施の認証テスト

以下は今後の手動実行契約であり、実行済みの仕組みではない。`--plan-worker-ok <cli>`は候補argvと
承認要件を表示するだけで、認証付きモデルを起動する機能は本診断に含めない。
将来実行ラッパーを追加する場合、独立した実行フラグとユーザーのローカル環境承認を両方必須にする。
このIssueの開始指示・AGENTS.mdへの導線・CLIの存在を、その承認として扱わない。

- jobには`job_id`、親/子CLI、依頼内容、受入条件、承認の出所、許可パス、read-only/write区分、
  一意のbranch/worktree、期限、出力先を明記する。ログインは人間のみ。GitHub/Driveへの書込み権限を暗黙に継承させない。
- 起動は人間または明示許可された親1つから子1つまで。子は他CLI/自分/親を呼ばない。
  `KANAGAWA_WORKER_CLI_DEPTH=1`を子へ渡し、本診断は深さ0以外を拒否する。
  この環境変数は協調規約であり、悪意あるコマンドに対するOS隔離ではない。
- ワーカーごとに`workers/<job-id>-<cli>`ブランチと別worktreeを割り当て、他者の作業ツリーを使わない。
  出力は各worktree内の`reports/workers/<job-id>/<cli>/`へ限定し、既存成果物を上書きしない。
- 認証済み`WORKER_OK`はネットワーク・料金が発生し得るため、GitHub Actionsでは行わない。
  明示承認後も空の隔離worktree、機密/Drive/実データへのアクセスを遮断した環境で1件ずつ実行する。
  承認範囲外のhooks/MCP/サブプロセスを起動しない。sandboxの実効性を確認できないCLIは停止する。
- モデル実行時は別途60秒・子1件・再試行0・出力上限を設定する。終了コードだけで成功とせず、
  返答が`WORKER_OK`と完全一致すること、ファイル変更と外部書込みがないことを検査する。
  認証失敗・非ゼロ・timeout・予期しない出力なら停止し、秘密を含まない状態コードだけを人間へ通知する。
- 今回確認できたのは4 CLIの版/helpのみ。認証確認、全方向のCLI間疎通、自律的な多段委任は**未実施**。
