# Phase 1-C1 実装・実行報告

判定: **PARTIAL — 実データ部分解析済み、全域・Drive最終保存は未完了**。

最新main `b24be1e`から開始。作業ブランチは`codex/phase1c1-building-road-analysis`。原本・取得台帳・旧派生物は変更していない。台帳追記の承認応答はまだなく、追記件数0。`acquisition_registered=false`を保持した。

FGDのNested ZIP / UTF-8 / Shift_JIS / Surfaceの外周・内周 / Curveの非連続線分に対応。内部ZIP1件・地物単位の逐次処理、2,000件batch、scratch1GB上限。Phase 1-Aのwriter・CRS検査・排他公開・SHA readback、Phase 1-Bと共通のscratch管理を再利用した。BldAは面、BldLとRdEdgは線。中心線化は行わない。

実データpilotは3年代・5内部ZIPの対象地物XMLを全件パースした。全県全XMLの検証ではない。全域取り込みはDrive APIの繰返しHTTP 403クォータ超過で中断。正常保存として記録できたのは2008年の5自治体区画・9レイヤーで、元CRS EPSG:4612を保持しanalysis_ready=false。マウントreadback一致とリモートupload完了は区別し、後者は未確認。

部分解析: 523867 / 533935 の県内交差部分（候補探索は県域＋20m）。県全域ではない。県土面積に対する対象メッシュ交差面積の割合は0.644%（アーカイブの2/45を面積率としない）。 原本から4区画を一時GeoParquet化してハッシュ照合し、建物・道路縁を1/5/10mで比較した。一時GISは処理終了時に削除。入力原本・コード・実行条件・集計CSV・図は保持する。部分解析GeoParquetと検証サンプルGISのDrive保存は未完了。原本再処理で再現する。

一時取り込みの観測ピークは180,878,033 bytes。解析ジョブの観測ピークは113,509,391 bytes。1GBを超えていない。メモリ量は一時ディスク容量と別で、都市区画の候補グラフではRAMが1GBを超える場合がある。

検証: 新規10テストを含む回帰 **116 passed / 8 skipped / 35 subtests passed**。従来の実Drive全件監査`test_phase0_4_1.py`を除外し、意図的に非マウントrootを指定した。最初の全試験はDrive待ちで中断。CLIのPATH不足による再試行後、Phase1B.5に既存のユーザー固有PROJパスを検出し、`sys.prefix/share/proj`へ修正して通過した。環境doctor PASS。合成試験を実測精度とは扱わない。

共有チェックアウトが別作業のPhase1C2ブランチへ変更されたため、独立worktreeへ移行した。監査の1行修正は共有側の`438da19`にも記録されており、他作業をresetせず指定ブランチへcherry-pickした。他作業ファイルは本PRに含めない。

再開コマンド、台帳追記の承認後手順、処理条件は`docs/phase1c1_usage.md`。API回復後に保存済みペアと残留partialを検証し、`--resume-report`で残りを実行する。JGD2000補正グリッド・2008年の地物別共通範囲を確認するまで2008年比較を開始しない。PRはdraftとして作成し、mainへmergeせず停止する。
