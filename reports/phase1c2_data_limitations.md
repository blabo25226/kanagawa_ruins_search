# Phase 1-C2 データの制約・品質上の発見・出典

## 1. 収録範囲

- 土地利用細分メッシュは1次メッシュ**5338・5339のみ**（北緯35°20′〜36°00′）。5339のうち2次メッシュ533927（東京湾・千葉側）は存在せず、127の2次メッシュを収録している。県南部の1次メッシュ5238・5239（北緯35°20′以南）は取得されていない。
- N03（2026）の県域2,416.2 km²に対し、収録範囲内は1,818.4 km²（**75.3%**）。
- **収録外の市町**（網羅率1%未満）: 横須賀市、小田原市、逗子市、三浦市、葉山町、大磯町（0.6%）、二宮町、箱根町、真鶴町、湯河原町。
- **一部のみ**: 鎌倉市39%、南足柄市15%、中井町56%、大井町56%、開成町56%、茅ヶ崎市68%、横浜市金沢区79%、平塚市82%、藤沢市83%、山北町99.9%。
- 地域では三浦半島7%、県西47%、湘南83%。三浦半島は比較から除外し、県西は山北・松田中心の参考値として扱った。**県全域の結果として外挿しない。**
- v0.2.0では、各市区町村・地域に網羅率区分（comparable ≥95%、reference_partial 30〜95%、excluded <30%）を出力に付けた。集計した陸域面積の合計が収録範囲の面積を超えないことを、実行時に検査している。結果JSONの`analysis_scope`に、収録外の面積（597.8 km²）と「推定・外挿しない」旨を記録した。県全域の値として示している数値はない。レポート中の「全体」「全セル」は、常に収録範囲内の神奈川県陸域を指す。
- 市区町村別の網羅率は`csv/municipality_coverage.csv`にある。

## 2. 座標系と位置合わせ

- 2014（元JGD2000）と2021（元JGD2011）は、Phase 1-AでEPSG:6677に変換済み。メッシュコードで結合し、重心の差が最大0.02 mmであることを全セルで確認した。PROJはJGD2000→JGD2011を実質的に恒等変換として扱っており、地殻変動補正（数cm規模）は反映されていない。100 mセルには影響しない。
- 1976年はEPSG:4301のままで、空間演算を一切行っていない。Bessel楕円体上の測地面積だけを、元の測地系の緯度経度範囲から計算した。
- 距離と面積はEPSG:6677（平面直角座標系第IX系）で計算した。収録範囲の西端（東経138°付近）は第IX系の原点（東経139°50′）から約165 km離れるが、楕円体面積との差はセルあたり最大0.048%だった。
- 市区町村・地域への割当はセル重心で行っている。境界上のセルは片側に割り当てられるが、合計面積の誤差は0.01%未満。

## 3. 分類と判読方法の年次差

- 2014・2021年はコード表と定義文が同一（LandUseCd-09）だが、使用画像と判読方法が異なる。公式に「2021年度は高解像度画像により判読が多く異なる」と注意書きがある。
- 変化面積の57.1%は1セル、76.7%は1〜2セルの連結成分（同一遷移・8近傍）の変化で、76.8%が境界上の変化である。建物用地の増減の84%、森林の増減の76%がswapである。これらには判読差による見かけの変化が大きく含まれると考えられる。成分の大きさはノイズの目安であり、真偽を判定するものではない。成分は収録範囲の南端で切れるため、その付近では小さく数えられる。v0.1.0の「82%が単独セル」は、2セルの連続変化を単独と数える規則によるもので、v0.2.0で置き換えた。
- 2021年の撮影日は2次メッシュ単位（2020-05-30〜2020-12-18）。2014年版には撮影日の属性がなく、撮影時期の季節差を補正できない。
- 100 mセルは優占分類であり、セル内の混在は表れない。
- 1976年は建物用地A/B、幹線交通用地、ゴルフ場を含む「その他の用地」など、分類体系が異なる。粗分類での対応（`GROUPS_1976`）は分析上の便宜で、公式な等価関係ではない。

## 4. 交通データの年次差

| データ | 対象年次 | 土地利用（2014・2021）との関係 |
|---|---|---|
| L03-b 道路セル | 2014 | 同じ年次だが、面として捉えられる道路のみ |
| N02 鉄道・駅 | 2023 | 2021年より後。2014年時点の鉄道網ではない |
| OSM 道路 | 2026-10 | 2014年の道路状況として扱わない。津久井周辺の窓のみ |

