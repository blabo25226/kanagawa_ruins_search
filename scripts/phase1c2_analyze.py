#!/usr/bin/env python3
"""Phase 1-C2: land-use transitions 2014->2021 and historical-geography context (Kanagawa).

Default is a local dry run into a scratch work directory. --execute additionally publishes
outputs under $RUINS_DATA_ROOT/processed/phase1c/claude/<version>/ (never overwriting).
--sample-mesh2 restricts the run to listed 2nd meshes for small-scale validation.

Descriptive analysis only: no candidate extraction, ranking, or existence/abandonment
judgement. 1976 (Tokyo Datum) is summarised by attributes only.
"""

import argparse
import json
from pathlib import Path
import sys
import tempfile
import time

import geopandas as gpd
import numpy as np
import pandas as pd
import pyproj
import shapely

from kanagawa_ruins.landuse_change import ANALYSIS_VERSION
from kanagawa_ruins.landuse_change import analysis as A
from kanagawa_ruins.landuse_change import plots as P
from kanagawa_ruins.landuse_change.aggregate import add_indicators, aggregate, assign_regions, load_regions
from kanagawa_ruins.landuse_change.codes import GROUP_LABELS, GROUP_ORDER, GROUPS_09, GROUPS_1976, tables_identical
from kanagawa_ruins.landuse_change.crosscheck import duckdb_crosscheck
from kanagawa_ruins.landuse_change.data import LAYERS, InputRegistry, assign_admin, build_cells, coverage_polygon
from kanagawa_ruins.landuse_change.proximity import osm_highway_lines, osm_union
from kanagawa_ruins.landuse_change.publish import publish_file, write_run_manifest
from kanagawa_ruins.storage.drive import get_verified_data_root

REPO = Path(__file__).resolve().parents[1]
OSM_WINDOW_WGS84 = (139.12, 35.51, 139.25, 35.62)  # Phase 1-A tsukui PBF selection bbox
RAIL_EDGES = [0, 500, 1000, 2000, 4000, 8000, np.inf]
ROAD_EDGES = [0, 200, 400, 800, 1600, np.inf]
OSM_EDGES = [0, 100, 200, 400, 800, np.inf]
MIN_DENOM_KM2 = 0.5
DIST_LABELS = {"rail": "鉄道（N02 2023）", "station": "駅（N02 2023）", "road_cell_2014": "2014年『道路』セル", "osm_motor_road": "OSM車道（2026-10）"}
RATE_LABELS = {"agri_to_forest_or_wasteland_rate": "農地→森林・荒地の転換率", "building_gross_loss_rate": "建物用地の総減少率"}


def log(msg, t0=[time.time()]):
    print(f"[{time.time() - t0[0]:7.1f}s] {msg}", flush=True)


def jsonable(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, pd.DataFrame):
        return json.loads(o.to_json(orient="split", force_ascii=False))
    if isinstance(o, pd.Series):
        return json.loads(o.to_json(force_ascii=False))
    raise TypeError(type(o))


