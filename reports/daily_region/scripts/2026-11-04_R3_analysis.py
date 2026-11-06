"""R3 (湘南) 2週目分析の再計算スクリプト.

`reports/phase1c2_results.json` (Phase 1-C2 v0.2.0) の
coverage / region / municipality / region_landscape / transitions 集計だけから、
2026-11-04_R3_week2.md の数値を再計算する。
新規データ取得・Drive アクセス・セル単位／候補地点の抽出は行わない。

2週目の主軸は先週の宿題の1件目「沿岸3市と内陸2市の群比較」である。
群は市区町村行の合計で作る（R4 の群合計手順の転用）。
沿岸群 = 平塚市・藤沢市・茅ヶ崎市（相模湾に面する3市）。
内陸群 = 秦野市・伊勢原市（網羅率 100% の内陸2市）。
寒川町は単独で残し、大磯町は 11 セル（農地・建物用地セル 0）のため
群には入れず、0 として扱うことはせず「寄与なし」として明記する。
二宮町は municipality 集計行そのものがない。

棚卸し結果（分析前に確認）:
- region 集計に R3 行はあり、coverage 表に R3 行もある
  （area 371.95 km2、covered 310.34 km2、coverage 83.4%、
  scope reference_partial）。地域行の陸域 310.17 km2 との差 0.16 km2 は
  1週目と同じ定義差として注記し、本レポートのセル換算には地域行を使う。
- 市区町村行の合計は地域行と一致する（下のアサーション）。
  ただし合計の一致は「欠けがない」ことの証明にはならない
  （大磯町 11 セル、二宮町は行なし）。
- 農地→建物用地の R3 値は results.json の region 集計に列がない。
  1週目と同じく公開レポート §2 の面積表（湘南 4.62 km2）からの
  補助引用に留め、仮説の判定には使わない。
- 農地の総増加（gross gain）に直接の列はないため、
  総増加 = 純変化 + 総減少 として導出する（恒等式であり推定ではない）。
  同様に森林の総減少 = 森林への総流入 - 森林純変化 として導出する。
  導出値は「導出」と明記し、一次集計の値と区別する。
- 荒地の行き先（荒地→各用途）は region / municipality / region_landscape
  のいずれの集計にも列がないため、「行き先不明」として扱う。
  市区町村×類型のクロス集計もないため、秦野の荒地減少を
  類型別に位置づけることはできない。
- P32 の地域別内訳は地点数（R3 = 30）のみで、R3 限定のバッファ集計はない。
- 距離帯・Moran・OSM の集計は県域全体または津久井窓のものであり、
  R3 限定の値は results.json にないため、R3 の言明には使わない。
"""

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
d = json.loads((ROOT / "reports" / "phase1c2_results.json").read_text())

cov = d["coverage"]["by_region"]
cov_rows = {name: dict(zip(cov["columns"], row))
            for name, row in zip(cov["index"], cov["data"])}
r3cov = cov_rows["R3_shonan"]

reg = {name: dict(zip(d["aggregates"]["region"]["columns"], row))
       for name, row in zip(d["aggregates"]["region"]["index"],
                            d["aggregates"]["region"]["data"])}
r3 = reg["R3_shonan"]

mcols = d["aggregates"]["municipality"]["columns"]
mrows = [dict(zip(mcols, r)) for r in d["aggregates"]["municipality"]["data"]]
r3m = [r for r in mrows if r["region"] == "R3_shonan"]
by_name = {r["muni_name"]: r for r in r3m}

rl = d["aggregates"]["region_landscape"]
rl_rows = {tuple(idx): dict(zip(rl["columns"], row))
           for idx, row in zip(rl["index"], rl["data"])}
r3_landscapes = {idx[1]: row for idx, row in rl_rows.items()
                 if idx[0] == "R3_shonan"}

focus = d["transitions"]["focus_by_region"]
fcols = focus["columns"]
focus_r3 = {row[1]: dict(zip(fcols, row))
            for row in focus["data"] if row[0] == "R3_shonan"}

cell_km2 = r3["land_km2"] / r3["n_cells"]


def share_km2(share, land):
    return share * land


