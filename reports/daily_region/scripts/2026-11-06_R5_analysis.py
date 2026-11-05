"""R5（相模原・旧津久井郡を除く）2週目の再計算と、非公開側への消失候補出力.

公開 JSON には件数だけを書く。名称と緯度経度は
`/opt/cursor/artifacts/kanagawa_private/2026-11-06_R5/` に出す。

閾値は結果を見る前に固定した（このファイル先頭の定数）。
"""

from __future__ import annotations

import csv
import json
import math
import re
import unicodedata
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, shape

ROOT = Path(__file__).resolve().parents[3]
DRIVE = Path.home() / "drive_r5"
PREV = Path("/opt/cursor/artifacts/kanagawa_private/supplemental_data")
OUT_PRIV = Path("/opt/cursor/artifacts/kanagawa_private/2026-11-06_R5")
OUT_SUP = Path("/opt/cursor/artifacts/kanagawa_private/supplemental_data/2026-11-06")
PUBLIC = ROOT / "reports/daily_region/data/2026-11-06_R5_week2_public.json"

# 週1が「5セル以上 28.6%」と書いた値は、1〜2セルの補集合である。
# 真の share_>=5 が 20% 未満で、補集合との差が 10 ポイント以上なら、
# その文は 5 セル以上そのものではない。
GE5_MAX = 0.20
COMPLEMENT_GAP = 0.10
# 都市的転換型の支持に必要な「建物用地の純増」。符号の閾値は週1のまま。
# 森林・荒地が建物総減少の 10% 未満なら、純減の主たる名前付き行き先ではない。
FOREST_OF_BUILDING_LOSS_MAX = 0.10
MIN_RATE_BASE_KM2 = 0.50

STATION_TYPES = {"かつての鉄道駅", "廃駅", "鉄道駅", "貨物駅", "鉄道の地上駅",
                 "路面電車停留場", "モノレール駅", "信号場"}
PLACE_TYPES = {"廃寺", "仏教寺院", "御所", "日本の幕府", "星形要塞", "台場",
               "窯跡", "関所", "飛行場", "御殿・御茶屋", "灯台", "木造灯台"}
EXCLUDE_TYPES = {"日本の廃止市区町村", "廃止された郡", "事件", "軍事基地", "海軍兵器廠",
                 "レストラン", "ホテル", "ショッピングモール", "温泉", "水族館"}
GENERIC = {"神社", "稲荷", "八幡", "八幡神社", "八幡宮", "神明", "神明社", "寺", "院"}


def norm(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKC", value)
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"（[^）]*）", "", text)
    text = re.sub(r"\([^)]*\)", "", text)
    return text.replace("・", "")


def stem_of(value: str | None) -> str:
    text = norm(value)
    return re.sub(r"(駅|跡|小学校|中学校|高等学校|高校|大学|病院|信号所|信号場)$", "", text)


def hav_m(lon1, lat1, lon2, lat2) -> float:
    radius = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(min(1.0, a)))


def tile_xy(lon: float, lat: float, zoom: int = 15) -> tuple[int, int]:
    n = 2 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    lat_r = math.radians(lat)
    y = int((1 - math.log(math.tan(lat_r) + 1 / math.cos(lat_r)) / math.pi) / 2 * n)
    return x, y


def load_region_table(path: Path) -> dict:
    data = json.loads(path.read_text())
    reg = {name: dict(zip(data["aggregates"]["region"]["columns"], row))
           for name, row in zip(data["aggregates"]["region"]["index"],
                                data["aggregates"]["region"]["data"])}
    mcols = data["aggregates"]["municipality"]["columns"]
    wards = [dict(zip(mcols, row)) for row in data["aggregates"]["municipality"]["data"]
             if row[mcols.index("muni_code")] in ("14151", "14152", "14153")]
    cc = data["transitions"]["component_class_share_by_region"]
    comp = {name: dict(zip(cc["columns"], row))
            for name, row in zip(cc["index"], cc["data"])}
    focus = data["transitions"]["focus_by_region"]
    focus_rows = {}
    for row in focus["data"]:
        rec = dict(zip(focus["columns"], row))
        if rec["region"] in ("R5_sagamihara", "R6_tsukui"):
            focus_rows[(rec["region"], rec["transition"])] = rec
    rl = data["aggregates"]["region_landscape"]
    landscapes = {}
    for idx, row in zip(rl["index"], rl["data"]):
        if idx[0] == "R5_sagamihara":
            landscapes[idx[1]] = dict(zip(rl["columns"], row))
    return {"reg": reg, "wards": wards, "comp": comp, "focus": focus_rows,
            "landscapes": landscapes, "cultural": data.get("cultural", {})}


