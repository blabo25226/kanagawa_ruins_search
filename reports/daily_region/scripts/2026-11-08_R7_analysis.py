"""R7（県西）2週目の再計算と、非公開側への消失候補メモ.

公開 JSON には件数だけを書く。名称と緯度経度は
`/opt/cursor/artifacts/kanagawa_private/2026-11-08_R7/` に出す。
新規取得した注記タイルは、同日の tar.gz にだけ入れる。
"""

from __future__ import annotations

import csv
import json
import math
import tarfile
import urllib.request
from collections import Counter
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, shape

ROOT = Path(__file__).resolve().parents[3]
DRIVE = Path.home() / "drive_r7"
PREV = Path("/opt/cursor/artifacts/kanagawa_private/supplemental_data")
OUT_PRIV = Path("/opt/cursor/artifacts/kanagawa_private/2026-11-08_R7")
PUBLIC = ROOT / "reports" / "daily_region" / "data" / "2026-11-08_R7_week2_public.json"
TAR = Path("/opt/cursor/artifacts/kanagawa_private/supplemental_2026-11-08.tar.gz")
TMP = Path("/tmp/r7_anno_20261108")

# 週1の 11.3% が share_>=5 そのものか、補集合かを 1 ポイントで判定する。
# 補集合との差が 10 ポイント以上なら、補集合を 5 セル以上と呼ばない。
GE5_CITED = 0.113
GE5_MATCH = 0.01
COMPLEMENT_GAP = 0.10
# 公開レポート §2 の県西列。農地の減少先であり、総増加の出所ではない。
PUBLISHED_AGRI_TO_BUILDING_KM2 = 0.49
MIN_RATE_BASE_KM2 = 0.50
MOUNTAIN = ("山北町", "松田町")
PLAIN = ("中井町", "大井町", "開成町")
HELD_OUT = ("南足柄市",)
MISSING = ("小田原市", "箱根町", "真鶴町", "湯河原町")

STATION_TYPES = {"かつての鉄道駅", "廃駅", "鉄道駅", "貨物駅", "鉄道の地上駅",
                 "路面電車停留場", "モノレール駅", "信号場"}
PLACE_TYPES = {"廃寺", "仏教寺院", "御所", "台場", "窯跡", "関所", "飛行場", "灯台", "木造灯台"}


def stem_of(value) -> str:
    import re
    import unicodedata
    if not isinstance(value, str) or not value:
        return ""
    text = unicodedata.normalize("NFKC", value)
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"（[^）]*）", "", text)
    text = re.sub(r"\([^)]*\)", "", text)
    return re.sub(r"(駅|跡|小学校|中学校|高等学校|高校|大学|病院|信号所|信号場)$", "", text)


def tile_xy(lon: float, lat: float, zoom: int = 15) -> tuple[int, int]:
    n = 2 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    lat_r = math.radians(lat)
    y = int((1 - math.log(math.tan(lat_r) + 1 / math.cos(lat_r)) / math.pi) / 2 * n)
    return x, y


