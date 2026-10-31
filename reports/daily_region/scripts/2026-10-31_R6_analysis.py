"""R6 (津久井・旧津久井郡4町) 1週目分析の再計算スクリプト.

`reports/phase1c2_results.json` (Phase 1-C2 v0.2.0) の
coverage / region / municipality / region_landscape / transitions 集計だけから、
2026-10-31_R6_week1.md の数値を再計算する。
新規データ取得・Drive アクセス・セル単位／候補地点の抽出は行わない。

棚卸し結果（分析前に確認）:
- region 集計に R6 行があり、公開レポート §1 の地域表にも津久井列がある
  （100%・comparable）。R6 の陸域は 238.38 km²、22,755 セル。
- coverage.by_region には R6 行がなく、R5 行の area_km2 は 328.87 km²
  （市全体相当）である。R6 単独の網羅率としては使わず、網羅率は
  公開レポート §1 の地域表（R6 238.4 km²・100%・comparable）と
  region 集計の coverage/scope 列に基づく。
- municipality 集計に R6 行はない。相模原 3 区行（緑区・中央区・南区）の
  合計は 31,401 セル・328.96 km² で、R6 地域行（22,755 セル・238.38 km²）
  とは一致しない。これは緑区行が R5（旧市域部分）を含む区全体の行で、
  かつ中央区・南区が全域 R5 だからである。R5 + R6 = 区行合計で一致する。
  したがって区行は R6 の内訳として使わず、参考としてのみ掲げる。
  緑区行は R6 の値でも R5 の値でもなく、両者を混ぜた区全体の値である。
- 農地→建物用地の R6 値は results.json の region 集計に列がなく、
  公開レポート §2 の面積表（津久井 0.70 km²）にのみあるため、本レポートでは
  その出典を明示した上で補助的にのみ引用し、仮説の判定には使わない。
  仮説の判定は results.json にある農地→森林・荒地、建物用地の純変化、
  森林化率、建物用地→森林・荒地率で行う。農地総減少から森林・荒地を
  引いた残差は「建物・交通・その他等への合計」であって、建物用地への
  値ではないので、そのようには使わない。
- P32 の地域別内訳は地点数（R6 = 6）のみで、R6 限定のバッファ集計はない。
- 距離帯・Moran の集計は県域全体のものであり、R6 限定の値は
  results.json にないため、R6 の言明には使わない。OSM の津久井窓は
  R6 とは範囲が異なるため、R6 の言明には使わない。
- focus_by_region の成分構造は地域全体のものであり、類型別・旧町別の
  成分構造は results.json にない。類型別の建物用地→森林・荒地率は
  絶対量（建物用地基数×率）と併記し、パッチの有無の判定には使わない。
  類型はいずれも陸域 0.5 km² を超えるため、類型間の比較は行える。
  ただし森林卓越メッシュ内の建物用地基数（2.34 km²）は小さく、
  その率は絶対量と併記する。
"""

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
d = json.loads((ROOT / "reports" / "phase1c2_results.json").read_text())

cov = d["coverage"]["by_region"]
cov_rows = {name: dict(zip(cov["columns"], row))
            for name, row in zip(cov["index"], cov["data"])}

reg = {name: dict(zip(d["aggregates"]["region"]["columns"], row))
       for name, row in zip(d["aggregates"]["region"]["index"],
                            d["aggregates"]["region"]["data"])}
r6 = reg["R6_tsukui"]
r5 = reg["R5_sagamihara"]

mcols = d["aggregates"]["municipality"]["columns"]
mrows = [dict(zip(mcols, r)) for r in d["aggregates"]["municipality"]["data"]]
sag_m = [r for r in mrows if r["muni_code"] in ("14151", "14152", "14153")]

rl = d["aggregates"]["region_landscape"]
rl_rows = {tuple(idx): dict(zip(rl["columns"], row))
           for idx, row in zip(rl["index"], rl["data"])}
r6_landscapes = {idx[1]: row for idx, row in rl_rows.items()
                 if idx[0] == "R6_tsukui"}

focus = d["transitions"]["focus_by_region"]
fcols = focus["columns"]
focus_r6 = {row[1]: dict(zip(fcols, row))
            for row in focus["data"] if row[0] == "R6_tsukui"}

cell_km2 = r6["land_km2"] / r6["n_cells"]
out = {}
out["coverage_by_region_row"] = {
    "has_R6_row": "R6_tsukui" in cov_rows,
    "R5_row_area_km2": cov_rows["R5_sagamihara"]["area_km2"],
    "R5_row_coverage": cov_rows["R5_sagamihara"]["coverage"],
    "R5_row_scope": cov_rows["R5_sagamihara"]["scope"],
}
out["n_cells"] = r6["n_cells"]
out["cell_km2"] = cell_km2
out["land_km2"] = r6["land_km2"]
out["region_coverage"] = r6["coverage"]
out["region_scope"] = r6["scope"]
# 区行合計と R5+R6 の一致、R6 単独との不一致（緑区行が R5 を含むため）。
out["ward_sum_cells"] = sum(r["n_cells"] for r in sag_m)
out["ward_sum_land_km2"] = sum(r["land_km2"] for r in sag_m)
out["ward_rows"] = len(sag_m)
out["r5_plus_r6_cells"] = r5["n_cells"] + r6["n_cells"]
out["r5_plus_r6_land_km2"] = r5["land_km2"] + r6["land_km2"]
out["r6_share_of_city_land"] = r6["land_km2"] / (r5["land_km2"] + r6["land_km2"])
out["r5_land_km2"] = r5["land_km2"]
out["ward_minus_r6_land_km2"] = out["ward_sum_land_km2"] - r6["land_km2"]


