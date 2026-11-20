"""R4（県央・相模原市を除く）2週目分析の再計算スクリプト.

`reports/phase1c2_results.json`（Phase 1-C2 v0.2.0）の
coverage / region / municipality / region_landscape / transitions /
component_class_share_by_region / cultural 集計だけから、
2026-11-05_R4_week2.md の数値を再計算する。
新規データ取得・Drive アクセス・セル単位／候補地点の抽出は行わない。

2週目の主軸は 1週目 §8 の宿題「南部4市・北部2町村・厚木市の3群比較」である。
群は市区町村行の合計で作る。

ベンチマークは結果を見る前に固定した（R3 週2の反省）:
- 農地純減少シェアの比較相手は農地基数シェア（2014年農地の群シェア）。
  陸域シェアとの差は再確認として出すが、H1 の支持条件には入れない。
- 建物用地純変化シェアの比較相手は陸域シェア。

その他の閾値（結果を見て動かさない）:
- NEAR_PP = 0.01。シェア差が 1 パーセントポイント未満なら境界付近。
- NEAR_CELLS = 1。10% 閾値までの余裕が 1 セル未満なら境界付近。
- RECOVERY_GAP = 0.10。回復率（総増加/総減少）の差の実質閾値。
- EX_MARGIN_CELLS = 5。厚木市を除いた残りが 10% から 5 セル以上離れること。
- ATSUGI_FW_SHARE = 0.70。農地→森林・荒地の面積に占める厚木市。
- DOMINANCE_SHARE = 0.50。R2 週2・R3 追補と同じ。動かさない。
- MIN_RATE_BASE_KM2 = 0.50。基数 0.5 km² 未満の率は順位付けに使わない。
- GE5_MAX = 0.10。変化全体の 5 セル以上シェア。
- COMPLEMENT_GAP = 0.10。1〜2 セルの補集合と 5 セル以上の差。

導出（恒等式。推定ではない）:
- 農地総増加 = 農地純変化 + 農地総減少
- 森林総減少 = 森林への総流入 - 森林純変化
"""

import json
import pathlib

NEAR_PP = 0.01
NEAR_CELLS = 1.0
RECOVERY_GAP = 0.10
EX_MARGIN_CELLS = 5.0
ATSUGI_FW_SHARE = 0.70
DOMINANCE_SHARE = 0.50
MIN_RATE_BASE_KM2 = 0.50
GE5_MAX = 0.10
COMPLEMENT_GAP = 0.10
URBAN_CONVERSION_FW_OF_LOSS = 0.10

SOUTH = ["大和市", "座間市", "海老名市", "綾瀬市"]
NORTH = ["清川村", "愛川町"]
ATSUGI = ["厚木市"]
GROUP_ORDER = ("south4", "north2", "atsugi")

ROOT = pathlib.Path(__file__).resolve().parents[3]
d = json.loads((ROOT / "reports" / "phase1c2_results.json").read_text())

cov = d["coverage"]["by_region"]
cov_rows = {name: dict(zip(cov["columns"], row))
            for name, row in zip(cov["index"], cov["data"])}
r4cov = cov_rows["R4_kenou"]

reg = {name: dict(zip(d["aggregates"]["region"]["columns"], row))
       for name, row in zip(d["aggregates"]["region"]["index"],
                            d["aggregates"]["region"]["data"])}
r4 = reg["R4_kenou"]

mcols = d["aggregates"]["municipality"]["columns"]
mrows = [dict(zip(mcols, r)) for r in d["aggregates"]["municipality"]["data"]]
r4m = [r for r in mrows if r["region"] == "R4_kenou"]
by_name = {r["muni_name"]: r for r in r4m}

rl = d["aggregates"]["region_landscape"]
rl_rows = {tuple(idx): dict(zip(rl["columns"], row))
           for idx, row in zip(rl["index"], rl["data"])}
r4_landscapes = {idx[1]: row for idx, row in rl_rows.items()
                 if idx[0] == "R4_kenou"}

focus = d["transitions"]["focus_by_region"]
fcols = focus["columns"]
focus_r4 = {row[1]: dict(zip(fcols, row))
            for row in focus["data"] if row[0] == "R4_kenou"}

comp = d["transitions"]["component_class_share_by_region"]
comp_rows = {name: dict(zip(comp["columns"], row))
             for name, row in zip(comp["index"], comp["data"])}
