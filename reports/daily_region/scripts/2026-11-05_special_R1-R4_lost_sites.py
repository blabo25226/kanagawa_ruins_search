"""特別回（2026-11-05）R1–R4 消失候補の再計算.

公開リポジトリには件数だけを書く。名称と緯度経度は非公開ディレクトリへ出す。
座標と名称は入力データにあるものだけを使い、補完や推定はしない。

入力:
- Drive: N03（2026）、P32（2014）、土地利用変化セル（2014→2021）
- 補完データ: Geofabrik 関東 PBF から抽出した OSM（2018-01-01 と 2026-11-04）、
  Wikidata の廃止日付き項目（2026-11-05 取得）

高確度は付けない。地理院の現行地形図記号を照合していないため、
OSM からの欠落だけでは「地図から消えた」を高確度にしない。
"""

from __future__ import annotations

import csv
import json
import math
import os
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import geopandas as gpd
import pandas as pd
import tomllib
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parents[3]
DRIVE = Path(os.environ.get("RUINS_DRIVE_ROOT", Path.home() / "drive"))
PRIVATE = Path(os.environ.get(
    "RUINS_PRIVATE_ROOT", "/cursor/stores/bot/kanagawa_private"))
SUP = PRIVATE / "supplemental_data"
OUT_DIR = PRIVATE / "2026-11-05_special_R1-R4"
PUBLIC_JSON = (ROOT / "reports" / "daily_region" / "data"
               / "2026-11-05_special_R1-R4_public_summary.json")

REGIONS = ("R1_yokohama_kawasaki", "R2_miura", "R3_shonan", "R4_kenou")
REGION_SHORT = {
    "R1_yokohama_kawasaki": "R1",
    "R2_miura": "R2",
    "R3_shonan": "R3",
    "R4_kenou": "R4",
}
CONF_ORDER = {"高": 0, "中": 1, "低": 2}

# 固有の地名を含まない社名。同名の別地点を同一視しやすいので候補にしない。
GENERIC_STEMS = {
    "神社", "稲荷", "稲荷神社", "稲荷大明神", "八幡", "八幡神社", "八幡宮",
    "神明", "神明社", "神明神社", "浅間", "浅間神社", "弁天", "弁財天",
    "弁天堂", "地蔵", "地蔵尊", "地蔵堂", "庚申", "庚申塔", "祠", "観音",
    "観音堂", "不動", "不動尊", "不動堂", "寺", "院", "宮", "堂", "社",
    "水神", "山神", "道祖神", "馬頭観音", "秋葉", "秋葉神社", "熊野",
    "熊野神社", "白山", "白山神社", "天神", "天神社", "天満宮", "厳島",
    "厳島神社", "日枝", "日枝神社", "御嶽", "御嶽神社", "三島", "三島神社",
    "伊勢", "伊勢神社", "金毘羅", "金比羅", "住吉", "住吉神社", "春日",
    "春日神社", "諏訪", "諏訪神社", "氷川", "氷川神社", "愛宕", "愛宕神社",
    "お宮", "お寺", "大神", "大神宮",
}

SCHOOL_TYPES = {
    "日本の小学校", "日本の中学校", "日本の高等学校", "日本の中高一貫校",
    "短期大学", "カレッジ", "専修学校", "学校", "病院", "旧病院", "診療所",
    "博物館", "美術館", "海事博物館", "少年院", "行政機関",
}
STATION_TYPES = {"かつての鉄道駅", "廃駅", "鉄道駅", "貨物駅", "鉄道の地上駅",
                 "路面電車停留場", "モノレール駅", "信号場"}
PLACE_TYPES = {"廃寺", "仏教寺院", "御所", "日本の幕府", "星形要塞", "台場",
               "窯跡", "関所", "飛行場", "御殿・御茶屋", "灯台", "木造灯台"}