def muni_summary(r):
    land = r["land_km2"]
    agri14 = (r["agri_2014_share"] * land
              if r["agri_2014_share"] is not None else None)
    bld14 = (r["building_2014_share"] * land
             if r["building_2014_share"] is not None else None)
    return {
        "n_cells": r["n_cells"],
        "land_km2": land,
        "coverage": r["coverage"],
        "scope": r["scope"],
        "agri_2014_km2": agri14,
        "agri_net_km2": r["agri_net_change_km2"],
        "agri_loss_km2": r["agri_loss_km2"],
        # 導出（恒等式）: 総増加 = 純変化 + 総減少
        "agri_gain_derived_km2": r["agri_net_change_km2"] + r["agri_loss_km2"],
        "agri_to_forest_km2": r["agri_to_forest_km2"],
        "agri_to_wasteland_km2": r["agri_to_wasteland_km2"],
        "building_2014_km2": bld14,
        "building_net_km2": r["building_net_change_km2"],
        "building_loss_km2": r["building_loss_km2"],
        "building_gain_km2": r["building_gain_km2"],
        "forest_net_km2": r["forest_net_change_km2"],
        "to_forest_km2": r["to_forest_km2"],
        "wasteland_2014_km2": r["wasteland_2014_share"] * land,
        "wasteland_net_km2": r["wasteland_net_change_km2"],
        "changed_km2": r["changed_km2"],
    }


def group_summary(names):
    g = [by_name[n] for n in names]
    s = {k: sum(muni_summary(r)[k] for r in g)
         for k in ["n_cells", "land_km2", "agri_2014_km2", "agri_net_km2",
                   "agri_loss_km2", "agri_gain_derived_km2",
                   "agri_to_forest_km2", "agri_to_wasteland_km2",
                   "building_2014_km2", "building_net_km2",
                   "building_loss_km2", "building_gain_km2",
                   "forest_net_km2", "to_forest_km2",
                   "wasteland_2014_km2", "wasteland_net_km2", "changed_km2"]}
    s["agri_net_rate"] = s["agri_net_km2"] / s["agri_2014_km2"]
    s["agri_gross_loss_rate"] = s["agri_loss_km2"] / s["agri_2014_km2"]
    s["agri_to_forest_wasteland_share_of_loss"] = (
        s["agri_to_forest_km2"] + s["agri_to_wasteland_km2"]
    ) / s["agri_loss_km2"] if s["agri_loss_km2"] else None
    s["building_net_rate"] = s["building_net_km2"] / s["building_2014_km2"]
    s["land_share_of_region"] = s["land_km2"] / r3["land_km2"]
    s["agri_base_share"] = s["agri_2014_km2"] / (
        r3["agri_2014_share"] * r3["land_km2"])
    s["agri_net_loss_share"] = s["agri_net_km2"] / r3["agri_net_change_km2"]
    s["building_net_share"] = (s["building_net_km2"]
                               / r3["building_net_change_km2"])
    s["wasteland_net_share"] = (s["wasteland_net_km2"]
                                / r3["wasteland_net_change_km2"])
    return s


out = {}
out["coverage"] = {
    "area_km2": r3cov["area_km2"],
    "covered_km2": r3cov["covered_km2"],
    "uncovered_km2": r3cov["area_km2"] - r3cov["covered_km2"],
    "coverage": r3cov["coverage"],
    "scope": r3cov["scope"],
}
out["n_cells"] = r3["n_cells"]
out["cell_km2"] = cell_km2
out["land_km2"] = r3["land_km2"]
out["muni_sum_cells"] = sum(r["n_cells"] for r in r3m)
out["muni_sum_land_km2"] = sum(r["land_km2"] for r in r3m)
out["muni_rows"] = len(r3m)
out["municipality"] = {r["muni_name"]: muni_summary(r) for r in r3m}
out["groups"] = {
    "coastal3": group_summary(["平塚市", "藤沢市", "茅ヶ崎市"]),
    "inland2": group_summary(["秦野市", "伊勢原市"]),
    "samukawa": group_summary(["寒川町"]),
}
# 沿岸群の農地純変化率で内陸群の農地基数を評価する算術的対照
# （因果の主張ではなく、群間差の大きさを示すための恒等計算）。
out["counterfactual_inland_agri_net_at_coastal_rate_km2"] = (
    out["groups"]["inland2"]["agri_2014_km2"]
    * out["groups"]["coastal3"]["agri_net_rate"])