r4comp = comp_rows["R4_kenou"]

cell_km2 = r4["land_km2"] / r4["n_cells"]

aggregate_names = sorted(d["aggregates"].keys())
transition_names = sorted(d["transitions"].keys())
cross_names = [
    name for name in aggregate_names + transition_names
    if ("muni" in name and ("land" in name or "landscape" in name))
]


def cells_of(km2):
    return km2 / cell_km2


def muni_summary(r):
    land = r["land_km2"]
    agri14 = r["agri_2014_share"] * land
    bld14 = r["building_2014_share"] * land
    forest14 = r["forest_2014_share"] * land
    fw = r["agri_to_forest_km2"] + r["agri_to_wasteland_km2"]
    return {
        "n_cells": r["n_cells"],
        "land_km2": land,
        "coverage": r["coverage"],
        "scope": r["scope"],
        "agri_2014_km2": agri14,
        "agri_net_km2": r["agri_net_change_km2"],
        "agri_loss_km2": r["agri_loss_km2"],
        # 導出: 総増加 = 純変化 + 総減少
        "agri_gain_derived_km2": r["agri_net_change_km2"] + r["agri_loss_km2"],
        "agri_to_forest_km2": r["agri_to_forest_km2"],
        "agri_to_wasteland_km2": r["agri_to_wasteland_km2"],
        "agri_to_forest_wasteland_km2": fw,
        "building_2014_km2": bld14,
        "building_net_km2": r["building_net_change_km2"],
        "building_loss_km2": r["building_loss_km2"],
        "building_gain_km2": r["building_gain_km2"],
        "building_to_forest_km2": r["building_to_forest_km2"],
        "building_to_wasteland_km2": r["building_to_wasteland_km2"],
        "forest_2014_km2": forest14,
        "forest_net_km2": r["forest_net_change_km2"],
        "to_forest_km2": r["to_forest_km2"],
        # 導出: 森林総減少 = 森林への総流入 - 森林純変化
        "forest_loss_derived_km2": r["to_forest_km2"] - r["forest_net_change_km2"],
        "wasteland_2014_km2": r["wasteland_2014_share"] * land,
        "wasteland_net_km2": r["wasteland_net_change_km2"],
        "changed_km2": r["changed_km2"],
        "singleton_change_share": r["singleton_change_share"],
        "small_component_change_share": r["small_component_change_share"],
    }


SUM_KEYS = [
    "n_cells", "land_km2", "agri_2014_km2", "agri_net_km2", "agri_loss_km2",
    "agri_gain_derived_km2", "agri_to_forest_km2", "agri_to_wasteland_km2",
    "agri_to_forest_wasteland_km2", "building_2014_km2", "building_net_km2",
    "building_loss_km2", "building_gain_km2", "building_to_forest_km2",
    "building_to_wasteland_km2", "forest_2014_km2", "forest_net_km2",
    "to_forest_km2", "forest_loss_derived_km2", "wasteland_2014_km2",
    "wasteland_net_km2", "changed_km2",
]

region_agri = r4["agri_2014_share"] * r4["land_km2"]
region_building = r4["building_2014_share"] * r4["land_km2"]
region_forest = r4["forest_2014_share"] * r4["land_km2"]
region_fw = r4["agri_to_forest_km2"] + r4["agri_to_wasteland_km2"]


