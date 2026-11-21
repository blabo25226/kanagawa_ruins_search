"""R7 (県西) 1週目分析の再計算スクリプト.

`reports/phase1c2_results.json` (Phase 1-C2 v0.2.0) の
coverage / region / municipality / region_landscape / transitions 集計だけから、
2026-11-01_R7_week1.md の数値を再計算する。
新規データ取得・Drive アクセス・セル単位／候補地点の抽出は行わない。

棚卸し結果（分析前に確認）:
- region 集計に R7 行があり、公開レポート §1 の地域表にも県西列がある
  （46.7%・reference_partial）。R7 の収録陸域は 296.75 km²、28,272 セル。
- coverage.by_region に R7 行があり、area 634.82 km²・covered 296.67 km²・
  coverage 0.4673・scope reference_partial である。公開レポート §1 の
  地域表（県西 296.8 km²・46.7%・参考値）と一致する。
- municipality 集計に R7 の 10 市町村のうち 6 行だけがある。
  欠けている 4 市町（小田原市・箱根町・真鶴町・湯河原町）は
  coverage.not_covered にあり、収録外である。市町村行の陸域合計は
  地域行の陸域と一致する（群合計の検証）。
- R7 の市町村行のうち南足柄市は scope excluded（網羅率 15.1%）だが、
  その行の陸域は収録部分（11.68 km²）であり、地域行の合計に含まれる。
  南足柄市行を「市全体の値」として読むことはしない。
- 農地→建物用地の R7 値は results.json の region 集計に列がなく、
  公開レポート §2 の面積表（県西 0.49 km²）にのみあるため、本レポートでは
  その出典を明示した上で補助的にのみ引用し、仮説の判定には使わない。
  仮説の判定は results.json にある農地→森林・荒地、建物用地の純変化、
  森林化率、建物用地→森林・荒地率、農地の純変化で行う。農地総減少から
  森林・荒地を引いた残差は「建物・交通・その他等への合計」であって、
  建物用地への値ではないので、そのようには使わない。
- P32 の地域別内訳は地点数（R7 = 10、公開レポート §5）のみで、
  R7 限定のバッファ集計は results.json にない。
- 距離帯・Moran の集計は県域全体のものであり、R7 限定の値は
  results.json にないため、R7 の言明には使わない。OSM の津久井窓は
  R7 とは範囲が異なるため、R7 の言明には使わない。
- focus_by_region の成分構造は地域全体のものであり、類型別・市町村別の
  成分構造は results.json にない。類型別の建物用地→森林・荒地率は
  絶対量（建物用地基数×率）と併記し、パッチの有無の判定には使わない。
  類型はいずれも陸域 0.5 km² を超えるため、類型間の比較は行える。
  ただし都市的メッシュ内の森林基数など、小さい基数の率は絶対量と併記する。
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
r7 = reg["R7_kensei"]

R7_CODES = ["14206", "14217", "14361", "14362", "14363", "14364",
            "14366", "14382", "14383", "14384"]
mcols = d["aggregates"]["municipality"]["columns"]
mrows = [dict(zip(mcols, r)) for r in d["aggregates"]["municipality"]["data"]]
r7_muni = [r for r in mrows if r["muni_code"] in R7_CODES]
r7_muni_codes = sorted(r["muni_code"] for r in r7_muni)

rl = d["aggregates"]["region_landscape"]
rl_rows = {tuple(idx): dict(zip(rl["columns"], row))
           for idx, row in zip(rl["index"], rl["data"])}
r7_landscapes = {idx[1]: row for idx, row in rl_rows.items()
                 if idx[0] == "R7_kensei"}

focus = d["transitions"]["focus_by_region"]
fcols = focus["columns"]
focus_r7 = {row[1]: dict(zip(fcols, row))
            for row in focus["data"] if row[0] == "R7_kensei"}

comp = d["transitions"]["component_class_share_by_region"]
comp_r7 = dict(zip(comp["columns"],
                   comp["data"][comp["index"].index("R7_kensei")]))

cell_km2 = r7["land_km2"] / r7["n_cells"]
out = {}
out["coverage_by_region_R7"] = cov_rows["R7_kensei"]
out["coverage_not_covered"] = d["coverage"]["not_covered"]
out["n_cells"] = r7["n_cells"]
out["cell_km2"] = cell_km2
out["land_km2"] = r7["land_km2"]
out["region_coverage"] = r7["coverage"]
out["region_scope"] = r7["scope"]
# 市町村行の群合計＝地域行の検証（R4 の手順を R7 に転用）。
out["muni_rows_present"] = len(r7_muni)
out["muni_rows_codes"] = r7_muni_codes
out["muni_rows_missing_codes"] = sorted(set(R7_CODES) - set(r7_muni_codes))
out["muni_sum_cells"] = sum(r["n_cells"] for r in r7_muni)
out["muni_sum_land_km2"] = sum(r["land_km2"] for r in r7_muni)


def share_km2(share):
    return share * r7["land_km2"]


out["composition_2014_km2"] = {
    "building": share_km2(r7["building_2014_share"]),
    "forest": share_km2(r7["forest_2014_share"]),
    "agri": share_km2(r7["agri_2014_share"]),
    "wasteland": share_km2(r7["wasteland_2014_share"]),
    "other": share_km2(r7["other_2014_share"]),
    "transport": share_km2(r7["transport_2014_share"]),
    "golf": share_km2(r7["golf_2014_share"]),
    "water": share_km2(r7["water_2014_share"]),
    "beach": share_km2(r7["beach_2014_share"]),
}
out["composition_2014_share"] = {
    "building": r7["building_2014_share"],
    "forest": r7["forest_2014_share"],
    "agri": r7["agri_2014_share"],
    "wasteland": r7["wasteland_2014_share"],
    "other": r7["other_2014_share"],
    "transport": r7["transport_2014_share"],
    "golf": r7["golf_2014_share"],
    "water": r7["water_2014_share"],
}
# 山北町＋松田町の収録陸域シェア（H1 の偏り条件）。
ym = {r["muni_name"]: r for r in r7_muni}
out["yamakita_land_km2"] = ym["山北町"]["land_km2"]
out["matsuda_land_km2"] = ym["松田町"]["land_km2"]
out["yamakita_plus_matsuda_share"] = (
    ym["山北町"]["land_km2"] + ym["松田町"]["land_km2"]) / r7["land_km2"]
out["muni_table"] = [{
    "code": r["muni_code"], "name": r["muni_name"],
    "n_cells": r["n_cells"], "land_km2": r["land_km2"],
    "coverage": r["coverage"], "scope": r["scope"],
    "building_2014_share": r["building_2014_share"],
    "forest_2014_share": r["forest_2014_share"],
    "agri_2014_share": r["agri_2014_share"],
} for r in r7_muni]

# 総流入の率と純変化を分ける判定表（R6 の反省 3）。
out["verdict_table"] = {
    "forest": {
        "gross_inflow_km2": r7["to_forest_km2"],
        "forestation_rate": r7["forestation_rate"],
        "nonforest_base_km2": r7["land_km2"] * (1 - r7["forest_2014_share"]),
        "net_change_km2": r7["forest_net_change_km2"],
        "implied_gross_outflow_km2":
            r7["to_forest_km2"] - r7["forest_net_change_km2"],
    },
    "building": {
        "gross_loss_km2": r7["building_loss_km2"],
        "gross_gain_km2": r7["building_gain_km2"],
        "to_forest_or_wasteland_km2":
            r7["building_to_forest_km2"] + r7["building_to_wasteland_km2"],
        "to_forest_or_wasteland_rate":
            r7["building_to_forest_or_wasteland_rate"],
        "net_change_km2": r7["building_net_change_km2"],
        "net_change_rate": r7["building_net_change_rate"],
    },
    "agri": {
        "gross_loss_km2": r7["agri_loss_km2"],
        "gross_loss_rate": r7["agri_gross_loss_rate"],
        "to_forest_km2": r7["agri_to_forest_km2"],
        "to_wasteland_km2": r7["agri_to_wasteland_km2"],
        "to_forest_or_wasteland_share_of_loss":
            (r7["agri_to_forest_km2"] + r7["agri_to_wasteland_km2"])
            / r7["agri_loss_km2"],
        "net_change_km2": r7["agri_net_change_km2"],
        "net_change_rate": r7["agri_net_change_rate"],
        "implied_gross_gain_km2":
            r7["agri_loss_km2"] + r7["agri_net_change_km2"],
    },
}
out["changed_km2"] = r7["changed_km2"]
out["changed_share"] = r7["changed_share"]
out["singleton_change_share"] = r7["singleton_change_share"]
out["small_component_change_share"] = r7["small_component_change_share"]
out["component_class_share"] = comp_r7

# 類型別。率の順位と絶対量の順位を両方出す（R6 の反省 4）。
out["landscapes"] = {}
for name, row in r7_landscapes.items():
    land = row["land_km2"]
    out["landscapes"][name] = {
        "land_km2": land,
        "agri_2014_km2": row["agri_2014_share"] * land,
        "agri_net_change_km2": row["agri_net_change_km2"],
        "agri_loss_km2": row["agri_loss_km2"],
        "agri_to_forest_km2": row["agri_to_forest_km2"],
        "forestation_rate": row["forestation_rate"],
        "nonforest_base_km2": land * (1 - row["forest_2014_share"]),
        "to_forest_km2": row["to_forest_km2"],
        "building_2014_km2": row["building_2014_share"] * land,
        "building_to_forest_or_wasteland_km2":
            row["building_to_forest_km2"] + row["building_to_wasteland_km2"],
        "building_to_forest_or_wasteland_rate":
            row["building_to_forest_or_wasteland_rate"],
        "building_net_change_km2": row["building_net_change_km2"],
        "changed_km2": row["changed_km2"],
    }

out["focus"] = {k: {
    "area_km2": v["area_km2"], "cells": v["cells"],
    "size_1_share": v["size_1_share"], "size_2_share": v["size_2_share"],
    "size_3_4_share": v["size_3-4_share"],
    "size_ge5_share": v["size_>=5_share"],
    "boundary_share": v["boundary_share"],
    "max_component_cells": v["max_component_cells"],
    "reverse_area_km2": v["reverse_area_km2"],
} for k, v in focus_r7.items()}

# 他地域との比較（農地純変化の符号・森林化率・建物用地純変化）。
out["region_comparison"] = {}
for name, row in reg.items():
    out["region_comparison"][name] = {
        "land_km2": row["land_km2"], "coverage": row["coverage"],
        "scope": row["scope"],
        "agri_net_change_km2": row["agri_net_change_km2"],
        "agri_loss_km2": row["agri_loss_km2"],
        "agri_to_forest_or_wasteland_share_of_loss":
            (row["agri_to_forest_km2"] + row["agri_to_wasteland_km2"])
            / row["agri_loss_km2"] if row["agri_loss_km2"] else None,
        "forest_net_change_km2": row["forest_net_change_km2"],
        "forestation_rate": row["forestation_rate"],
        "building_net_change_km2": row["building_net_change_km2"],
        "building_to_forest_or_wasteland_rate":
            row["building_to_forest_or_wasteland_rate"],
        "changed_share": row["changed_share"],
        "singleton_change_share": row["singleton_change_share"],
    }

print(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True))