TOWN_TYPES = {"廃止された町・字", "町丁", "集落"}
EXCLUDE_TYPES = {"日本の廃止市区町村", "廃止された郡", "事件", "シリアル・キリング",
                 "強盗致死傷罪", "現住建造物等放火罪", "組織", "公団",
                 "認定博覧会", "国際園芸博覧会", "レストラン", "ホテル",
                 "ショッピングモール", "温泉", "水族館", "テーマ・パーク",
                 "建物・構造物のグループ", "軍事基地", "海軍兵器廠"}


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
    text = re.sub(
        r"(仮乗降場|乗降場|停留場|停留所|小学校|中学校|高等学校|短期大学|"
        r"高校|大学|分院|病院|信号所|信号場|跡|駅)$",
        "",
        text,
    )
    return text


def specific(value: str | None) -> bool:
    stem = stem_of(value)
    if len(stem) < 2:
        return False
    if stem in GENERIC_STEMS or norm(value) in GENERIC_STEMS:
        return False
    return True


def hav_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class Grid:
    def __init__(self, step: float = 0.005):
        self.step = step
        self.cells: dict[tuple[int, int], list] = defaultdict(list)

    def add(self, lon: float, lat: float, payload) -> None:
        self.cells[(int(lon / self.step), int(lat / self.step))].append(
            (lon, lat, payload))

    def near(self, lon: float, lat: float, meters: float):
        ix, iy = int(lon / self.step), int(lat / self.step)
        span = int(meters / 80000) + 1
        for dx in range(-span, span + 1):
            for dy in range(-span, span + 1):
                for olon, olat, payload in self.cells.get((ix + dx, iy + dy), ()):
                    dist = hav_m(lon, lat, olon, olat)
                    if dist <= meters:
                        yield dist, payload


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open() as handle:
        for line in handle:
            rows.append(json.loads(line))
    return rows


def feature_name(row: dict) -> str:
    tags = row.get("tags") or {}
    return tags.get("name") or tags.get("name:ja") or ""


def load_regions() -> dict[str, str]:
    with (ROOT / "config" / "phase1c2_regions.toml").open("rb") as handle:
        cfg = tomllib.load(handle)
    code_to_region = {}
    for key in REGIONS:
        for code in cfg["regions"][key]["muni_codes"]:
            code_to_region[code] = key
    return code_to_region


def load_admin(code_to_region: dict[str, str]) -> gpd.GeoDataFrame:
    admin = gpd.read_parquet(
        DRIVE / "data/processed/phase1a/vectors/admin__n03__2026_kanagawa.parquet")
    admin = admin[admin["muni_code"].isin(code_to_region)].copy()
    admin["region"] = admin["muni_code"].map(code_to_region)
    def display_name(frame: gpd.GeoDataFrame) -> str:
        city = next((x for x in frame["N03_004"] if isinstance(x, str) and x), "")
        ward = next((x for x in frame["N03_005"] if isinstance(x, str) and x), "")
        if not city:
            city = next((x for x in frame["muni"] if isinstance(x, str) and x), "")
        return f"{city}{ward}" if ward else city

    dissolved = admin.dissolve(by="muni_code", as_index=False)
    names = admin.groupby("muni_code", group_keys=False).apply(display_name, include_groups=False)
    dissolved["muni_name"] = dissolved["muni_code"].map(names)
    dissolved["region"] = dissolved["muni_code"].map(code_to_region)
    return dissolved