def group_summary(names):
    g = [by_name[n] for n in names]
    parts = [muni_summary(r) for r in g]
    s = {k: sum(p[k] for p in parts) for k in SUM_KEYS}
    s["members"] = names
    s["agri_net_rate"] = s["agri_net_km2"] / s["agri_2014_km2"]
    s["agri_gross_loss_rate"] = s["agri_loss_km2"] / s["agri_2014_km2"]
    s["agri_recovery_rate"] = (
        s["agri_gain_derived_km2"] / s["agri_loss_km2"]
        if s["agri_loss_km2"] else None)
    s["agri_fw_of_loss"] = (
        s["agri_to_forest_wasteland_km2"] / s["agri_loss_km2"]
        if s["agri_loss_km2"] else None)
    s["building_net_rate"] = s["building_net_km2"] / s["building_2014_km2"]
    s["building_share"] = s["building_2014_km2"] / s["land_km2"]
    s["forest_share"] = s["forest_2014_km2"] / s["land_km2"]
    s["land_share"] = s["land_km2"] / r4["land_km2"]
    s["agri_base_share"] = s["agri_2014_km2"] / region_agri
    s["agri_net_loss_share"] = s["agri_net_km2"] / r4["agri_net_change_km2"]
    s["agri_loss_share"] = s["agri_loss_km2"] / r4["agri_loss_km2"]
    s["agri_fw_share_of_region"] = (
        s["agri_to_forest_wasteland_km2"] / region_fw if region_fw else None)
    # ベンチマーク差。正なら「基数（または陸域）以上に純減少を占める」。
    s["agri_excess_over_base_share"] = (
        s["agri_net_loss_share"] - s["agri_base_share"])
    s["agri_excess_over_land_share"] = (
        s["agri_net_loss_share"] - s["land_share"])
    s["building_net_share"] = (
        s["building_net_km2"] / r4["building_net_change_km2"])
    s["building_excess_over_land_share"] = (
        s["building_net_share"] - s["land_share"])
    s["changed_density"] = s["changed_km2"] / s["land_km2"]
    s["agri_base_below_0_5"] = s["agri_2014_km2"] < MIN_RATE_BASE_KM2
    s["building_base_below_0_5"] = s["building_2014_km2"] < MIN_RATE_BASE_KM2
    s["fw_margin_to_10pct_km2"] = (
        URBAN_CONVERSION_FW_OF_LOSS * s["agri_loss_km2"]
        - s["agri_to_forest_wasteland_km2"])
    s["fw_margin_to_10pct_cells"] = cells_of(s["fw_margin_to_10pct_km2"])
    return s


muni_out = {r["muni_name"]: muni_summary(r) for r in r4m}
groups = {
    "south4": group_summary(SOUTH),
    "north2": group_summary(NORTH),
    "atsugi": group_summary(ATSUGI),
}

# 反事実（恒等計算。因果ではない）:
# 厚木市の農地基数に南部4市の農地純変化率を掛けた値と、実測との差。
cf_south = groups["atsugi"]["agri_2014_km2"] * groups["south4"]["agri_net_rate"]
cf_region = groups["atsugi"]["agri_2014_km2"] * r4["agri_net_change_rate"]

ex_names = [n for n in by_name if n not in ATSUGI]
ex = group_summary(ex_names)

region_fw_ratio = region_fw / r4["agri_loss_km2"]
region_margin_km2 = (URBAN_CONVERSION_FW_OF_LOSS * r4["agri_loss_km2"]
                     - region_fw)
region_margin_cells = cells_of(region_margin_km2)

h1_a = groups["atsugi"]["agri_excess_over_base_share"] > 0
h1_b = (groups["south4"]["agri_excess_over_base_share"] <= 0
        and groups["north2"]["agri_excess_over_base_share"] <= 0)
h1_c = groups["atsugi"]["building_net_share"] < groups["atsugi"]["land_share"]
h1_near = abs(groups["atsugi"]["agri_excess_over_base_share"]) < NEAR_PP
h1_support = h1_a and h1_b and h1_c

south_recovery = groups["south4"]["agri_recovery_rate"]
atsugi_recovery = groups["atsugi"]["agri_recovery_rate"]
recovery_gap = south_recovery - atsugi_recovery
h2_c1 = (groups["atsugi"]["agri_gross_loss_rate"]
         > groups["south4"]["agri_gross_loss_rate"])
h2_c2 = atsugi_recovery < south_recovery
h2_c3 = recovery_gap >= RECOVERY_GAP
h2_support = h2_c1 and h2_c2 and h2_c3

h3_reconfirm = (region_fw_ratio < URBAN_CONVERSION_FW_OF_LOSS
                and region_margin_cells < NEAR_CELLS)
h3_c2 = (ex["agri_fw_of_loss"] < URBAN_CONVERSION_FW_OF_LOSS
         and ex["fw_margin_to_10pct_cells"] >= EX_MARGIN_CELLS)
h3_c3 = groups["atsugi"]["agri_fw_share_of_region"] > ATSUGI_FW_SHARE
h3_support = h3_reconfirm and h3_c2 and h3_c3
groups_at_or_over_10 = [
    name for name in GROUP_ORDER
    if groups[name]["agri_fw_of_loss"] >= URBAN_CONVERSION_FW_OF_LOSS
]

