"""R5 (相模原・旧津久井郡を除く) 1週目分析の再計算スクリプト.

`reports/phase1c2_results.json` (Phase 1-C2 v0.2.0) の
coverage / region / municipality / region_landscape / transitions 集計だけから、
2026-10-30_R5_week1.md の数値を再計算する。
新規データ取得・Drive アクセス・セル単位／候補地点の抽出は行わない。

棚卸し結果（分析前に確認）:
- region 集計に R5 行があり、公開レポート §1 の地域表にも相模原列がある
  （100%・comparable）。R5 の陸域は 90.59 km²、8,646 セル。
- municipality 集計の相模原 3 区行（緑区・中央区・南区）の合計は
  31,401 セル・328.96 km² で、R5 地域行とは一致しない。
  これは緑区行が R6（旧津久井郡）を含む区全体の行だからである。
  R5 + R6 = 31,401 セル・328.96 km² で区行合計と一致する。
  したがって R4 で使えた「区行の合計 = 地域行」「区行の範囲 = 地域のばらつき」
  の手順は R5 には転用できない。区行は R5 の内訳として使わず、
  参考としてのみ掲げ、緑区行は R5 の値として読まない。
- coverage.by_region には R6 行がなく、R5 行の area_km2 は 328.87 km²
  （市全体相当）である。R5 単独の網羅率としては使わず、網羅率は
  公開レポート §1 の地域表（R5 90.6 km²・R6 238.4 km²、ともに 100%・
  comparable）と region 集計の coverage/scope 列に基づく。
- 農地→建物用地の R5 値は results.json の region 集計に列がなく、
  公開レポート §2 の面積表（相模原 0.91 km²）にのみあるため、本レポートでは
  その出典を明示した上で補助的にのみ引用し、仮説の判定には使わない。
  仮説の判定は results.json にある農地→森林・荒地、建物用地の純変化で
  行う。農地総減少から森林・荒地を引いた残差は「建物・交通・その他等への
  合計」であって、建物用地への値ではないので、そのようには使わない。
- P32 の地域別内訳は地点数（R5 = 3）のみで、R5 限定のバッファ集計はない。
- 距離帯・Moran・OSM の集計は県域全体または津久井窓のものであり、
  R5 限定の値は results.json にないため、R5 の言明には使わない。
- focus_by_region の成分構造は地域全体のものであり、類型別・区別の
  成分構造は results.json にない。類型別の建物用地→森林・荒地率は
  絶対量（建物用地基数×率）と併記し、パッチの有無の判定には使わない。
  森林卓越メッシュは R5 内で 13 セル・0.14 km² しかなく、基数 0.5 km² 未満
  のため順位付けには使わない。
"""

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
d = json.loads((ROOT / "reports" / "phase1c2_results.json").read_text())

cov = d["coverage"]["by_region"]
cov_rows = {name: dict(zip(cov["columns"], row))
            for name, row in zip(cov["index"], cov["data"])}
r5cov = cov_rows["R5_sagamihara"]

reg = {name: dict(zip(d["aggregates"]["region"]["columns"], row))
       for name, row in zip(d["aggregates"]["region"]["index"],
                            d["aggregates"]["region"]["data"])}
r5 = reg["R5_sagamihara"]
r6 = reg["R6_tsukui"]

mcols = d["aggregates"]["municipality"]["columns"]
mrows = [dict(zip(mcols, r)) for r in d["aggregates"]["municipality"]["data"]]
sag_m = [r for r in mrows if r["muni_code"] in ("14151", "14152", "14153")]

rl = d["aggregates"]["region_landscape"]
rl_rows = {tuple(idx): dict(zip(rl["columns"], row))
           for idx, row in zip(rl["index"], rl["data"])}
r5_landscapes = {idx[1]: row for idx, row in rl_rows.items()
                 if idx[0] == "R5_sagamihara"}

focus = d["transitions"]["focus_by_region"]
fcols = focus["columns"]
focus_r5 = {row[1]: dict(zip(fcols, row))
            for row in focus["data"] if row[0] == "R5_sagamihara"}