out["counterfactual_excess_km2"] = (
    out["groups"]["inland2"]["agri_net_km2"]
    - out["counterfactual_inland_agri_net_at_coastal_rate_km2"])
out["region"] = {
    "agri_2014_km2": r3["agri_2014_share"] * r3["land_km2"],
    "agri_net_km2": r3["agri_net_change_km2"],
    "agri_net_rate": r3["agri_net_change_rate"],
    "agri_loss_km2": r3["agri_loss_km2"],
    "agri_gain_derived_km2": r3["agri_net_change_km2"] + r3["agri_loss_km2"],
    "agri_to_forest_km2": r3["agri_to_forest_km2"],
    "agri_to_wasteland_km2": r3["agri_to_wasteland_km2"],
    "agri_to_forest_wasteland_share_of_loss": (
        r3["agri_to_forest_km2"] + r3["agri_to_wasteland_km2"]
    ) / r3["agri_loss_km2"],
    "building_2014_km2": r3["building_2014_share"] * r3["land_km2"],
    "building_net_km2": r3["building_net_change_km2"],
    "building_loss_km2": r3["building_loss_km2"],
    "building_gain_km2": r3["building_gain_km2"],
    "forest_2014_km2": r3["forest_2014_share"] * r3["land_km2"],
    "forest_net_km2": r3["forest_net_change_km2"],
    "to_forest_km2": r3["to_forest_km2"],
    "forestation_rate": r3["forestation_rate"],
    # 導出（恒等式）: 森林の総減少 = 森林への総流入 - 森林純変化
    "forest_loss_derived_km2": r3["to_forest_km2"] - r3["forest_net_change_km2"],
    "wasteland_2014_km2": r3["wasteland_2014_share"] * r3["land_km2"],
    "wasteland_net_km2": r3["wasteland_net_change_km2"],
    "changed_km2": r3["changed_km2"],
}
out["landscape"] = {
    name: {
        "land_km2": row["land_km2"],
        "agri_2014_km2": row["agri_2014_share"] * row["land_km2"],
        "agri_net_km2": row["agri_net_change_km2"],
        "agri_loss_km2": row["agri_loss_km2"],
        "agri_gain_derived_km2": (row["agri_net_change_km2"]
                                  + row["agri_loss_km2"]),
        "to_forest_km2": row["to_forest_km2"],
        "forest_net_km2": row["forest_net_change_km2"],
        "building_net_km2": row["building_net_change_km2"],
        "wasteland_2014_km2": row["wasteland_2014_share"] * row["land_km2"],
        "wasteland_net_km2": row["wasteland_net_change_km2"],
    } for name, row in r3_landscapes.items()
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
        "reverse_area_km2": row["reverse_area_km2"],
    } for name, row in focus_r3.items()
}
out["p32_sites_by_region"] = d["cultural"]["sites_by_region"]
out["p32_usable_sites"] = d["cultural"]["usable_sites"]

# 検証アサーション：レポートの前提が崩れればスクリプトが失敗する。
assert out["muni_sum_cells"] == r3["n_cells"]
assert abs(out["muni_sum_land_km2"] - r3["land_km2"]) < 1e-6
assert out["muni_rows"] == 7  # 二宮町は行なし
for field in ["agri_net_change_km2", "agri_loss_km2", "building_net_change_km2",
              "building_loss_km2", "building_gain_km2", "forest_net_change_km2",
              "to_forest_km2", "wasteland_net_change_km2", "changed_km2"]:
    assert abs(sum(r[field] for r in r3m) - r3[field]) < 1e-3, field
# 群合計 + 寒川町 + 大磯町（0）が地域行と一致すること。
region_by_key = {
    "agri_net_km2": r3["agri_net_change_km2"],
    "building_net_km2": r3["building_net_change_km2"],
    "wasteland_net_km2": r3["wasteland_net_change_km2"],
}
for key, region_value in region_by_key.items():
    total = (out["groups"]["coastal3"][key] + out["groups"]["inland2"][key]
             + out["groups"]["samukawa"][key]
             + out["municipality"]["大磯町"][key])
    assert abs(total - region_value) < 1e-3, key
print(json.dumps(out, ensure_ascii=False, indent=1))