share_1 = r4comp["share_1"]
share_2 = r4comp["share_2"]
share_34 = r4comp["share_3-4"]
share_ge5 = r4comp["share_>=5"]
changed_comp = r4comp["changed_km2"]
complement_12 = 1.0 - share_1 - share_2
h4_c1 = share_ge5 < GE5_MAX
h4_c2 = (complement_12 - share_ge5) > COMPLEMENT_GAP
h4_c3 = (focus_r4["building->forest"]["size_>=5_share"] == 0
         and focus_r4["agri->forest"]["size_>=5_share"] == 0)
h4_support = h4_c1 and h4_c2 and h4_c3

land_rows = []
for name, row in r4_landscapes.items():
    base = row["agri_2014_share"] * row["land_km2"]
    land_rows.append({
        "landscape": name,
        "land_km2": row["land_km2"],
        "changed_km2": row["changed_km2"],
        "agri_2014_km2": base,
        "agri_net_km2": row["agri_net_change_km2"],
        "agri_net_rate": row["agri_net_change_rate"],
        "agri_loss_km2": row["agri_loss_km2"],
        "agri_gain_derived_km2": (row["agri_net_change_km2"]
                                  + row["agri_loss_km2"]),
        "agri_to_forest_km2": row["agri_to_forest_km2"],
        "agri_to_wasteland_km2": row["agri_to_wasteland_km2"],
        "to_forest_km2": row["to_forest_km2"],
        "forest_net_km2": row["forest_net_change_km2"],
        "nonforest_km2": row["land_km2"] * (1.0 - row["forest_2014_share"]),
        "forestation_rate": row["forestation_rate"],
        "building_2014_km2": row["building_2014_share"] * row["land_km2"],
        "building_net_km2": row["building_net_change_km2"],
        "building_to_forest_km2": row["building_to_forest_km2"],
        "building_to_wasteland_km2": row["building_to_wasteland_km2"],
        "rate_rank_eligible": base >= MIN_RATE_BASE_KM2,
    })
changed_land_total = sum(r["changed_km2"] for r in land_rows)
agri_net_land_total = sum(r["agri_net_km2"] for r in land_rows)
for r in land_rows:
    r["changed_share"] = r["changed_km2"] / changed_land_total
    r["agri_net_loss_share"] = r["agri_net_km2"] / agri_net_land_total
dominant = max(land_rows, key=lambda r: r["changed_share"])
h5_dominates = dominant["changed_share"] > DOMINANCE_SHARE
h5_support = not h5_dominates  # 「単一類型が 50% を超えない」

abs_leader = min(land_rows, key=lambda r: r["agri_net_km2"])
eligible = [r for r in land_rows if r["rate_rank_eligible"]]
rate_leader = min(eligible, key=lambda r: r["agri_net_rate"])
h6_support = abs_leader["landscape"] != rate_leader["landscape"]

# クロス表は無い。点推定はしない。
# 周辺分布だけから、厚木市の農地→森林が各類型と交わる面積の
# 上下限（Fréchet）を出す。下限 = max(0, 厚木 + 類型 - 地域)、上限 = min(厚木, 類型)。
atsugi_a2f = groups["atsugi"]["agri_to_forest_km2"]
region_a2f = r4["agri_to_forest_km2"]
frechet_agri_to_forest = []
for r in land_rows:
    lower = max(0.0, atsugi_a2f + r["agri_to_forest_km2"] - region_a2f)
    upper = min(atsugi_a2f, r["agri_to_forest_km2"])
    frechet_agri_to_forest.append({
        "landscape": r["landscape"],
        "landscape_km2": r["agri_to_forest_km2"],
        "lower_km2": lower,
        "upper_km2": upper,
        "single_type_can_hold_all_atsugi": upper + 1e-12 >= atsugi_a2f,
    })

# 率の順位付けを禁止する基数の棚卸し（0.5 km² 未満）。
rate_base_flags = []
for name, g in groups.items():
    rate_base_flags.append({
        "unit": name,
        "metric": "agri_2014",
        "base_km2": g["agri_2014_km2"],
        "below_0_5": g["agri_base_below_0_5"],
    })
    rate_base_flags.append({
        "unit": name,
        "metric": "building_2014",
        "base_km2": g["building_2014_km2"],
        "below_0_5": g["building_base_below_0_5"],
    })
