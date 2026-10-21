# Issue #17: agy経由のDrive読取検証（2026-10-22）

**結論: (D) 失敗／未検証。独立したGoogle Driveアクセスも、実ファイルの読取りも確認できなかった。**

既存agyによるモデル呼出しは1回のみ。CLI exit code 0、runtimeのresultはSUCCESSだったが、`denied_actions`に`RunCommand`が1件あり、最終応答は空だった。実行記録には「非対話モードではcommand権限を確認できず自動拒否した」とある。失敗後の再試行・設定変更は行わなかった。Phase 1-C1全域解析の解除条件は満たしていない。

## 分離と使用したコマンド

main `b24be1ee767b8668207e0187e03295878dc9a936`から専用ブランチ `codex/phase1c-agy-drive-probe` / worktree `/tmp/kanagawa-agy-drive-probe`を作った。PR #6/#7/#8/#16のブランチや他者のworktreeは編集していない。

実行前に`agy --help`で以下のフラグを確認した。今回versionは再照合していない（PR #16では2026-10-21にagy 1.3.2を観測）。`agy mcp list`はexit 0で、設定済みMCPサーバーなしを示した。出力の全文や認証情報は保存せず、サイズ・SHA・判定だけをJSONへ記録した。ログイン、models、install、updateは実行していない。

実際に実行したCLIコマンドのargvは以下。プロンプト全体は`phase1c1_agy_drive_probe_prompt.txt`に保存した。
これは**実行記録であり、推奨する再実行コマンドではない**。

```text
agy --mode plan --sandbox --disable-slash-commands \
    --output-format stream-json --print-timeout 75s \
    --print <reports/phase1c1_agy_drive_probe_prompt.txtの全文を1つの引数として渡す>
```

Python `subprocess.Popen`へargv配列として渡し、shellは使用していない。stdinは無効、CLIの時間制限75秒、外側100秒、stdout+stderrは最大512KiB、同一プロセス群の終了待ち3秒。呼出し回数1、再試行0。所要時間16.885秒。外側の終了コード0、6 JSONイベントを取得した。

**実行時の重要な制約:** `--disable-slash-commands`との併用では`--mode plan`が無効になるとCLIが警告した。この組合せでplanが有効だったとは主張しない。initのpermission_modeは`request-review`。この値とCLIのモード指定を同じものとは扱わない。`--sandbox`も指定したが、今回コマンドが拒否されたため、sandboxの実効性は試験していない。

モデル側のツール記録は、対象のローカルFUSEパスへ`python3 -c ... os.stat ...`でアクセスしようとした1つの`run_command`だった。ACTIVEとDONEは同じstepであり、2回の実行ではない。CommandLineは途中省略されているため、子コマンドの全文は復元できない。DONEを成功扱いせず、resultの明示的な拒否記録を優先した。

CLIはheadlessではcommand権限を質問できないため自動拒否したと明示した。CLIが提示した権限変更・全許可の回避策は実行していない。ユーザーのIssue開始許可と、CLI内部のcommand許可は別の判定だった。

## 対象の同一性・取得結果

対象は`kanagawa_ruins_search_databank/data/`、既存記録のdata folder IDは`1XqQEuapdFd5dms0xa3I8reLGyenzc8gf`。
モデルには既知の名前だけを渡し、以下のサイズやmanifestの期待SHAを渡していない。

| ZIP相対パス | 既存台帳追記案の期待サイズ | 今回の実測 |
| --- | ---: | --- |
| raw/fgd/20261011005041318-001.zip | 638,547,984 bytes | 未取得 |
| raw/fgd/20261011005145933-001.zip | 865,319,242 bytes | 未取得 |

folder IDは今回観測できず、ZIP名・サイズとの実照合もできなかった。似た名前の別コピーを排除したとも主張しない。期待値はPR #6の承認済み登録案からGit経由で読んだもので、Driveを再取得した結果ではない。

小さな既知manifest `processed/phase1c/codex/manifests/fgd__2008_14101__blda_v1.json`について最大8192 bytesのread-only取得を依頼したが、バイト内容は返らなかった。
旧ingestレポートと元publisherのシリアライズ形式から再構成した参照値は2842 bytes / SHA-256 `7facaab9ef32f45916f782cd6024057d07b77168526e59f41638cda252c1e5d9`。これはリモート実測ではない。取得内容との正確なバイト比較は**未実施**で、`file_content_verified=false`。

## 経路と認証を区別する

- `/proc/mounts`のローカル記録から`/home/blabo/gdrive`が`fuse.rclone`であることを確認した。実際にこのパスを読めても、それだけなら同じrclone経路である。
- 今回の観測はそのFUSEパスへの**試行**であり、実際の読取りは拒否された。したがって「(C) 同じ経路で読取成功」とも分類しない。
- agyの公開ツール一覧にはfilesystem/browser系があり、Drive名の専用ツールは見当たらなかった。MCPも未設定。ただし命名による確認に限られ、browser経由等の全可能性を否定する証拠ではない。ブラウザ操作や直接Driveツールは試していない。
- 1モデルターンが進んだことは確認できるが、アカウント名・契約プラン・Drive OAuth scopeは調べていない。モデルの利用認証とDriveデータの読取権限を同一視しない。
- `independent_drive_access=null`（未確定）、`file_content_verified=false`、`large_binary_transfer_verified=false`、`can_resume_c1_full_run=false`。

今回の直接の停止理由は**agyのheadless command権限拒否**である。Drive APIの403がこの呼出しでも再発したとする証拠はなく、逆にDrive APIが回復したとする証拠もない。以前の対話Gemini環境で成功した操作と同じ権限条件かどうかも未検証。

## 保存した証拠と検証

- `phase1c1_agy_drive_probe.json`: exit、上限、時間、期待メタデータ、拒否記録の件数、参照SHA、結果の分類。
- `phase1c1_agy_drive_probe_prompt.txt`: 実際の依頼。再委任、ログイン、設定変更、大容量読取、書込みを禁止。
- `scripts/summarize_agy_drive_trace.py`: オフラインの要約器のみ。モデル・Driveを呼ばず、未検証の自然言語応答をA/B/Cへ昇格させない。
- 生traceは4097 bytes / SHA-256 `8058d77d3044ef305ec7f6e440f518fb9e167bb8e200f3296dba18b3d47e098d`。一時ファイルを0600で保持し、SHAを再確認して要約後に削除した。取得したGIS/manifest内容は0件。私有地座標・認証情報・生traceはGitへ入れていない。
- 合成traceテスト7件成功。exit 0/SUCCESSでも拒否なら未検証、ツールDONEでも読取成功にしないこと、秘密を含む自然言語/コマンドをログへ転記しないこと、入力上限を検証した。これは実Drive読取精度の検証ではない。

```bash
python -m unittest discover -s tests -p 'test_agy_drive_trace.py' -v
python -m compileall -q scripts/summarize_agy_drive_trace.py tests/test_agy_drive_trace.py
git diff --check
```

参考: [GoogleのAntigravity CLI codelab](https://codelabs.developers.google.com/sdd-agy-cli?hl=ja)はCLIとMCPによる外部サービス接続を説明しているが、今回のDrive接続成功を示す資料ではない。本報告は実測のruntime記録を根拠とする。

Issue #17の禁止事項に従い、設定・権限を変更しての再試行や、C1全域解析の再開は行わない。新しいDraft PRでレビュー待ちとし、mainへmergeしない。