def clean(o):
    """Replace non-finite floats (NaN/inf) with None so the report is strict JSON."""
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [clean(v) for v in o]
    if isinstance(o, float) and not np.isfinite(o):
        return None
    return o


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--execute", action="store_true", help="publish to processed/phase1c/claude on Drive")
    ap.add_argument("--sample-mesh2", action="append", default=[], help="restrict to 2nd mesh code(s)")
    ap.add_argument("--work-dir", type=Path, default=None)
    ap.add_argument("--report-json", type=Path, default=REPO / "reports" / "phase1c2_results.json")
    ap.add_argument("--figures-dir", type=Path, default=REPO / "reports" / "figures" / "phase1c2")
    ap.add_argument("--permutations", type=int, default=999)
    ap.add_argument("--bootstrap", type=int, default=999)
    ap.add_argument("--skip-duckdb", action="store_true")
    ap.add_argument("--no-verify-sha", action="store_true", help="development only; refused with --execute")
    a = ap.parse_args(argv)
    if a.execute and (a.sample_mesh2 or a.no_verify_sha):
        ap.error("--execute requires a full run with input SHA verification")
    work = a.work_dir or Path(tempfile.mkdtemp(prefix="phase1c2_"))
    for sub in ("csv", "geoparquet", "figures", "qa"):
        (work / sub).mkdir(parents=True, exist_ok=True)
    P.setup_fonts()
    data_root = get_verified_data_root()
    reg = InputRegistry(data_root, verify_sha=not a.no_verify_sha)
    R = dict(analysis_version=ANALYSIS_VERSION, sample_mesh2=a.sample_mesh2)

    # 1. cells and positional QA -------------------------------------------------------
    cells, qa = build_cells(reg)
    R["alignment_qa"] = qa
    log(f"cells {len(cells)} {qa}")
    cells, muni, codh = assign_admin(cells, reg)
    cov, present = coverage_polygon(cells)
    R["landuse_mesh2_present"] = len(present)
    regions = load_regions()
    cells["region"] = assign_regions(cells.muni_code, cells.old_tsukui_gun, regions).values
    if a.sample_mesh2:
        cells = cells[cells.mesh2.isin(a.sample_mesh2)].reset_index(drop=True)
        log(f"sample restricted to {a.sample_mesh2}: {len(cells)} cells")
    R["code_tables_2014_2021_identical"] = tables_identical(2014, 2021)
    kmask = cells.muni_code.notna().values
    R["code_validation"] = A.code_report(cells, kmask)

    # coverage per municipality / region
    muni["area_km2"] = muni.area / 1e6
    muni["covered_km2"] = muni.intersection(cov).area / 1e6
    muni["coverage"] = muni.covered_km2 / muni.area_km2
    muni["region"] = assign_regions(muni.muni_code, np.zeros(len(muni), bool), regions).values
    cov_tab = muni[["muni_code", "muni_name", "region", "area_km2", "covered_km2", "coverage"]].copy()
    rcov = cov_tab.groupby("region")[["area_km2", "covered_km2"]].sum()
    rcov["coverage"] = rcov.covered_km2 / rcov.area_km2
    R["coverage"] = dict(
        pref_area_km2=float(muni.area_km2.sum()),
        covered_km2=float(muni.covered_km2.sum()),
        share=float(muni.covered_km2.sum() / muni.area_km2.sum()),
        by_region=rcov,
        not_covered=cov_tab[cov_tab.coverage < 0.01].muni_name.tolist(),
        partial=cov_tab[(cov_tab.coverage >= 0.01) & (cov_tab.coverage < 0.99)][["muni_name", "coverage"]],
    )
    cov_tab.to_csv(work / "csv" / "municipality_coverage.csv", index=False)

    # 2. neighbourhood context on the full grid, then Kanagawa subset ----------------------
    cells = A.add_context(cells)
    cells = add_indicators(cells)
    k = cells[kmask].reset_index(drop=True)
    k = k[k.land_m2 > 0].reset_index(drop=True)
    land_type = A.landscape_type(k)
    k["landscape"] = k.mesh1km.map(land_type).values
    log(f"Kanagawa land cells {len(k)}, {k.land_m2.sum() / 1e6:.1f} km2")
    R["kanagawa_land_km2"] = float(k.land_m2.sum() / 1e6)
    R["kanagawa_land_cells"] = int(len(k))
    R["sea_involving_changes_km2"] = float(k.loc[(k.grp2014 == "sea") ^ (k.grp2021 == "sea"), "area_m2"].sum() / 1e6)

    # 3. transitions --------------------------------------------------------------------
    T = A.transitions(k)
    for name in ["fine_area_km2", "fine_cells", "group_area_km2", "group_patch_only_km2", "group_gls", "fine_gls"]:
        T[name].to_csv(work / "csv" / f"transition_{name}.csv")
    long = pd.concat({r: m.stack() for r, m in T["by_region"].items()}, names=["region", "grp2014", "grp2021"]).rename("area_km2").reset_index()
    long.to_csv(work / "csv" / "transition_group_by_region_long.csv", index=False)
    ctx = A.context_breakdown(k)
    ctx.to_csv(work / "csv" / "transition_context_breakdown.csv")
    focus = A.focus_summary(k)
    focus.to_csv(work / "csv" / "focus_transitions.csv", index=False)
    focus_reg = pd.concat({r: A.focus_summary(g) for r, g in k.groupby("region")}, names=["region", "i"]).reset_index(level=0)
    focus_reg.to_csv(work / "csv" / "focus_transitions_by_region.csv", index=False)
    clusters = A.building_loss_clusters(k)
    k["building_loss_cluster"] = clusters.pop("cell_label")
    clusters["size_bins"].to_csv(work / "csv" / "building_loss_cluster_sizes.csv")
    R["transitions"] = dict(
        group_area_km2=T["group_area_km2"], group_gls=T["group_gls"], fine_area_km2=T["fine_area_km2"], fine_gls=T["fine_gls"],
        group_patch_only_km2=T["group_patch_only_km2"], context=ctx.head(25), focus=focus, focus_by_region=focus_reg,
        building_loss_clusters=dict(n=clusters["n_clusters"], size_bins=clusters["size_bins"]),
        changed_land_share=float(k.changed_m2.sum() / k.land_m2.sum()),
        changed_context_share=k[k.changed_m2 > 0].groupby("context").area_m2.sum() / k.changed_m2.sum(),
    )
    fine_changed = k.lu2014 != k.lu2021
    R["transitions"]["fine_changed_land_share"] = float(k.loc[fine_changed, "area_m2"].sum() / k.land_m2.sum())

    # 4. aggregates -------------------------------------------------------------------
    rlabels = {r: s["label"] for r, s in regions.items()}
    agg_muni = aggregate(k, ["muni_code", "muni_name"]).reset_index().merge(cov_tab[["muni_code", "coverage"]], on="muni_code")
    agg_muni["region"] = agg_muni.muni_code.map(dict(zip(muni.muni_code, muni.region)))
    agg_reg = aggregate(k, "region")
    agg_reg["label"] = agg_reg.index.map(rlabels)
    agg_reg["coverage"] = agg_reg.index.map(rcov.coverage)
    agg_reg.loc["R5_sagamihara", "coverage"] = 1.0
    agg_reg.loc["R6_tsukui", "coverage"] = 1.0
    agg_all = aggregate(k.assign(all="kanagawa_covered"), "all")
    agg_land = aggregate(k, "landscape")
    agg_reg_land = aggregate(k, ["region", "landscape"])
    agg_1km = aggregate(k, "mesh1km")
    agg_1km["landscape"] = land_type.reindex(agg_1km.index).values
    agg_500 = aggregate(k, "mesh500m")
    for n, t in [("municipality", agg_muni), ("region", agg_reg), ("kanagawa_covered", agg_all), ("landscape", agg_land), ("region_landscape", agg_reg_land), ("mesh1km", agg_1km), ("mesh500m", agg_500)]:
        t.to_csv(work / "csv" / f"agg_{n}.csv")
    R["aggregates"] = dict(all=agg_all, region=agg_reg, landscape=agg_land, region_landscape=agg_reg_land, municipality=agg_muni)
    R["landscape_mesh_counts"] = land_type.value_counts()

    # 5. proximity ----------------------------------------------------------------------
    box = shapely.box(*k.total_bounds).buffer(20000) if len(k) else None
    rail = reg.read(LAYERS["rail"])
    rail = rail[rail.intersects(box)]
    station = reg.read(LAYERS["station"])
    station = station[station.intersects(box)]
    osm_frames = [reg.read(l) for l in reg.osm_layers("roads")]
    roads, road_dups = osm_union(osm_frames)
    tr = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:6677", always_xy=True)
    wx, wy = tr.transform([OSM_WINDOW_WGS84[0], OSM_WINDOW_WGS84[2], OSM_WINDOW_WGS84[0], OSM_WINDOW_WGS84[2]], [OSM_WINDOW_WGS84[1], OSM_WINDOW_WGS84[1], OSM_WINDOW_WGS84[3], OSM_WINDOW_WGS84[3]])
    window = (min(wx), min(wy), max(wx), max(wy))
    lines = osm_highway_lines(roads)
    motor = osm_highway_lines(roads, motor_only=True)
    # compute on the full grid for road-cell distance, subset to Kanagawa land cells
    dist, cellsize = A.proximity(cells, kmask, rail.geometry.values, station.geometry.values, (lines.geometry.values, motor.geometry.values), window)
    dist = dist.reset_index(drop=True)
    land_sel = (cells.loc[kmask, "land_m2"] > 0).values
    dist = dist[land_sel].reset_index(drop=True)
    rivers = reg.read(LAYERS["rivers"])
    from kanagawa_ruins.landuse_change.proximity import nearest_distance

    dist["dist_river_w05_m"] = nearest_distance(k.cen_x.values, k.cen_y.values, rivers.geometry.values)
    k = pd.concat([k, dist], axis=1)
    R["proximity_meta"] = dict(
        rail_sections=int(len(rail)), stations=int(len(station)), osm_road_union_duplicates_removed=int(road_dups),
        osm_highway_lines=int(len(lines)), osm_motor_lines=int(len(motor)), osm_window_6677=window, cell_size=cellsize,
        road_cell_censored_share=float(k.road_cell_censored.mean()), osm_window_cells=int(k.in_osm_window.sum()),
        vintages=dict(landuse="2014 / 2021", rail="N02 2023", osm="2026-10 (Tsukui window only)", road_cells="L03-b 2014 道路(0901)", rivers="W05 2008"),
    )
    strata = {"all": "全セル", **{kk: v for kk, v in A.LANDSCAPE_LABELS.items()}}
    dr = {}
    for name, col, edges, sub in [
        ("rail", "dist_rail_m", RAIL_EDGES, k),
        ("station", "dist_station_m", RAIL_EDGES, k),
        ("road_cell_2014", "dist_road_cell_2014_m", ROAD_EDGES, k[~k.road_cell_censored]),
        ("osm_motor_road", "dist_osm_motor_road_m", OSM_EDGES, k[k.in_osm_window]),
    ]:
        tab = A.rates_by_bin(sub, col, edges, strata_col=None if name == "osm_motor_road" else "landscape", n_boot=a.bootstrap)
        tab["sufficient_denominator"] = tab.denom_km2 >= MIN_DENOM_KM2
        tab.to_csv(work / "csv" / f"distance_rates_{name}.csv", index=False)
        comp = aggregate(sub.assign(dist_bin=A.bin_distance(sub[col].values, edges).astype(str)), "dist_bin")
        comp.to_csv(work / "csv" / f"distance_composition_{name}.csv")
        dr[name] = dict(rates=tab, composition=comp)
    R["distance"] = dr
    log("proximity done")

    # 6. spatial autocorrelation --------------------------------------------------------
    mor = A.moran_table(agg_1km, permutations=a.permutations)
    mor.to_csv(work / "csv" / "moran_mesh1km.csv", index=False)
    R["moran"] = mor
    log("moran done")

    # 7. cultural properties (P32) and OSM worship/historic ----------------------------------
    p32 = reg.read(LAYERS["cultural"])
    R["p32"] = dict(total=int(len(p32)), by_point_class=p32.P32_009.value_counts(), by_small_class=p32.P32_005.value_counts())
    p32 = p32[p32.P32_009.astype(int).isin([1, 2, 9])].copy()
    xy = np.c_[p32.geometry.x.values, p32.geometry.y.values]
    loc_key = pd.Series([f"{x:.3f},{y:.3f}" for x, y in xy], index=p32.index)
    p32["site"] = loc_key.values
    sites = p32.groupby("site").agg(n_props=("P32_006", "size"), classes=("P32_005", lambda v: ",".join(sorted(set(map(str, v))))), x=("geometry", lambda g: g.iloc[0].x), y=("geometry", lambda g: g.iloc[0].y)).reset_index()
    pref_poly = muni.geometry.union_all()
    # distance to the edge of the analysable area (coverage within Kanagawa), so buffers are complete
    edge_dist = shapely.distance(shapely.intersection(cov, pref_poly).boundary, shapely.points(sites.x.values, sites.y.values))
    inside = shapely.contains_xy(cov, sites.x.values, sites.y.values) & shapely.contains_xy(pref_poly, sites.x.values, sites.y.values)
    sites["usable"] = inside & (edge_dist > 500)
    cultural = {}
    from scipy.spatial import cKDTree

    kd = cKDTree(np.c_[k.cen_x.values, k.cen_y.values])
    _, nearest = kd.query(np.c_[sites.x.values, sites.y.values])
    sites["region"] = k.region.values[nearest]
    sites["landscape"] = k.landscape.values[nearest]
    us = sites[sites.usable].reset_index(drop=True)
    buf = A.buffer_composition(np.c_[us.x.values, us.y.values], k)
    for r, bdf in buf.items():
        bdf = pd.concat([us[["site", "n_props", "classes", "region", "landscape"]], bdf], axis=1)
        agg = aggregate(bdf.assign(all="p32_sites"), "all")
        # region- and landscape-weighted baselines: each site contributes its stratum's rates
        reg_base = agg_reg.reindex(us.region)
        land_base = agg_land.reindex(us.landscape)
        cultural[r] = dict(
            sites=int(len(us)), site_buffers=agg, baseline_region_weighted=reg_base.mean(numeric_only=True), baseline_landscape_weighted=land_base.mean(numeric_only=True),
            by_class=aggregate(bdf.assign(c=bdf.classes.str.contains("43").map({True: "天然記念物を含む", False: "天然記念物を含まない"})), "c"),
        )
        bdf.drop(columns=["site"]).to_csv(work / "csv" / f"p32_buffer_{r}m_sites.csv", index=False)
    R["cultural"] = dict(
        usable_sites=int(sites.usable.sum()), all_sites=int(len(sites)), props_in_usable=int(sites.loc[sites.usable, "n_props"].sum()),
        sites_by_region=sites[sites.usable].region.value_counts(), sites_by_landscape=sites[sites.usable].landscape.value_counts(),
        buffers=cultural,
        dist_to_rail_station=pd.DataFrame(dict(rail=k.dist_rail_m.values[nearest], station=k.dist_station_m.values[nearest]))[sites.usable.values].describe(),
        landscape_baseline_land_share=k.groupby("landscape").land_m2.sum() / k.land_m2.sum(),
    )
    sites[["site", "n_props", "classes", "usable", "region", "landscape"]].to_csv(work / "csv" / "p32_sites_summary.csv", index=False)

    wor, wdup = osm_union([reg.read(l) for l in reg.osm_layers("worship")])
    his, hdup = osm_union([reg.read(l) for l in reg.osm_layers("historic")])
    wc = wor.geometry.centroid
    in_win = (wc.x >= window[0]) & (wc.x <= window[2]) & (wc.y >= window[1]) & (wc.y <= window[3])
    wor = wor.assign(px=wc.x.values, py=wc.y.values)
    _, wn = kd.query(np.c_[wor.px.values, wor.py.values])
    wor["landscape"] = k.landscape.values[wn]
    wor["old_muni_2005"] = None
    for _, row in codh.iterrows():
        wor.loc[shapely.contains_xy(row.geometry, wor.px.values, wor.py.values), "old_muni_2005"] = row.muni
    wor["dist_osm_motor_road_m"] = A.nearest_distance(wor.px.values, wor.py.values, motor.geometry.values)
    wor["dist_osm_any_road_m"] = A.nearest_distance(wor.px.values, wor.py.values, lines.geometry.values)
    codh1955 = reg.read(LAYERS["codh_1955"])
    wor["in_tsukui_1955"] = shapely.contains_xy(codh1955.geometry.union_all(), wor.px.values, wor.py.values)
    wbuf = A.buffer_composition(np.c_[wor.px.values, wor.py.values], k, radii=(250,))[250]
    wagg = aggregate(pd.concat([wor[["religion"]].reset_index(drop=True), wbuf], axis=1).assign(all="osm_worship"), "all")
    win_cells = k[k.in_osm_window]
    window_road = win_cells.dist_osm_motor_road_m
    R["osm"] = dict(
        worship_unique=int(len(wor)), worship_duplicates_removed=int(wdup), historic_unique=int(len(his)), historic_duplicates_removed=int(hdup),
        worship_in_window=int(in_win.sum()),
        worship_religion=wor.religion.fillna("unknown").value_counts(), worship_geom=wor.geometry.geom_type.value_counts(),
        worship_landscape=wor.landscape.fillna("outside").value_counts(), worship_old_muni_2005=wor.old_muni_2005.fillna("not_in_former_tsukui_gun").value_counts(),
        worship_in_tsukui_1955=int(wor.in_tsukui_1955.sum()),
        worship_dist_motor_road=wor.dist_osm_motor_road_m.describe(), window_cells_dist_motor_road=window_road.describe(),
        worship_dist_percentile_in_window=[float((window_road < d).mean()) for d in wor.dist_osm_motor_road_m],
        worship_buffer_250m=wagg, window_baseline=aggregate(win_cells.assign(all="osm_window"), "all"),
        historic_types=his.historic.fillna("none").value_counts(),
    )
    wor.drop(columns=["geometry", "tags_json"]).assign(name=None).to_csv(work / "csv" / "osm_worship_context.csv", index=False)
    log("cultural/worship done")

    # 8. 1976 attributes only ------------------------------------------------------------
    f76 = {lid: reg.read_attributes(lid, ["L03b_001", "landuse_code"]) for lid in LAYERS["lu1976"]}
    s76 = A.attribute_summary_1976(f76)
    s76.to_csv(work / "csv" / "landuse_1976_attribute_summary.csv", index=False)
    whole = []
    for y, col in [("2014", "lu2014"), ("2021", "lu2021")]:
        t = cells.groupby(cells[col].map(GROUPS_09)).area_geodesic_m2.sum() / 1e6
        whole.append(t.rename(y))
    g76 = s76.groupby("group").area_km2.sum().rename("1976")
    cmp = pd.concat([g76] + whole, axis=1)
    cmp.to_csv(work / "csv" / "reference_whole_mesh_group_area_1976_2014_2021.csv")
    R["landuse_1976"] = dict(summary=s76, whole_mesh_reference=cmp, codes_valid=A.validate_codes("1976", s76.groupby("code").cells.sum().to_dict()))

    # 9. cross-checks --------------------------------------------------------------------
    cc = {}
    cc["area_projected_vs_geodesic_kanagawa"] = dict(projected_km2=float(k.area_m2.sum() / 1e6), geodesic_km2=float(k.area_geodesic_m2.sum() / 1e6))
    cc["matrix_sum_equals_land"] = abs(float(T["group_area_km2"].to_numpy().sum()) - k.land_m2.sum() / 1e6) < 1e-6
    cc["region_sum_equals_total"] = abs(float(agg_reg.land_km2.sum()) - k.land_m2.sum() / 1e6) < 1e-6
    if not a.skip_duckdb and not a.sample_mesh2:
        cc["duckdb"] = duckdb_crosscheck(reg, k, T["group_area_km2"], agg_muni, rail)
    R["crosscheck"] = cc
    (work / "qa" / "crosscheck.json").write_text(json.dumps(cc, ensure_ascii=False, indent=2, default=jsonable), encoding="utf-8")
    log(f"crosscheck {cc.get('duckdb', {}).get('passed')}")

    # 10. geoparquet outputs --------------------------------------------------------------
    keep = ["code", "mesh2", "mesh1km", "mesh500m", "lu2014", "lu2021", "grp2014", "grp2021", "area_m2", "muni_code", "muni_name", "region", "old_muni_2005",
            "landscape", "context", "same_transition_neighbours", "to_class_in_2014_neighbourhood", "fine_context", "building_loss_cluster",
            "dist_rail_m", "dist_station_m", "dist_road_cell_2014_m", "road_cell_censored", "in_osm_window", "dist_osm_motor_road_m", "dist_river_w05_m"]
    gk = gpd.GeoDataFrame(k[keep].copy(), geometry=k.geometry.values, crs="EPSG:6677")
    gk["changed"] = gk.grp2014 != gk.grp2021
    gk.to_parquet(work / "geoparquet" / "cells_landuse_change_2014_2021.parquet", index=False, compression="zstd")
    m1 = gk.dissolve("mesh1km", aggfunc={"area_m2": "sum"})[["geometry"]].join(agg_1km)
    m1.reset_index().to_parquet(work / "geoparquet" / "mesh1km_landuse_change_2014_2021.parquet", index=False, compression="zstd")
    m5 = gk.dissolve("mesh500m", aggfunc={"area_m2": "sum"})[["geometry"]].join(agg_500)
    m5.reset_index().to_parquet(work / "geoparquet" / "mesh500m_landuse_change_2014_2021.parquet", index=False, compression="zstd")
    mm = muni[["muni_code", "geometry"]].merge(agg_muni, on="muni_code", how="left")
    gpd.GeoDataFrame(mm, crs="EPSG:6677").to_parquet(work / "geoparquet" / "municipality_landuse_change_2014_2021.parquet", index=False, compression="zstd")
    log("geoparquet done")

    # 11. figures --------------------------------------------------------------------------
    fig = work / "figures"
    note = "出典: 国土数値情報 土地利用細分メッシュ L03-b（2014・2021年）。収録範囲（1次メッシュ5338・5339）内の神奈川県陸域のみ。面積はEPSG:6677投影面積。"
    P.heatmap(T["group_area_km2"], fig / "fig_transition_heatmap_group.png", "土地利用遷移行列 2014→2021（分析用グループ）", note + " 変化には判読手法差による見かけの変化を含む。")
    P.heatmap(T["group_patch_only_km2"], fig / "fig_transition_heatmap_group_patch_only.png", "遷移行列（同一遷移が隣接2セル以上の『まとまった変化』のみ）", note)
    outline = gpd.GeoDataFrame(geometry=[g for g in gpd.GeoSeries(muni.geometry).groupby(muni.region.fillna("none")).apply(lambda s: s.union_all())], crs="EPSG:6677")
    rp = dict(muni.dissolve("region").geometry.items())
    tsukui_poly = shapely.intersection(codh.geometry.union_all(), muni.loc[muni.muni_code == "14151", "geometry"].union_all())
    rp["R5_sagamihara"] = rp["R5_sagamihara"].difference(tsukui_poly)
    rp["R6_tsukui"] = tsukui_poly
    reg_poly = gpd.GeoDataFrame(geometry=list(rp.values()), index=list(rp.keys()), crs="EPSG:6677")
    lab = gpd.GeoDataFrame(dict(label=[rlabels.get(r, r) for r in reg_poly.index]), geometry=reg_poly.representative_point().values, crs="EPSG:6677")
    pref = muni.geometry.union_all()
    uncovered = gpd.GeoDataFrame(geometry=[pref.difference(cov)], crs="EPSG:6677")
    m1g = gpd.GeoDataFrame(m1, crs="EPSG:6677")
    cnote = note + " 濃い灰色＝収録範囲外。"
    P.mesh_map(m1g.assign(v=m1g.building_gross_loss_rate.where(m1g.building_2014_share >= 0.05) * 100), "v", fig / "map_mesh1km_building_gross_loss_rate.png", "建物用地の総減少率（%、2014年建物用地≥5%の1kmメッシュ）", cnote, outline=gpd.GeoDataFrame(geometry=reg_poly.geometry.values, crs="EPSG:6677"), labels=lab, uncovered=uncovered)
    P.mesh_map(m1g.assign(v=(m1g.agri_to_forest_km2 + m1g.agri_to_wasteland_km2) / (m1g.agri_2014_share * m1g.land_km2).where(m1g.agri_2014_share >= 0.05) * 100), "v", fig / "map_mesh1km_agri_to_forest_wasteland_rate.png", "農地→森林・荒地の転換率（%、2014年農地≥5%の1kmメッシュ）", cnote, outline=gpd.GeoDataFrame(geometry=reg_poly.geometry.values, crs="EPSG:6677"), labels=lab, uncovered=uncovered)
    P.mesh_map(m1g.assign(v=m1g.building_net_change_km2 * 100), "v", fig / "map_mesh1km_building_net_change.png", "建物用地の純増減（ha、1kmメッシュ）", cnote, outline=gpd.GeoDataFrame(geometry=reg_poly.geometry.values, crs="EPSG:6677"), labels=lab, diverging=True, uncovered=uncovered)
    P.mesh_map(m1g.assign(v=m1g.forest_net_change_km2 * 100), "v", fig / "map_mesh1km_forest_net_change.png", "森林の純増減（ha、1kmメッシュ）", cnote, outline=gpd.GeoDataFrame(geometry=reg_poly.geometry.values, crs="EPSG:6677"), labels=lab, diverging=True, uncovered=uncovered)
    P.mesh_map(m1g.assign(v=m1g.changed_share * 100), "v", fig / "map_mesh1km_changed_share.png", "分類が変化した陸域面積の割合（%、1kmメッシュ）", cnote, outline=gpd.GeoDataFrame(geometry=reg_poly.geometry.values, crs="EPSG:6677"), labels=lab, uncovered=uncovered)
    P.mesh_map(m1g.assign(v=m1g.landscape.map({"urban": 0, "agri_mixed": 1, "other_mixed": 2, "forest_dominant": 3})), "v", fig / "map_mesh1km_landscape_type.png", "2014年土地被覆類型（0都市的・1農地混在・2その他混在・3森林卓越）", cnote, outline=gpd.GeoDataFrame(geometry=reg_poly.geometry.values, crs="EPSG:6677"), labels=lab, uncovered=uncovered, vmax=3)
    order_reg = [r for r in rlabels if r in agg_reg.index and agg_reg.loc[r, "coverage"] >= 0.3]
    disp = {r: (f"{rlabels[r]}（収録{agg_reg.loc[r, 'coverage']:.0%}）" if agg_reg.loc[r, "coverage"] < 0.95 else rlabels[r]) for r in order_reg}
    P.region_composition(agg_reg.loc[order_reg], disp, fig / "chart_region_composition.png", note + " 三浦半島は収録7%のため除外。")
    for name, edges in [("rail", RAIL_EDGES), ("station", RAIL_EDGES), ("road_cell_2014", ROAD_EDGES)]:
        order = list(A.bin_distance(np.array([0.0]), edges).categories)
        for rate in ["agri_to_forest_or_wasteland_rate", "building_gross_loss_rate"]:
            P.distance_rates(dr[name]["rates"], rate, order, fig / f"chart_distance_{name}_{rate}.png", f"{DIST_LABELS[name]}からの距離帯（m）別：{RATE_LABELS[rate]}", note + " 距離帯間の差は因果を示さない。", strata)
    log("figures done")

    # 12. publish -------------------------------------------------------------------------------
    figs_out = a.figures_dir
    figs_out.mkdir(parents=True, exist_ok=True)
    for p in sorted(fig.glob("*.png")):
        (figs_out / p.name).write_bytes(p.read_bytes())
    params = dict(sample_mesh2=a.sample_mesh2, permutations=a.permutations, bootstrap=a.bootstrap, rail_edges=[str(e) for e in RAIL_EDGES], road_edges=[str(e) for e in ROAD_EDGES],
                  osm_edges=[str(e) for e in OSM_EDGES], osm_window_wgs84=OSM_WINDOW_WGS84, osm_inner_buffer_m=1000, p32_point_classes=[1, 2, 9], p32_edge_exclusion_m=500,
                  landscape_rules="forest>=0.7; building+transport>=0.5; agri>=0.2; else other (2014 shares per 1km mesh)", context_rule="patch: >=2 of 8 neighbours share the group transition")
    R["parameters"] = params
    R["inputs"] = list(reg.records.values())
    if a.execute:
        outs = []
        for p in sorted(x for x in work.rglob("*") if x.is_file()):
            outs.append(publish_file(data_root, p, str(p.relative_to(work))))
        manifest, rec = write_run_manifest(data_root, work, inputs=R["inputs"], outputs=outs, parameters=params, repo=REPO)
        R["published"] = dict(outputs=outs, manifest=rec)
        log(f"published {len(outs)} files + manifest")
    R["work_dir"] = str(work)
    text = json.dumps(R, ensure_ascii=False, indent=1, default=jsonable)
    a.report_json.write_text(json.dumps(clean(json.loads(text)), ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")
    log(f"report {a.report_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