for name, m in muni_out.items():
    for metric, key in (("agri_2014", "agri_2014_km2"),
                        ("building_2014", "building_2014_km2"),
                        ("wasteland_2014", "wasteland_2014_km2")):
        base = m[key]
        if base < MIN_RATE_BASE_KM2:
            rate_base_flags.append({
                "unit": name,
                "metric": metric,
                "base_km2": base,
                "below_0_5": True,
            })
for r in land_rows:
    if r["agri_2014_km2"] < MIN_RATE_BASE_KM2:
        rate_base_flags.append({
            "unit": r["landscape"],
            "metric": "agri_2014",
            "base_km2": r["agri_2014_km2"],
            "below_0_5": True,
        })

out = {
    "thresholds": {
        "agri_benchmark": "agri_base_share",
        "building_benchmark": "land_share",
        "near_pp": NEAR_PP,
        "near_cells": NEAR_CELLS,
        "recovery_gap": RECOVERY_GAP,
        "ex_margin_cells": EX_MARGIN_CELLS,
        "atsugi_fw_share_min": ATSUGI_FW_SHARE,
        "dominance_share": DOMINANCE_SHARE,
        "min_rate_base_km2": MIN_RATE_BASE_KM2,
        "ge5_max": GE5_MAX,
        "complement_gap": COMPLEMENT_GAP,
        "urban_conversion_fw_of_loss": URBAN_CONVERSION_FW_OF_LOSS,
    },
    "coverage": {
        "area_km2": r4cov["area_km2"],
        "covered_km2": r4cov["covered_km2"],
        "uncovered_km2": r4cov["area_km2"] - r4cov["covered_km2"],
        "coverage": r4cov["coverage"],
        "scope": r4cov["scope"],
        "land_minus_covered_km2": r4["land_km2"] - r4cov["covered_km2"],
    },
    "n_cells": r4["n_cells"],
    "cell_km2": cell_km2,
    "land_km2": r4["land_km2"],
    "muni_rows": len(r4m),
    "muni_names": sorted(by_name),
    "muni_sum_cells": sum(r["n_cells"] for r in r4m),
    "muni_sum_land_km2": sum(r["land_km2"] for r in r4m),
    "muni_scopes": sorted({r["scope"] for r in r4m}),
    "muni_coverages": sorted({r["coverage"] for r in r4m}),
    "cross_tab_names": cross_names,
    "aggregate_names": aggregate_names,
    "transition_names": transition_names,
    "municipality": muni_out,
    "groups": groups,
    "ex_atsugi": ex,
    "counterfactual": {
        "atsugi_agri_net_at_south_rate_km2": cf_south,
        "atsugi_excess_vs_south_rate_km2": (
            groups["atsugi"]["agri_net_km2"] - cf_south),
        "atsugi_excess_vs_south_rate_cells": cells_of(
            groups["atsugi"]["agri_net_km2"] - cf_south),
        "atsugi_agri_net_at_region_rate_km2": cf_region,
        "atsugi_excess_vs_region_rate_km2": (
            groups["atsugi"]["agri_net_km2"] - cf_region),
        "note": "恒等計算。南部または地域の率を厚木市の農地基数に掛けた値と実測の差。因果ではない。",
    },
    "region": {
        "agri_2014_km2": region_agri,
        "agri_net_km2": r4["agri_net_change_km2"],
        "agri_net_rate": r4["agri_net_change_rate"],
        "agri_loss_km2": r4["agri_loss_km2"],
        "agri_gain_derived_km2": (r4["agri_net_change_km2"]
                                  + r4["agri_loss_km2"]),
        "agri_to_forest_km2": r4["agri_to_forest_km2"],
        "agri_to_wasteland_km2": r4["agri_to_wasteland_km2"],
        "agri_fw_km2": region_fw,
        "agri_fw_of_loss": region_fw_ratio,
        "fw_margin_to_10pct_km2": region_margin_km2,
        "fw_margin_to_10pct_cells": region_margin_cells,
        "building_2014_km2": region_building,
        "building_net_km2": r4["building_net_change_km2"],
        "building_loss_km2": r4["building_loss_km2"],
        "building_gain_km2": r4["building_gain_km2"],
        "building_to_forest_km2": r4["building_to_forest_km2"],
        "forest_2014_km2": region_forest,
        "forest_net_km2": r4["forest_net_change_km2"],
        "to_forest_km2": r4["to_forest_km2"],
        "forest_loss_derived_km2": (r4["to_forest_km2"]
                                    - r4["forest_net_change_km2"]),
        "forestation_rate": r4["forestation_rate"],
        "changed_km2": r4["changed_km2"],
        "singleton_change_share": r4["singleton_change_share"],
        "small_component_change_share": r4["small_component_change_share"],
        "building_2014_share": r4["building_2014_share"],
        "forest_2014_share": r4["forest_2014_share"],
    },
    "component_class": {
        "share_1": share_1,
        "share_2": share_2,
        "share_3_4": share_34,
        "share_ge5": share_ge5,
        "changed_km2": changed_comp,
        "area_1_km2": share_1 * changed_comp,
        "area_2_km2": share_2 * changed_comp,
        "area_1_2_km2": (share_1 + share_2) * changed_comp,
        "area_3_4_km2": share_34 * changed_comp,
        "area_ge5_km2": share_ge5 * changed_comp,
        "area_ge3_km2": complement_12 * changed_comp,
        "complement_of_1_2": complement_12,
        "complement_minus_ge5": complement_12 - share_ge5,
        "matches_region_changed": abs(changed_comp - r4["changed_km2"]) < 1e-6,
    },
    "focus_transitions": {
        name: {
            "area_km2": row["area_km2"],
            "cells": row["cells"],
            "rate_of_2014_class": row["rate_of_2014_class"],
            "size_1_share": row["size_1_share"],
            "size_2_share": row["size_2_share"],
            "size_3_4_share": row["size_3-4_share"],
            "size_ge5_share": row["size_>=5_share"],
            "max_component_cells": row["max_component_cells"],
            "boundary_share": row["boundary_share"],
            "reverse_area_km2": row["reverse_area_km2"],
        } for name, row in focus_r4.items()
    },
    "landscape": land_rows,
    "rate_base_flags_below_0_5": [
        row for row in rate_base_flags if row["below_0_5"]
    ],
    "judgments": {
        "H1": {
            "a_atsugi_above_agri_base": h1_a,
            "b_other_groups_not_above_base": h1_b,
            "c_building_share_below_land": h1_c,
            "near_1pp": h1_near,
            "support": h1_support,
        },
        "H2": {
            "c1_atsugi_gross_loss_rate_higher": h2_c1,
            "c2_atsugi_recovery_lower": h2_c2,
            "c3_recovery_gap_ge_10pp": h2_c3,
            "recovery_gap": recovery_gap,
            "support": h2_support,
        },
        "H3": {
            "reconfirm_region_boundary": h3_reconfirm,
            "c2_ex_atsugi_margin_ge_5_cells": h3_c2,
            "c3_atsugi_fw_share_gt_70pct": h3_c3,
            "groups_fw_of_loss_ge_10pct": groups_at_or_over_10,
            "support": h3_support,
        },
        "H4": {
            "c1_ge5_below_10pct": h4_c1,
            "c2_complement_gap_gt_10pp": h4_c2,
            "c3_focus_ge5_is_zero": h4_c3,
            "support": h4_support,
        },
        "H5": {
            "dominant_landscape": dominant["landscape"],
            "dominant_share": dominant["changed_share"],
            "single_type_dominates": h5_dominates,
            "support_no_dominance": h5_support,
        },
        "H6": {
            "abs_leader": abs_leader["landscape"],
            "abs_leader_net_km2": abs_leader["agri_net_km2"],
            "abs_leader_rate": abs_leader["agri_net_rate"],
            "abs_leader_base_km2": abs_leader["agri_2014_km2"],
            "rate_leader": rate_leader["landscape"],
            "rate_leader_rate": rate_leader["agri_net_rate"],
            "rate_leader_net_km2": rate_leader["agri_net_km2"],
            "rate_leader_base_km2": rate_leader["agri_2014_km2"],
            "support_names_differ": h6_support,
        },
        "HA": {
            "cross_tab_absent": len(cross_names) == 0,
            "verdict": "保留（検証不能）" if len(cross_names) == 0 else "クロス表あり",
            "note": "上下限は周辺分布の制約であり、クロス表の点推定ではない。",
        },
    },
    "frechet_atsugi_agri_to_forest": frechet_agri_to_forest,
    "kiyokawa_building_to_forest": {
        "km2": muni_out["清川村"]["building_to_forest_km2"],
        "cell_equivalent": cells_of(muni_out["清川村"]["building_to_forest_km2"]),
        "share_of_region": (
            muni_out["清川村"]["building_to_forest_km2"]
            / r4["building_to_forest_km2"]),
        # 市町村行にあるのは変化全体の singleton / small_component シェアだけ。
        # 建物用地→森林の成分階級（size_>=5、最大成分）は focus_by_region の地域行のみ。
        "transition_component_columns_present": any(
            c.startswith("size_") or c == "max_component_cells" for c in mcols),
        "overall_change_component_shares_present": (
            "singleton_change_share" in mcols
            and "small_component_change_share" in mcols),
    },
    "north_members": {
        name: {
            "agri_loss_km2": muni_out[name]["agri_loss_km2"],
            "agri_fw_km2": muni_out[name]["agri_to_forest_wasteland_km2"],
            "agri_fw_of_loss": (
                muni_out[name]["agri_to_forest_wasteland_km2"]
                / muni_out[name]["agri_loss_km2"]),
            "agri_loss_below_0_5": (
                muni_out[name]["agri_loss_km2"] < MIN_RATE_BASE_KM2),
            "forest_net_km2": muni_out[name]["forest_net_km2"],
            "forest_2014_km2": muni_out[name]["forest_2014_km2"],
            "building_2014_km2": muni_out[name]["building_2014_km2"],
            "building_to_forest_km2": muni_out[name]["building_to_forest_km2"],
            "singleton_change_share": muni_out[name]["singleton_change_share"],
            "small_component_change_share": (
                muni_out[name]["small_component_change_share"]),
        } for name in NORTH
    },
    "p32_sites_r4": d["cultural"]["sites_by_region"]["R4_kenou"],
    "p32_usable_sites": d["cultural"]["usable_sites"],
}

