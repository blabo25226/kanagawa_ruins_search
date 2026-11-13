"""R2 (三浦半島) 1週目分析の再計算スクリプト.

`reports/phase1c2_results.json` (Phase 1-C2 v0.2.0) の
coverage / region / municipality / region_landscape 集計だけから、
2026-10-27_R2_week1.md の数値を再計算する。
新規データ取得・Drive アクセス・セル単位／候補地点の抽出は行わない。

棚卸し結果（分析前に確認）:
- region 集計に R2 行はあるが、公開レポート §2 の地域別表には R2 列がない
  （excluded のため比較から除外されている）。
- municipality 集計の R2 所属行は鎌倉市のみ。横須賀・逗子・三浦・葉山は
  coverage.not_covered にあり、municipality 集計行そのものがない。
- 農地→建物用地の内訳は results.json の region 集計に列がなく、公開表にも
  R2 列がないため、R2 については取得できない。農地総減少から森林・荒地を
  引いた残差（1セル分）は「建物・交通・その他等への合計」であって、
  建物用地への値ではないので、そのようには使わない。
- P32 の地域別内訳は地点数（R2 = 3）のみで、R2 限定のバッファ集計はない。
"""

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
d = json.loads((ROOT / "reports" / "phase1c2_results.json").read_text())

cov = d["coverage"]["by_region"]
cov_rows = {name: dict(zip(cov["columns"], row))
            for name, row in zip(cov["index"], cov["data"])}
r2cov = cov_rows["R2_miura"]

reg = {name: dict(zip(d["aggregates"]["region"]["columns"], row))
       for name, row in zip(d["aggregates"]["region"]["index"],
                            d["aggregates"]["region"]["data"])}
r2 = reg["R2_miura"]

mcols = d["aggregates"]["municipality"]["columns"]
mrows = [dict(zip(mcols, r)) for r in d["aggregates"]["municipality"]["data"]]
r2m = [r for r in mrows if r["region"] == "R2_miura"]

rl = d["aggregates"]["region_landscape"]
rl_rows = {tuple(idx): dict(zip(rl["columns"], row))
           for idx, row in zip(rl["index"], rl["data"])}
r2_landscapes = {idx[1]: row for idx, row in rl_rows.items()
                 if idx[0] == "R2_miura"}

cell_km2 = r2["land_km2"] / r2["n_cells"]
out = {}
out["coverage"] = {
    "area_km2": r2cov["area_km2"],
    "covered_km2": r2cov["covered_km2"],
    "uncovered_km2": r2cov["area_km2"] - r2cov["covered_km2"],
    "coverage": r2cov["coverage"],
    "scope": r2cov["scope"],
}
out["not_covered"] = d["coverage"]["not_covered"]
out["partial_kamakura_coverage"] = next(
    row[1] for row in d["coverage"]["partial"]["data"]
    if row[0] == "鎌倉市")
out["kamakura_total_implied_km2"] = r2["land_km2"] / out["partial_kamakura_coverage"]
out["n_cells"] = r2["n_cells"]
out["cell_km2"] = cell_km2
out["land_km2"] = r2["land_km2"]

def share_km2(share):
    return share * r2["land_km2"]

out["composition_2014_km2"] = {
    "building": share_km2(r2["building_2014_share"]),
    "forest": share_km2(r2["forest_2014_share"]),
    "agri": share_km2(r2["agri_2014_share"]),
    "other": share_km2(r2["other_2014_share"]),
    "transport": share_km2(r2["transport_2014_share"]),
    "golf": share_km2(r2["golf_2014_share"]),
}
out["composition_2014_share"] = {
    "building": r2["building_2014_share"],
    "forest": r2["forest_2014_share"],
    "agri": r2["agri_2014_share"],
}
out["changed_km2"] = r2["changed_km2"]
out["changed_share"] = r2["changed_share"]
out["changed_cells"] = r2["changed_km2"] / cell_km2
out["singleton_share"] = r2["singleton_change_share"]
out["singleton_km2"] = r2["singleton_change_share"] * r2["changed_km2"]
out["small_component_share"] = r2["small_component_change_share"]

