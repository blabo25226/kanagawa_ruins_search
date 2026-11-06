"""R3（湘南）2週目レビュー追補の再計算.

2026-11-04 の R3 週2本文は上書きしない。本文が暦上の前日（R2 週2）の
反省を読めなかったため残った問い「内陸偏重の変化はどの類型の変化か」を、
`reports/phase1c2_results.json` の既存集計だけで検証する。

閾値は結果を見る前に、系列で既に使われている基準を定数として固定した。
- DOMINANCE_SHARE = 0.50
  R2 週2 H1(a) と同じ。「単一類型が変化を支配する」は変化面積シェアが
  50% を超える場合だけとする。
- MIN_RATE_BASE_KM2 = 0.50
  系列ルール。農地基数 0.5 km² 未満の類型は、純変化率の順位付けに使わない。

新規 GIS 取得、Drive アクセス、台帳追記、地点抽出は行わない。
"""

import json
import pathlib

DOMINANCE_SHARE = 0.50
MIN_RATE_BASE_KM2 = 0.50

ROOT = pathlib.Path(__file__).resolve().parents[3]
d = json.loads((ROOT / "reports" / "phase1c2_results.json").read_text())

# H-A: 市区町村×類型のクロス集計が無いことを、表の名前で確認する。
# ある表は region_landscape（地域×類型）と municipality（市区町村）が別々である。
aggregate_names = sorted(d["aggregates"].keys())
transition_names = sorted(d["transitions"].keys())
cross_names = [
    name for name in aggregate_names + transition_names
    if "muni" in name and "land" in name
]
h_a_cross_tab_absent = len(cross_names) == 0

reg = {name: dict(zip(d["aggregates"]["region"]["columns"], row))
       for name, row in zip(d["aggregates"]["region"]["index"],
                            d["aggregates"]["region"]["data"])}
r3 = reg["R3_shonan"]

rl = d["aggregates"]["region_landscape"]
landscapes = []
for idx, row in zip(rl["index"], rl["data"]):
    if idx[0] != "R3_shonan":
        continue
    rec = dict(zip(rl["columns"], row))
    rec["landscape"] = idx[1]
    landscapes.append(rec)

changed_total = sum(r["changed_km2"] for r in landscapes)
agri_net_total = sum(r["agri_net_change_km2"] for r in landscapes)
agri_base_total = sum(r["agri_2014_share"] * r["land_km2"] for r in landscapes)

rows = []
for r in landscapes:
    base = r["agri_2014_share"] * r["land_km2"]
    net = r["agri_net_change_km2"]
    rows.append({
        "landscape": r["landscape"],
        "land_km2": r["land_km2"],
        "changed_km2": r["changed_km2"],
        "changed_share": r["changed_km2"] / changed_total,
        "agri_2014_km2": base,
        "agri_base_share": base / agri_base_total,
        "agri_net_km2": net,
        "agri_loss_share": net / agri_net_total,  # 純減なので正のシェアは net/total
        "agri_net_rate": r["agri_net_change_rate"],
        "rate_rank_eligible": base >= MIN_RATE_BASE_KM2,
    })

# 地域行と類型行の変化面積・農地純変化が一致すること（切り口の取り違え防止）。
assert abs(changed_total - r3["changed_km2"]) < 1e-6
assert abs(agri_net_total - r3["agri_net_change_km2"]) < 1e-6
assert abs(agri_base_total - r3["agri_2014_share"] * r3["land_km2"]) < 1e-6

# H-B: 変化面積の最大類型が DOMINANCE_SHARE を超えるか。
dominant = max(rows, key=lambda r: r["changed_share"])
h_b_single_type_dominates = dominant["changed_share"] > DOMINANCE_SHARE

# H-C: 絶対量シェア1位と、基数条件を満たす率の1位（より負）が別類型か。
abs_leader = min(rows, key=lambda r: r["agri_net_km2"])  # 純減が最大（最も負）
rate_candidates = [r for r in rows if r["rate_rank_eligible"]]
rate_leader = min(rate_candidates, key=lambda r: r["agri_net_rate"])
h_c_leaders_differ = abs_leader["landscape"] != rate_leader["landscape"]

out = {
    "thresholds": {
        "dominance_share": DOMINANCE_SHARE,
        "min_rate_base_km2": MIN_RATE_BASE_KM2,
    },
    "aggregate_names": aggregate_names,
    "h_a_cross_tab_names": cross_names,
    "h_a_cross_tab_absent": h_a_cross_tab_absent,
    "h_a_verdict": "保留（検証不能）" if h_a_cross_tab_absent else "クロス集計あり",
    "changed_total_km2": changed_total,
    "landscapes": rows,
    "h_b_dominant_landscape": dominant["landscape"],
    "h_b_dominant_share": dominant["changed_share"],
    "h_b_single_type_dominates": h_b_single_type_dominates,
    "h_b_verdict": "支持" if h_b_single_type_dominates else "棄却",
    "h_c_absolute_leader": abs_leader["landscape"],
    "h_c_absolute_net_km2": abs_leader["agri_net_km2"],
    "h_c_absolute_loss_share": abs_leader["agri_loss_share"],
    "h_c_absolute_base_share": abs_leader["agri_base_share"],
    "h_c_rate_leader": rate_leader["landscape"],
    "h_c_rate": rate_leader["agri_net_rate"],
    "h_c_rate_base_km2": rate_leader["agri_2014_km2"],
    "h_c_leaders_differ": h_c_leaders_differ,
    "h_c_verdict": "支持" if h_c_leaders_differ else "棄却",
}

if __name__ == "__main__":
    print(json.dumps(out, ensure_ascii=False, indent=2))
