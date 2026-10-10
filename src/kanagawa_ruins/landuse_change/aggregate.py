"""Unit-level composition and change indicators (area based).

Denominators use land cells only: cells classified 海水域 in both years are excluded.
Rates are NaN when the denominator area is zero. Definitions:
- agri_net_change_rate        = (agri2021 - agri2014) / agri2014
- agri_gross_loss_rate        = area(agri2014 -> non-agri 2021) / agri2014
- agri_to_forest_rate         = area(agri -> forest) / agri2014
- agri_to_wasteland_rate      = area(agri -> wasteland) / agri2014
- forestation_rate            = area(non-forest land 2014 -> forest) / non-forest land 2014
- building_gross_loss_rate    = area(building -> non-building) / building2014
- building_to_forest_or_wasteland_rate = area(building -> forest|wasteland) / building2014
- building_net_change_rate    = (building2021 - building2014) / building2014
- changed_share               = area(group changed) / land area
- isolated_change_share       = share of changed area not in a 'patch' context
"""

import tomllib
from pathlib import Path

import numpy as np
import pandas as pd

from .codes import GROUP_ORDER

REPO_ROOT = Path(__file__).resolve().parents[3]


def load_regions(path=None):
    p = Path(path) if path else REPO_ROOT / "config" / "phase1c2_regions.toml"
    return tomllib.loads(p.read_text(encoding="utf-8"))["regions"]


def assign_regions(muni_code, old_tsukui_gun, regions):
    muni_code = pd.Series(muni_code).astype("string")
    out = pd.Series(pd.NA, index=muni_code.index, dtype="string")
    for rid, spec in regions.items():
        if spec.get("old_tsukui_gun"):
            continue
        mask = muni_code.isin(spec.get("muni_codes", []))
        if (out[mask].notna()).any():
            raise ValueError(f"Overlapping region definitions at {rid}")
        out[mask] = rid
    tsukui = [r for r, s in regions.items() if s.get("old_tsukui_gun")]
    if tsukui:
        out[np.asarray(old_tsukui_gun, dtype=bool)] = tsukui[0]
    return out


def add_indicators(cells):
    """Add per-cell area indicator columns used by aggregate()."""
    c = cells
    a = c["area_m2"].to_numpy(float)
    g0 = c["grp2014"].to_numpy()
    g1 = c["grp2021"].to_numpy()
    land = ~((g0 == "sea") & (g1 == "sea"))
    ind = {"land_m2": a * land}
    for g in GROUP_ORDER:
        ind[f"{g}_2014_m2"] = a * (g0 == g)
        ind[f"{g}_2021_m2"] = a * (g1 == g)
    chg = (g0 != g1) & land
    ind["changed_m2"] = a * chg
    ind["changed_isolated_m2"] = a * chg * (c["context"].to_numpy() != "patch") if "context" in c else np.nan
    ind["agri_loss_m2"] = a * ((g0 == "agri") & (g1 != "agri"))
    ind["agri_to_forest_m2"] = a * ((g0 == "agri") & (g1 == "forest"))
    ind["agri_to_wasteland_m2"] = a * ((g0 == "agri") & (g1 == "wasteland"))
    ind["nonforest_land_2014_m2"] = a * ((g0 != "forest") & land)
    ind["to_forest_m2"] = a * ((g0 != "forest") & (g1 == "forest") & land)
    ind["building_loss_m2"] = a * ((g0 == "building") & (g1 != "building"))
    ind["building_to_forest_m2"] = a * ((g0 == "building") & (g1 == "forest"))
    ind["building_to_wasteland_m2"] = a * ((g0 == "building") & (g1 == "wasteland"))
    ind["building_gain_m2"] = a * ((g0 != "building") & (g1 == "building"))
    return pd.concat([c.reset_index(drop=True), pd.DataFrame(ind)], axis=1)


def _rates(s):
    def r(num, den):
        return np.where(s[den] > 0, s[num] / s[den].where(s[den] > 0), np.nan)

    out = pd.DataFrame(index=s.index)
    out["n_cells"] = s["n_cells"]
    out["land_km2"] = s["land_m2"] / 1e6
    for g in GROUP_ORDER:
        if g == "sea":
            continue
        out[f"{g}_2014_share"] = r(f"{g}_2014_m2", "land_m2")
        out[f"{g}_2021_share"] = r(f"{g}_2021_m2", "land_m2")
        out[f"{g}_net_change_km2"] = (s[f"{g}_2021_m2"] - s[f"{g}_2014_m2"]) / 1e6
    out["agri_net_change_rate"] = np.where(s.agri_2014_m2 > 0, (s.agri_2021_m2 - s.agri_2014_m2) / s.agri_2014_m2.where(s.agri_2014_m2 > 0), np.nan)
    out["agri_gross_loss_rate"] = r("agri_loss_m2", "agri_2014_m2")
    out["agri_to_forest_rate"] = r("agri_to_forest_m2", "agri_2014_m2")
    out["agri_to_wasteland_rate"] = r("agri_to_wasteland_m2", "agri_2014_m2")
    out["forestation_rate"] = r("to_forest_m2", "nonforest_land_2014_m2")
    out["building_gross_loss_rate"] = r("building_loss_m2", "building_2014_m2")
    s2 = s.assign(bfw=s.building_to_forest_m2 + s.building_to_wasteland_m2)
    out["building_to_forest_or_wasteland_rate"] = np.where(s2.building_2014_m2 > 0, s2.bfw / s2.building_2014_m2.where(s2.building_2014_m2 > 0), np.nan)
    out["building_net_change_rate"] = np.where(s.building_2014_m2 > 0, (s.building_2021_m2 - s.building_2014_m2) / s.building_2014_m2.where(s.building_2014_m2 > 0), np.nan)
    out["changed_share"] = r("changed_m2", "land_m2")
    out["isolated_change_share"] = r("changed_isolated_m2", "changed_m2")
    for k in ["agri_loss_m2", "agri_to_forest_m2", "agri_to_wasteland_m2", "to_forest_m2", "building_loss_m2", "building_to_forest_m2", "building_to_wasteland_m2", "building_gain_m2", "changed_m2"]:
        out[k.replace("_m2", "_km2")] = s[k] / 1e6
    return out


def aggregate(frame, by):
    cols = [c for c in frame.columns if c.endswith("_m2") and c not in ("area_m2", "area_geodesic_m2")]
    s = frame.groupby(by, dropna=False)[cols].sum()
    s["n_cells"] = frame.groupby(by, dropna=False).size()
    return _rates(s)