out["agri"] = {
    "km2_2014": share_km2(r2["agri_2014_share"]),
    "cells_2014": share_km2(r2["agri_2014_share"]) / cell_km2,
    "loss_km2": r2["agri_loss_km2"],
    "loss_cells": r2["agri_loss_km2"] / cell_km2,
    "to_forest_km2": r2["agri_to_forest_km2"],
    "to_forest_cells": r2["agri_to_forest_km2"] / cell_km2,
    "to_wasteland_km2": r2["agri_to_wasteland_km2"],
    # 残差は行き先不明の合計（建物用地への値ではない）。
    "residual_to_other_destinations_km2": (
        r2["agri_loss_km2"] - r2["agri_to_forest_km2"]
        - r2["agri_to_wasteland_km2"]),
    "residual_cells": (
        r2["agri_loss_km2"] - r2["agri_to_forest_km2"]
        - r2["agri_to_wasteland_km2"]) / cell_km2,
    "net_km2": r2["agri_net_change_km2"],
    "net_rate": r2["agri_net_change_rate"],
    "gross_loss_rate": r2["agri_gross_loss_rate"],
    "to_forest_rate": r2["agri_to_forest_rate"],
}
out["building"] = {
    "km2_2014": share_km2(r2["building_2014_share"]),
    "cells_2014": share_km2(r2["building_2014_share"]) / cell_km2,
    "loss_km2": r2["building_loss_km2"],
    "loss_cells": r2["building_loss_km2"] / cell_km2,
    "gain_km2": r2["building_gain_km2"],
    "gain_cells": r2["building_gain_km2"] / cell_km2,
    "net_km2": r2["building_net_change_km2"],
    "net_cells": r2["building_net_change_km2"] / cell_km2,
    "to_forest_km2": r2["building_to_forest_km2"],
    "to_forest_cells": r2["building_to_forest_km2"] / cell_km2,
    "gross_loss_rate": r2["building_gross_loss_rate"],
    "to_forest_or_wasteland_rate": r2["building_to_forest_or_wasteland_rate"],
    "net_rate": r2["building_net_change_rate"],
}
out["forest"] = {
    "km2_2014": share_km2(r2["forest_2014_share"]),
    "net_km2": r2["forest_net_change_km2"],
    "net_cells": r2["forest_net_change_km2"] / cell_km2,
    "to_forest_km2": r2["to_forest_km2"],
    "to_forest_cells": r2["to_forest_km2"] / cell_km2,
    "forestation_rate": r2["forestation_rate"],
}
out["wasteland"] = {
    "km2_2014": share_km2(r2["wasteland_2014_share"]),
    "net_km2": r2["wasteland_net_change_km2"],
}
out["municipalities_in_region_agg"] = [
    {"name": r["muni_name"], "land_km2": r["land_km2"],
     "coverage": r["coverage"], "scope": r["scope"], "n_cells": r["n_cells"]}
    for r in r2m]
out["all_region_coverage"] = {
    k: {"coverage": v["coverage"], "scope": v["scope"],
        "covered_km2": v["covered_km2"], "area_km2": v["area_km2"]}
    for k, v in cov_rows.items()}
out["landscapes"] = {
    k: {"land_km2": v["land_km2"], "n_cells": v["n_cells"],
        "changed_km2": v["changed_km2"],
        "agri_2014_km2": v["agri_2014_share"] * v["land_km2"],
        "building_2014_km2": v["building_2014_share"] * v["land_km2"]}
    for k, v in r2_landscapes.items()}
out["p32_sites_by_region"] = d["cultural"]["sites_by_region"]
out["p32_usable_sites"] = d["cultural"]["usable_sites"]
# 検証: 市区町村行の合計が地域行と一致すること。
out["check_muni_land_sum_km2"] = sum(r["land_km2"] for r in r2m)
out["check_muni_cells_sum"] = sum(r["n_cells"] for r in r2m)
# 検証: 農地→森林 + 建物→森林 = 全体 to_forest。
out["check_to_forest_sum_km2"] = (
    r2["agri_to_forest_km2"] + r2["building_to_forest_km2"])

if __name__ == "__main__":
    print(json.dumps(out, ensure_ascii=False, indent=2))