def fetch_anno(x: int, y: int, dest: Path) -> dict | None:
    if dest.exists() and dest.stat().st_size > 0:
        return json.loads(dest.read_text())
    url = f"https://cyberjapandata.gsi.go.jp/xyz/experimental_anno/15/{x}/{y}.geojson"
    req = urllib.request.Request(url, headers={"User-Agent": "kanagawa-ruins-search/2026-11-08"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
    except Exception as exc:
        dest.with_suffix(".error").write_text(f"{type(exc).__name__}: {exc}\n{url}\n")
        return None
    dest.write_bytes(raw)
    return json.loads(raw)


def main() -> None:
    data = json.loads((ROOT / "reports" / "phase1c2_results.json").read_text())
    reg = {n: dict(zip(data["aggregates"]["region"]["columns"], r))
           for n, r in zip(data["aggregates"]["region"]["index"], data["aggregates"]["region"]["data"])}
    r7 = reg["R7_kensei"]
    cc = data["transitions"]["component_class_share_by_region"]
    comp = {n: dict(zip(cc["columns"], r)) for n, r in zip(cc["index"], cc["data"])}["R7_kensei"]
    focus = {}
    block = data["transitions"]["focus_by_region"]
    for row in block["data"]:
        rec = dict(zip(block["columns"], row))
        if rec["region"] == "R7_kensei":
            focus[rec["transition"]] = rec
    rl = data["aggregates"]["region_landscape"]
    landscapes = {}
    for idx, row in zip(rl["index"], rl["data"]):
        if idx[0] == "R7_kensei":
            landscapes[idx[1]] = dict(zip(rl["columns"], row))
    mcols = data["aggregates"]["municipality"]["columns"]
    munis = [dict(zip(mcols, row)) for row in data["aggregates"]["municipality"]["data"]
             if dict(zip(mcols, row)).get("region") == "R7_kensei"]

    s1, s2, s34, s5 = comp["share_1"], comp["share_2"], comp["share_3-4"], comp["share_>=5"]
    changed = comp["changed_km2"]
    complement = 1 - s1 - s2
    agri_gain = r7["agri_net_change_km2"] + r7["agri_loss_km2"]
    forest_to_agri = focus["agri->forest"]["reverse_area_km2"]
    waste_to_agri = focus["agri->wasteland"]["reverse_area_km2"]
    agri_named = forest_to_agri + waste_to_agri
    agri_remainder = agri_gain - agri_named
    b_gain = r7["building_gain_km2"]
    forest_to_b = focus["building->forest"]["reverse_area_km2"]
    waste_to_b = focus["building->wasteland"]["reverse_area_km2"]
    b_remainder = b_gain - forest_to_b - waste_to_b
    gain_cols = [c for c in rl["columns"] if "forest_to_agri" in c or c.startswith("agri_from")]
    h1 = (len(gain_cols) == 0
          and agri_remainder > 0
          and abs(agri_remainder - PUBLISHED_AGRI_TO_BUILDING_KM2) >= 0
          and PUBLISHED_AGRI_TO_BUILDING_KM2 != round(agri_remainder, 2))
    h2 = b_remainder > 0 and "building_from_agri_km2" not in rl["columns"]
    h3 = (abs(s5 - GE5_CITED) < GE5_MATCH
          and (complement - s5) >= COMPLEMENT_GAP
          and focus["building->forest"]["size_>=5_share"] == 0
          and focus["agri->forest"]["size_>=5_share"] == 0)

    def group_sum(names, key):
        return sum(row[key] for row in munis if row["muni_name"] in names)

    mountain_land = group_sum(MOUNTAIN, "land_km2")
    plain_land = group_sum(PLAIN, "land_km2")
    mountain_agri_net = group_sum(MOUNTAIN, "agri_net_change_km2")
    plain_agri_net = group_sum(PLAIN, "agri_net_change_km2")
    mountain_agri_base = sum(row["agri_2014_share"] * row["land_km2"] for row in munis if row["muni_name"] in MOUNTAIN)
    plain_agri_base = sum(row["agri_2014_share"] * row["land_km2"] for row in munis if row["muni_name"] in PLAIN)
    missing_rows = [row for row in munis if row["muni_name"] in MISSING]
    h4 = (mountain_land / r7["land_km2"] >= 0.80
          and plain_agri_net > mountain_agri_net
          and mountain_agri_base >= MIN_RATE_BASE_KM2
          and plain_agri_base >= MIN_RATE_BASE_KM2
          and len(missing_rows) == 0)

    cells = gpd.read_parquet(
        DRIVE / "data/processed/phase1c/claude/phase1c2-claude-0.2.0/geoparquet"
        / "cells_landuse_change_2014_2021.parquet")
    r7_cells = cells[cells["region"] == "R7_kensei"].copy()
    if len(r7_cells) != int(r7["n_cells"]):
        raise SystemExit(f"cell count {len(r7_cells)} != {r7['n_cells']}")
    focus_cells = r7_cells[
        ((r7_cells.grp2014 == "building") & (r7_cells.grp2021 == "forest"))
        | ((r7_cells.grp2014 == "agri") & (r7_cells.grp2021 == "forest"))
    ]
    n_bf = int(((r7_cells.grp2014 == "building") & (r7_cells.grp2021 == "forest")).sum())
    n_af = int(((r7_cells.grp2014 == "agri") & (r7_cells.grp2021 == "forest")).sum())
    if (n_bf, n_af) != (focus["building->forest"]["cells"], focus["agri->forest"]["cells"]):
        raise SystemExit(f"focus counts {n_bf} {n_af}")
    focus_ll = gpd.GeoDataFrame(
        focus_cells.drop(columns="geometry"),
        geometry=focus_cells.geometry.centroid,
        crs=focus_cells.crs,
    ).to_crs(4326)

    TMP.mkdir(parents=True, exist_ok=True)
    tiles = {}
    for _, row in focus_ll.iterrows():
        key = tile_xy(float(row.geometry.x), float(row.geometry.y))
        tiles[key] = tiles.get(key, 0) + 1
    anno_rows, tile_status = [], []
    for (x, y), ncell in sorted(tiles.items()):
        path = TMP / f"15_{x}_{y}.geojson"
        payload = fetch_anno(x, y, path)
        ok = payload is not None
        tile_status.append({"z": 15, "x": x, "y": y, "ok": ok, "focus_cells": ncell,
                            "features": 0 if not ok else len(payload.get("features", []))})
        if not ok:
            continue
        for feat in payload.get("features", []):
            props = feat.get("properties") or {}
            anno_rows.append({"knj": props.get("knj") or "", "geometry": shape(feat["geometry"])})
    shrine_cells = 0
    if anno_rows:
        anno = gpd.GeoDataFrame(anno_rows, geometry="geometry", crs="EPSG:4326").to_crs(focus_cells.crs)
        marked = anno[anno["knj"].fillna("").str.contains("神社|寺院|鳥居")]
        if len(marked):
            hit = gpd.sjoin(focus_cells, marked[["geometry"]], how="inner", predicate="intersects")
            shrine_cells = int(hit.index.nunique())
    bad_cells = sum(t["focus_cells"] for t in tile_status if not t["ok"])

    worship = []
    osm_path = PREV / "osm_features_2026-11-04.jsonl"
    if osm_path.exists():
        seen = set()
        for line in osm_path.open():
            row = json.loads(line)
            if row.get("kind") != "worship":
                continue
            key = (row.get("osm_type"), row.get("osm_id"))
            if key in seen:
                continue
            seen.add(key)
            worship.append(row)
    worship_gdf = gpd.GeoDataFrame(
        worship, geometry=[Point(r["lon"], r["lat"]) for r in worship], crs="EPSG:4326"
    ).to_crs(r7_cells.crs) if worship else gpd.GeoDataFrame(geometry=[], crs=r7_cells.crs)
    worship_in = gpd.sjoin(worship_gdf, r7_cells[["geometry"]], how="inner", predicate="within") if len(worship_gdf) else worship_gdf

    rail = []
    rail_path = PREV / "osm_rail_2026-11-04.jsonl"
    if rail_path.exists():
        seen = set()
        for line in rail_path.open():
            row = json.loads(line)
            key = (row.get("osm_type"), row.get("osm_id"))
            if key in seen:
                continue
            seen.add(key)
            rail.append(row)
    rail_gdf = gpd.GeoDataFrame(
        rail, geometry=[Point(r["lon"], r["lat"]) for r in rail], crs="EPSG:4326"
    ).to_crs(r7_cells.crs) if rail else gpd.GeoDataFrame(geometry=[], crs=r7_cells.crs)

    p32 = gpd.read_parquet(DRIVE / "data/processed/phase1a/vectors/cultural__mlit_cultural_properties_kanagawa__2014.parquet")
    p32_in = gpd.sjoin(p32.to_crs(r7_cells.crs), r7_cells[["muni_name", "geometry"]], how="inner", predicate="within")
    p32_in = p32_in[~p32_in.index.duplicated(keep="first")]

    excluded = Counter()
    rejected, candidates = [], []
    wd_path = PREV / "wikidata_ended_kanagawa_2026-11-05.json"
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
            if "日本の廃止市区町村" in types or types == {"廃止された郡"}:
                excluded["admin"] += 1
                continue
            if not item["coord"].startswith("Point(") or not (types & (STATION_TYPES | PLACE_TYPES)):
                continue
            lon_s, lat_s = item["coord"][len("Point("):-1].split()
            points.append(Point(float(lon_s), float(lat_s)))
            meta.append(item)
        if points:
            joined = gpd.sjoin(
                gpd.GeoDataFrame(meta, geometry=points, crs="EPSG:4326").to_crs(r7_cells.crs),
                r7_cells[["muni_name", "grp2014", "grp2021", "geometry"]],
                how="inner", predicate="within")
            joined = joined[~joined.index.duplicated(keep="first")]
            for _, rec in joined.iterrows():
                stem = stem_of(rec["label"])
                if len(stem) < 2:
                    excluded["short"] += 1
                    continue
                pt = rec.geometry
                still = False
                if len(worship_in):
                    for _, wrow in worship_in.iterrows():
                        if pt.distance(wrow.geometry) <= 400 and stem_of((wrow.get("tags") or {}).get("name") if isinstance(wrow.get("tags"), dict) else "") == stem:
                            still = True
                            break
                # worship json rows are not on the sjoin frame tags. Match by geometry index.
                if not still and len(worship_gdf):
                    dists = worship_gdf.geometry.distance(pt)
                    for idx, dist in dists.items():
                        if dist <= 400 and stem_of((worship[idx].get("tags") or {}).get("name")) == stem:
                            still = True
                            break
                if not still and len(rail_gdf):
                    dists = rail_gdf.geometry.distance(pt)
                    for idx, dist in dists.items():
                        if dist <= 400 and stem_of((rail[idx].get("tags") or {}).get("name")) == stem:
                            still = True
                            break
                lon = float(rec["coord"].split()[0][len("Point("):])
                lat = float(rec["coord"].split()[1][:-1])
                if still:
                    excluded["still_named"] += 1
                    rejected.append({"muni_name": rec["muni_name"], "name": rec["label"], "lat": lat,
                                     "lon": lon, "id": rec["id"], "end": rec["end"]})
                    continue
                candidates.append({
                    "muni_name": rec["muni_name"], "name": rec["label"], "lat": lat, "lon": lon,
                    "category": "station" if set(rec["types"]) & STATION_TYPES else "facility",
                    "confidence": "中",
                    "reason": "Wikidataの終了日と座標がR7収録セル内にあり、2026年OSMの礼拝・鉄道に同じ語幹が400m以内に無い。旧版地形図は未照合のため高にしない。収録外への外挿はしない。",
                    "present": f"Wikidata {rec['id']} 終了日 {rec['end']}",
                    "absent": "現行OSMに同じ語幹が400m以内に無い。旧版の鳥居記号は未照合。",
                    "lu2014": rec["grp2014"], "lu2021": rec["grp2021"], "source_id": rec["id"],
                })

    numbers = {
        "rotation": {"elapsed_days": 13, "week": 2, "region_index": 6, "region": "R7"},
        "h1_agri_gain_source_unfilled": h1,
        "h2_building_gain_source_unfilled": h2,
        "h3_week1_11_3_is_share_ge5": h3,
        "h4_plain_agri_net_exceeds_mountain": h4,
        "agri_gain": {
            "implied_km2": agri_gain,
            "forest_to_agri_km2": forest_to_agri,
            "wasteland_to_agri_km2": waste_to_agri,
            "unnamed_remainder_km2": agri_remainder,
            "published_agri_to_building_km2": PUBLISHED_AGRI_TO_BUILDING_KM2,
            "remainder_minus_published_km2": agri_remainder - PUBLISHED_AGRI_TO_BUILDING_KM2,
        },
        "building_gain": {
            "gain_km2": b_gain,
            "forest_to_building_km2": forest_to_b,
            "wasteland_to_building_km2": waste_to_b,
            "unnamed_remainder_km2": b_remainder,
        },
        "groups": {
            "mountain_land_share": mountain_land / r7["land_km2"],
            "mountain_land_km2": mountain_land,
            "plain_land_km2": plain_land,
            "mountain_agri_net_km2": mountain_agri_net,
            "plain_agri_net_km2": plain_agri_net,
            "mountain_agri_base_km2": mountain_agri_base,
            "plain_agri_base_km2": plain_agri_base,
            "missing_muni_rows": len(missing_rows),
        },
        "components": {
            "share_1": s1, "share_2": s2, "share_3_4": s34, "share_ge5": s5,
            "changed_km2": changed, "ge5_km2": s5 * changed,
            "complement_of_1_2": complement, "complement_km2": complement * changed,
            "gap_pp": (complement - s5) * 100,
            "week1_cited_share": GE5_CITED,
        },
        "focus": {
            "building_to_forest_cells": focus["building->forest"]["cells"],
            "agri_to_forest_cells": focus["agri->forest"]["cells"],
            "building_ge5": focus["building->forest"]["size_>=5_share"],
            "agri_ge5": focus["agri->forest"]["size_>=5_share"],
            "building_max": focus["building->forest"]["max_component_cells"],
            "agri_max": focus["agri->forest"]["max_component_cells"],
        },
        "gsi_anno": {
            "zoom": 15, "unique_tiles": len(tiles),
            "tiles_ok": sum(1 for t in tile_status if t["ok"]),
            "focus_cells": int(len(focus_cells)),
            "focus_cells_on_failed_tiles": bad_cells,
            "focus_cells_with_shrine_annotation": shrine_cells,
            "note": "現行注記。404は未確認であり、注記が無いという意味ではない。旧版の鳥居記号ではない。",
        },
        "osm_worship_unique_in_r7_cells": int(len(worship_in)),
        "p32_in_r7_cells": int(len(p32_in)),
        "lost_site_excluded": dict(excluded),
        "lost_sites": {
            "total": len(candidates), "高": 0,
            "中": sum(1 for c in candidates if c["confidence"] == "中"),
            "低": sum(1 for c in candidates if c["confidence"] == "低"),
            "shrine_candidates": 0, "old_map_torii_compared": False,
            "by_municipality": [],
        },
    }
    for i, cand in enumerate(sorted(candidates, key=lambda c: (c["muni_name"], c["name"])), start=1):
        cand["id"] = f"R7-{i:03d}"
    by_muni = Counter(c["muni_name"] for c in candidates)
    numbers["lost_sites"]["by_municipality"] = [
        {"muni_name": name, "total": count,
         "ids": [c["id"] for c in candidates if c["muni_name"] == name]}
        for name, count in sorted(by_muni.items())]
    blob = json.dumps(numbers, ensure_ascii=False)
    for cand in candidates + rejected:
        if cand["name"] and cand["name"] in blob:
            raise SystemExit("public json contains a site name")
    PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC.write_text(json.dumps(numbers, ensure_ascii=False, indent=2) + "\n")

    OUT_PRIV.mkdir(parents=True, exist_ok=True)
    fields = ["id", "muni_name", "name", "lat", "lon", "category", "confidence",
              "reason", "present", "absent", "lu2014", "lu2021", "source_id"]
    with (OUT_PRIV / "candidates.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for cand in candidates:
            row = dict(cand)
            row["lat"] = f"{cand['lat']:.7f}"
            row["lon"] = f"{cand['lon']:.7f}"
            writer.writerow({k: row.get(k, "") for k in fields})
    lines = [
        "# 非公開: R7 2026-11-08 消失候補", "",
        "名称と座標を含む。リポジトリには置かない。",
        f"採用 {len(candidates)} 件。高確度は旧版地形図未照合のため 0。",
        "文化財の座標対照に使う CSV は、この添付に緯度列付きで入っていない。",
        "OSM の欠落は候補にしていない。収録外4市町へは外挿していない。", "",
    ]
    if not candidates:
        lines.append("採用した候補は無い。")
        lines.append("旧版地形図の鳥居記号は、ラスタが無く、今昔マップと迅速測図のタイル一括取得をしないため照合していない。")
    if rejected:
        lines += ["", "## 不採用（現行OSMに同じ語幹が残る）", ""]
        for rec in rejected:
            lines.append(f"- {rec['muni_name']} {rec['name']} {rec['lat']:.7f},{rec['lon']:.7f} {rec['id']} 終了日 {rec['end']}。")
    for cand in candidates:
        lines += [f"## {cand['id']}", "", f"- 市区町村: {cand['muni_name']}", f"- 名称: {cand['name']}",
                  f"- 緯度: {cand['lat']:.7f}", f"- 経度: {cand['lon']:.7f}", f"- 種別: {cand['category']}",
                  f"- 確度: {cand['confidence']}", f"- 理由: {cand['reason']}",
                  f"- あった資料: {cand['present']}", f"- 無い資料: {cand['absent']}",
                  f"- 土地利用: {cand['lu2014']} → {cand['lu2021']}", ""]
    (OUT_PRIV / "findings.md").write_text("\n".join(lines) + "\n")

    prov = TMP / "provenance_supplemental.jsonl"
    prov.write_text(json.dumps({
        "source_id": "gsi_experimental_anno_z15_r7_focus",
        "source_url_pattern": "https://cyberjapandata.gsi.go.jp/xyz/experimental_anno/15/{x}/{y}.geojson",
        "source_page": "https://maps.gsi.go.jp/development/ichiran.html",
        "retrieved": "2026-11-08",
        "license": "国土地理院コンテンツ利用規約（出典明示）",
        "scope": "R7収録セルのうち建物用地→森林と農地→森林の重心が落ちるz15タイルのみ。404は未確認。旧版地形図ではない。",
        "tiles": tile_status,
    }, ensure_ascii=False) + "\n" + json.dumps({
        "source_id": "reused_osm_and_wikidata_2026-11-05",
        "reused_on": "2026-11-08",
        "license": "OSM ODbL; Wikidata CC0",
        "note": "再ダウンロードしていない。R7収録セルで再切出し。津久井窓の worship parquet は県西に使わない。",
    }, ensure_ascii=False) + "\n")
    if TAR.exists():
        TAR.unlink()
    with tarfile.open(TAR, "w:gz") as archive:
        for path in sorted(TMP.glob("15_*.geojson")):
            archive.add(path, arcname=f"gsi_experimental_anno_z15/{path.name}")
        archive.add(prov, arcname="provenance_supplemental.jsonl")
    print(json.dumps({
        "h1": h1, "h2": h2, "h3": h3, "h4": h4,
        "ge5": round(s5, 4), "complement": round(complement, 4),
        "agri_remainder": round(agri_remainder, 4),
        "b_remainder": round(b_remainder, 4),
        "plain_net": round(plain_agri_net, 4), "mountain_net": round(mountain_agri_net, 4),
        "tiles": len(tiles), "ok": sum(1 for t in tile_status if t["ok"]),
        "bad_cells": bad_cells, "shrine_cells": shrine_cells,
        "worship": int(len(worship_in)), "candidates": len(candidates), "rejected": len(rejected),
        "p32": int(len(p32_in)),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