def public_numbers(tables: dict) -> dict:
    r5 = tables["reg"]["R5_sagamihara"]
    r6 = tables["reg"]["R6_tsukui"]
    comp = tables["comp"]["R5_sagamihara"]
    s1, s2 = comp["share_1"], comp["share_2"]
    s34, s5 = comp["share_3-4"], comp["share_>=5"]
    changed = comp["changed_km2"]
    complement = 1 - s1 - s2
    b_loss = r5["building_loss_km2"]
    b_forest = r5["building_to_forest_km2"] + r5["building_to_wasteland_km2"]
    wards = {row["muni_code"]: row for row in tables["wards"]}
    central = wards["14152"]["building_net_change_km2"]
    south = wards["14153"]["building_net_change_km2"]
    midori_published = wards["14151"]["building_net_change_km2"]
    h1 = (r6["agri_to_forest_rate"] > r5["agri_to_forest_rate"]
          and r6["building_to_forest_or_wasteland_rate"] > r5["building_to_forest_or_wasteland_rate"]
          and r6["agri_to_forest_km2"] > r5["agri_to_forest_km2"]
          and r6["building_to_forest_km2"] > r5["building_to_forest_km2"])
    h2 = (b_forest / b_loss) < FOREST_OF_BUILDING_LOSS_MAX
    h3 = (s5 < GE5_MAX and (complement - s5) >= COMPLEMENT_GAP
          and tables["focus"][("R5_sagamihara", "building->forest")]["size_>=5_share"] == 0
          and tables["focus"][("R5_sagamihara", "agri->forest")]["size_>=5_share"] == 0)
    h4 = central < 0 and south < 0 and r5["building_net_change_km2"] < 0
    bases = {
        "R5_agri": r5["agri_2014_share"] * r5["land_km2"],
        "R6_agri": r6["agri_2014_share"] * r6["land_km2"],
        "R5_building": r5["building_2014_share"] * r5["land_km2"],
        "R6_building": r6["building_2014_share"] * r6["land_km2"],
    }
    return {
        "h1_supported": h1,
        "h2_supported": h2,
        "h3_supported": h3,
        "h4_supported": h4,
        "rate_bases_km2": bases,
        "rate_bases_all_at_least_0_5": all(v >= MIN_RATE_BASE_KM2 for v in bases.values()),
        "r5": {
            "land_km2": r5["land_km2"],
            "n_cells": r5["n_cells"],
            "agri_to_forest_rate": r5["agri_to_forest_rate"],
            "agri_to_forest_km2": r5["agri_to_forest_km2"],
            "building_to_forest_or_wasteland_rate": r5["building_to_forest_or_wasteland_rate"],
            "building_to_forest_km2": r5["building_to_forest_km2"],
            "building_to_wasteland_km2": r5["building_to_wasteland_km2"],
            "building_loss_km2": b_loss,
            "building_gain_km2": r5["building_gain_km2"],
            "building_net_km2": r5["building_net_change_km2"],
            "forest_wasteland_share_of_building_loss": b_forest / b_loss,
            "building_loss_residual_km2": b_loss - b_forest,
        },
        "r6": {
            "agri_to_forest_rate": r6["agri_to_forest_rate"],
            "agri_to_forest_km2": r6["agri_to_forest_km2"],
            "building_to_forest_or_wasteland_rate": r6["building_to_forest_or_wasteland_rate"],
            "building_to_forest_km2": r6["building_to_forest_km2"],
            "building_net_km2": r6["building_net_change_km2"],
        },
        "components": {
            "share_1": s1,
            "share_2": s2,
            "share_3_4": s34,
            "share_ge5": s5,
            "changed_km2": changed,
            "ge5_km2": s5 * changed,
            "complement_of_1_2": complement,
            "complement_km2": complement * changed,
            "gap_pp": (complement - s5) * 100,
        },
        "wards_published_building_net_km2": {
            "中央区": central,
            "南区": south,
            "緑区_区行はR6を含む": midori_published,
        },
        "focus_ge5": {
            "building_to_forest": tables["focus"][("R5_sagamihara", "building->forest")]["size_>=5_share"],
            "agri_to_forest": tables["focus"][("R5_sagamihara", "agri->forest")]["size_>=5_share"],
            "building_to_forest_cells": tables["focus"][("R5_sagamihara", "building->forest")]["cells"],
            "agri_to_forest_cells": tables["focus"][("R5_sagamihara", "agri->forest")]["cells"],
        },
        "landscape_types_are_region_only": True,
        "landscape_names": sorted(tables["landscapes"]),
    }


