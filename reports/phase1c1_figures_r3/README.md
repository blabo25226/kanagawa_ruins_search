# 実データ図と集計の出典・範囲

「基盤地図情報」（国土地理院、2014/2025年版）と「国土数値情報N03行政区域」（国土交通省、2026年版）を加工して作成した研究用集計。原本の出典・利用条件・SHAはphase1c1_registration_plan.json、Phase1Aのmanifest、およびphase1c1_data_quality.mdを参照。

対象は523867 / 533935の県内部分だけ。県全域分析ではなく、自治体全域の統計でもない。建物記録差を新築・解体・廃墟と判断しない。道路縁を中心線・廃道と判断しない。

- **building_regional_map_reviewed.png / road_edge_regional_map_reviewed.png**: 視覚確認済みの地域別地図。対象メッシュ交差部分だけを着色し、ゼロ中心の色尺度を使用する。
- **matching_validation.png**: 実データの対応候補1例。相対座標であり、個々の所在地を示す地図ではない。重なる輪郭が同一形状に見えることは、全データの対応精度を証明しない。
- **change_distribution.png**: 少なくとも片版に記録のある1kmグリッドの記録数差。両版ゼロ・未分析地域は分布から除外。
- grid_statistics.csv / municipality_statistics.csv: 図と記述統計に使った実集計。市区町村への面積・延長の配分は地物全体を重心で帰属させた値であり、境界でclipした実面積・実延長とは異なる。
- suffixなしのregional_map PNGは最初の機械出力として保持している。自治体を全体着色しているため、対象範囲の解釈には**reviewed版**を使う。

図の視覚確認とSHAは../phase1c1_plot_review.json。検出精度の実測、一般化可能な有意差検定は行っていない。
