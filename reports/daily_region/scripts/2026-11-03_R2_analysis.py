"""R2 (三浦半島) 2週目分析の再計算スクリプト.

`reports/phase1c2_results.json` (Phase 1-C2 v0.2.0) の
coverage / region / municipality / region_landscape / cultural 集計だけから、
2026-11-03_R2_week2.md の数値を再計算する。
新規データ取得・Drive アクセス・セル単位／候補地点の抽出は行わない。

2週目の引き継ぎ (先週の R2 レポート §8 の宿題):
- 類型別の変化量を掘り、「収録範囲内の変化は都市部の変化である」という限定を定量化する。
- P32 の 3 地点について、地点数以外に言えることがあるかを再確認し、
  他地域のバッファ集計との比較可能性 (比較対象に入れるべきでない理由) を明文化する。

棚卸し結果 (分析前に確認):
- region_landscape の R2 行は 4 類型すべてあり、類型別の変化量・純変化が取れる。
  ただし forest_dominant の singleton_change_share は変化 0 のため None であり、
  率としては扱わない (分母 0)。
- 農地→建物用地の内訳は 1 週目と同様に results.json になく、残差は
  「行き先不明の合計」としてのみ使う。
- P32 バッファ集計は 250 m / 500 m とも pooled (site_buffers の index は
  ['p32_sites'] のみ) で、by_class は天然記念物の有無による区分のみ。
  地域別のバッファ集計は存在しないため、R2 限定のバッファ値は作れない。
- 森林の流出量は直接の列がないため、純変化と流入量からの implied 値
  (流出 = 流入 - 純変化) として算出し、implied と明記する。同様に類型別の
  農地増加量は 純変化 + 総減少量からの implied 値である。
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
r2_land = {idx[1]: row for idx, row in rl_rows.items()
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
out["n_cells"] = r2["n_cells"]
out["cell_km2"] = cell_km2
out["land_km2"] = r2["land_km2"]
out["changed_km2"] = r2["changed_km2"]
out["changed_share"] = r2["changed_share"]
out["changed_cells"] = r2["changed_km2"] / cell_km2
out["singleton_share"] = r2["singleton_change_share"]
out["small_component_share"] = r2["small_component_change_share"]


def km2_of(row, share_key):
    return row[share_key] * row["land_km2"]


def landscape_summary(row):
    return {
        "land_km2": row["land_km2"],
        "n_cells": row["n_cells"],
        "land_share": row["land_km2"] / r2["land_km2"],
        "changed_km2": row["changed_km2"],
        "changed_cells": row["changed_km2"] / cell_km2,
        "changed_share": row["changed_share"],
        "changed_share_of_region_changed": row["changed_km2"] / r2["changed_km2"],
        "singleton_share": row["singleton_change_share"],
        "agri_loss_km2": row["agri_loss_km2"],
        "agri_to_forest_km2": row["agri_to_forest_km2"],
        "agri_net_km2": row["agri_net_change_km2"],
        # implied: 増加量 = 純変化 + 総減少量。
        "agri_gain_implied_km2": row["agri_net_change_km2"] + row["agri_loss_km2"],
        "building_loss_km2": row["building_loss_km2"],
        "building_gain_km2": row["building_gain_km2"],
        "building_net_km2": row["building_net_change_km2"],
        "building_to_forest_km2": row["building_to_forest_km2"],
        "forest_net_km2": row["forest_net_change_km2"],
        "to_forest_km2": row["to_forest_km2"],
        # implied: 森林流出量 = 流入量 - 純変化。
        "forest_outflow_implied_km2": row["to_forest_km2"] - row["forest_net_change_km2"],
        "forestation_rate": row["forestation_rate"],
    }


out["landscapes"] = {k: landscape_summary(v) for k, v in r2_land.items()}
urban = out["landscapes"]["urban"]
non_urban_changed = sum(v["changed_km2"] for k, v in out["landscapes"].items()
                        if k != "urban")
out["urban_changed_dominance"] = {
    "urban_changed_km2": urban["changed_km2"],
    "non_urban_changed_km2": non_urban_changed,
    "urban_share_of_changed": urban["changed_km2"] / r2["changed_km2"],
    "urban_building_net_km2": urban["building_net_km2"],
    "region_building_net_km2": r2["building_net_change_km2"],
    "non_urban_building_net_km2": sum(
        v["building_net_km2"] for k, v in out["landscapes"].items()
        if k != "urban"),
}
out["region"] = {
    "agri_loss_km2": r2["agri_loss_km2"],
    "agri_to_forest_km2": r2["agri_to_forest_km2"],
    "agri_to_wasteland_km2": r2["agri_to_wasteland_km2"],
    "agri_residual_km2": (r2["agri_loss_km2"] - r2["agri_to_forest_km2"]
                          - r2["agri_to_wasteland_km2"]),
    "agri_net_km2": r2["agri_net_change_km2"],
    "building_loss_km2": r2["building_loss_km2"],
    "building_gain_km2": r2["building_gain_km2"],
    "building_net_km2": r2["building_net_change_km2"],
    "building_to_forest_km2": r2["building_to_forest_km2"],
    "to_forest_km2": r2["to_forest_km2"],
    "forest_net_km2": r2["forest_net_change_km2"],
    "forest_outflow_implied_km2": r2["to_forest_km2"] - r2["forest_net_change_km2"],
    "forestation_rate": r2["forestation_rate"],
    "non_forest_base_km2": r2["land_km2"] - km2_of(r2, "forest_2014_share"),
}
out["municipalities_in_region_agg"] = [
    {"name": r["muni_name"], "land_km2": r["land_km2"],
     "coverage": r["coverage"], "scope": r["scope"], "n_cells": r["n_cells"]}
    for r in r2m]
# 検証: 市区町村行の合計が地域行と一致すること (1 週目と同手順)。
out["check_muni_land_sum_km2"] = sum(r["land_km2"] for r in r2m)
out["check_muni_cells_sum"] = sum(r["n_cells"] for r in r2m)
# 検証: 類型別の変化量の合計が地域行の変化量と一致すること。
out["check_landscape_changed_sum_km2"] = sum(
    v["changed_km2"] for v in r2_land.values())
# 検証: 類型別の建物用地純変化の合計が地域行と一致すること。
out["check_landscape_building_net_sum_km2"] = sum(
    v["building_net_change_km2"] for v in r2_land.values())
# 検証: 類型別の農地純変化の合計が地域行と一致すること。
out["check_landscape_agri_net_sum_km2"] = sum(
    v["agri_net_change_km2"] for v in r2_land.values())

# P32: 地点数とバッファ集計の構造。
out["p32_sites_by_region"] = d["cultural"]["sites_by_region"]
out["p32_usable_sites"] = d["cultural"]["usable_sites"]
out["p32_r2_share_of_usable"] = (
    d["cultural"]["sites_by_region"]["R2_miura"] / d["cultural"]["usable_sites"])
buffers = d["cultural"]["buffers"]
out["p32_buffer_structure"] = {
    radius: {
        "sites": v["sites"],
        "site_buffers_index": v["site_buffers"]["index"],
        "by_class_index": v["by_class"]["index"],
    }
    for radius, v in buffers.items()
}
# R2 限定のバッファ集計が存在しないことの確認: バッファ構造のいずれの
# index にも地域名は現れない。
out["check_no_region_in_buffer_indexes"] = all(
    "R2_miura" not in idx
    for v in buffers.values()
    for idx in (v["site_buffers"]["index"] + v["by_class"]["index"]))

if __name__ == "__main__":
    print(json.dumps(out, ensure_ascii=False, indent=2))
