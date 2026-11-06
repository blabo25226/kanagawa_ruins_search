"""R6（津久井・旧津久井郡4町）2週目の再計算と、非公開側への消失候補メモ.

公開 JSON には件数だけを書く。名称と緯度経度は
`/opt/cursor/artifacts/kanagawa_private/2026-11-07_R6/` に出す。
新規取得した注記タイルは、同日の tar.gz にだけ入れる。

閾値は結果の採用前に、このファイル先頭の定数として固定した。
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
DRIVE = Path.home() / "drive_r6"
PREV = Path("/opt/cursor/artifacts/kanagawa_private/supplemental_data")
OUT_PRIV = Path("/opt/cursor/artifacts/kanagawa_private/2026-11-07_R6")
PUBLIC = ROOT / "reports" / "daily_region" / "data" / "2026-11-07_R6_week2_public.json"
TAR = Path("/opt/cursor/artifacts/kanagawa_private/supplemental_2026-11-07.tar.gz")
TMP = Path("/tmp/r6_anno_20261107")

# 週1の「5セル以上 22.5%」は 1〜2 セルの補集合かどうかを、差 10 ポイントと
# 真値が 20% 未満かで判定する。R5 週2と同じ二つの閾値。動かさない。
GE5_MAX = 0.20
COMPLEMENT_GAP = 0.10
# 補助値 0.70 と残差が同じ数ではない、とみなす差。
AUX_GAP_KM2 = 0.05
# 公開レポート §2 の津久井列。results.json の region 列には無い。
PUBLISHED_AGRI_TO_BUILDING_KM2 = 0.70
FLOW_TOL_KM2 = 0.01

STATION_TYPES = {"かつての鉄道駅", "廃駅", "鉄道駅", "貨物駅", "鉄道の地上駅",
                 "路面電車停留場", "モノレール駅", "信号場"}
PLACE_TYPES = {"廃寺", "仏教寺院", "御所", "台場", "窯跡", "関所", "飛行場",
               "灯台", "木造灯台"}


def stem_of(value: str | None) -> str:
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
    req = urllib.request.Request(url, headers={"User-Agent": "kanagawa-ruins-search/2026-11-07"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
    except Exception as exc:
        dest.with_suffix(".error").write_text(f"{type(exc).__name__}: {exc}\n{url}\n")
        return None
    dest.write_bytes(raw)
    return json.loads(raw)


def load_tables() -> dict:
    data = json.loads((ROOT / "reports" / "phase1c2_results.json").read_text())
    reg = {name: dict(zip(data["aggregates"]["region"]["columns"], row))
           for name, row in zip(data["aggregates"]["region"]["index"],
                                data["aggregates"]["region"]["data"])}
    cc = data["transitions"]["component_class_share_by_region"]
    comp = {name: dict(zip(cc["columns"], row))
            for name, row in zip(cc["index"], cc["data"])}
    focus = {}
    block = data["transitions"]["focus_by_region"]
    for row in block["data"]:
        rec = dict(zip(block["columns"], row))
        if rec["region"] == "R6_tsukui":
            focus[rec["transition"]] = rec
    rl = data["aggregates"]["region_landscape"]
    landscapes = {}
    for idx, row in zip(rl["index"], rl["data"]):
        if idx[0] == "R6_tsukui":
            landscapes[idx[1]] = dict(zip(rl["columns"], row))
    return {
        "reg": reg["R6_tsukui"],
        "comp": comp["R6_tsukui"],
        "focus": focus,
        "landscapes": landscapes,
        "has_r6_coverage_row": "R6_tsukui" in data["coverage"]["by_region"]["index"],
    }


def main() -> None:
    tables = load_tables()
    r6 = tables["reg"]
    comp = tables["comp"]
    s1, s2, s34, s5 = comp["share_1"], comp["share_2"], comp["share_3-4"], comp["share_>=5"]
    changed = comp["changed_km2"]
    complement = 1 - s1 - s2
    loss = r6["agri_loss_km2"]
    a2f = r6["agri_to_forest_km2"]
    a2w = r6["agri_to_wasteland_km2"]
    residual = loss - a2f - a2w
    inflow = r6["to_forest_km2"]
    forest_net = r6["forest_net_change_km2"]
    outflow = inflow - forest_net

    flows = {}
    for name, row in tables["landscapes"].items():
        flows[name] = {
            "to_forest_km2": row["to_forest_km2"],
            "forest_net_km2": row["forest_net_change_km2"],
            "outflow_km2": row["to_forest_km2"] - row["forest_net_change_km2"],
            "forestation_rate": row["forestation_rate"],
            "agri_to_forest_km2": row["agri_to_forest_km2"],
            "agri_loss_km2": row["agri_loss_km2"],
            "land_km2": row["land_km2"],
        }
    sum_out = sum(v["outflow_km2"] for v in flows.values())
    sum_in = sum(v["to_forest_km2"] for v in flows.values())
    if abs(sum_out - outflow) > FLOW_TOL_KM2 or abs(sum_in - inflow) > FLOW_TOL_KM2:
        raise SystemExit(f"landscape forest flows do not add up: {sum_out} {outflow}")
    max_out = max(flows, key=lambda k: flows[k]["outflow_km2"])
    max_rate = max(flows, key=lambda k: flows[k]["forestation_rate"])

    h1 = (PUBLISHED_AGRI_TO_BUILDING_KM2 > a2f
          and PUBLISHED_AGRI_TO_BUILDING_KM2 < loss
          and abs(residual - PUBLISHED_AGRI_TO_BUILDING_KM2) >= AUX_GAP_KM2)
    h2 = max_out != max_rate and abs(sum_out - outflow) <= FLOW_TOL_KM2
    h3 = (s5 < GE5_MAX and (complement - s5) >= COMPLEMENT_GAP
          and tables["focus"]["building->forest"]["size_>=5_share"] == 0
          and tables["focus"]["agri->forest"]["size_>=5_share"] == 0)
    h4 = all("/" not in name and name in {"urban", "agri_mixed", "other_mixed", "forest_dominant"}
             for name in flows)

    cells = gpd.read_parquet(
        DRIVE / "data/processed/phase1c/claude/phase1c2-claude-0.2.0/geoparquet"
        / "cells_landuse_change_2014_2021.parquet")
    r6_cells = cells[cells["region"] == "R6_tsukui"].copy()
    if len(r6_cells) != int(r6["n_cells"]):
        raise SystemExit(f"R6 cells {len(r6_cells)} != {r6['n_cells']}")
    n_bf = int(((r6_cells.grp2014 == "building") & (r6_cells.grp2021 == "forest")).sum())
    n_af = int(((r6_cells.grp2014 == "agri") & (r6_cells.grp2021 == "forest")).sum())
    if (n_bf, n_af) != (tables["focus"]["building->forest"]["cells"],
                       tables["focus"]["agri->forest"]["cells"]):
        raise SystemExit(f"focus cell counts {n_bf} {n_af}")
    focus = r6_cells[
        ((r6_cells.grp2014 == "building") & (r6_cells.grp2021 == "forest"))
        | ((r6_cells.grp2014 == "agri") & (r6_cells.grp2021 == "forest"))
    ]
    focus_ll = gpd.GeoDataFrame(
        focus.drop(columns="geometry"),
        geometry=focus.geometry.centroid,
        crs=focus.crs,
    ).to_crs(4326)
    focus_ll["lon"] = focus_ll.geometry.x
    focus_ll["lat"] = focus_ll.geometry.y

    TMP.mkdir(parents=True, exist_ok=True)
    tiles = {}
    for _, row in focus_ll.iterrows():
        tiles.setdefault(tile_xy(float(row["lon"]), float(row["lat"])), 0)
        tiles[tile_xy(float(row["lon"]), float(row["lat"]))] += 1
    anno_rows = []
    tile_status = []
    for (x, y), ncell in sorted(tiles.items()):
        path = TMP / f"15_{x}_{y}.geojson"
        data = fetch_anno(x, y, path)
        ok = data is not None
        tile_status.append({"z": 15, "x": x, "y": y, "ok": ok, "focus_cells": ncell,
                            "features": 0 if not ok else len(data.get("features", []))})
        if not ok:
            continue
        for feat in data.get("features", []):
            props = feat.get("properties") or {}
            anno_rows.append({"knj": props.get("knj") or "", "geometry": shape(feat["geometry"])})
    shrine_cells = 0
    if anno_rows:
        anno = gpd.GeoDataFrame(anno_rows, geometry="geometry", crs="EPSG:4326").to_crs(focus.crs)
        marked = anno[anno["knj"].fillna("").str.contains("神社|寺院|鳥居")]
        if len(marked):
            hit = gpd.sjoin(focus, marked[["geometry"]], how="inner", predicate="intersects")
            shrine_cells = int(hit.index.nunique())

    bunk = pd.read_csv(DRIVE / "data/raw/sagamihara_cultural_assets/bunkazai.csv", dtype=str)
    lat_n = int(bunk["緯度"].fillna("").str.strip().ne("").sum()) if "緯度" in bunk.columns else 0

    worship_ids, historic_ids = set(), set()
    name_rows = []
    for kind, bucket in (("worship", worship_ids), ("historic", historic_ids)):
        for path in (DRIVE / "data/processed/phase1a/vectors").glob(f"osm__{kind}__*tsukui*.parquet"):
            gdf = gpd.read_parquet(path)
            if gdf.crs is None or "osm_id" not in gdf.columns:
                continue
            inside = gpd.sjoin(gdf.to_crs(r6_cells.crs), r6_cells[["geometry"]], how="inner", predicate="within")
            inside = inside[~inside["osm_id"].duplicated(keep="first")]
            for _, rec in inside.iterrows():
                if rec["osm_id"] in bucket:
                    continue
                bucket.add(rec["osm_id"])
                name_rows.append((stem_of(rec.get("name")), rec.geometry))
    worship_n, historic_n = len(worship_ids), len(historic_ids)

    rail = []
    rail_path = PREV / "osm_rail_2026-11-04.jsonl"
    if rail_path.exists():
        for line in rail_path.open():
            rail.append(json.loads(line))
    rail_gdf = gpd.GeoDataFrame(
        rail, geometry=[Point(r["lon"], r["lat"]) for r in rail], crs="EPSG:4326"
    ).to_crs(r6_cells.crs) if rail else gpd.GeoDataFrame(geometry=[], crs=r6_cells.crs)

    excluded = Counter()
    rejected = []
    candidates = []
    wd_path = PREV / "wikidata_ended_kanagawa_2026-11-05.json"
    if wd_path.exists():
        wd = json.loads(wd_path.read_text())
        items = {}
        for row in wd["results"]["bindings"]:
            iid = row["item"]["value"].rsplit("/", 1)[-1]
            slot = items.setdefault(iid, {
                "id": iid,
                "label": row.get("itemLabel", {}).get("value", ""),
                "end": (row.get("end", {}).get("value") or "")[:10],
                "coord": row.get("coord", {}).get("value", ""),
                "types": set(),
            })
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
                gpd.GeoDataFrame(meta, geometry=points, crs="EPSG:4326").to_crs(r6_cells.crs),
                r6_cells[["muni_name", "grp2014", "grp2021", "geometry"]],
                how="inner", predicate="within")
            joined = joined[~joined.index.duplicated(keep="first")]
            for _, rec in joined.iterrows():
                stem = stem_of(rec["label"])
                if len(stem) < 2:
                    excluded["short_name"] += 1
                    continue
                pt = rec.geometry
                still = any(other == stem and other and pt.distance(geom) <= 400
                            for other, geom in name_rows)
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
                    rejected.append({"name": rec["label"], "lat": lat, "lon": lon,
                                     "muni_name": rec["muni_name"], "id": rec["id"], "end": rec["end"]})
                    continue
                candidates.append({
                    "muni_name": rec["muni_name"],
                    "name": rec["label"],
                    "lat": lat,
                    "lon": lon,
                    "category": "station" if set(rec["types"]) & STATION_TYPES else "facility",
                    "confidence": "中",
                    "reason": "Wikidataの終了日と座標がR6セル内にあり、津久井OSMの礼拝・史跡と2026年の鉄道名称に同じ語幹が400m以内に無い。旧版地形図は未照合のため高にしない。",
                    "present": f"Wikidata {rec['id']} 終了日 {rec['end']}",
                    "absent": "現行OSMの同じ語幹が400m以内に無い。旧版の鳥居記号は未照合。",
                    "lu2014": rec["grp2014"],
                    "lu2021": rec["grp2021"],
                    "source_id": rec["id"],
                })

    numbers = {
        "rotation": {"elapsed_days": 12, "week": 2, "region_index": 5, "region": "R6"},
        "has_r6_coverage_row": tables["has_r6_coverage_row"],
        "h1_aux_relation_supported": h1,
        "h2_outflow_leader_differs_from_rate_leader": h2,
        "h3_ge5_recomputed": h3,
        "h4_no_old_town_split": h4,
        "agri": {
            "loss_km2": loss,
            "to_forest_km2": a2f,
            "to_wasteland_km2": a2w,
            "forest_wasteland_share_of_loss": (a2f + a2w) / loss,
            "residual_unnamed_km2": residual,
            "published_agri_to_building_km2": PUBLISHED_AGRI_TO_BUILDING_KM2,
            "residual_minus_published_km2": residual - PUBLISHED_AGRI_TO_BUILDING_KM2,
        },
        "building_gain": {
            "gain_km2": r6["building_gain_km2"],
            "forest_to_building_km2": tables["focus"]["building->forest"]["reverse_area_km2"],
            "unnamed_remainder_km2": r6["building_gain_km2"] - tables["focus"]["building->forest"]["reverse_area_km2"],
        },
        "forest": {
            "inflow_km2": inflow,
            "net_km2": forest_net,
            "outflow_km2": outflow,
            "max_outflow_landscape": max_out,
            "max_forestation_rate_landscape": max_rate,
            "by_landscape": flows,
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
        "focus_ge5": {
            "building_to_forest_cells": tables["focus"]["building->forest"]["cells"],
            "agri_to_forest_cells": tables["focus"]["agri->forest"]["cells"],
            "building_max_component": tables["focus"]["building->forest"]["max_component_cells"],
            "agri_max_component": tables["focus"]["agri->forest"]["max_component_cells"],
            "building_ge5": tables["focus"]["building->forest"]["size_>=5_share"],
            "agri_ge5": tables["focus"]["agri->forest"]["size_>=5_share"],
        },
        "gsi_anno": {
            "zoom": 15,
            "unique_tiles": len(tiles),
            "tiles_ok": sum(1 for t in tile_status if t["ok"]),
            "focus_cells": int(len(focus)),
            "focus_cells_with_shrine_annotation": shrine_cells,
            "note": "現行注記。旧版の鳥居記号ではない。",
        },
        "bunkazai_rows": int(len(bunk)),
        "bunkazai_lat_nonempty": lat_n,
        "osm_worship_in_r6_cells": worship_n,
        "osm_historic_in_r6_cells": historic_n,
        "lost_site_excluded": dict(excluded),
        "lost_sites": {
            "total": len(candidates),
            "高": 0,
            "中": sum(1 for c in candidates if c["confidence"] == "中"),
            "低": sum(1 for c in candidates if c["confidence"] == "低"),
            "shrine_candidates": 0,
            "old_map_torii_compared": False,
        },
    }
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
        for i, cand in enumerate(candidates, start=1):
            cand["id"] = f"R6-{i:03d}"
            row = dict(cand)
            row["lat"] = f"{cand['lat']:.7f}"
            row["lon"] = f"{cand['lon']:.7f}"
            writer.writerow({k: row.get(k, "") for k in fields})
    lines = [
        "# 非公開: R6 2026-11-07 消失候補",
        "",
        "名称と座標を含む。リポジトリには置かない。",
        f"採用 {len(candidates)} 件。高確度は旧版地形図未照合のため 0。",
        "相模原市文化財CSVの緯度非空件数は先に確認し、0件だったので座標対照に使っていない。",
        "OSMの現存地物の欠落は候補にしていない。",
        "",
    ]
    if not candidates:
        lines.append("採用した候補は無い。")
        lines.append("旧版地形図の鳥居記号は、ラスタが無く、今昔マップと迅速測図のタイル一括取得をしないため照合していない。")
    if rejected:
        lines += ["", "## 不採用（現行OSMに同じ語幹が残る）", ""]
        for rec in rejected:
            lines.append(
                f"- {rec['muni_name']} {rec['name']} {rec['lat']:.7f},{rec['lon']:.7f} "
                f"{rec['id']} 終了日 {rec['end']}。"
            )
    for cand in candidates:
        lines += [
            f"## {cand['id']}", "",
            f"- 市区町村: {cand['muni_name']}",
            f"- 名称: {cand['name']}",
            f"- 緯度: {cand['lat']:.7f}",
            f"- 経度: {cand['lon']:.7f}",
            f"- 種別: {cand['category']}",
            f"- 確度: {cand['confidence']}",
            f"- 理由: {cand['reason']}",
            f"- あった資料: {cand['present']}",
            f"- 無い資料: {cand['absent']}",
            f"- 土地利用: {cand['lu2014']} → {cand['lu2021']}", "",
        ]
    (OUT_PRIV / "findings.md").write_text("\n".join(lines) + "\n")

    prov = TMP / "provenance_supplemental.jsonl"
    prov.write_text(json.dumps({
        "source_id": "gsi_experimental_anno_z15_r6_focus",
        "source_url_pattern": "https://cyberjapandata.gsi.go.jp/xyz/experimental_anno/15/{x}/{y}.geojson",
        "source_page": "https://maps.gsi.go.jp/development/ichiran.html",
        "retrieved": "2026-11-07",
        "license": "国土地理院コンテンツ利用規約（出典明示）",
        "scope": "R6の建物用地→森林と農地→森林のセル重心が落ちるz15タイルのみ。旧版地形図ではない。",
        "tiles": tile_status,
    }, ensure_ascii=False) + "\n" + json.dumps({
        "source_id": "reused_wikidata_and_osm_rail_2026-11-05",
        "reused_on": "2026-11-07",
        "license": "Wikidata CC0; OSM ODbL",
        "note": "再ダウンロードしていない。R6セルで再切出し。",
    }, ensure_ascii=False) + "\n")
    if TAR.exists():
        TAR.unlink()
    with tarfile.open(TAR, "w:gz") as archive:
        for path in sorted(TMP.glob("15_*.geojson")):
            archive.add(path, arcname=f"gsi_experimental_anno_z15/{path.name}")
        archive.add(prov, arcname="provenance_supplemental.jsonl")
    print(json.dumps({
        "h1": h1, "h2": h2, "h3": h3, "h4": h4,
        "ge5": s5, "complement": complement,
        "max_out": max_out, "max_rate": max_rate,
        "tiles": len(tiles), "tiles_ok": sum(1 for t in tile_status if t["ok"]),
        "shrine_anno_cells": shrine_cells,
        "candidates": len(candidates), "rejected": len(rejected),
        "worship": worship_n, "historic": historic_n, "lat_n": lat_n,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