OSM道路のPBFは、Phase 1-Aで津久井周辺のbbox（139.12,35.51,139.25,35.62）と交差する地物だけが抽出されている。窓の端の影響を避けるため、内側1 kmのセル（9,662セル）に限定した。県全域でのOSM道路分析はできない。

## 5. OSMとP32の制約

- **OSMは網羅的な神社台帳ではない。** 宗教施設21件、historic 39件は、すべて津久井周辺の抽出範囲にある。登録の有無・精度は登録者の活動に依存し、道路沿いの施設が登録されやすい偏りがありうる。**OSMにないことから廃絶を推論しない。** 宗教施設の閉じたway（14件）はLineStringとして保存されているため、重心で代表させた。
- **P32**は都道府県指定文化財（国指定等を除く）で、データ基準日は2014-01-31。個人情報等の観点から一部が非公開とされている。位置は「おおよその代表点」で、代表点区分3（大字・丁目）の2件を除外した。同一座標の重複が115件ある（同じ社寺の複数の文化財）。市町村指定文化財と未指定の社寺は含まない。
- P32の周辺集計は、半径内に重心があるセルの合計である。地点の円は重なりうる（セルが重複して数えられる）。境界から500 m以内の地点は除外した（215地点中108地点を使用）。

## 6. 統計上の注意

- 1 kmメッシュのすべての指標で正の空間自己相関がある（Moran's I 0.11〜0.40）。独立観測を前提とした検定は使っていない。
- 距離帯別の率の区間は、約5 km四方のブロックを単位としたブロック・ブートストラップによる。ブロック間に依存性が残る場合、区間は狭すぎる可能性がある。ブロック数が少ない層（OSM窓のブロック数は6）では区間が不安定。
- 森林卓越メッシュでの率は、建物用地・農地の基数（1〜5 km²）が小さく、不確実性が大きい。
- 2014年土地被覆類型は結果指標と同じデータから作った層別変数であり、平均への回帰の影響を受けうる（例: 森林卓越メッシュでは森林以外が少ないため、森林化率が高く出やすい）。
- 相関関係から因果関係は結論しない。

## 7. 品質上の発見（Phase 1-A/0の資産について。修正はしていない）

1. **CODHのファイル名（source_id・レイヤーID）と内容の入れ替わり**: `admin__codh_fujino_2005__2005_01_01`（原本`raw/historical_boundaries/codh_fujino_20050101.geojson`）の内容は**相模湖町**（14423、31.5 km²）、`admin__codh_sagamiko_2005__2005_01_01`（原本`codh_sagamiko_20050101.geojson`）の内容は**藤野町**（14424、64.9 km²）である。
   - **原因**: 取得台帳では、`codh_fujino_2005`の取得URLが`…/20050101/14/14423A1968.geojson`、`codh_sagamiko_2005`が`…/14424A1968.geojson`になっている。ダウンロードされた内容はURLのコードと一致しているので、取得処理そのものは正しい。Phase 0で、ソース名（藤野／相模湖）と自治体コード（14424／14423）を対応づける段階で取り違えている。城山町（14421）と津久井町（14422）は名前と内容が一致する。
   - **再現可能な検証**: `kanagawa_ruins.landuse_change.data.codh_identity_records(data_root)`が、原本GeoJSONの属性（`N03_004`・`N03_007`）、取得台帳のURLコードとSHA-256、Phase 1-Aレイヤーの属性と面積を読み取り専用で照合する。合成テスト`CodhIdentityTests`と実データテスト`test_codh_fujino_sagamiko_file_names_and_contents_are_swapped`（原本SHA-256＝台帳、URLコード＝内容、レイヤー属性＝原本、藤野・相模湖のみ不一致、面積は藤野60〜70 km²・相模湖28〜35 km²）で確認した。実行結果は`qa/codh_identity.json`に出力した。
   - **扱い**: 本分析ではIDではなく`muni`属性を使った。原本・派生物・取得台帳は変更していない。台帳のソース名を訂正するかどうか（例: 訂正イベントを追記する、別名を付ける）は、ユーザーの判断が必要。