cell_km2 = r5["land_km2"] / r5["n_cells"]
out = {}
out["coverage_by_region_row"] = {
    "area_km2": r5cov["area_km2"],
    "covered_km2": r5cov["covered_km2"],
    "coverage": r5cov["coverage"],
    "scope": r5cov["scope"],
    "has_R6_row": "R6_tsukui" in cov_rows,
}
out["n_cells"] = r5["n_cells"]
out["cell_km2"] = cell_km2
out["land_km2"] = r5["land_km2"]
out["region_coverage"] = r5["coverage"]
out["region_scope"] = r5["scope"]
# 区行合計と地域行の不一致（緑区行が R6 を含むため）、および R5+R6 での一致。
out["ward_sum_cells"] = sum(r["n_cells"] for r in sag_m)
out["ward_sum_land_km2"] = sum(r["land_km2"] for r in sag_m)
out["ward_rows"] = len(sag_m)
out["r5_plus_r6_cells"] = r5["n_cells"] + r6["n_cells"]
out["r5_plus_r6_land_km2"] = r5["land_km2"] + r6["land_km2"]
out["r5_share_of_city_land"] = r5["land_km2"] / (r5["land_km2"] + r6["land_km2"])
out["r6_land_km2"] = r6["land_km2"]
out["r6_cells"] = r6["n_cells"]
# 差し引きによる緑区内 R5 部分（中央・南区は全域が R5 のため）。
central_south_land = sum(r["land_km2"] for r in sag_m
                         if r["muni_code"] in ("14152", "14153"))
central_south_cells = sum(r["n_cells"] for r in sag_m
                          if r["muni_code"] in ("14152", "14153"))
out["central_south_land_km2"] = central_south_land
out["central_south_cells"] = central_south_cells
out["midori_r5_slice_land_km2"] = r5["land_km2"] - central_south_land
out["midori_r5_slice_cells"] = r5["n_cells"] - central_south_cells


def share_km2(share):
    return share * r5["land_km2"]


out["composition_2014_km2"] = {
    "building": share_km2(r5["building_2014_share"]),
    "forest": share_km2(r5["forest_2014_share"]),
    "agri": share_km2(r5["agri_2014_share"]),
    "wasteland": share_km2(r5["wasteland_2014_share"]),
    "other": share_km2(r5["other_2014_share"]),
    "transport": share_km2(r5["transport_2014_share"]),
    "golf": share_km2(r5["golf_2014_share"]),
    "water": share_km2(r5["water_2014_share"]),
}
out["changed_km2"] = r5["changed_km2"]
out["changed_share"] = r5["changed_share"]
out["changed_cells"] = r5["changed_km2"] / cell_km2
out["singleton_share"] = r5["singleton_change_share"]
out["singleton_km2"] = r5["singleton_change_share"] * r5["changed_km2"]
out["small_component_share"] = r5["small_component_change_share"]

