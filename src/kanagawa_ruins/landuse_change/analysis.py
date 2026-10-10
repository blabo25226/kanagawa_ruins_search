"""Phase 1-C2 analysis steps operating on the verified cell table."""

import numpy as np
import pandas as pd
import shapely
from scipy import ndimage
from scipy.spatial import cKDTree

from .aggregate import add_indicators, aggregate
from .codes import FINE_ORDER_09, GROUP_ORDER, GROUPS_1976, validate_codes
from .mesh import decode_100m
from .proximity import bin_distance, grid_distance, nearest_distance
from .stats import block_bootstrap_ratio, morans_i_test
from .transition import change_context, gain_loss_swap, transition_matrix

FOCUS = [
    ("building", "forest"),
    ("building", "wasteland"),
    ("agri", "forest"),
    ("agri", "wasteland"),
]

LANDSCAPE_LABELS = {
    "forest_dominant": "森林卓越（2014森林≥70%）",
    "urban": "都市的（2014建物+交通≥50%）",
    "agri_mixed": "農地混在（2014農地≥20%）",
    "other_mixed": "その他混在",
}


def code_report(cells, kanagawa_mask):
    out = {}
    for y in ("2014", "2021"):
        out[f"all_cells_{y}"] = validate_codes(y, cells[f"lu{y}"].value_counts().to_dict())
        out[f"kanagawa_{y}"] = validate_codes(y, cells.loc[kanagawa_mask, f"lu{y}"].value_counts().to_dict())
    return out


def add_context(cells):
    ctx = change_context(cells.iy.values, cells.ix.values, cells.grp2014.values, cells.grp2021.values)
    fine = change_context(cells.iy.values, cells.ix.values, cells.lu2014.values, cells.lu2021.values)
    cells = cells.copy()
    cells["context"] = ctx.context.values
    cells["same_transition_neighbours"] = ctx.same_transition_neighbours.values
    cells["to_class_in_2014_neighbourhood"] = ctx.to_class_in_from_neighbourhood.values
    cells["fine_context"] = fine.context.values
    return cells


def landscape_type(k):
    """2014 land-cover typology per 1 km mesh (Kanagawa land cells). Not a terrain class."""
    a = k.groupby("mesh1km")[["land_m2", "forest_2014_m2", "building_2014_m2", "transport_2014_m2", "agri_2014_m2"]].sum()
    land = a.land_m2.where(a.land_m2 > 0)
    f = a.forest_2014_m2 / land
    u = (a.building_2014_m2 + a.transport_2014_m2) / land
    g = a.agri_2014_m2 / land
    t = np.select([f >= 0.7, u >= 0.5, g >= 0.2], ["forest_dominant", "urban", "agri_mixed"], "other_mixed")
    t = pd.Series(t, index=a.index)
    t[land.isna()] = "no_land"
    return t


def transitions(k, by_region=True):
    land = k[~((k.grp2014 == "sea") & (k.grp2021 == "sea"))]
    out = {}
    out["fine_area_km2"] = transition_matrix(land.assign(a=land.area_m2 / 1e6), "lu2014", "lu2021", "a", FINE_ORDER_09)
    out["fine_cells"] = transition_matrix(land.assign(a=1), "lu2014", "lu2021", "a", FINE_ORDER_09)
    out["group_area_km2"] = transition_matrix(land.assign(a=land.area_m2 / 1e6), "grp2014", "grp2021", "a", GROUP_ORDER)
    out["group_patch_only_km2"] = transition_matrix(
        land.assign(a=np.where((land.context == "patch") | (land.grp2014 == land.grp2021), land.area_m2 / 1e6, 0.0)),
        "grp2014", "grp2021", "a", GROUP_ORDER,
    )
    out["group_gls"] = gain_loss_swap(out["group_area_km2"], unit="km2")
    out["fine_gls"] = gain_loss_swap(out["fine_area_km2"], unit="km2")
    if by_region:
        out["by_region"] = {
            r: transition_matrix(g.assign(a=g.area_m2 / 1e6), "grp2014", "grp2021", "a", GROUP_ORDER)
            for r, g in land.groupby("region")
        }
    return out


def context_breakdown(k):
    ch = k[(k.grp2014 != k.grp2021) & ~((k.grp2014 == "sea") & (k.grp2021 == "sea"))]
    t = ch.groupby(["grp2014", "grp2021", "context"]).area_m2.sum().unstack(fill_value=0) / 1e6
    t["total_km2"] = t.sum(axis=1)
    for c in ["patch", "isolated_boundary", "isolated_interior"]:
        if c not in t:
            t[c] = 0.0
        t[f"{c}_share"] = t[c] / t.total_km2
    return t.sort_values("total_km2", ascending=False)