def fetch_anno(x: int, y: int, dest: Path) -> dict | None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return json.loads(dest.read_text())
    url = f"https://cyberjapandata.gsi.go.jp/xyz/experimental_anno/15/{x}/{y}.geojson"
    req = urllib.request.Request(url, headers={"User-Agent": "kanagawa-ruins-search/2026-11-06"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
    except Exception as exc:
        dest.with_suffix(".error").write_text(f"{type(exc).__name__}: {exc}\n{url}\n")
        return None
    dest.write_bytes(raw)
    return json.loads(raw)


def main() -> None:
    tables = load_region_table(ROOT / "reports/phase1c2_results.json")
    numbers = public_numbers(tables)
    cells = gpd.read_parquet(
        DRIVE / "data/processed/phase1c/claude/phase1c2-claude-0.2.0/geoparquet"
        / "cells_landuse_change_2014_2021.parquet")
    r5_cells = cells[cells["region"] == "R5_sagamihara"].copy()
    if len(r5_cells) != 8646:
        raise SystemExit(f"R5 cells {len(r5_cells)} != 8646")
    slice_net = {}
    for name, group in r5_cells.groupby("muni_name"):
        b14 = group.loc[group["grp2014"] == "building", "area_m2"].sum() / 1e6
        b21 = group.loc[group["grp2021"] == "building", "area_m2"].sum() / 1e6
        slice_net[name] = {"building_2014_km2": b14, "building_net_km2": b21 - b14,
                           "n_cells": int(len(group))}
    numbers["r5_cell_slices_building_net"] = slice_net
    numbers["r5_cell_slices_all_negative"] = all(
        row["building_net_km2"] < 0 for row in slice_net.values())
    focus = r5_cells[
        ((r5_cells["grp2014"] == "building") & (r5_cells["grp2021"] == "forest"))
        | ((r5_cells["grp2014"] == "agri") & (r5_cells["grp2021"] == "forest"))
    ].copy()
    n_bf = int(((r5_cells.grp2014 == "building") & (r5_cells.grp2021 == "forest")).sum())
    n_af = int(((r5_cells.grp2014 == "agri") & (r5_cells.grp2021 == "forest")).sum())
    if n_bf != 14 or n_af != 3:
        raise SystemExit(f"focus cells b2f={n_bf} a2f={n_af}")
    focus_cent = gpd.GeoDataFrame(
        focus.drop(columns="geometry"),
        geometry=focus.geometry.centroid,
        crs=focus.crs,
    ).to_crs(4326)
    focus_ll = focus_cent
    focus_ll["lon"] = focus_ll.geometry.x
    focus_ll["lat"] = focus_ll.geometry.y

    OUT_SUP.mkdir(parents=True, exist_ok=True)
    tile_dir = OUT_SUP / "gsi_experimental_anno_z15"
    tiles = {}
    for _, row in focus_ll.iterrows():
        tiles.setdefault(tile_xy(row["lon"], row["lat"]), []).append(row["code"] if "code" in row else None)
    anno_features = []
    tile_status = []
    for (x, y), _codes in sorted(tiles.items()):
        path = tile_dir / f"15_{x}_{y}.geojson"
        data = fetch_anno(x, y, path)
        ok = data is not None
        tile_status.append({"z": 15, "x": x, "y": y, "ok": ok,
                            "features": 0 if not ok else len(data.get("features", []))})
        if not ok:
            continue
        for feat in data.get("features", []):
            geom = shape(feat["geometry"])
            props = feat.get("properties") or {}
            anno_features.append({"knj": props.get("knj") or "", "ftCode": props.get("ftCode"),
                                  "annoCtg": props.get("annoCtg"), "geometry": geom})

    shrine_cells = 0
    if anno_features:
        anno_gdf = gpd.GeoDataFrame(anno_features, geometry="geometry", crs="EPSG:4326").to_crs(focus.crs)
        shrine_anno = anno_gdf[anno_gdf["knj"].fillna("").str.contains("神社|寺院|鳥居")]
        if len(shrine_anno):
            hit = gpd.sjoin(focus, shrine_anno[["geometry"]], how="inner", predicate="intersects")
            shrine_cells = int(hit.index.nunique())
    numbers["gsi_anno"] = {
        "zoom": 15,
        "unique_tiles": len(tiles),
        "tiles_ok": sum(1 for t in tile_status if t["ok"]),
        "focus_cells": int(len(focus)),
        "focus_cells_with_shrine_annotation": shrine_cells,
        "note": "現行の注記。旧版地形図の鳥居記号ではない。",
    }

    # 相模原市文化財（現存台帳）を R5 セルに載せる。座標が無い行は数えない。
    bunk = pd.read_csv(DRIVE / "data/raw/sagamihara_cultural_assets/bunkazai.csv", dtype=str)
    bunk["lat"] = pd.to_numeric(bunk["緯度"], errors="coerce")
    bunk["lon"] = pd.to_numeric(bunk["経度"], errors="coerce")
    located = bunk.dropna(subset=["lat", "lon"])
    bunk_gdf = gpd.GeoDataFrame(
        located, geometry=[Point(xy) for xy in zip(located["lon"], located["lat"])], crs="EPSG:4326"
    ).to_crs(r5_cells.crs)
    bunk_in = gpd.sjoin(bunk_gdf, r5_cells[["muni_name", "region", "geometry"]], how="inner", predicate="within")
    bunk_in = bunk_in[~bunk_in.index.duplicated(keep="first")]
    shrine_mask = bunk_in["名称"].fillna("").str.contains("神社|神宮|社")
    numbers["bunkazai"] = {
        "rows": int(len(bunk)),
        "rows_with_coordinates": int(len(located)),
        "in_r5_cells": int(len(bunk_in)),
        "in_r5_name_has_sha": int(shrine_mask.sum()),
        "by_muni": bunk_in["muni_name"].value_counts().to_dict(),
    }

    # 2026-11-05 に取得済みの OSM / Wikidata を R5 セルで再切出しする。再ダウンロードしない。
    osm_path = PREV / "osm_features_2026-11-04.jsonl"
    wd_path = PREV / "wikidata_ended_kanagawa_2026-11-05.json"
    worship = []
    rail = []
    if osm_path.exists():
        for line in osm_path.open():
            row = json.loads(line)
            if row.get("kind") == "worship":
                worship.append(row)
    rail_path = PREV / "osm_rail_2026-11-04.jsonl"
    if rail_path.exists():
        for line in rail_path.open():
            rail.append(json.loads(line))
    worship_gdf = gpd.GeoDataFrame(
        worship, geometry=[Point(r["lon"], r["lat"]) for r in worship], crs="EPSG:4326"
    ).to_crs(r5_cells.crs) if worship else gpd.GeoDataFrame(geometry=[], crs=r5_cells.crs)
    worship_in = gpd.sjoin(worship_gdf, r5_cells[["geometry"]], how="inner", predicate="within") if len(worship_gdf) else worship_gdf
    numbers["osm_worship_in_r5_cells"] = int(len(worship_in))

    matched_shrines = 0
    if int(shrine_mask.sum()) and len(worship_gdf):
        shrines = bunk_in[shrine_mask]
        near = gpd.sjoin_nearest(shrines[["名称", "geometry"]], worship_gdf[["geometry"]],
                                 how="left", distance_col="dist_m")
        matched_shrines = int((near["dist_m"] <= 200).sum())
    numbers["bunkazai_sha_within_200m_of_osm_worship"] = matched_shrines

    candidates = []
    rejected_still = []
    excluded = Counter()
    if wd_path.exists():
        wd = json.loads(wd_path.read_text())
        items = {}
        for row in wd["results"]["bindings"]:
            iid = row["item"]["value"].rsplit("/", 1)[-1]
            slot = items.setdefault(iid, {"id": iid, "label": row.get("itemLabel", {}).get("value", ""),
                                          "end": (row.get("end", {}).get("value") or "")[:10],
                                          "coord": row.get("coord", {}).get("value", ""), "types": set()})
            if "typeLabel" in row:
                slot["types"].add(row["typeLabel"]["value"])
        points, meta = [], []
        for item in items.values():
            types = item["types"]
            if types <= {"日本の廃止市区町村"} or types == {"廃止された郡"} or (
                    "日本の廃止市区町村" in types and not (types & (STATION_TYPES | PLACE_TYPES))):
                excluded["admin_merger"] += 1
                continue
            if types & EXCLUDE_TYPES and not (types & (STATION_TYPES | PLACE_TYPES)):
                excluded["other_type"] += 1
                continue
            if not item["coord"].startswith("Point("):
                continue
            if not (types & (STATION_TYPES | PLACE_TYPES)):
                continue
            lon_s, lat_s = item["coord"][len("Point("):-1].split()
            points.append(Point(float(lon_s), float(lat_s)))
            meta.append(item)
        if points:
            wd_gdf = gpd.GeoDataFrame(meta, geometry=points, crs="EPSG:4326").to_crs(r5_cells.crs)
            joined = gpd.sjoin(wd_gdf, r5_cells[["muni_name", "grp2014", "grp2021", "geometry"]],
                               how="inner", predicate="within")
            joined = joined[~joined.index.duplicated(keep="first")]
            for _, rec in joined.iterrows():
                label = rec["label"]
                stem = stem_of(label)
                if len(stem) < 2 or stem in GENERIC:
                    excluded["generic"] += 1
                    continue
                lon = float(rec["coord"].split()[0][len("Point("):])
                lat = float(rec["coord"].split()[1][:-1])
                # same stem in current OSM worship/name within 400 m, or bunkazai name
                still = False
                pt = rec.geometry
                def stem_within(rows, gdf, meters):
                    if not len(gdf):
                        return False
                    dists = gdf.geometry.distance(pt)
                    for idx, dist in dists.items():
                        if dist > meters:
                            continue
                        other = stem_of((rows[idx].get("tags") or {}).get("name"))
                        if other and other == stem:
                            return True
                    return False
                rail_gdf = gpd.GeoDataFrame(
                    rail, geometry=[Point(r["lon"], r["lat"]) for r in rail], crs="EPSG:4326"
                ).to_crs(r5_cells.crs) if rail else gpd.GeoDataFrame(geometry=[], crs=r5_cells.crs)
                if stem_within(worship, worship_gdf, 400) or stem_within(rail, rail_gdf, 400):
                    still = True
                    rejected_still.append({
                        "muni_name": rec["muni_name"],
                        "name": label,
                        "lat": lat,
                        "lon": lon,
                        "source_id": rec["id"],
                        "end": rec["end"],
                    })
                if not still and len(bunk_in):
                    bd = bunk_in.geometry.distance(pt)
                    for dist, name in zip(bd, bunk_in["名称"].tolist()):
                        if stem_of(name) == stem and dist <= 400:
                            still = True
                            break
                if still:
                    excluded["still_named"] += 1
                    continue
                types = rec["types"] if isinstance(rec["types"], set) else set(rec["types"])
                category = "station" if types & STATION_TYPES else "facility"
                candidates.append({
                    "muni_name": rec["muni_name"],
                    "name": label,
                    "lat": lat,
                    "lon": lon,
                    "category": category,
                    "confidence": "中",
                    "confidence_reason": "Wikidataの終了日と座標があり、R5セル内で、2026年OSM礼拝施設と相模原市文化財CSVの同じ語幹が400m以内に無い。地理院の旧版地形図は未照合のため高にしない。",
                    "evidence_present": f"Wikidata {rec['id']} 終了日 {rec['end']} 型 { '、'.join(sorted(types)) }",
                    "evidence_absent": "OSM 2026-11-04 抽出の礼拝施設と bunkazai.csv に同じ語幹が400m以内に無い。旧版地形図の鳥居記号は未取得。",
                    "lu2014": rec["grp2014"],
                    "lu2021": rec["grp2021"],
                    "source_id": rec["id"],
                })
    numbers["lost_site_excluded"] = dict(excluded)
    # ids
    candidates.sort(key=lambda c: (c["muni_name"], c["category"], c["name"]))
    for i, cand in enumerate(candidates, start=1):
        cand["id"] = f"R5-{i:03d}"
    by_muni = Counter(c["muni_name"] for c in candidates)
    by_conf = Counter(c["confidence"] for c in candidates)
    by_cat = Counter(c["category"] for c in candidates)
    numbers["lost_sites"] = {
        "total": len(candidates),
        "高": by_conf.get("高", 0),
        "中": by_conf.get("中", 0),
        "低": by_conf.get("低", 0),
        "by_category": dict(by_cat),
        "by_municipality": [
            {"muni_name": name, "total": count,
             "ids": [c["id"] for c in candidates if c["muni_name"] == name]}
            for name, count in sorted(by_muni.items())
        ],
        "shrine_candidates": 0,
        "old_map_torii_compared": False,
    }
    # leak check
    blob = json.dumps({k: v for k, v in numbers.items()}, ensure_ascii=False, default=str)
    for cand in candidates:
        if cand["name"] in blob:
            raise SystemExit("public json contains a candidate name")
    PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC.write_text(json.dumps(numbers, ensure_ascii=False, indent=2, default=str) + "\n")

    OUT_PRIV.mkdir(parents=True, exist_ok=True)
    fields = ["id", "muni_name", "name", "lat", "lon", "category", "confidence",
              "confidence_reason", "evidence_present", "evidence_absent", "lu2014", "lu2021", "source_id"]
    with (OUT_PRIV / "candidates.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for cand in candidates:
            row = dict(cand)
            row["lat"] = f"{cand['lat']:.7f}"
            row["lon"] = f"{cand['lon']:.7f}"
            writer.writerow(row)
    lines = ["# 非公開: R5 2026-11-06 消失候補", "",
             "名称と座標を含む。リポジトリには置かない。",
             f"候補 {len(candidates)} 件。高確度は旧版地形図未照合のため 0。", ""]
    if not candidates:
        lines.append("採用した候補は無い。")
        lines.append("旧版地形図の鳥居記号は、ラスタが添付に無く、今昔マップのタイル一括取得をしないため照合していない。")
    if rejected_still:
        lines.append("")
        lines.append("## 不採用（現行OSMに同じ語幹が残る）")
        lines.append("")
        for rec in rejected_still:
            lines.append(
                f"- {rec['muni_name']} {rec['name']} {rec['lat']:.7f},{rec['lon']:.7f} "
                f"{rec['source_id']} 終了日 {rec['end']}。2026年OSMの鉄道または礼拝に同じ語幹が400m以内。"
            )
    for cand in candidates:
        lines += [f"## {cand['id']}", "",
                  f"- 市区町村: {cand['muni_name']}",
                  f"- 名称: {cand['name']}",
                  f"- 緯度: {cand['lat']:.7f}",
                  f"- 経度: {cand['lon']:.7f}",
                  f"- 種別: {cand['category']}",
                  f"- 確度: {cand['confidence']}",
                  f"- 理由: {cand['confidence_reason']}",
                  f"- あった資料: {cand['evidence_present']}",
                  f"- 無い資料: {cand['evidence_absent']}",
                  f"- 土地利用: {cand['lu2014']} → {cand['lu2021']}", ""]
    (OUT_PRIV / "lost_sites_R5.md").write_text("\n".join(lines) + "\n")

    prov = {
        "source_id": "gsi_experimental_anno_z15_r5_focus",
        "source_url_pattern": "https://cyberjapandata.gsi.go.jp/xyz/experimental_anno/15/{x}/{y}.geojson",
        "source_page": "https://maps.gsi.go.jp/development/ichiran.html",
        "retrieved": "2026-11-06",
        "license": "国土地理院コンテンツ利用規約（出典明示）",
        "scope": "R5の建物用地→森林14セルと農地→森林3セルの重心が落ちるz15タイルのみ。全市一括ではない。旧版地形図ではない。",
        "tiles": tile_status,
    }
    with (OUT_SUP / "provenance_supplemental.jsonl").open("w") as handle:
        handle.write(json.dumps(prov, ensure_ascii=False) + "\n")
        handle.write(json.dumps({
            "source_id": "reused_osm_wikidata_2026-11-05",
            "retrieved_original": "2026-11-05",
            "reused_on": "2026-11-06",
            "license": "OSM ODbL; Wikidata CC0",
            "paths": [str(osm_path), str(wd_path)],
            "note": "再ダウンロードしていない。R5セルで切り出した。",
        }, ensure_ascii=False) + "\n")
    print(json.dumps({
        "h1": numbers["h1_supported"], "h2": numbers["h2_supported"],
        "h3": numbers["h3_supported"], "h4": numbers["h4_supported"],
        "ge5": numbers["components"]["share_ge5"],
        "complement": numbers["components"]["complement_of_1_2"],
        "slices_negative": numbers["r5_cell_slices_all_negative"],
        "gsi_tiles": numbers["gsi_anno"]["unique_tiles"],
        "gsi_ok": numbers["gsi_anno"]["tiles_ok"],
        "shrine_anno_cells": shrine_cells,
        "candidates": len(candidates),
        "bunkazai_in_r5": numbers["bunkazai"]["in_r5_cells"],
        "osm_worship_r5": numbers["osm_worship_in_r5_cells"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
