"""R1 (横浜・川崎) 2週目分析の再計算スクリプト.

`reports/phase1c2_results.json` (Phase 1-C2 v0.2.0) の
region / municipality / region_landscape / focus_by_region / coverage /
cultural 集計だけから、2026-11-02_R1_week2.md の数値を再計算する。
新規データ取得・Drive アクセス・セル単位／候補地点の抽出は行わない。

農地→建物用地 3.73 km² のみ、results.json の region 集計に遷移先内訳が
含まれないため、公開済み reports/phase1c2_regional_analysis.md §2 の
面積表の値を定数として参照し、出典を明記して使う（1週目と同じ扱い）。
"""

import json
import pathlib
import statistics

ROOT = pathlib.Path(__file__).resolve().parents[3]
d = json.loads((ROOT / "reports" / "phase1c2_results.json").read_text())


def rows_of(table):
    return [dict(zip(table["columns"], r)) for r in table["data"]]


reg = {name: dict(zip(d["aggregates"]["region"]["columns"], row))
       for name, row in zip(d["aggregates"]["region"]["index"],
                            d["aggregates"]["region"]["data"])}
r1 = reg["R1_yokohama_kawasaki"]
muni = [r for r in rows_of(d["aggregates"]["municipality"])
        if r["region"] == "R1_yokohama_kawasaki"]
# region_landscape の index は [region, landscape] の複合キー
rl_rows = []
for idx, row in zip(d["aggregates"]["region_landscape"]["index"],
                    d["aggregates"]["region_landscape"]["data"]):
    if idx[0] == "R1_yokohama_kawasaki":
        r = dict(zip(d["aggregates"]["region_landscape"]["columns"], row))
        r["landscape"] = idx[1]
        rl_rows.append(r)
focus = [r for r in rows_of(d["transitions"]["focus_by_region"])
         if r["region"] == "R1_yokohama_kawasaki"]
cov = {name: dict(zip(d["coverage"]["by_region"]["columns"], row))
       for name, row in zip(d["coverage"]["by_region"]["index"],
                            d["coverage"]["by_region"]["data"])}
cov_r1 = cov["R1_yokohama_kawasaki"]

out = {}
out["cell_km2"] = r1["land_km2"] / r1["n_cells"]
out["region"] = {k: r1[k] for k in (
    "n_cells", "land_km2", "coverage", "scope",
    "agri_2014_share", "agri_net_change_km2", "agri_net_change_rate",
    "agri_gross_loss_rate", "agri_loss_km2", "agri_to_forest_km2",
    "agri_to_wasteland_km2", "forest_2014_share", "forest_net_change_km2",
    "forest_net_change_rate" if "forest_net_change_rate" in r1 else "forest_2014_share",
    "wasteland_net_change_km2", "building_2014_share",
    "building_net_change_km2", "building_net_change_rate",
    "building_loss_km2", "building_gain_km2", "building_gross_loss_rate",
    "building_to_forest_km2", "building_to_wasteland_km2",
    "building_to_forest_or_wasteland_rate", "forestation_rate", "to_forest_km2",
    "transport_net_change_km2", "other_net_change_km2", "changed_km2",
    "changed_share", "singleton_change_share", "small_component_change_share")}
out["coverage_table"] = cov_r1
# 群合計の検証（R4 の手順の転用）
out["muni_group_sum"] = {
    "n_cells": sum(r["n_cells"] for r in muni),
    "land_km2": sum(r["land_km2"] for r in muni),
    "forest_net_km2": sum(r["forest_net_change_km2"] for r in muni),
    "agri_net_km2": sum(r["agri_net_change_km2"] for r in muni),
    "building_net_km2": sum(r["building_net_change_km2"] for r in muni),
    "n_muni": len(muni),
}
# 2014年構成率の範囲（区レベル）
for key, share in (("building", "building_2014_share"),
                   ("forest", "forest_2014_share")):
    vals = sorted(((r["muni_name"], r[share] * 100,
                    r[share] * r["land_km2"]) for r in muni),
                  key=lambda t: t[1])
    out[f"{key}_2014_share_range"] = {
        "min": vals[0], "max": vals[-1],
        "range_points": vals[-1][1] - vals[0][1]}
# 森林・農地の純変化上位と集中度
for key, col in (("forest", "forest_net_change_km2"),
                 ("agri", "agri_net_change_km2")):
    ranked = sorted(muni, key=lambda x: x[col])
    total = sum(r[col] for r in muni)
    out[f"{key}_top6"] = [(r["muni_name"], round(r[col], 3)) for r in ranked[:6]]
    out[f"{key}_top6_share_pct"] = -sum(r[col] for r in ranked[:6]) / -total * 100
    out[f"{key}_negative_n"] = sum(1 for r in muni if r[col] < 0)
    out[f"{key}_positive"] = [(r["muni_name"], round(r[col], 3))
                              for r in muni if r[col] > 0]