def share_km2(share):
    return share * r6["land_km2"]


out["composition_2014_km2"] = {
    "building": share_km2(r6["building_2014_share"]),
    "forest": share_km2(r6["forest_2014_share"]),
    "agri": share_km2(r6["agri_2014_share"]),
    "wasteland": share_km2(r6["wasteland_2014_share"]),
    "other": share_km2(r6["other_2014_share"]),
    "transport": share_km2(r6["transport_2014_share"]),
    "golf": share_km2(r6["golf_2014_share"]),
    "water": share_km2(r6["water_2014_share"]),
}
out["changed_km2"] = r6["changed_km2"]
out["changed_share"] = r6["changed_share"]
out["changed_cells"] = r6["changed_km2"] / cell_km2
out["singleton_share"] = r6["singleton_change_share"]
out["singleton_km2"] = r6["singleton_change_share"] * r6["changed_km2"]
out["small_component_share"] = r6["small_component_change_share"]

out["agri"] = {
    "km2_2014": share_km2(r6["agri_2014_share"]),
    "cells_2014": share_km2(r6["agri_2014_share"]) / cell_km2,
    "loss_km2": r6["agri_loss_km2"],
    "loss_cells": r6["agri_loss_km2"] / cell_km2,
    "to_forest_km2": r6["agri_to_forest_km2"],
    "to_forest_cells": r6["agri_to_forest_km2"] / cell_km2,
    "to_wasteland_km2": r6["agri_to_wasteland_km2"],
    "to_forest_or_wasteland_share_of_loss": (
        r6["agri_to_forest_km2"] + r6["agri_to_wasteland_km2"]
    ) / r6["agri_loss_km2"],
    "residual_to_other_destinations_km2": (
        r6["agri_loss_km2"] - r6["agri_to_forest_km2"]
        - r6["agri_to_wasteland_km2"]),
    "net_km2": r6["agri_net_change_km2"],
    "net_rate": r6["agri_net_change_rate"],
    "gross_loss_rate": r6["agri_gross_loss_rate"],
    "to_forest_rate": r6["agri_to_forest_rate"],
    "to_wasteland_rate": r6["agri_to_wasteland_rate"],
}
out["building"] = {
    "km2_2014": share_km2(r6["building_2014_share"]),
    "loss_km2": r6["building_loss_km2"],
    "gain_km2": r6["building_gain_km2"],
    "net_km2": r6["building_net_change_km2"],
    "net_rate": r6["building_net_change_rate"],
    "gross_loss_rate": r6["building_gross_loss_rate"],
    "to_forest_km2": r6["building_to_forest_km2"],
    "to_forest_cells": r6["building_to_forest_km2"] / cell_km2,
    "to_wasteland_km2": r6["building_to_wasteland_km2"],
    "to_forest_or_wasteland_rate": r6["building_to_forest_or_wasteland_rate"],
}
out["forest"] = {
    "km2_2014": share_km2(r6["forest_2014_share"]),
    "net_km2": r6["forest_net_change_km2"],
    "to_forest_km2": r6["to_forest_km2"],
    "forestation_rate": r6["forestation_rate"],
    "nonforest_base_km2": r6["land_km2"] - share_km2(r6["forest_2014_share"]),
}
out["wasteland"] = {
    "km2_2014": share_km2(r6["wasteland_2014_share"]),
    "km2_2021": share_km2(r6["wasteland_2021_share"]),
    "net_km2": r6["wasteland_net_change_km2"],
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
    "r5_building_2014_share": r5["building_2014_share"],
    "r5_forest_2014_share": r5["forest_2014_share"],
    "r5_agri_to_forest_km2": r5["agri_to_forest_km2"],
    "r5_agri_to_forest_rate": r5["agri_to_forest_rate"],
    "r5_building_to_forest_km2": r5["building_to_forest_km2"],
    "r5_building_to_forest_or_wasteland_rate":
        r5["building_to_forest_or_wasteland_rate"],
    "r5_forestation_rate": r5["forestation_rate"],
    "r5_building_net_km2": r5["building_net_change_km2"],
    "r6_building_net_km2": r6["building_net_change_km2"],
    "city_building_net_km2":
        r5["building_net_change_km2"] + r6["building_net_change_km2"],
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
    } for name, row in r6_landscapes.items()
}
out["landscape_land_sum_km2"] = sum(
    row["land_km2"] for row in r6_landscapes.values())
out["focus_transitions"] = focus_r6
out["p32"] = {
    "sites_by_region": d["cultural"]["sites_by_region"],
    "usable_sites": d["cultural"]["usable_sites"],
}

# 検証（失敗すればスクリプト自体が止まる）。
assert abs(out["r5_plus_r6_land_km2"] - out["ward_sum_land_km2"]) < 0.01
assert out["r5_plus_r6_cells"] == out["ward_sum_cells"]
assert abs(out["landscape_land_sum_km2"] - r6["land_km2"]) < 0.01
assert not out["coverage_by_region_row"]["has_R6_row"]
print(json.dumps(out, indent=2, ensure_ascii=False, sort_keys=True))