2. **CODHの1955年と2005年の津久井町**は同じ実体ID（`gci:14422A1968`）で、対称差は約2,000 m²。1955〜2005年に境界変化はなく、1955年境界を使っても追加の情報はない。
3. **2014年L03-bの`source_id`**: Phase 1-Aのmanifestに「Source ID vintage disagrees with ZIP/internal metadata; output uses verified 2014」と記録されている（行の`source_id`は`mlit_landuse_2021_5339`、内容は平成26年）。年次はZIP内のメタデータに従い2014として扱った。
4. **P32の県版と全国版14は同一**（336件、ID・名称の集合が一致）。
5. **既存テスト`tests/test_phase0_4_1.py::test_databank_actual_files_classification`の失敗**: データバンク全体のファイル数を65件に固定していたことが原因（2026-10-11時点で150件）。増えた内訳は、Phase 1-B.5の`raw/fgd/`が11件、Phase 1-Cの`processed/phase1c/claude/`と`processed/phase1c/codex/`、`.provenance.lock`（2026-10-11に作成された`fetch_sources.py`の台帳ロック）。Phase 1-C2の変更が原因ではない。
   - **修正方針**: 総数を固定せず、(1) Phase 0の65件スナップショット（コミット済みのFULL_PASS監査）が記録どおりのサイズで残っていることを確認し、(2) それ以外のファイルは各フェーズの記録（Phase 1-A/1-Bの登録済み派生ペア、Phase 1-B.5のinventory、Phase 1-Cのmanifest、運用ロック）で説明できることを要求する。どの記録でも説明できないファイルがあれば失敗とする。
   - 共通テストであり、Codex（PR #6）の成果物も対象になるため、**別PR #8（ドラフト、`claude/fix-phase0-snapshot-accounting`）に切り出した**。PR #8のブランチで`tests/test_phase0_4_1.py`の11件すべての合格を確認した。PR #7には含めていない。

## 8. 入力の出典とSHA-256

すべてPhase 1-Aの派生物（`processed/phase1a/vectors/`）で、読み込み時にSHA-256を再計算し、manifestと一致することを確認した。完全なハッシュ値・原本パス・ライセンスは`run_manifest.json`の`inputs`にある。

| layer_id | 原本 | CRS（元→保存） | SHA-256（先頭16桁） |
|---|---|---|---|
| landuse__l03b__2014_5338 | raw/landuse/L03-b-14_5338-jgd_GML.zip | EPSG:4612→6677 | 4f94e4260d73c11c |
| landuse__l03b__2014_5339 | raw/landuse/L03-b-14_5339-jgd_GML.zip | EPSG:4612→6677 | 1a7ec92800589ec0 |
| landuse__l03b__2021_5338 | raw/landuse/L03-b-21_5338-jgd2011_GML.zip | EPSG:6668→6677 | 7ab5cea56abd7346 |
| landuse__l03b__2021_5339 | raw/landuse/L03-b-21_5339-jgd2011_GML.zip | EPSG:6668→6677 | c6d160f2a908bc50 |
| landuse__l03b__1976_5338 | raw/landuse/L03-b-76_5338_GML.zip | EPSG:4301（変換なし） | 542e64e98d77f776 |
| landuse__l03b__1976_5339 | raw/landuse/L03-b-76_5339_GML.zip | EPSG:4301（変換なし） | eb854c72286d2128 |
| admin__n03__2026_kanagawa | raw/administrative/N03-20260101_14_GML.zip | EPSG:6668→6677 | 63cfa1caa0be4258 |
| admin__codh_fujino_2005__2005_01_01（内容は相模湖町） | raw/historical_boundaries/codh_fujino_20050101.geojson | EPSG:4326→6677 | 0eec01653d5ef468 |
| admin__codh_sagamiko_2005__2005_01_01（内容は藤野町） | raw/historical_boundaries/codh_sagamiko_20050101.geojson | EPSG:4326→6677 | f5c4b04f68bc84ef |
| admin__codh_shiroyama_2005__2005_01_01 | raw/historical_boundaries/codh_shiroyama_20050101.geojson | EPSG:4326→6677 | 3f4aa4dfe589f461 |
| admin__codh_tsukui_2005__2005_01_01 | raw/historical_boundaries/codh_tsukui_20050101.geojson | EPSG:4326→6677 | a6b013e5604bb9be |
| admin__codh_tsukui_1955__1955_10_01 | raw/historical_boundaries/codh_tsukui_19551001.geojson | EPSG:4326→6677 | c5ce05e5f4e7300a |
| railways__…_railroadsection | raw/railways/N02-23_GML.zip | EPSG:6668→6677 | be210c6731a93e26 |
| railways__…_station | raw/railways/N02-23_GML.zip | EPSG:6668→6677 | 37de7952bfcac4a6 |
| rivers__mlit_rivers_kanagawa__2008_w05_08_14_g_stream | raw/rivers/W05-08_14_GML.zip | EPSG:4612→6677 | 970a9e1391576f4d |
| cultural__mlit_cultural_properties_kanagawa__2014 | raw/cultural_properties/P32-14_14_GML.zip | EPSG:4612→6677 | 6870c1a2b800544b |
| osm__{roads,worship,historic,waterways}__2026_10_*（20レイヤー） | raw/osm/（Geofabrik関東・中部PBF、津久井XML） | EPSG:4326→6677 | manifest参照 |