out["agri"] = {
    "km2_2014": share_km2(r5["agri_2014_share"]),
    "cells_2014": share_km2(r5["agri_2014_share"]) / cell_km2,
    "loss_km2": r5["agri_loss_km2"],
    "loss_cells": r5["agri_loss_km2"] / cell_km2,
    "to_forest_km2": r5["agri_to_forest_km2"],
    "to_forest_cells": r5["agri_to_forest_km2"] / cell_km2,
    "to_wasteland_km2": r5["agri_to_wasteland_km2"],
    "to_forest_or_wasteland_share_of_loss": (
        r5["agri_to_forest_km2"] + r5["agri_to_wasteland_km2"]
    ) / r5["agri_loss_km2"],
    "residual_to_other_destinations_km2": (
        r5["agri_loss_km2"] - r5["agri_to_forest_km2"]
        - r5["agri_to_wasteland_km2"]),
    "net_km2": r5["agri_net_change_km2"],
    "net_rate": r5["agri_net_change_rate"],
    "gross_loss_rate": r5["agri_gross_loss_rate"],
    "to_forest_rate": r5["agri_to_forest_rate"],
    "to_wasteland_rate": r5["agri_to_wasteland_rate"],
}
out["building"] = {
    "km2_2014": share_km2(r5["building_2014_share"]),
    "loss_km2": r5["building_loss_km2"],
    "gain_km2": r5["building_gain_km2"],
    "net_km2": r5["building_net_change_km2"],
    "net_rate": r5["building_net_change_rate"],
    "gross_loss_rate": r5["building_gross_loss_rate"],
    "to_forest_km2": r5["building_to_forest_km2"],
    "to_forest_cells": r5["building_to_forest_km2"] / cell_km2,
    "to_wasteland_km2": r5["building_to_wasteland_km2"],
    "to_forest_or_wasteland_rate": r5["building_to_forest_or_wasteland_rate"],
}
out["forest"] = {
    "km2_2014": share_km2(r5["forest_2014_share"]),
    "net_km2": r5["forest_net_change_km2"],
    "to_forest_km2": r5["to_forest_km2"],
    "forestation_rate": r5["forestation_rate"],
    "nonforest_base_km2": r5["land_km2"] - share_km2(r5["forest_2014_share"]),
}
out["wasteland"] = {
    "km2_2014": share_km2(r5["wasteland_2014_share"]),
    "km2_2021": share_km2(r5["wasteland_2021_share"]),
    "net_km2": r5["wasteland_net_change_km2"],
}
out["ward_rows_reference_only"] = {
    r["muni_name"]: {
        "n_cells": r["n_cells"],
        "land_km2": r["land_km2"],
        "coverage": r["coverage"],
        "scope": r["scope"],
        "building_2014_share": r["building_2014_share"],
        "forest_2014_share": r["forest_2014_share"],
        "agri_2014_share": r["agri_2014_share"],
        "agri_net_km2": r["agri_net_change_km2"],
        "agri_loss_km2": r["agri_loss_km2"],
        "agri_to_forest_km2": r["agri_to_forest_km2"],
        "building_net_km2": r["building_net_change_km2"],
        "building_loss_km2": r["building_loss_km2"],
        "building_gain_km2": r["building_gain_km2"],
        "building_to_forest_km2": r["building_to_forest_km2"],
    } for r in sag_m
}
# R5 と R6 の対比（同じ市の分割であることの定量化）。
out["r5_vs_r6"] = {
    "building_2014_share_gap_pp": (
        r5["building_2014_share"] - r6["building_2014_share"]) * 100,
    "forest_2014_share_gap_pp": (
        r6["forest_2014_share"] - r5["forest_2014_share"]) * 100,
    "r6_building_2014_share": r6["building_2014_share"],
    "r6_forest_2014_share": r6["forest_2014_share"],
    "r6_agri_loss_km2": r6["agri_loss_km2"],
    "r6_agri_to_forest_km2": r6["agri_to_forest_km2"],
    "r6_building_net_km2": r6["building_net_change_km2"],
}
out["landscape"] = {
    name: {
        "n_cells": row["n_cells"],
        "land_km2": row["land_km2"],
        "agri_2014_km2": row["agri_2014_share"] * row["land_km2"],
        "agri_net_km2": row["agri_net_change_km2"],
        "agri_net_rate": row["agri_net_change_rate"],
        "agri_to_forest_km2": row["agri_to_forest_km2"],
        "forest_2014_km2": row["forest_2014_share"] * row["land_km2"],
        "forest_net_km2": row["forest_net_change_km2"],
        "to_forest_km2": row["to_forest_km2"],
        "forestation_rate": row["forestation_rate"],
        "nonforest_base_km2": row["land_km2"]
        - row["forest_2014_share"] * row["land_km2"],
        "building_2014_km2": row["building_2014_share"] * row["land_km2"],
        "building_net_km2": row["building_net_change_km2"],
        "building_gross_loss_rate": row["building_gross_loss_rate"],
        "building_to_forest_or_wasteland_rate":
            row["building_to_forest_or_wasteland_rate"],
        "building_to_forest_or_wasteland_km2":
            row["building_to_forest_or_wasteland_rate"]
            * row["building_2014_share"] * row["land_km2"],
        "changed_share": row["changed_share"],
        "singleton_share": row["singleton_change_share"],
    } for name, row in r5_landscapes.items()
}
out["focus_transitions"] = {
    name: {
        "area_km2": row["area_km2"],
        "cells": row["cells"],
        "rate_of_2014_class": row["rate_of_2014_class"],
        "size_1_share": row["size_1_share"],
        "size_ge5_share": row["size_>=5_share"],
        "max_component_cells": row["max_component_cells"],
        "boundary_share": row["boundary_share"],
    } for name, row in focus_r5.items()
}
out["p32_sites_by_region"] = d["cultural"]["sites_by_region"]
out["p32_usable_sites"] = d["cultural"]["usable_sites"]

# 検証アサーション：レポートの前提が崩れればスクリプトが失敗する。
assert out["ward_sum_cells"] != r5["n_cells"]  # 区行合計 ≠ 地域行（緑区行が R6 を含む）
assert out["r5_plus_r6_cells"] == out["ward_sum_cells"]
assert abs(out["r5_plus_r6_land_km2"] - out["ward_sum_land_km2"]) < 1e-6
assert out["ward_rows"] == 3
assert not out["coverage_by_region_row"]["has_R6_row"]
assert abs(r5["coverage"] - 1.0) < 1e-9
assert r5["scope"] == "comparable"
assert abs(sum(out["landscape"][k]["land_km2"]
               for k in out["landscape"]) - r5["land_km2"]) < 1e-6
print(json.dumps(out, ensure_ascii=False, indent=1))
