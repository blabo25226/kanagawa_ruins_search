"""R4 (県央・相模原市を除く) 1週目分析の再計算スクリプト.

`reports/phase1c2_results.json` (Phase 1-C2 v0.2.0) の
coverage / region / municipality / region_landscape / transitions 集計だけから、
2026-10-29_R4_week1.md の数値を再計算する。
新規データ取得・Drive アクセス・セル単位／候補地点の抽出は行わない。

棚卸し結果（分析前に確認）:
- region 集計に R4 行があり、公開レポート §2 の地域別表にも県央列がある
  （comparable として比較表に残されている）。
- municipality 集計の R4 所属行は 7 行（厚木・大和・海老名・座間・綾瀬・
  愛川・清川）で、すべて網羅率 100%・comparable。欠け・行なしはない。
- 農地→建物用地の R4 値は results.json の region 集計に列がなく、
  公開レポート §2 の面積表（県央 2.50 km²）にのみあるため、本レポートでは
  その出典を明示した上で補助的にのみ引用し、仮説の判定には使わない。
  仮説の判定は results.json にある農地→森林・荒地、建物用地の純変化で
  行う。農地総減少から森林・荒地を引いた残差は「建物・交通・その他等への
  合計」であって、建物用地への値ではないので、そのようには使わない。
- P32 の地域別内訳は地点数（R4 = 21）のみで、R4 限定のバッファ集計はない。
- 距離帯・Moran・OSM の集計は県域全体または津久井窓のものであり、
  R4 限定の値は results.json にないため、R4 の言明には使わない。
- focus_by_region の成分構造は地域全体のものであり、類型別・市町村別の
  成分構造は results.json にない。類型別の建物用地→森林・荒地率は
  絶対量（建物用地基数×率）と併記し、パッチの有無の判定には使わない。
"""

import json
import pathlib

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

rl = d["aggregates"]["region_landscape"]
rl_rows = {tuple(idx): dict(zip(rl["columns"], row))
           for idx, row in zip(rl["index"], rl["data"])}
r4_landscapes = {idx[1]: row for idx, row in rl_rows.items()
                 if idx[0] == "R4_kenou"}

focus = d["transitions"]["focus_by_region"]
fcols = focus["columns"]
focus_r4 = {row[1]: dict(zip(fcols, row))
            for row in focus["data"] if row[0] == "R4_kenou"}

cell_km2 = r4["land_km2"] / r4["n_cells"]
out = {}
out["coverage"] = {
    "area_km2": r4cov["area_km2"],
    "covered_km2": r4cov["covered_km2"],
    "uncovered_km2": r4cov["area_km2"] - r4cov["covered_km2"],
    "coverage": r4cov["coverage"],
    "scope": r4cov["scope"],
}
out["n_cells"] = r4["n_cells"]
out["cell_km2"] = cell_km2
out["land_km2"] = r4["land_km2"]
# 地域行 = 市区町村行の合計 であることの検証（7 行すべて comparable）。
out["muni_sum_cells"] = sum(r["n_cells"] for r in r4m)
out["muni_sum_land_km2"] = sum(r["land_km2"] for r in r4m)
out["muni_rows"] = len(r4m)
out["muni_scopes"] = sorted({r["scope"] for r in r4m})
out["muni_coverages"] = sorted({r["coverage"] for r in r4m})


def share_km2(share):
    return share * r4["land_km2"]


out["composition_2014_km2"] = {
    "building": share_km2(r4["building_2014_share"]),
    "forest": share_km2(r4["forest_2014_share"]),
    "agri": share_km2(r4["agri_2014_share"]),
    "wasteland": share_km2(r4["wasteland_2014_share"]),
    "other": share_km2(r4["other_2014_share"]),
    "transport": share_km2(r4["transport_2014_share"]),
    "golf": share_km2(r4["golf_2014_share"]),
    "water": share_km2(r4["water_2014_share"]),
}
out["changed_km2"] = r4["changed_km2"]
out["changed_share"] = r4["changed_share"]
out["changed_cells"] = r4["changed_km2"] / cell_km2
out["singleton_share"] = r4["singleton_change_share"]
out["singleton_km2"] = r4["singleton_change_share"] * r4["changed_km2"]
out["small_component_share"] = r4["small_component_change_share"]