def focus_summary(k):
    rows = []
    for a, b in FOCUS:
        m = (k.grp2014 == a) & (k.grp2021 == b)
        base = k.loc[k.grp2014 == a, "area_m2"].sum()
        sub = k[m]
        rows.append(
            dict(
                transition=f"{a}->{b}",
                area_km2=sub.area_m2.sum() / 1e6,
                cells=int(m.sum()),
                rate_of_2014_class=sub.area_m2.sum() / base if base else np.nan,
                patch_share=(sub.context == "patch").mean() if len(sub) else np.nan,
                isolated_boundary_share=(sub.context == "isolated_boundary").mean() if len(sub) else np.nan,
                isolated_interior_share=(sub.context == "isolated_interior").mean() if len(sub) else np.nan,
                reverse_area_km2=k.loc[(k.grp2014 == b) & (k.grp2021 == a), "area_m2"].sum() / 1e6,
            )
        )
    return pd.DataFrame(rows)


def building_loss_clusters(k):
    """8-connected clusters of building -> non-building cells (spatial, single interval)."""
    m = ((k.grp2014 == "building") & (k.grp2021 != "building")).values
    r = k.iy.values - k.iy.min()
    c = k.ix.values - k.ix.min()
    grid = np.zeros((r.max() + 1, c.max() + 1), dtype=bool)
    grid[r[m], c[m]] = True
    lab, n = ndimage.label(grid, structure=np.ones((3, 3)))
    sizes = np.bincount(lab.ravel())[1:]
    cell_label = lab[r, c]
    hist = pd.Series(sizes).value_counts().sort_index()
    bins = pd.cut(pd.Series(sizes), [0, 1, 2, 4, 9, np.inf], labels=["1", "2", "3-4", "5-9", ">=10"])
    return dict(n_clusters=int(n), size_hist=hist, size_bins=bins.value_counts().sort_index(), cell_label=cell_label)


def proximity(cells, k_mask, rail, station, osm_roads, osm_bbox_6677, inner_buffer_m=1000.0):
    """Distances for Kanagawa cells. Road-cell distance uses the full landuse grid."""
    d = pd.DataFrame(index=cells.index[k_mask])
    x = cells.cen_x.values[k_mask]
    y = cells.cen_y.values[k_mask]
    d["dist_rail_m"] = nearest_distance(x, y, rail)
    d["dist_station_m"] = nearest_distance(x, y, station)
    dy, dx = cell_edge_lengths(cells.geometry.values)
    dr, de = grid_distance(cells.iy.values, cells.ix.values, (cells.lu2014 == "0901").values, np.ones(len(cells), bool), dy, dx)
    d["dist_road_cell_2014_m"] = dr[k_mask]
    d["road_cell_censored"] = (dr > de)[k_mask]
    if osm_roads is not None:
        minx, miny, maxx, maxy = osm_bbox_6677
        inner = (x >= minx + inner_buffer_m) & (x <= maxx - inner_buffer_m) & (y >= miny + inner_buffer_m) & (y <= maxy - inner_buffer_m)
        d["in_osm_window"] = inner
        all_lines, motor = osm_roads
        d["dist_osm_road_m"] = np.where(inner, nearest_distance(x, y, all_lines), np.nan)
        d["dist_osm_motor_road_m"] = np.where(inner, nearest_distance(x, y, motor), np.nan)
    return d, dict(cell_dy_m=dy, cell_dx_m=dx)