出典: 国土交通省 国土数値情報（土地利用細分メッシュ、行政区域、鉄道、河川、文化財）。人文学オープンデータ共同利用センター（CODH）の歴史的行政区域データセット。© OpenStreetMap contributors（ODbL）。ライセンスの詳細は各manifestの`license`にある。

## 9. 出力（派生データ）

- 保存先: `$RUINS_DATA_ROOT/processed/phase1c/claude/phase1c2-claude-0.2.0/`（csv 40、geoparquet 4、figures 16、qa 2、`run_manifest.json`）。旧版`phase1c2-claude-0.1.0/`（54ファイル＋manifest）は上書き・削除せずに残している。両版で共通するCSVの数値は、置き換えた旧規則の列を除いて完全に一致することを確認した。
- 公開手順: Driveのrcloneマウントを確認したうえで、`processed/phase1c/claude/`の外への書き込みと、`raw`・`processed/phase1a`・`processed/phase1b`への書き込みを拒否する。一意のpartialファイルにコピーし、SHA-256を再読込で照合してからrenameし、公開後にも再照合する。既存の出力は上書きしない（内容が違えば停止する）。
- `run_manifest.json`には、入力の一覧（パス・manifestのSHA-256・再計算したSHA-256・原本・CRS・ライセンス）、出力の一覧（SHA-256・バイト数）、パラメータ、ライブラリの版、gitの状態を記録した。v0.2.0の公開時のコードはコミット`c8c0032`。manifestの`git.analysis_code_clean`は`false`だが、これは実行中に再生成した`reports/figures/phase1c2/`の図の写しを判定が誤検知したためである。変更パス（`modified_tracked_paths`）は、図の写しと他エージェントの`agent/rules/00-phase-gate.md`だけで、分析コードは変更されていない。判定は後続のコミットで、src・scripts・configのパスだけを見るよう修正した。
- 主なSHA-256（v0.2.0）: `cells_landuse_change_2014_2021.parquet` 1aee7e5c47d756df…、`mesh1km_…` 03c387a19cd8d14f…、`mesh500m_…` f0ef7fddb15b404b…、`municipality_…` 7ee1f8ec7abfcefe…、`qa/codh_identity.json` 1ed8fdcaa088cf67…、`run_manifest.json` e578f2331f7bacf9…。
- GitHubにはコード・テスト・レポート、レポート用の図の写し（`reports/figures/phase1c2/`）、集計値の要約（`reports/phase1c2_results.json`）だけを置いた。GeoParquet・CSVはDriveのみ。P32の地点別CSVとOSM宗教施設の地点別CSV（名称は消去）はDriveのみに置き、リポジトリやレポートには地点を載せていない。

## 10. 未実施事項

- **DEMを使った地形解析: 未実施。** 検証済みの実DEM派生物がない（[拡張設計](../docs/phase1c2_terrain_extension.md)）。
- 1976年を含む空間的な変化分析: 測地変換の検証待ち。
- 県南部（5238・5239）の土地利用: データが未取得。今回は新規取得を行っていない。
- 県全域でのOSM道路・宗教施設の分析: 抽出範囲が津久井周辺に限られる。
- 河川（W05 2008）は、セル属性`dist_river_w05_m`として出力しただけで、分析はしていない。