out["agri"] = {
    "km2_2014": share_km2(r4["agri_2014_share"]),
    "cells_2014": share_km2(r4["agri_2014_share"]) / cell_km2,
    "loss_km2": r4["agri_loss_km2"],
    "loss_cells": r4["agri_loss_km2"] / cell_km2,
    "to_forest_km2": r4["agri_to_forest_km2"],
    "to_forest_cells": r4["agri_to_forest_km2"] / cell_km2,
    "to_wasteland_km2": r4["agri_to_wasteland_km2"],
    "to_wasteland_cells": r4["agri_to_wasteland_km2"] / cell_km2,
    "to_forest_or_wasteland_share_of_loss": (
        r4["agri_to_forest_km2"] + r4["agri_to_wasteland_km2"]
    ) / r4["agri_loss_km2"],
    # 10% 閾値までの余裕。1セル未満なら判定は境界付近である。
    "margin_to_10pct_km2": (
        0.10 * r4["agri_loss_km2"]
        - r4["agri_to_forest_km2"] - r4["agri_to_wasteland_km2"]
    ),
    "margin_to_10pct_cells": (
        0.10 * r4["agri_loss_km2"]
        - r4["agri_to_forest_km2"] - r4["agri_to_wasteland_km2"]
    ) / cell_km2,
    "residual_to_other_destinations_km2": (
        r4["agri_loss_km2"] - r4["agri_to_forest_km2"]
        - r4["agri_to_wasteland_km2"]),
    "net_km2": r4["agri_net_change_km2"],
    "net_rate": r4["agri_net_change_rate"],
    "gross_loss_rate": r4["agri_gross_loss_rate"],
    "to_forest_rate": r4["agri_to_forest_rate"],
    "to_wasteland_rate": r4["agri_to_wasteland_rate"],
}
out["building"] = {
    "km2_2014": share_km2(r4["building_2014_share"]),
    "loss_km2": r4["building_loss_km2"],
    "gain_km2": r4["building_gain_km2"],
    "net_km2": r4["building_net_change_km2"],
    "net_rate": r4["building_net_change_rate"],
    "gross_loss_rate": r4["building_gross_loss_rate"],
    "to_forest_km2": r4["building_to_forest_km2"],
    "to_forest_cells": r4["building_to_forest_km2"] / cell_km2,
    "to_wasteland_km2": r4["building_to_wasteland_km2"],
    "to_forest_or_wasteland_rate": r4["building_to_forest_or_wasteland_rate"],
}
out["forest"] = {
    "km2_2014": share_km2(r4["forest_2014_share"]),
    "net_km2": r4["forest_net_change_km2"],
    "to_forest_km2": r4["to_forest_km2"],
    "forestation_rate": r4["forestation_rate"],
    "nonforest_base_km2": r4["land_km2"] - share_km2(r4["forest_2014_share"]),
}
out["wasteland"] = {
    "km2_2014": share_km2(r4["wasteland_2014_share"]),
    "km2_2021": share_km2(r4["wasteland_2021_share"]),
    "net_km2": r4["wasteland_net_change_km2"],
}
out["municipality"] = {
    r["muni_name"]: {
        "n_cells": r["n_cells"],
        "land_km2": r["land_km2"],
        "coverage": r["coverage"],
        "scope": r["scope"],
        "agri_2014_km2": r["agri_2014_share"] * r["land_km2"]
        if r["agri_2014_share"] is not None else None,
        "agri_net_km2": r["agri_net_change_km2"],
        "agri_loss_km2": r["agri_loss_km2"],
        "agri_to_forest_km2": r["agri_to_forest_km2"],
        "building_2014_km2": r["building_2014_share"] * r["land_km2"]
        if r["building_2014_share"] is not None else None,
        "building_net_km2": r["building_net_change_km2"],
        "building_loss_km2": r["building_loss_km2"],
        "building_gain_km2": r["building_gain_km2"],
        "building_to_forest_km2": r["building_to_forest_km2"],
        "wasteland_net_km2": r["wasteland_net_change_km2"],
        "to_forest_km2": r["to_forest_km2"],
        "changed_share": r["changed_share"],
        "singleton_share": r["singleton_change_share"],
    } for r in r4m
}
by_name = {r["muni_name"]: r for r in r4m}
# 二極構造の定量化：建物用地率・森林率の市町村間レンジと清川村の陸域シェア。
out["building_share_range_pp"] = (
    max(r["building_2014_share"] for r in r4m)
    - min(r["building_2014_share"] for r in r4m)) * 100
out["forest_share_range_pp"] = (
    max(r["forest_2014_share"] for r in r4m)
    - min(r["forest_2014_share"] for r in r4m)) * 100
out["kiyokawa_land_share"] = by_name["清川村"]["land_km2"] / r4["land_km2"]
# 南部4市（大和・座間・海老名・綾瀬）と北部2町村（清川・愛川）の群合計。
for group_name, names in [
        ("south4", ["大和市", "座間市", "海老名市", "綾瀬市"]),
        ("north2", ["清川村", "愛川町"])]:
    g = [r for r in r4m if r["muni_name"] in names]
    land = sum(r["land_km2"] for r in g)
    out[group_name] = {
        "land_km2": land,
        "building_2014_km2": sum(
            r["building_2014_share"] * r["land_km2"] for r in g),
        "forest_2014_km2": sum(
            r["forest_2014_share"] * r["land_km2"] for r in g),
        "agri_2014_km2": sum(
            r["agri_2014_share"] * r["land_km2"] for r in g),
        "agri_net_km2": sum(r["agri_net_change_km2"] for r in g),
        "agri_loss_km2": sum(r["agri_loss_km2"] for r in g),
        "building_net_km2": sum(r["building_net_change_km2"] for r in g),
    }
out["atsugi_share_of_agri_loss"] = (
    by_name["厚木市"]["agri_loss_km2"] / r4["agri_loss_km2"])
out["atsugi_share_of_agri_net_loss"] = (
    by_name["厚木市"]["agri_net_change_km2"] / r4["agri_net_change_km2"])
out["atsugi_share_of_agri_to_forest"] = (
    by_name["厚木市"]["agri_to_forest_km2"] / r4["agri_to_forest_km2"])
out["kiyokawa_share_of_building_to_forest"] = (
    by_name["清川村"]["building_to_forest_km2"] / r4["building_to_forest_km2"])
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
    } for name, row in r4_landscapes.items()
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
    } for name, row in focus_r4.items()
}
out["p32_sites_by_region"] = d["cultural"]["sites_by_region"]
out["p32_usable_sites"] = d["cultural"]["usable_sites"]

# 検証アサーション：レポートの前提が崩れればスクリプトが失敗する。
assert out["muni_sum_cells"] == r4["n_cells"]
assert abs(out["muni_sum_land_km2"] - r4["land_km2"]) < 1e-6
assert out["muni_rows"] == 7  # 欠け・行なしなし
assert out["muni_scopes"] == ["comparable"]
assert out["muni_coverages"] == [1.0]
assert abs(r4cov["coverage"] - 1.0) < 1e-9
print(json.dumps(out, ensure_ascii=False, indent=1))