def cell_edge_lengths(geoms, sample=5000):
    """Mean north-south and east-west edge lengths (m) of projected mesh cells.

    Bounding boxes would overstate them because the lat/lon grid is slightly rotated
    in the transverse Mercator plane (meridian convergence)."""
    g = np.asarray(geoms)[:: max(1, len(geoms) // sample)]
    rings = [np.asarray(p.exterior.coords) for p in g]
    ns, ew = [], []
    for c in rings:
        e = np.hypot(*np.diff(c[:5], axis=0).T)
        d = np.abs(np.diff(c[:5], axis=0))
        vertical = d[:, 1] > d[:, 0]
        ns.append(e[vertical].mean())
        ew.append(e[~vertical].mean())
    return float(np.mean(ns)), float(np.mean(ew))


RATE_DEFS = {
    "agri_gross_loss_rate": ("agri_loss_m2", "agri_2014_m2"),
    "agri_to_forest_or_wasteland_rate": ("agri_to_fw_m2", "agri_2014_m2"),
    "forestation_rate": ("to_forest_m2", "nonforest_land_2014_m2"),
    "building_gross_loss_rate": ("building_loss_m2", "building_2014_m2"),
    "building_to_forest_or_wasteland_rate": ("building_to_fw_m2", "building_2014_m2"),
}


def rates_by_bin(k, dist_col, edges, strata_col="landscape", n_boot=999, block=("iy", "ix", 50)):
    k = k.assign(
        agri_to_fw_m2=k.agri_to_forest_m2 + k.agri_to_wasteland_m2,
        building_to_fw_m2=k.building_to_forest_m2 + k.building_to_wasteland_m2,
        dist_bin=bin_distance(k[dist_col].values, edges),
        block=(k[block[0]] // block[2]).astype(str) + "_" + (k[block[1]] // block[2]).astype(str),
    )
    rows = []
    strata = [("all", k)] + ([(s, g) for s, g in k.groupby(strata_col)] if strata_col else [])
    for sname, sg in strata:
        for b, g in sg.groupby("dist_bin", observed=True):
            for rate, (num, den) in RATE_DEFS.items():
                if g[den].sum() <= 0:
                    continue
                bb = block_bootstrap_ratio(g[num].values, g[den].values, g.block.values, n_boot=n_boot)
                rows.append(dict(stratum=sname, dist_bin=str(b), rate=rate, denom_km2=g[den].sum() / 1e6, land_km2=g.land_m2.sum() / 1e6, n_cells=len(g), **bb))
    return pd.DataFrame(rows)


def moran_table(mesh_agg, permutations=999, min_land_km2=0.5):
    m = mesh_agg[mesh_agg.land_km2 >= min_land_km2].copy()
    iy, ix = decode_100m(np.char.add(m.index.values.astype(str), "00"))
    rows = []
    for col, den, min_den in [
        ("building_gross_loss_rate", "building_2014_share", 0.05),
        ("agri_gross_loss_rate", "agri_2014_share", 0.05),
        ("agri_to_forest_rate", "agri_2014_share", 0.05),
        ("forestation_rate", None, None),
        ("changed_share", None, None),
        ("agri_net_change_rate", "agri_2014_share", 0.05),
    ]:
        mask = m[col].notna().to_numpy().copy()
        if den:
            mask &= (m[den] >= min_den).values
        res = morans_i_test(m[col].values[mask], iy[mask] // 10, ix[mask] // 10, permutations=permutations)
        rows.append(dict(variable=col, inclusion=(f"{den}>={min_den}" if den else "all meshes"), **res))
    return pd.DataFrame(rows)


def buffer_composition(points_xy, cells_k, radii=(250, 500)):
    """Land-use composition of Kanagawa cells whose centroid lies within r of each point."""
    tree = cKDTree(np.c_[cells_k.cen_x.values, cells_k.cen_y.values])
    cols = [c for c in cells_k.columns if c.endswith("_m2") and c not in ("area_m2", "area_geodesic_m2")]
    vals = cells_k[cols].to_numpy(float)
    out = {}
    for r in radii:
        idx = tree.query_ball_point(points_xy, r)
        rows = [vals[i].sum(axis=0) if len(i) else np.full(len(cols), np.nan) for i in idx]
        out[r] = pd.DataFrame(rows, columns=cols)
    return out


def attribute_summary_1976(frame_by_file):
    """1976 counts and Bessel-ellipsoid areas per 1st-mesh file; no spatial operation."""
    from .data import geodesic_cell_area

    rows = []
    for lid, df in frame_by_file.items():
        code = df["L03b_001"].astype(str).values
        iy, _ = decode_100m(code)
        area = geodesic_cell_area(iy, ellps="bessel")
        t = pd.DataFrame(dict(code=df.landuse_code.astype(str).values, area=area))
        g = t.groupby("code").agg(cells=("area", "size"), area_km2=("area", lambda v: v.sum() / 1e6))
        g["layer_id"] = lid
        g["group"] = g.index.map(GROUPS_1976)
        rows.append(g.reset_index())
    return pd.concat(rows, ignore_index=True)


def point_cells(x, y, cells):
    """Index of the cell containing each point (projected polygon test)."""
    tree = shapely.STRtree(cells.geometry.values)
    pts = shapely.points(x, y)
    pi, ci = tree.query(pts, predicate="within")
    out = np.full(len(pts), -1)
    out[pi] = ci
    return out
