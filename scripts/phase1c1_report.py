#!/usr/bin/env python3
"""Generate conservative Phase1C1 review reports from actual execution artifacts."""
from collections import Counter
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]


def load(name):return json.loads((ROOT/"reports"/name).read_text())
def write(name,text):
    with (ROOT/"reports"/name).open("x",encoding="utf8") as f:f.write(text)
def number(value):return f"{value:,.2f}" if isinstance(value,float) else str(value)
def table(headers,rows):
    return "| "+" | ".join(headers)+" |\n| "+" | ".join(["---"]*len(headers))+" |\n"+"".join("| "+" | ".join(number(x) for x in row)+" |\n" for row in rows)


def main():
    analysis=load("phase1c1_analysis.json")
    pilot=load("phase1c1_pilot_r2.json")
    ingestion=load("phase1c1_ingest_r2.json")
    plan=load("phase1c1_registration_plan.json")
    ledger=load("phase1c1_ledger_check.json")
    coverage=load("phase1c1_coverage_check.json")
    temporary=load("phase1c1_temporary_ingest.json")
    plot_review=load("phase1c1_plot_review.json")
    stats=pd.read_csv(ROOT/"reports/phase1c1_figures_r3/grid_statistics.csv",dtype={"era":str,"muni_code":str})
    summary=pd.DataFrame(analysis["summary"])
    rows=[];sensitivity=[];road=[]
    for tolerance in [1,5,10]:
        for era in ["2014","2025"]:
            f=summary[(summary.domain=="building")&(summary.tolerance_m==tolerance)&(summary.era==era)]
            n=int(f.record_count.sum());matched=int(f.loc[f.status=="matched","record_count"].sum())
            missing=int(f.loc[f.status.isin(["missing_in_newer_dataset","only_in_newer_dataset"]),"record_count"].sum())
            ambiguous=int(f.loc[f.status.str.startswith("ambiguous"),"record_count"].sum())
            indeterminate=int(f.loc[f.status.str.startswith("indeterminate"),"record_count"].sum())
            sensitivity.append([tolerance,era,n,matched,100*matched/n if n else None,missing,ambiguous,indeterminate])
            if tolerance==5:rows.append([era,n,float(f.area_m2.sum()),matched,missing,ambiguous,indeterminate])
            f=summary[(summary.domain=="road_edge")&(summary.tolerance_m==tolerance)&(summary.era==era)]
            length=float(f.edge_length_m.sum());unmatched=float(f.unmatched_length_m.sum())
            road.append([tolerance,era,int(f.record_count.sum()),length,unmatched,100*(1-unmatched/length) if length else None])
    raw_counts=Counter();invalid=Counter()
    for result in pilot["results"]:raw_counts.update(result["counts"]);invalid.update(result["excluded_invalid"])
    baseline=sum(x[2] for x in sensitivity if x[0]==5 and x[1]=="2014")
    newer=sum(x[2] for x in sensitivity if x[0]==5 and x[1]=="2025")
    municipal=stats[(stats.domain=="building")&(stats.tolerance_m==5)].groupby(["muni_code","era"])[["record_count","area_m2"]].sum().unstack(fill_value=0)
    municipal_rows=[]
    for code,row in municipal.iterrows():
        old=int(row[("record_count","2014")]);new=int(row[("record_count","2025")])
        municipal_rows.append([code,old,new,new-old,100*(new-old)/old if old else None,float(row[("area_m2","2025")]-row[("area_m2","2014")])])
    common="523867 / 533935 の県内交差部分（候補探索は県域＋20m）。県全域ではない。県土面積に対する対象メッシュ交差面積の割合は"+f"{100*plot_review['selected_prefecture_land_fraction']:.3f}%"+"（アーカイブの2/45を面積率としない）。"
    write("phase1c1_implementation.md",f'''# Phase 1-C1 実装・実行報告

判定: **PARTIAL — 実データ部分解析済み、全域・Drive最終保存は未完了**。

最新main `b24be1e`から開始。作業ブランチは`codex/phase1c1-building-road-analysis`。原本・取得台帳・旧派生物は変更していない。台帳追記の承認応答はまだなく、追記件数0。`acquisition_registered=false`を保持した。

FGDのNested ZIP / UTF-8 / Shift_JIS / Surfaceの外周・内周 / Curveの非連続線分に対応。内部ZIP1件・地物単位の逐次処理、2,000件batch、scratch1GB上限。Phase 1-Aのwriter・CRS検査・排他公開・SHA readback、Phase 1-Bと共通のscratch管理を再利用した。BldAは面、BldLとRdEdgは線。中心線化は行わない。

実データpilotは3年代・5内部ZIPの対象地物XMLを全件パースした。全県全XMLの検証ではない。全域取り込みはDrive APIの繰返しHTTP 403クォータ超過で中断。正常保存として記録できたのは2008年の5自治体区画・9レイヤーで、元CRS EPSG:4612を保持しanalysis_ready=false。マウントreadback一致とリモートupload完了は区別し、後者は未確認。

部分解析: {common} 原本から4区画を一時GeoParquet化してハッシュ照合し、建物・道路縁を1/5/10mで比較した。一時GISは処理終了時に削除。入力原本・コード・実行条件・集計CSV・図は保持する。部分解析GeoParquetと検証サンプルGISのDrive保存は未完了。原本再処理で再現する。

一時取り込みの観測ピークは{temporary['scratch_peak_bytes']:,} bytes。解析ジョブの観測ピークは{analysis['scratch_peak_bytes']:,} bytes。1GBを超えていない。メモリ量は一時ディスク容量と別で、都市区画の候補グラフではRAMが1GBを超える場合がある。

検証: 新規10テストを含む回帰 **116 passed / 8 skipped / 35 subtests passed**。従来の実Drive全件監査`test_phase0_4_1.py`を除外し、意図的に非マウントrootを指定した。最初の全試験はDrive待ちで中断。CLIのPATH不足による再試行後、Phase1B.5に既存のユーザー固有PROJパスを検出し、`sys.prefix/share/proj`へ修正して通過した。環境doctor PASS。合成試験を実測精度とは扱わない。

共有チェックアウトが別作業のPhase1C2ブランチへ変更されたため、独立worktreeへ移行した。監査の1行修正は共有側の`438da19`にも記録されており、他作業をresetせず指定ブランチへcherry-pickした。他作業ファイルは本PRに含めない。

再開コマンド、台帳追記の承認後手順、処理条件は`docs/phase1c1_usage.md`。API回復後に保存済みペアと残留partialを検証し、`--resume-report`で残りを実行する。JGD2000補正グリッド・2008年の地物別共通範囲を確認するまで2008年比較を開始しない。PRはdraftとして作成し、mainへmergeせず停止する。
''')
    write("phase1c1_data_quality.md",f'''# Phase 1-C1 データ品質

基本項目8原本のSHA-256とサイズを独立に再検証し、B.5の記録と一致した。完全重複1原本を変更・削除せず保持。残る7原本が登録案。出典配布ページは[国土地理院](https://service.gsi.go.jp/kiban/app/)、利用条件は[国土地理院コンテンツ利用規約](https://www.gsi.go.jp/kikakuchousei/kikakuchousei40182.html)を確認した。出典と加工の明示、個別成果の条件を保持する。認証付き直接URL・正確な取得時刻は独立確認できずnull。規約への新規同意・新規取得はしていない。

独立に実ZIPのcentral directoryを列挙し、同年代・同コードはファイル版日付の最大を選択した。同日重複は内部ZIPの実SHA一致を確認。選択区画は2008年41自治体コード、2014年45メッシュ、2025年45メッシュ。更新版の除外は原本削除を意味しない。選択・除外履歴はpilot JSONに保持する。

独立N03幾何交差で県に交差する2次メッシュは{coverage['expected_count']}。2014/2025のアーカイブコード集合は一致する。ただし地物収録の完全性とは別であり、県全域100%地物網羅とは宣言しない。2008年のB.5「18/35=51.4%」は年代当時の分母を独立確認できていないため採用しない。2007年の合併は[相模原市の一次資料](https://www.city.sagamihara.kanagawa.jp/shisei/1026709/profile/gappei/1005292.html)で確認でき、年代別行政単位の照合が必要である。41コードの存在から自治体内の全地物収録を推定しない。

少数ZIPの**対象地物XML全件**の構造検査:

{table(['地物','読取レコード数（県外含む）','不正形状除外数'],[[k,raw_counts[k],invalid[k]] for k in ['BldA','BldL','RdEdg']])}

2008年14101の最初の内部ZIPにはBldA/BldLがあるがRdEdg XMLはない。別の2008年区画には道路縁があり、年代一括で「道路なし」とはしない。UTF-8 / Shift_JISを宣言どおり厳格に解読。orgGILvl、orgMDId、devDate、lfSpanFr、XML meshとファイルのコードを別属性で保持し、欠損はunknown/null。2025年等のorgMDId欠損から実測量年月を復元しない。ファイル名の版日付と内部devDateが違う場合も両方保持する。

JGD2011/JGD2024の元宣言を区別して保持する。水平定義の変更を伴わない名称改定であることは[国土地理院の説明](https://web2.gsi.go.jp/sokuchikijun/hyoko2024rev.html)を確認した。B.5の「2024地震補正を含む3世代の水平基準」という説明やCRS推測フォールバックは採用しない。

JGD2000では、PROJのbest_available=trueでも選択操作の適用説明は神奈川県を除外する。神奈川県を含む補正操作はグリッド不足で利用できないため、2008年をEPSG:4612のまま保存して比較を停止した。往復誤差0は投影計算の数値整合であり、地殻変動・測量誤差が0という意味ではない。詳細は`phase1c1_crs_check.json`。

不正面の除外、異なる原情報レベル、境界付近の未対応、欠損を別管理する。未確認メッシュにゼロ件や「建物なし」を与えない。台帳前後SHAは一致し、実追記0。Drive APIクォータ障害の証跡は`phase1c1_drive_block.json`。
''')
    write("phase1c1_building_analysis.md",f'''# Phase 1-C1 建物の部分実データ解析

対象: {common} 2014年・2025年の**建物ポリゴン記録**を比較した。実建物の棟数・新築・解体・廃墟の件数ではない。2008年はCRS補正と共通範囲未確定で比較未実施。

5m条件の県内重心帰属集計:

{table(['版','ポリゴン記録数','全形状面積m2','matched','片版のみ記録','曖昧対応','判定不能'],rows)}

記録数の差は{newer-baseline:+,}（基準版に対し{100*(newer-baseline)/baseline:.2f}%）。全形状の面積を重心帰属先に集計しており、行政境界で切り取った建物面積ではない。区画端のポリゴン断片を物理的に同一の1棟へ再構成していない。

照合条件はusageに記載。IoU・交差面積割合・重心距離・面積比・buffer IoUを使い、連結成分からpossible_split / possible_merge / ambiguous_many_to_manyを分ける。距離だけで消失と扱わない。不正面を含む比較区画の未対応は保守的にindeterminate_geometry_qualityとした。情報レベル差はambiguous_survey_scale。正解ラベルはなく精度を実測したとは主張しない。

{table(['距離m','版','全記録','matched','matched率%','片版のみ','曖昧','判定不能'],sensitivity)}

距離を広げると近接建物の多対多対応が増える場合がある。都合のよい距離を選んで結果を確定しない。missing_in_newer_dataset / only_in_newer_datasetは版間の記録差であり、収録省略・更新時期・位置誤差でも生じる。orgGILvlから一律の誤差mを捏造していない。

乱数seed 20261011、各メッシュから最大10対応候補の検証サンプルを抽出した。県域＋20mの候補範囲であり、非対応地物の正解ラベルや人手による全標本判定はない。検証図は実データの相対座標表示。検証サンプルGISのDrive保存は障害で未完了、原本とコードから再生成する。

図: `phase1c1_figures_r3/building_regional_map_reviewed.png`、`matching_validation.png`。地域別地図は選択メッシュ内の集計で、色の付いた自治体の全域値ではない。小さな検証図1例を全体の正解率へ一般化しない。
''')
    write("phase1c1_road_analysis.md",f'''# Phase 1-C1 道路縁の部分実データ解析

対象: {common} 道路縁RdEdgを比較する。道路中心線・道路区間数・廃道判定ではない。旧版の細かな分割と新版の長い線分を、地物数だけで道路増減と解釈しない。

双方向に、相手版の道路縁buffer内に入る線の延長割合を計算した。下表の一致率は全道路縁延長で重み付けした値である。

{table(['距離m','版','線地物記録数','道路縁延長m','buffer外延長m','延長一致率%'],road)}

延長・不一致量は重心が県内の地物全形状の集計であり、行政界・グリッド内へ厳密にclipした延長ではない。mesh境界付近の記録はindeterminate_partition_boundaryとして別分類した。buffer外延長にはその境界不確実性も残るため、実道路の変化量と断定しない。位置ずれ・線分の統合・図式差・収録欠損があり得る。

2008年の道路収録は自治体別に異なり、CRS補正も未解決のため比較未実施。中心線化の適切な変換・資料は検証しておらず、道路網の接続性変化は未実施。OSMの現代道路を過去版の正解として使わない。

図: `phase1c1_figures_r3/road_edge_regional_map_reviewed.png`。選択メッシュ内の道路縁延長の版間差であり、表示自治体の全域値ではない。
''')
    write("phase1c1_statistical_summary.md",f'''# Phase 1-C1 記述統計と制約

対象: {common} 人口の多い都市部に一般化しない。西部側と都市部側の2メッシュを使った実行確認であり、県全域の代表標本ではない。無作為に選んだ地域ではなく、取り込み確認に選定した地域である。

市区町村別（コード、対象メッシュ内の重心帰属値）:

{table(['コード','2014記録数','2025記録数','差','変化率%','全形状面積差m2'],municipal_rows)}

1kmはEPSG:6677で原点(0,0)から作る正方形グリッドであり、JIS標準地域メッシュと同一ではない。集計CSVは市区町村×グリッド×版×許容距離×状態を保持する。ポリゴン数を海域を除くN03県土面積で割る密度計算も実装し、未処理のグリッドにはselected_archive_support_fractionを持たせた。この一時GeoParquetはDrive未保存。表示上の細かさを元測量精度と混同しない。

占有グリッドの分布:

```json
{json.dumps(analysis.get('grid_distribution',{}),ensure_ascii=False,indent=2)}
```

分布図は少なくとも片版に県内帰属記録があるセルだけを対象にする。両版ゼロ・未処理セルはこのヒストグラムに含めない。基準版ゼロの変化率は未定義とする。県全体の平均や全セル分布とは解釈しない。

年代別のアーカイブ収録コードを独立に比較したが、地物の真の収録率を推定する外部母集団はない。2008/2014/2025年の県全域収録率の統計検定は行わない。1/5/10mの感度表を建物・道路報告に示した。一致率の分母、曖昧・判定不能を残し、成功した対応だけへ再正規化していない。

都市部・山間部の比較は未完了。2021土地利用の森林/建物用地を代理区分にする処理は実装したが、Drive障害で実行しなかった。森林は標高・斜度から定義した山間部と同義ではなく、その代理区分も原データのある5338/5339に限定される。DEMを実検証せず山間部と断定しない。空間自己相関は未実施。標本設計・正解ラベル・独立性の仮定がないため、一般化可能性のないp値・検出精度は算出していない。

図: `phase1c1_figures_r3/change_distribution.png`。元集計は同ディレクトリのgrid_statistics.csv / municipality_statistics.csv。原本はDrive不変保存、再計算コードとSHA・条件は本PRに保持する。
''')
    validation=dict(status="PARTIAL_REAL_DATA_VALIDATED_NOT_PREFECTURE_COMPLETE",complete=False,
                    tested_real_meshes=analysis['meshes'],target_prefecture_meshes=coverage['expected_count'],
                    analyzed_mesh_count=len(analysis['meshes']),analysis_errors=analysis['errors'],
                    raw_basic_packages_sha256_verified=8,raw_package_hash_mismatches=0,
                    acquisition_ledger_unchanged=ledger['unchanged'],acquisition_records_appended=0,
                    acquisition_registration_approval="pending_no_append",published_ingest_partitions=5,
                    published_ingest_layers=9,remote_upload_completion_confirmed=False,
                    temporal_derivative_geoparquet_published=False,default_scratch_limit_bytes=1_000_000_000,
                    temporary_ingest_peak_bytes=temporary['scratch_peak_bytes'],analysis_scratch_peak_bytes=analysis['scratch_peak_bytes'],
                    tests=dict(passed=116,skipped=8,subtests_passed=35,new_tests=10,excluded="tests/test_phase0_4_1.py actual-Drive historical full audit"),
                    figures=[a for a in analysis['artifacts'] if str(a.get('path','')).endswith('.png') and 'regional_map' not in a.get('path','')]+plot_review['artifacts'],
                    plot_visual_review=plot_review['status'],selected_prefecture_land_fraction=plot_review['selected_prefecture_land_fraction'],
                    building_sensitivity_headers=['tolerance_m','era','records','matched','matched_percent','one_edition_only','ambiguous','indeterminate'],building_sensitivity=sensitivity,
                    road_sensitivity_headers=['tolerance_m','era','records','length_m','unmatched_length_m','length_agreement_percent'],road_sensitivity=road,
                    scientific_claims=dict(construction_or_demolition_dates_inferred=False,abandonment_inferred=False,
                                           ground_truth_accuracy_measured=False,p_values_generated=False,
                                           source_feature_completeness_established=False),
                    not_completed=['prefecture-wide feature ingestion and temporal analysis','2008 common-coverage comparison and valid datum correction','urban versus mountain comparison','spatial autocorrelation','independent labelled sample validation','road centreline connectivity','temporal GeoParquet and review sample publication to Drive'],
                    blockers=['Drive API HTTP 403 shared project quota exceeded','JGD2000 correction grid unavailable for Kanagawa'],
                    stop_after_pr=True,merge_main=False)
    write('phase1c1_validation.json',json.dumps(validation,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