# 検証アサーション。前提が崩れればスクリプトが失敗する。
assert out["muni_sum_cells"] == r4["n_cells"]
assert abs(out["muni_sum_land_km2"] - r4["land_km2"]) < 1e-6
assert out["muni_rows"] == 7
assert out["muni_scopes"] == ["comparable"]
assert out["muni_coverages"] == [1.0]
for field in ["agri_net_change_km2", "agri_loss_km2", "agri_to_forest_km2",
              "agri_to_wasteland_km2", "building_net_change_km2",
              "building_loss_km2", "building_gain_km2",
              "building_to_forest_km2", "forest_net_change_km2",
              "to_forest_km2", "wasteland_net_change_km2", "changed_km2"]:
    assert abs(sum(r[field] for r in r4m) - r4[field]) < 1e-3, field
for key, region_value in {
    "agri_net_km2": r4["agri_net_change_km2"],
    "agri_loss_km2": r4["agri_loss_km2"],
    "building_net_km2": r4["building_net_change_km2"],
    "changed_km2": r4["changed_km2"],
    "land_km2": r4["land_km2"],
    "n_cells": r4["n_cells"],
}.items():
    total = sum(groups[name][key] for name in GROUP_ORDER)
    assert abs(total - region_value) < 1e-3, key
assert abs(changed_land_total - r4["changed_km2"]) < 1e-6
assert abs(agri_net_land_total - r4["agri_net_change_km2"]) < 1e-6
assert abs(sum(r["agri_to_forest_km2"] for r in land_rows)
           - r4["agri_to_forest_km2"]) < 1e-6
assert all(row["lower_km2"] <= row["upper_km2"] + 1e-12
           for row in frechet_agri_to_forest)
assert abs((share_1 + share_2 + share_34 + share_ge5) - 1.0) < 1e-9
assert abs(r4["small_component_change_share"] - (share_1 + share_2)) < 1e-6
assert out["component_class"]["matches_region_changed"]
assert len(cross_names) == 0
assert out["kiyokawa_building_to_forest"]["transition_component_columns_present"] is False
assert out["kiyokawa_building_to_forest"]["overall_change_component_shares_present"] is True

print(json.dumps(out, ensure_ascii=False, indent=1))