out["top6_overlap"] = sorted(
    set(n for n, _ in out["forest_top6"]) & set(n for n, _ in out["agri_top6"]))


def ranks(v):
    order = sorted(range(len(v)), key=lambda i: v[i])
    rk = [0] * len(v)
    for rank, i in enumerate(order):
        rk[i] = rank
    return rk


xs = [r["forest_net_change_km2"] for r in muni]
ys = [r["agri_net_change_km2"] for r in muni]
rx, ry = ranks(xs), ranks(ys)
mx, my = statistics.mean(rx), statistics.mean(ry)
out["spearman_forest_vs_agri_net"] = (
    sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    / (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5)
mx2, my2 = statistics.mean(xs), statistics.mean(ys)
out["pearson_forest_vs_agri_net"] = (
    sum((a - mx2) * (b - my2) for a, b in zip(xs, ys))
    / (sum((a - mx2) ** 2 for a in xs) * sum((b - my2) ** 2 for b in ys)) ** 0.5)
# 類型別（都市的メッシュのシェア）
for r in rl_rows:
    out[f"landscape_{r['landscape']}"] = {
        "land_km2": r["land_km2"],
        "land_share_pct": r["land_km2"] / r1["land_km2"] * 100,
        "forest_net_km2": r["forest_net_change_km2"],
        "agri_net_km2": r["agri_net_change_km2"],
        "building_net_km2": r["building_net_change_km2"],
        "forest_2014_share_pct": r["forest_2014_share"] * 100,
        "building_2014_share_pct": r["building_2014_share"] * 100,
    }
urban = next(r for r in rl_rows if r["landscape"] == "urban")
out["urban_share_of_forest_net_pct"] = -urban["forest_net_change_km2"] / -r1["forest_net_change_km2"] * 100
out["urban_share_of_agri_net_pct"] = -urban["agri_net_change_km2"] / -r1["agri_net_change_km2"] * 100
# 建物用地の区別バランス
for name in ("川崎市川崎区", "横浜市保土ケ谷区", "横浜市青葉区", "横浜市金沢区",
             "横浜市西区", "横浜市南区"):
    r = next(x for x in muni if x["muni_name"] == name)
    out[f"building_{name}"] = {
        "building_2014_km2": r["building_2014_share"] * r["land_km2"],
        "gross_loss_rate_pct": r["building_gross_loss_rate"] * 100,
        "loss_km2": r["building_loss_km2"],
        "gain_km2": r["building_gain_km2"],
        "net_km2": r["building_net_change_km2"],
        "net_rate_pct": r["building_net_change_rate"] * 100,
        "coverage": r["coverage"],
    }
gross_sorted = sorted(muni, key=lambda x: x["building_gross_loss_rate"])
out["building_gross_loss_lowest3"] = [
    (r["muni_name"], round(r["building_gross_loss_rate"] * 100, 2))
    for r in gross_sorted[:3]]
out["building_gross_loss_highest"] = (
    gross_sorted[-1]["muni_name"],
    round(gross_sorted[-1]["building_gross_loss_rate"] * 100, 2))
net_sorted = sorted(muni, key=lambda x: x["building_net_change_km2"])
out["building_net_most_negative"] = (net_sorted[0]["muni_name"],
                                     round(net_sorted[0]["building_net_change_km2"], 3))
out["building_net_most_positive"] = (net_sorted[-1]["muni_name"],
                                     round(net_sorted[-1]["building_net_change_km2"], 3))
rate_sorted = sorted(muni, key=lambda x: x["building_net_change_rate"])
out["building_net_rate_highest2"] = [
    (r["muni_name"], round(r["building_net_change_rate"] * 100, 2),
     round(r["building_net_change_km2"], 3)) for r in rate_sorted[-2:]]
# focus 遷移
out["focus"] = {r["transition"]: {
    "area_km2": r["area_km2"], "cells": r["cells"],
    "size_1_share_pct": (r["size_1_share"] * 100 if r["size_1_share"] is not None else None),
    "boundary_share_pct": (r["boundary_share"] * 100 if r["boundary_share"] is not None else None),
    "max_component_cells": r["max_component_cells"],
    "reverse_area_km2": r["reverse_area_km2"],
} for r in focus}
out["p32_R1"] = d["cultural"]["sites_by_region"]["R1_yokohama_kawasaki"]
out["p32_usable_total"] = d["cultural"]["usable_sites"]
out["green_net_km2"] = (r1["forest_net_change_km2"] + r1["agri_net_change_km2"]
                        + r1["wasteland_net_change_km2"])
out["agri_to_building_aux_km2"] = 3.73  # phase1c2_regional_analysis.md §2 面積表 (R1)
out["agri_to_building_share_of_loss_pct"] = 3.73 / r1["agri_loss_km2"] * 100

if __name__ == "__main__":
    print(json.dumps(out, ensure_ascii=False, indent=2))