def assign_admin(frame: gpd.GeoDataFrame, admin: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    projected = frame.to_crs(admin.crs)
    joined = gpd.sjoin(
        projected,
        admin[["muni_code", "muni_name", "region", "geometry"]],
        how="left",
        predicate="within",
    )
    joined = joined[~joined.index.duplicated(keep="first")]
    return joined


def main() -> None:
    code_to_region = load_regions()
    admin = load_admin(code_to_region)
    cells = gpd.read_parquet(
        DRIVE / "data/processed/phase1c/claude/phase1c2-claude-0.2.0/geoparquet"
        / "cells_landuse_change_2014_2021.parquet")
    p32 = gpd.read_parquet(
        DRIVE / "data/processed/phase1a/vectors"
        / "cultural__mlit_cultural_properties_kanagawa__2014.parquet")
    p32 = p32.to_crs(4326)
    p32_names = []
    p32_grid = Grid(0.005)
    for _, row in p32.iterrows():
        name = row["P32_006"] or ""
        if not specific(name) and "跡" not in norm(name):
            continue
        lon, lat = row.geometry.x, row.geometry.y
        p32_grid.add(lon, lat, stem_of(name) or norm(name))
        p32_names.append(norm(name))

    old_rows = load_jsonl(SUP / "osm_features_2018-01-01.jsonl")
    new_rows = (load_jsonl(SUP / "osm_features_2026-11-04.jsonl")
                + load_jsonl(SUP / "osm_rail_2026-11-04.jsonl"))
    name_grid = Grid(0.005)
    worship_grid = Grid(0.002)
    railway_grid = Grid(0.01)
    n_worship_2026 = 0
    for row in new_rows:
        name = feature_name(row)
        if specific(name) or ("跡" in norm(name) and len(stem_of(name)) >= 2):
            name_grid.add(row["lon"], row["lat"], stem_of(name) or norm(name))
        if row.get("kind") == "worship":
            n_worship_2026 += 1
            worship_grid.add(row["lon"], row["lat"], row["osm_id"])
        if row.get("kind") == "railway" and specific(name):
            railway_grid.add(row["lon"], row["lat"], stem_of(name))

    def stem_nearby(lon: float, lat: float, stem: str, meters: float) -> bool:
        if not stem:
            return False
        for _, other in name_grid.near(lon, lat, meters):
            if other == stem:
                return True
        for _, other in p32_grid.near(lon, lat, meters):
            if other == stem:
                return True
        return False

    def worship_nearby(lon: float, lat: float, meters: float) -> bool:
        return next(worship_grid.near(lon, lat, meters), None) is not None

    candidates: list[dict] = []
    excluded = Counter()

    old_points = []
    for row in old_rows:
        if row.get("osm_type") != "node":
            continue
        name = feature_name(row)
        if not specific(name):
            excluded["osm2018_generic_or_unnamed"] += 1
            continue
        old_points.append(row)
    old_gdf = gpd.GeoDataFrame(
        old_points,
        geometry=[Point(r["lon"], r["lat"]) for r in old_points],
        crs="EPSG:4326",
    )
    old_admin = assign_admin(old_gdf, admin)

    for rec, (_, located) in zip(old_points, old_admin.iterrows()):
        region = located.get("region")
        if not isinstance(region, str):
            excluded["osm2018_outside_r1r4"] += 1
            continue
        name = feature_name(rec)
        stem = stem_of(name)
        lon, lat = rec["lon"], rec["lat"]
        kind = rec.get("kind")
        tags = rec.get("tags") or {}
        if kind == "worship":
            if tags.get("religion") not in {"shinto", "buddhist"}:
                excluded["worship_other_religion"] += 1
                continue
            excluded["worship_named_in_region"] += 1
            if worship_nearby(lon, lat, 80):
                excluded["worship_still_within_80m"] += 1
                continue
            if stem_nearby(lon, lat, stem, 400):
                excluded["worship_same_stem_within_400m"] += 1
                continue
            # 社殿が複数地点にまたがると、現存社でもノードの削除が消失に見える。
            # 大山阿夫利神社の下社・本社のずれで誤検出したため、候補には採用しない。
            excluded["worship_gap_not_adopted"] += 1
        elif kind == "place" and tags.get("place") in {"hamlet", "village", "isolated_dwelling"}:
            excluded["place_named_in_region"] += 1
            if stem_nearby(lon, lat, stem, 500):
                excluded["place_same_stem_within_500m"] += 1
                continue
            # 名称の大半は「地名+番号」の街区ノードで、消滅集落ではない。
            excluded["place_gap_not_adopted"] += 1

    # Wikidata: 廃止日のある地物。行政合併は候補にしない。
    wd = json.loads((SUP / "wikidata_ended_kanagawa_2026-11-05.json").read_text())
    items: dict[str, dict] = {}
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

    wd_points = []
    wd_meta = []
    for item in items.values():
        types = item["types"]
        if types <= {"日本の廃止市区町村"} or types == {"廃止された郡"}:
            excluded["wikidata_admin_merger"] += 1
            continue
        if "日本の廃止市区町村" in types and not (types & (STATION_TYPES | PLACE_TYPES | TOWN_TYPES | SCHOOL_TYPES)):
            excluded["wikidata_admin_merger"] += 1
            continue
        if types & EXCLUDE_TYPES and not (types & (STATION_TYPES | PLACE_TYPES | SCHOOL_TYPES | TOWN_TYPES)):
            excluded["wikidata_excluded_type"] += 1
            continue
        coord = item["coord"]
        if not coord.startswith("Point("):
            excluded["wikidata_no_point"] += 1
            continue
        lon_s, lat_s = coord[len("Point("):-1].split()
        lon, lat = float(lon_s), float(lat_s)
        label = item["label"]
        if not specific(label) and "跡" not in norm(label):
            excluded["wikidata_generic_name"] += 1
            continue
        relevant = types & (STATION_TYPES | PLACE_TYPES | SCHOOL_TYPES | TOWN_TYPES)
        if not relevant:
            excluded["wikidata_not_target_class"] += 1
            continue
        wd_points.append(Point(lon, lat))
        wd_meta.append(item)

    if wd_points:
        wd_gdf = gpd.GeoDataFrame(wd_meta, geometry=wd_points, crs="EPSG:4326")
        wd_admin = assign_admin(wd_gdf, admin)
    else:
        wd_admin = gpd.GeoDataFrame()

    for item, (_, located) in zip(wd_meta, wd_admin.iterrows()):
        region = located.get("region")
        if not isinstance(region, str):
            excluded["wikidata_outside_r1r4"] += 1
            continue
        types = item["types"]
        if "日本の廃止市区町村" in types and not (types & TOWN_TYPES):
            excluded["wikidata_admin_in_region"] += 1
            continue
        label = item["label"]
        stem = stem_of(label)
        lon, lat = located.geometry.x, located.geometry.y
        # assign_admin returns projected geometry. Use original lon/lat from the point before transform.
        # GeoDataFrame.to_crs in assign_admin replaces geometry. Recover from the WKT stored on the item.
        lon_s, lat_s = item["coord"][len("Point("):-1].split()
        lon, lat = float(lon_s), float(lat_s)
        if stem_nearby(lon, lat, stem, 400):
            excluded["wikidata_still_named_on_osm_or_p32"] += 1
            continue
        if types & STATION_TYPES and any(
                other == stem for _, other in railway_grid.near(lon, lat, 1000)):
            excluded["station_stem_within_1000m_of_railway"] += 1
            continue
        if types & STATION_TYPES:
            category = "station"
            confidence = "中"
            reason = (
                "Wikidataに廃止日と座標があり、2026-11-04のOSM抽出とP32に"
                "同じ語幹が400m以内にない。地理院地形図の注記は未照合のため高確度にしない。"
            )
        elif types & TOWN_TYPES and not (types & (STATION_TYPES | PLACE_TYPES)):
            category = "town_name"
            confidence = "低"
            reason = (
                "Wikidataの型は廃止された町・字または集落である。"
                "住居表示の改称で、集落の物理的な消失とは限らない。座標はWikidataの点。"
            )
        elif types & PLACE_TYPES and not (types & SCHOOL_TYPES):
            category = "facility"
            confidence = "中"
            reason = (
                "Wikidataに施設の終了日と座標があり、2026-11-04のOSMとP32に同じ語幹がない。"
                "史跡として別の地図に残る可能性は、この照合だけでは否定できない。"
            )
        elif types & SCHOOL_TYPES:
            category = "facility"
            confidence = "低"
            reason = (
                "学校・病院等の機関の終了日がWikidataにあり、OSMに同じ語幹がない。"
                "建物が別の名称で残っている可能性があり、土地利用が建物のままなら候補から外す。"
            )
        else:
            continue
        type_text = "、".join(sorted(types))
        candidates.append({
            "region": region,
            "muni_code": located["muni_code"],
            "muni_name": located["muni_name"],
            "name": label,
            "lat": lat,
            "lon": lon,
            "category": category,
            "confidence": confidence,
            "confidence_reason": reason,
            "evidence_present": (
                f"Wikidata {item['id']}（型: {type_text}、終了日: {item['end']}、"
                "座標はWikidataのP625）。取得日 2026-11-05。ライセンス CC0。"
            ),
            "evidence_absent": (
                "kanto-261103.osm.pbf（2026-11-04）の抽出と、"
                "国土数値情報P32神奈川（2014-01-31）に、同じ語幹が400m以内にない。"
            ),
            "verification": (
                "Wikidataの項目ページで終了日の出典を開き、"
                "OSMとP32の語幹照合を再実行する。地理院地形図は未照合。"
            ),
            "source_ids": item["id"],
        })

    # 土地利用。学校等は2021年も建物なら候補から外す。
    if candidates:
        cand_gdf = gpd.GeoDataFrame(
            candidates,
            geometry=[Point(c["lon"], c["lat"]) for c in candidates],
            crs="EPSG:4326",
        ).to_crs(cells.crs)
        land = gpd.sjoin(
            cand_gdf,
            cells[["grp2014", "grp2021", "geometry"]],
            how="left",
            predicate="within",
        )
        land = land[~land.index.duplicated(keep="first")]
    else:
        land = gpd.GeoDataFrame()

    kept = []
    for cand, (_, lu) in zip(candidates, land.iterrows()):
        g2014 = lu["grp2014"] if isinstance(lu.get("grp2014"), str) else ""
        g2021 = lu["grp2021"] if isinstance(lu.get("grp2021"), str) else ""
        cand["lu2014"] = g2014
        cand["lu2021"] = g2021
        if norm(cand["name"]) == norm(cand["muni_name"]) or stem_of(cand["name"]) == stem_of(cand["muni_name"]):
            excluded["name_is_current_municipality"] += 1
            continue
        schoolish = cand["confidence_reason"].startswith("学校・病院")
        if schoolish:
            gone = (g2014 in {"building", "transport"}
                    and g2021 in {"forest", "agri", "wasteland"})
            if not gone:
                excluded["school_footprint_not_gone"] += 1
                continue
            cand["confidence"] = "中"
            cand["confidence_reason"] += (
                f" 同じ点の2014年土地利用は{g2014}、2021年は{g2021}。"
            )
        kept.append(cand)
    candidates = kept

    # 近い同一語幹は1件にまとめる。確度が高い方を残し、根拠は両方残す。
    candidates.sort(key=lambda c: (CONF_ORDER[c["confidence"]], c["name"]))
    merged: list[dict] = []
    for cand in candidates:
        stem = stem_of(cand["name"])
        host = None
        for prev in merged:
            if stem_of(prev["name"]) == stem and hav_m(
                    prev["lon"], prev["lat"], cand["lon"], cand["lat"]) <= 300:
                host = prev
                break
        if host is None:
            merged.append(cand)
            continue
        if CONF_ORDER[cand["confidence"]] < CONF_ORDER[host["confidence"]]:
            extra_present = host["evidence_present"]
            extra_absent = host["evidence_absent"]
            host.update(cand)
            host["evidence_present"] += " / " + extra_present
            host["evidence_absent"] += " / " + extra_absent
        else:
            host["evidence_present"] += " / " + cand["evidence_present"]
            host["evidence_absent"] += " / " + cand["evidence_absent"]
            host["source_ids"] += ";" + cand["source_ids"]
    candidates = merged

    # 厚木市の農地→森林・建物→森林。週2のセル数と一致することを確認する。
    atsugi = cells[cells["muni_name"] == "厚木市"]
    agri_forest = atsugi[(atsugi.grp2014 == "agri") & (atsugi.grp2021 == "forest")]
    bld_forest = atsugi[(atsugi.grp2014 == "building") & (atsugi.grp2021 == "forest")]
    if len(agri_forest) != 29 or len(bld_forest) != 11:
        raise SystemExit(
            f"厚木市の遷移セル数が週2と一致しない: agri→forest {len(agri_forest)}, "
            f"building→forest {len(bld_forest)}")

    worship_pts = gpd.GeoDataFrame(
        geometry=[Point(r["lon"], r["lat"]) for r in new_rows if r.get("kind") == "worship"],
        crs="EPSG:4326",
    ).to_crs(cells.crs)
    near = gpd.sjoin_nearest(
        agri_forest[["geometry"]], worship_pts, how="left", distance_col="dist_m")
    agri_within_100 = int((near["dist_m"] <= 100).sum())
    cand_proj = gpd.GeoDataFrame(
        candidates,
        geometry=[Point(c["lon"], c["lat"]) for c in candidates],
        crs="EPSG:4326",
    ).to_crs(cells.crs) if candidates else gpd.GeoDataFrame(geometry=[], crs=cells.crs)
    in_agri = set()
    in_bld = set()
    if len(cand_proj):
        hit_a = gpd.sjoin(cand_proj, agri_forest[["geometry"]], how="inner", predicate="within")
        hit_b = gpd.sjoin(cand_proj, bld_forest[["geometry"]], how="inner", predicate="within")
        in_agri = set(hit_a.index)
        in_bld = set(hit_b.index)

    by_region_conf = {REGION_SHORT[r]: Counter() for r in REGIONS}
    by_muni = defaultdict(Counter)
    by_region_cat = {REGION_SHORT[r]: Counter() for r in REGIONS}
    counters = {s: 1 for s in REGION_SHORT.values()}
    ordered = sorted(candidates, key=lambda c: (
        c["region"], CONF_ORDER[c["confidence"]], c["category"], c["muni_code"], c["name"]))
    for idx, cand in enumerate(ordered):
        short = REGION_SHORT[cand["region"]]
        cand["id"] = f"{short}-{counters[short]:03d}"
        counters[short] += 1
        cand["in_atsugi_agri_to_forest"] = idx in in_agri and cand["muni_name"] == "厚木市"
        cand["in_atsugi_building_to_forest"] = idx in in_bld and cand["muni_name"] == "厚木市"
        # sjoin index is the cand_proj index, which follows `candidates` order, not `ordered`.
    # 上の index 対応は ordered ではなく candidates の並びなので、作り直す。
    id_by_object = {id(c): c["id"] for c in ordered}
    agri_ids = []
    bld_ids = []
    if len(cand_proj):
        for src_index in in_agri:
            agri_ids.append(id_by_object[id(candidates[src_index])])
        for src_index in in_bld:
            bld_ids.append(id_by_object[id(candidates[src_index])])
    for cand in ordered:
        cand["in_atsugi_agri_to_forest"] = cand["id"] in agri_ids
        cand["in_atsugi_building_to_forest"] = cand["id"] in bld_ids
        short = cand["id"].split("-")[0]
        by_region_conf[short][cand["confidence"]] += 1
        by_region_conf[short]["total"] += 1
        by_muni[(short, cand["muni_code"], cand["muni_name"])][cand["confidence"]] += 1
        by_muni[(short, cand["muni_code"], cand["muni_name"])]["total"] += 1
        by_region_cat[short][cand["category"]] += 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_DIR / "candidates.csv"
    fields = [
        "id", "region", "muni_code", "muni_name", "name", "lat", "lon",
        "category", "confidence", "confidence_reason", "evidence_present",
        "evidence_absent", "lu2014", "lu2021", "in_atsugi_agri_to_forest",
        "in_atsugi_building_to_forest", "verification", "source_ids",
    ]
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for cand in ordered:
            row = dict(cand)
            row["region"] = REGION_SHORT[cand["region"]]
            row["lat"] = f"{cand['lat']:.7f}"
            row["lon"] = f"{cand['lon']:.7f}"
            writer.writerow(row)

    md_path = OUT_DIR / "lost_sites_R1-R4.md"
    lines = [
        "# 非公開: R1–R4 消失候補（2026-11-05 特別回）",
        "",
        "このファイルは公開リポジトリに置かない。名称と緯度経度を含む。",
        "座標は入力データの値であり、空白を補完していない。",
        "高確度は0件。地理院地形図の記号照合をしていない。",
        "",
        f"- 候補件数: {len(ordered)}",
        "",
    ]
    for cand in ordered:
        lines.extend([
            f"## {cand['id']}",
            "",
            f"- 地域: {REGION_SHORT[cand['region']]}",
            f"- 市区町村: {cand['muni_name']}（{cand['muni_code']}）",
            f"- 名称: {cand['name']}",
            f"- 緯度: {cand['lat']:.7f}",
            f"- 経度: {cand['lon']:.7f}",
            f"- 種別: {cand['category']}",
            f"- 確度: {cand['confidence']}",
            f"- 確度の理由: {cand['confidence_reason']}",
            f"- あった資料: {cand['evidence_present']}",
            f"- 無い資料: {cand['evidence_absent']}",
            f"- 2014年土地利用（セル）: {cand['lu2014'] or 'セル外または不明'}",
            f"- 2021年土地利用（セル）: {cand['lu2021'] or 'セル外または不明'}",
            f"- 厚木市の農地→森林セル内: {cand['in_atsugi_agri_to_forest']}",
            f"- 厚木市の建物→森林セル内: {cand['in_atsugi_building_to_forest']}",
            f"- 確認方法: {cand['verification']}",
            "",
        ])
    md_path.write_text("\n".join(lines))

    def conf_dict(counter: Counter) -> dict:
        return {
            "total": int(counter.get("total", 0)),
            "高": int(counter.get("高", 0)),
            "中": int(counter.get("中", 0)),
            "低": int(counter.get("低", 0)),
        }

    public = {
        "round": "2026-11-05 special R1-R4",
        "note": "件数のみ。名称・座標・大字以下は含まない。詳細は非公開の内部資料。",
        "confidence_policy": "高は0。地理院地形図記号を未照合のため。",
        "by_region": {
            short: {
                **conf_dict(by_region_conf[short]),
                "by_category": dict(by_region_cat[short]),
            }
            for short in ("R1", "R2", "R3", "R4")
        },
        "by_municipality": [
            {
                "region": key[0],
                "muni_code": key[1],
                "muni_name": key[2],
                **conf_dict(counter),
            }
            for key, counter in sorted(by_muni.items())
        ],
        "atsugi_priority": {
            "agri_to_forest_cells": int(len(agri_forest)),
            "building_to_forest_cells": int(len(bld_forest)),
            "agri_to_forest_cells_within_100m_of_osm_worship_2026": agri_within_100,
            "candidate_ids_in_agri_to_forest_cell": sorted(agri_ids),
            "candidate_ids_in_building_to_forest_cell": sorted(bld_ids),
        },
        "excluded_counts": dict(excluded),
        "osm_worship_points_in_bbox_2026": n_worship_2026,
        "candidate_ids_by_municipality": [
            {
                "region": key[0],
                "muni_name": key[2],
                "ids": [c["id"] + ":" + c["confidence"]
                        for c in ordered
                        if REGION_SHORT[c["region"]] == key[0] and c["muni_code"] == key[1]],
            }
            for key in sorted(by_muni)
        ],
    }
    # 公開JSONの文字列値そのものが、候補の名称や座標になっていないこと。
    def walk_strings(obj):
        if isinstance(obj, str):
            yield obj
        elif isinstance(obj, dict):
            for value in obj.values():
                yield from walk_strings(value)
        elif isinstance(obj, list):
            for value in obj:
                yield from walk_strings(value)

    forbidden_names = {c["name"] for c in ordered if c["name"]}
    forbidden_coords = set()
    for cand in ordered:
        forbidden_coords.add(f"{cand['lat']:.5f}")
        forbidden_coords.add(f"{cand['lon']:.5f}")
        forbidden_coords.add(f"{cand['lat']:.6f}")
        forbidden_coords.add(f"{cand['lon']:.6f}")
    for text in walk_strings(public):
        if text in forbidden_names or text in forbidden_coords:
            raise SystemExit("公開サマリに名称または座標が混入した")
    PUBLIC_JSON.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC_JSON.write_text(json.dumps(public, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({
        "candidates": len(ordered),
        "by_region": {k: conf_dict(v) for k, v in by_region_conf.items()},
        "atsugi_agri_forest_within_100m_worship": agri_within_100,
        "atsugi_candidate_cells_agri": len(agri_ids),
        "atsugi_candidate_cells_building": len(bld_ids),
        "public_json": str(PUBLIC_JSON),
        "private_md": str(md_path),
        "private_csv": str(csv_path),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
