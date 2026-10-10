#!/usr/bin/env python3
"""Partitioned FGD edition comparison. All spatial outputs stay on verified Drive."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import uuid
import shutil
from contextlib import nullcontext

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import box
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from kanagawa_ruins.temporal_pipeline import TemporalSettings
from kanagawa_ruins.geo.temporal import building_matches, road_agreement
from kanagawa_ruins.geo.temporal_statistics import grid_support, landuse_proxy
from kanagawa_ruins.catalog import load_layer, list_layers
from kanagawa_ruins.storage.scratch import scratch_job
from kanagawa_ruins.pipeline import authorized, publication_lock, implementation_sha256
from kanagawa_ruins.qa.hashing import sha256
from kanagawa_ruins.raster.io import local_output

LOCAL_ARTIFACT_ROOT = None


def write_parquet(frame,path,job):
    estimate=int(frame.memory_usage(deep=True).sum())+16_000_000
    if isinstance(frame,gpd.GeoDataFrame):
        estimate+=sum(len(w) for w in frame.geometry.to_wkb())
    job.check(estimate)
    frame.to_parquet(path,index=False,compression="zstd")
    job.check()


def save(settings, local, relative):
    """Exclusive, readback-verified derivative; immutable run namespace."""
    if LOCAL_ARTIFACT_ROOT is not None:
        # Offline fallback retains only small aggregate tables and images.
        # Geometries and per-record GIS artifacts remain temporary.
        if local.suffix == ".parquet":
            return dict(status="not_published_drive_quota_block",name=local.name)
        destination=LOCAL_ARTIFACT_ROOT/local.name
        if destination.exists():raise FileExistsError(destination)
        destination.parent.mkdir(parents=True,exist_ok=True)
        with local.open("rb") as src,destination.open("xb") as dst:shutil.copyfileobj(src,dst,1024*1024)
        return dict(status="local_aggregate_or_figure",path=str(destination),sha256=sha256(destination),bytes=destination.stat().st_size)
    destination = settings.output_root / relative
    with publication_lock(settings):
        authorized(settings, destination)
        if destination.exists(): raise FileExistsError(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_name(destination.name + "." + uuid.uuid4().hex + ".partial")
        try:
            with local.open("rb") as src, partial.open("xb") as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)
            digest = sha256(local)
            if sha256(partial) != digest: raise OSError("Drive readback mismatch")
            partial.rename(destination)
            if sha256(destination) != digest: raise OSError("Published readback mismatch")
        finally:
            partial.unlink(missing_ok=True)
    return dict(path=str(destination.relative_to(settings.data_root)), sha256=digest,
                bytes=destination.stat().st_size)


def mesh_bounds(code):
    if len(code) != 6: raise ValueError("Second mesh required")
    y = int(code[:2]) * 2 / 3 + int(code[4]) / 12
    x = int(code[2:4]) + 100 + int(code[5]) / 8
    return gpd.GeoSeries([box(x, y, x + 1/8, y + 1/12)], crs=6668).to_crs(6677).iloc[0]


def attach(frame, admin):
    """Centroid allocation is explicit; no claim of clipped municipal lengths."""
    points = gpd.GeoDataFrame({"row": np.arange(len(frame))}, geometry=frame.geometry.centroid, crs=6677)
    joined = gpd.sjoin(points, admin[["muni_code", "geometry"]], predicate="within", how="left")
    # Boundary ambiguity stays unknown; avoid multiplying records at boundaries.
    joined = joined.drop_duplicates("row").set_index("row").reindex(range(len(frame)))
    out = frame.copy().reset_index(drop=True)
    out["muni_code"] = joined.muni_code.to_numpy()
    out["grid_x"] = np.floor(points.geometry.x / 1000).astype(int)
    out["grid_y"] = np.floor(points.geometry.y / 1000).astype(int)
    return out


def aggregate(frame, era, domain, tolerance, code):
    frame = frame.loc[frame.muni_code.notna()].copy()
    frame["era"] = era; frame["domain"] = domain; frame["tolerance_m"] = tolerance
    frame["source_code"] = code
    frame["record_count"] = 1
    frame["area_m2"] = frame.geometry.area if domain == "building" else 0.
    frame["edge_length_m"] = frame.geometry.length if domain == "road_edge" else 0.
    frame["unmatched_length_m"] = frame.edge_length_m * (1 - frame.get("agreement", 1.))
    frame["iou_sum"] = frame.get("best_iou", 0.)
    keys = ["era", "domain", "tolerance_m", "muni_code", "grid_x", "grid_y", "status"]
    return frame.groupby(keys, dropna=False)[["record_count", "area_m2", "edge_length_m", "unmatched_length_m", "iou_sum"]].sum().reset_index()


def main(job_override=None):
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--ingest-report", default="reports/phase1c1_ingest.json")
    p.add_argument("--report", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--codes", help="Comma-separated second meshes, otherwise all ingested common meshes")
    p.add_argument("--local-pilot-artifacts", help="Quota fallback: only aggregate CSV/PNG retained locally; GIS outputs remain temporary")
    p.add_argument("--skip-landuse",action="store_true",help="Record unavailable auxiliary reads; do not infer mountain classes")
    args = p.parse_args()
    global LOCAL_ARTIFACT_ROOT
    LOCAL_ARTIFACT_ROOT=local_output(args.local_pilot_artifacts) if args.local_pilot_artifacts else None
    if not args.run_id.replace("_", "").isalnum(): raise ValueError("Unsafe run ID")
    target = local_output(args.report)
    settings = TemporalSettings.from_env(); settings.check_mount()
    ingested = json.load(open(args.ingest_report))
    admin_id = "admin__n03__2026_kanagawa"
    admin = load_layer(admin_id).to_crs(6677).dissolve(by="muni_code", as_index=False)
    analysis_mask=admin.geometry.union_all().buffer(20)
    shapely.prepare(analysis_mask)
    available = {}
    quality = {}
    for result in ingested["results"]:
        quality[(result["era"],result["code"])] = result.get("excluded_invalid",{})
        for layer in result["layers"]:
            available[(result["era"], result["code"], layer["layer_id"].split("__")[-1].split("_")[0])] = layer
    common = sorted({c for y,c,k in available if y == "2014" and k == "blda"} &
                    {c for y,c,k in available if y == "2025" and k == "blda"})
    if args.codes: common = [c for c in common if c in args.codes.split(",")]
    report = dict(status="RUNNING", run_id=args.run_id, meshes=common, results=[], errors=[], artifacts=[],
                  implementation_sha256=implementation_sha256(),
                  coverage_claim="selected archives with observed features; feature completeness not established",
                  spatial_allocation="EPSG:6677 centroid allocation, whole area/length per record; boundary totals are not clipped area/length",
                  comparison="2014_2025", tolerances_m=[1,5,10],
                  input_report_sha256=sha256(Path(args.ingest_report)), admin_layer=admin_id)
    target.write_text(json.dumps(report, indent=2))
    chunks = []
    samples = []
    rng = np.random.default_rng(20261011)
    def read(era, code, kind):
        entry = available.get((era, code, kind))
        if not entry: return None
        path = Path(entry["temporary_path"]) if LOCAL_ARTIFACT_ROOT is not None and "temporary_path" in entry else settings.data_root / entry["processed_path"]
        if sha256(path) != entry["output_sha256"]: raise ValueError("Input GeoParquet SHA mismatch")
        return gpd.read_parquet(path)
    with (nullcontext(job_override) if job_override is not None else scratch_job(settings.scratch_limit)) as job:
        for code in common:
            try:
                print("analyzing", code, flush=True)
                boundary = mesh_bounds(code).boundary
                for domain, kind in [("building", "blda"), ("road_edge", "rdedg")]:
                    old, new = read("2014", code, kind), read("2025", code, kind)
                    if old is None or new is None:
                        report["results"].append(dict(code=code, domain=domain, status="indeterminate_missing_feature_member"))
                        continue
                    old=old.loc[shapely.intersects(analysis_mask,old.geometry.to_numpy())].reset_index(drop=True)
                    new=new.loc[shapely.intersects(analysis_mask,new.geometry.to_numpy())].reset_index(drop=True)
                    # Geometric duplicates with differing IDs are reported and
                    # removed within a partition; source polygon fragments at
                    # mesh boundaries are retained as records.
                    duplicates = []
                    for f in [old,new]:
                        f["wkb_key"] = shapely.to_wkb(shapely.normalize(f.geometry.to_numpy()))
                        duplicates.append(int(f.duplicated(["wkb_key","feature_type","orgGILvl","devDate"]).sum()))
                    dedup_columns=["wkb_key","feature_type","orgGILvl","devDate"]
                    old = old.drop_duplicates(dedup_columns).drop(columns="wkb_key").reset_index(drop=True)
                    new = new.drop_duplicates(dedup_columns).drop(columns="wkb_key").reset_index(drop=True)
                    old, new = attach(old, admin), attach(new, admin)
                    for tolerance in [1,5,10]:
                        if domain == "building":
                            left, right, edges = building_matches(old, new, tolerance, coverage_confirmed=True)
                            for f, labels in [(old,left),(new,right)]:
                                f["status"] = labels.status.to_numpy()
                                f["best_iou"] = labels.best_iou.to_numpy()
                                near_edge = f.geometry.distance(boundary) <= tolerance + 1
                                unmatched = f.status.isin(["missing_in_newer_dataset","only_in_newer_dataset"])
                                f.loc[near_edge & unmatched, "status"] = "indeterminate_partition_boundary"
                                if quality.get(("2014",code),{}).get("BldA",0) or quality.get(("2025",code),{}).get("BldA",0):
                                    f.loc[f.status.isin(["missing_in_newer_dataset","only_in_newer_dataset"]),"status"]="indeterminate_geometry_quality"
                            # Stratified by mesh, fixed seed, no ground truth.
                            if tolerance == 5 and len(edges):
                                picked = rng.choice(len(edges), size=min(10,len(edges)), replace=False)
                                for idx in picked:
                                    i,j,iou = edges[idx]
                                    samples.append(dict(mesh=code,old_fid=old.iloc[i].fid,new_fid=new.iloc[j].fid,
                                                        iou=iou,status=old.iloc[i].status,
                                                        old_geometry=old.geometry.iloc[i],new_geometry=new.geometry.iloc[j]))
                                if not any(x.get("kind")=="matching_validation" for x in report["artifacts"]):
                                    i,j,_ = edges[int(picked[0])]
                                    origin = old.geometry.iloc[i].centroid
                                    from shapely.affinity import translate
                                    fig,ax = plt.subplots(figsize=(6,6))
                                    for f,color in [(old.iloc[[i]],"#1565c0"),(new.iloc[[j]],"#ef6c00")]:
                                        gpd.GeoSeries([translate(f.geometry.iloc[0], -origin.x, -origin.y)],crs=6677).boundary.plot(ax=ax,color=color)
                                    ax.set_aspect("equal");ax.set_xlabel("Relative east (m)");ax.set_ylabel("Relative north (m)")
                                    ax.set_title("Real correspondence hypothesis; blue 2014 / orange 2025")
                                    fig.tight_layout();local=job.path/"matching_validation.png";job.check(5_000_000);fig.savefig(local,dpi=150);job.check();plt.close(fig)
                                    report["artifacts"].append(dict(kind="matching_validation", **save(settings,local,f"analysis/{args.run_id}/matching_validation.png")))
                        else:
                            for f, other in [(old,new),(new,old)]:
                                f["agreement"] = road_agreement(f, other, tolerance)
                                f["status"] = np.where(f.agreement >= .9,"spatially_agreeing", "edge_geometry_disagreement")
                                f.loc[f.geometry.distance(boundary) <= tolerance+1,"status"] = "indeterminate_partition_boundary"
                        for era,f in [("2014",old),("2025",new)]:
                            chunks.append(aggregate(f,era,domain,tolerance,code))
                        result = dict(code=code,domain=domain,tolerance_m=tolerance,
                                      old_records=len(old),new_records=len(new),duplicates_removed=duplicates,
                                      old_status=old.status.value_counts().to_dict(),new_status=new.status.value_counts().to_dict())
                        report["results"].append(result)
                        print(domain,tolerance,result["old_status"],flush=True)
                    # Persist record-level results at primary 5m tolerance by
                    # recomputing building labels; road per-tolerance aggregates
                    # remain quantitative and reproducible from the source.
                    if domain == "building":
                        left,right,_ = building_matches(old,new,5,coverage_confirmed=True)
                        for era,f,labels in [("2014",old,left),("2025",new,right)]:
                            f["status_5m"] = labels.status.to_numpy();f["best_iou_5m"] = labels.best_iou.to_numpy()
                            f.loc[(f.geometry.distance(boundary)<=6)&f.status_5m.isin(["missing_in_newer_dataset","only_in_newer_dataset"]),"status_5m"]="indeterminate_partition_boundary"
                            if quality.get(("2014",code),{}).get("BldA",0) or quality.get(("2025",code),{}).get("BldA",0):
                                f.loc[f.status_5m.isin(["missing_in_newer_dataset","only_in_newer_dataset"]),"status_5m"]="indeterminate_geometry_quality"
                            f=f.drop(columns=["status","best_iou"])
                            local=job.path/"matches.parquet";write_parquet(f,local,job)
                            report["artifacts"].append(save(settings,local,f"analysis/{args.run_id}/{code}_{era}_building_matches.parquet"));local.unlink()
            except Exception as e:
                report["errors"].append(dict(code=code,error=repr(e)));print("ERROR",repr(e),flush=True)
            target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
        if chunks:
            stats=pd.concat(chunks,ignore_index=True)
            keys=["era","domain","tolerance_m","muni_code","grid_x","grid_y","status"]
            stats=stats.groupby(keys,dropna=False).sum(numeric_only=True).reset_index()
            try:
                grid=grid_support(admin,stats)
                # Partial regional runs must not interpret all other prefectural
                # cells as observed zeros. Keep support explicit in the artifact.
                coverage=shapely.union_all([mesh_bounds(c) for c in common])
                grid["selected_archive_support_fraction"]=grid.geometry.intersection(coverage).area/grid.geometry.area
                if args.skip_landuse:
                    grid["stratum"]="unavailable_landuse_support"
                    proxy_inputs=[]
                    report["landuse_proxy_status"]="not_run_drive_quota_block"
                else:
                    grid,proxy_summary,proxy_inputs=landuse_proxy(grid)
                eligible=grid.selected_archive_support_fraction>=.999
                report["landuse_proxy_summary"]=[]
                for label,f in grid.loc[eligible].groupby("stratum"):
                    old_n=int(f.count_2014.sum());new_n=int(f.count_2025.sum())
                    report["landuse_proxy_summary"].append(dict(stratum=label,cells=len(f),old_polygon_records=old_n,new_polygon_records=new_n,change_rate=(new_n-old_n)/old_n if old_n else None))
                report["landuse_proxy_inputs"]=proxy_inputs
                local=job.path/"grid_support.parquet";write_parquet(grid,local,job)
                report["artifacts"].append(save(settings,local,f"analysis/{args.run_id}/grid_support.parquet"));local.unlink()
            except Exception as e:
                report["errors"].append(dict(stage="grid_landuse_statistics",error=repr(e)))
            for name,table in [("grid_statistics",stats),("municipality_statistics",stats.drop(columns=["grid_x","grid_y"]).groupby(["era","domain","tolerance_m","muni_code","status"]).sum(numeric_only=True).reset_index())]:
                local=job.path/(name+".csv");job.check(int(table.memory_usage(deep=True).sum())+1_000_000);table.to_csv(local,index=False);job.check()
                report["artifacts"].append(save(settings,local,f"analysis/{args.run_id}/{name}.csv"));local.unlink()
            # Published maps use aggregate municipalities only. Missing analyzed
            # support stays NaN instead of a false zero.
            for domain,measure in [("building","record_count"),("road_edge","edge_length_m")]:
                table=stats[(stats.domain==domain)&(stats.tolerance_m==5)].groupby(["muni_code","era"])[measure].sum().unstack()
                if {"2014","2025"}<=set(table.columns):
                    table["change"]=table["2025"]-table["2014"]
                    layer=admin.merge(table[["change"]],left_on="muni_code",right_index=True,how="left")
                    fig,ax=plt.subplots(figsize=(8,7));layer.plot(column="change",cmap="RdBu",legend=True,ax=ax,missing_kwds={"color":"lightgrey"})
                    ax.set_axis_off();ax.set_title(f"{domain}: recorded {measure} difference, 2025 minus 2014\nSelected mesh intersections; municipalities may be partial")
                    fig.tight_layout();local=job.path/(domain+"_regional_map.png");job.check(5_000_000);fig.savefig(local,dpi=150);job.check();plt.close(fig)
                    report["artifacts"].append(save(settings,local,f"analysis/{args.run_id}/{local.name}"));local.unlink()
            # Distribution uses paired occupied grid cells; empty cells absent
            # from both editions are explicitly outside this histogram.
            table=stats[(stats.domain=="building")&(stats.tolerance_m==5)].groupby(["grid_x","grid_y","era"]).record_count.sum().unstack(fill_value=0)
            if {"2014","2025"}<=set(table.columns):
                difference=table["2025"]-table["2014"]
                report["grid_distribution"]=dict(occupied_grid_cells=len(table),change_quantiles=difference.quantile([0,.1,.25,.5,.75,.9,1]).to_dict())
                fig,ax=plt.subplots(figsize=(8,5));ax.hist(difference,bins=50);ax.set_xlabel("Recorded polygon count change per occupied projected 1km cell");ax.set_ylabel("Cells");fig.tight_layout()
                local=job.path/"change_distribution.png";job.check(5_000_000);fig.savefig(local,dpi=150);job.check();plt.close(fig)
                report["artifacts"].append(save(settings,local,f"analysis/{args.run_id}/{local.name}"));local.unlink()
            report["summary"] = stats.groupby(["era","domain","tolerance_m","status"])[["record_count","area_m2","edge_length_m","unmatched_length_m"]].sum().reset_index().to_dict(orient="records")
        if samples:
            table=pd.DataFrame(samples)
            table["old_geometry"] = shapely.to_wkb(table.old_geometry.to_numpy()).tolist()
            table["new_geometry"] = shapely.to_wkb(table.new_geometry.to_numpy()).tolist()
            local=job.path/"review_samples.parquet";write_parquet(table,local,job)
            report["validation_sample_metadata"]=[{k:v for k,v in r.items() if k not in {"old_geometry","new_geometry"}} for r in samples]
            report["artifacts"].append(save(settings,local,f"analysis/{args.run_id}/review_samples.parquet"));local.unlink()
        report["scratch_peak_bytes"]=job.peak_bytes
    report["status"]=("PARTIAL_REAL_DATA_PILOT_DRIVE_BLOCKED" if LOCAL_ARTIFACT_ROOT is not None else "COMPLETED_SELECTED_MESHES") if not report["errors"] else "PARTIAL_FAILURE"
    report["not_implemented"]=["2008 common coverage mask and comparisons", "DEM-defined urban versus mountain strata", "spatial autocorrelation", "labelled detection accuracy", "road centreline connectivity"]
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    return bool(report["errors"])


if __name__=="__main__":raise SystemExit(main())
