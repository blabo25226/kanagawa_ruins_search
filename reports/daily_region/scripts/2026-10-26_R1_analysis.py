"""R1 (横浜・川崎) 1週目分析の再計算スクリプト.

`reports/phase1c2_results.json` (Phase 1-C2 v0.2.0, main 由来) の
region / municipality 集計だけから、2026-10-26_R1_week1.md の数値を再計算する。
新規データ取得・Drive アクセス・セル単位／候補地点の抽出は行わない。

農地→建物用地 3.73 km² のみ、results.json の region 集計に遷移先内訳が
含まれないため、公開済み reports/phase1c2_regional_analysis.md §2 の
面積表の値を定数として参照し、出典を明記して使う。
"""
import json
import pathlib
import statistics

ROOT = pathlib.Path(__file__).resolve().parents[3]
d = json.loads((ROOT / "reports" / "phase1c2_results.json").read_text())

reg = {name: dict(zip(d["aggregates"]["region"]["columns"], row))
       for name, row in zip(d["aggregates"]["region"]["index"],
                            d["aggregates"]["region"]["data"])}
r1 = reg["R1_yokohama_kawasaki"]
out = {}

# --- H1: 農地総減少の行き先 ---
loss = r1["agri_loss_km2"]
agri_to_building = 3.73  # phase1c2_regional_analysis.md §2 面積表 (R1)
out["agri_loss_km2"] = loss
out["agri_to_forest_share_of_loss"] = r1["agri_to_forest_km2"] / loss
out["agri_to_building_share_of_loss"] = agri_to_building / loss
out["agri_to_other_residual_share"] = (
    loss - r1["agri_to_forest_km2"] - r1["agri_to_wasteland_km2"] - agri_to_building) / loss
out["building_net_km2"] = r1["building_net_change_km2"]
out["building_gain_km2"] = r1["building_gain_km2"]
out["building_loss_km2"] = r1["building_loss_km2"]
out["forest_net_km2"] = r1["forest_net_change_km2"]
for k, r in reg.items():
    out[k] = {key: r[key] for key in (
        "label", "coverage", "scope", "agri_net_change_rate",
        "agri_gross_loss_rate", "forestation_rate",
        "building_gross_loss_rate", "building_to_forest_or_wasteland_rate",
        "building_net_change_rate", "changed_share")}

# --- H2: 区別の率と絶対量 ---
mcols = d["aggregates"]["municipality"]["columns"]
mrows = [dict(zip(mcols, r)) for r in d["aggregates"]["municipality"]["data"]]
r1m = [r for r in mrows if r["region"] == "R1_yokohama_kawasaki"]
out["r1_muni_agri_net_total_km2"] = sum(r["agri_net_change_km2"] for r in r1m)
out["r1_muni_most_negative"] = [
    {"name": r["muni_name"], "agri_net_km2": round(r["agri_net_change_km2"], 3),
     "agri_2014_km2": round(r["agri_2014_share"] * r["land_km2"], 2),
     "agri_net_rate": r["agri_net_change_rate"]}
    for r in sorted(r1m, key=lambda x: x["agri_net_change_km2"])[:8]]
pairs = [(r["agri_2014_share"] * r["land_km2"], abs(r["agri_net_change_rate"]))
         for r in r1m if r["agri_net_change_rate"] is not None
         and r["agri_2014_share"] * r["land_km2"] > 0.05]

def ranks(v):
    s = sorted(range(len(v)), key=lambda i: v[i])
    r = [0] * len(v)
    for rank, i in enumerate(s):
        r[i] = rank
    return r

xs, ys = ranks([p[0] for p in pairs]), ranks([p[1] for p in pairs])
mx, my = statistics.mean(xs), statistics.mean(ys)
den = (sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys)) ** 0.5
out["spearman_base_vs_abs_net_rate"] = (
    sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / den if den else None)
out["spearman_n"] = len(pairs)

if __name__ == "__main__":
    print(json.dumps(out, ensure_ascii=False, indent=2))
