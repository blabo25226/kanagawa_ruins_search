"""R1（横浜・川崎）3週目の再計算と、非公開側への消失候補メモ.

公開 JSON には件数・区名・候補 ID だけを書く。名称と緯度経度は
`/opt/cursor/artifacts/kanagawa_private/2026-11-09_R1/` に出す。
新規取得は同日の tar.gz にだけ入れる。

閾値は集計を見る前に定数へ置いた。前日 R7 の手続きを二つ入れている。
- 近い二つの数を、減少と増加、純変化と総流出のように種類が違えば等置しない。
- 週2の「5セル以上 9.6%」は share_>=5 に式を当ててから、補集合の誤記かどうかを書く。
注記タイルの 404 は未確認であり、注記が無いという意味にしない。
"""

from __future__ import annotations

import csv
import json
import math
import re
import tarfile
import time
import unicodedata
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

import osmium

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, shape

ROOT = Path(__file__).resolve().parents[3]
DRIVE = Path("/tmp/kanagawa_drive_20261109")
OUT_PRIV = Path("/opt/cursor/artifacts/kanagawa_private/2026-11-09_R1")
PUBLIC = ROOT / "reports" / "daily_region" / "data" / "2026-11-09_R1_week3_public.json"
TAR = Path("/opt/cursor/artifacts/kanagawa_private/supplemental_2026-11-09.tar.gz")
TMP = Path("/tmp/r1_anno_20261109")
RETRIEVED = "2026-11-09"

# セル面積の端数。地域行とセル合計の一致判定。
TOL_KM2 = 0.015
# 前日 R7: 差が小さくても種類が違えば等置しない。見た目が同じ、の上限。
CLOSE_KM2 = 0.05
# 森林の総流出のうち、建物用地以外がこれ以上あれば、純減と森林→建物用地は別の数。
MATERIAL_OTHER_KM2 = 1.0
# レビュー追補と同じ 50%。都筑区の森林純増を単一類型へ帰属する下限。動かさない。
SINGLE_TYPE_SHARE = 0.50
# 川崎区の建物用地総減少の行き先。週1の都市的転換の「森林＋荒地 15%未満」を行き先シェアに使う。
OTHER_SHARE_MIN = 0.50
FOREST_WASTE_SHARE_MAX = 0.15
# 週2本文の「5セル以上 9.6%（3.17 km²）」。1ポイント以内なら share_>=5 そのもの。
# 1〜2セルの補集合との差が 10 ポイント以上なら、補集合を 5セル以上と呼ばない。
GE5_CITED = 0.096
GE5_CITED_KM2 = 3.17
GE5_MATCH = 0.01
GE5_KM2_MATCH = 0.05
COMPLEMENT_GAP = 0.10
# 特別回と同じ距離。注記はタイル内の点なので 200 m。
OSM_MATCH_M = 400.0
ANNO_MATCH_M = 200.0
PLACE_FT = {"0210", "0220"}

R1_CODES = {f"141{i:02d}" for i in range(1, 19)} | {f"141{i:02d}" for i in range(31, 38)}
WIKIDATA = "https://query.wikidata.org/sparql"
PBF = Path("/tmp/kanto-latest.osm.pbf")
PBF_URL = "https://download.geofabrik.de/asia/japan/kanto-latest.osm.pbf"
RAIL_VALUES = {"station", "halt", "stop", "tram_stop", "abandoned", "disused", "razed"}
HIST_VALUES = {"wayside_shrine", "ruins", "shrine"}
UA = "kanagawa-ruins-search/2026-11-09"

SHRINE_TYPES = ("神社", "廃社", "神宮", "寺院", "廃寺")


def stem_of(value) -> str:
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
    y = int((1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r)) / math.pi) / 2.0 * n)
    return x, y


def tiles_for_buffer(lon: float, lat: float, radius_m: float = ANNO_MATCH_M) -> set[tuple[int, int]]:
    dlat = radius_m / 111_320.0
    dlon = radius_m / (111_320.0 * max(0.2, math.cos(math.radians(lat))))
    pts = [(lon, lat), (lon - dlon, lat - dlat), (lon + dlon, lat - dlat),
           (lon - dlon, lat + dlat), (lon + dlon, lat + dlat)]
    return {tile_xy(x, y) for x, y in pts}


def fetch_bytes(url: str, dest: Path, data: bytes | None = None, timeout: int = 180) -> bytes | None:
    if dest.exists() and dest.stat().st_size > 0:
        return dest.read_bytes()
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except Exception as exc:
        dest.with_suffix(dest.suffix + ".error").write_text(f"{type(exc).__name__}: {exc}\n{url}\n")
        return None
    dest.write_bytes(raw)
    return raw


def fetch_anno(x: int, y: int) -> dict | None:
    dest = TMP / f"15_{x}_{y}.geojson"
    url = f"https://cyberjapandata.gsi.go.jp/xyz/experimental_anno/15/{x}/{y}.geojson"
    raw = fetch_bytes(url, dest, timeout=30)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def rows_of(table):
    return [dict(zip(table["columns"], row)) for row in table["data"]]


def flow_km2(frame: pd.DataFrame, src: str, dst: str) -> float:
    sub = frame[(frame.grp2014 == src) & (frame.grp2021 == dst)]
    return float(sub.km2.sum())


def kind_of(tags) -> str:
    if tags.get("amenity") == "place_of_worship":
        return "worship"
    if tags.get("historic") in HIST_VALUES:
        return "historic"
    if tags.get("railway") in RAIL_VALUES:
        return "railway"
    return ""


class OsmWindow(osmium.SimpleHandler):
    """R1 を覆う矩形だけを残す。PBF 自体は保存しない。"""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[dict] = []
        self.relations_without_node = 0

    def _add(self, osm_type: str, osm_id: int, lon: float, lat: float, tags, kind: str) -> None:
        if not (139.44 <= lon <= 139.85 and 35.30 <= lat <= 35.65):
            return
        self.rows.append({
            "osm_type": osm_type, "osm_id": osm_id, "lat": lat, "lon": lon, "kind": kind,
            "name": tags.get("name") or tags.get("name:ja") or "",
            "religion": tags.get("religion") or "", "historic": tags.get("historic") or "",
            "railway": tags.get("railway") or "",
        })

    def node(self, n) -> None:
        kind = kind_of(n.tags)
        if kind and n.location.valid():
            self._add("node", n.id, n.location.lon, n.location.lat, n.tags, kind)

    def way(self, w) -> None:
        kind = kind_of(w.tags)
        if not kind:
            return
        lons, lats = [], []
        for node in w.nodes:
            if node.location.valid():
                lons.append(node.location.lon)
                lats.append(node.location.lat)
        if lons:
            self._add("way", w.id, sum(lons) / len(lons), sum(lats) / len(lats), w.tags, kind)

    def relation(self, r) -> None:
        kind = kind_of(r.tags)
        if not kind:
            return
        lons, lats = [], []
        for member in r.members:
            loc = getattr(member, "location", None)
            if member.type == "n" and loc is not None and loc.valid():
                lons.append(loc.lon)
                lats.append(loc.lat)
        if not lons:
            self.relations_without_node += 1
            return
        self._add("relation", r.id, sum(lons) / len(lons), sum(lats) / len(lats), r.tags, kind)


def pdf_signals(path: Path) -> dict:
    out = {"file": path.name, "pages": 0, "chars": 0, "counts": {}, "error": ""}
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        parts = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        blob = "\n".join(parts)
        out["pages"] = len(reader.pages)
        out["chars"] = len(blob)
        out["counts"] = {key: blob.count(key) for key in ("廃社", "廃寺", "合祀", "廃村", "横浜", "川崎")}
    except Exception as exc:
        out["error"] = type(exc).__name__
    return out


def main() -> None:
    TMP.mkdir(parents=True, exist_ok=True)
    data = json.loads((ROOT / "reports" / "phase1c2_results.json").read_text())
    reg = {name: dict(zip(data["aggregates"]["region"]["columns"], row))
           for name, row in zip(data["aggregates"]["region"]["index"], data["aggregates"]["region"]["data"])}
    r1 = reg["R1_yokohama_kawasaki"]
    region_cols = set(data["aggregates"]["region"]["columns"])
    rl_cols = set(data["aggregates"]["region_landscape"]["columns"])
    muni_cols = data["aggregates"]["municipality"]["columns"]
    munis = [row for row in rows_of(data["aggregates"]["municipality"]) if row["region"] == "R1_yokohama_kawasaki"]
    cc = data["transitions"]["component_class_share_by_region"]
    comp = {name: dict(zip(cc["columns"], row)) for name, row in zip(cc["index"], cc["data"])}["R1_yokohama_kawasaki"]
    focus = {}
    block = data["transitions"]["focus_by_region"]
    for row in block["data"]:
        rec = dict(zip(block["columns"], row))
        if rec["region"] == "R1_yokohama_kawasaki":
            focus[rec["transition"]] = rec
    breakdown_cols = sorted(c for c in (region_cols | rl_cols) if "other_from" in c or "to_other" in c or c.startswith("other_to_"))
    md = (ROOT / "reports" / "phase1c2_regional_analysis.md").read_text()
    area_table_has_other_transition = "その他→" in md or "→その他" in md

    cells = pd.read_parquet(
        DRIVE / "data/processed/phase1c/claude/phase1c2-claude-0.2.0/geoparquet/cells_landuse_change_2014_2021.parquet",
        columns=["region", "muni_code", "muni_name", "grp2014", "grp2021", "area_m2", "landscape"])
    r1c = cells[cells.region == "R1_yokohama_kawasaki"].copy()
    r1c["km2"] = r1c.area_m2 / 1e6
    if len(r1c) != int(r1["n_cells"]):
        raise SystemExit(f"cell count {len(r1c)} != {r1['n_cells']}")
    if abs(float(r1c.km2.sum()) - float(r1["land_km2"])) > TOL_KM2:
        raise SystemExit("cell land area disagrees with the region row")
    csv_row = pd.read_csv(
        DRIVE / "data/processed/phase1c/claude/phase1c2-claude-0.2.0/csv/agg_region.csv")
    csv_r1 = csv_row[csv_row.region == "R1_yokohama_kawasaki"].iloc[0]
    if abs(float(csv_r1.other_net_change_km2) - float(r1["other_net_change_km2"])) > 1e-9:
        raise SystemExit("Drive agg_region other_net disagrees with results.json")

    into_other = r1c[(r1c.grp2021 == "other") & (r1c.grp2014 != "other")]
    out_other = r1c[(r1c.grp2014 == "other") & (r1c.grp2021 != "other")]
    other_gain = float(into_other.km2.sum())
    other_loss = float(out_other.km2.sum())
    other_net = other_gain - other_loss
    into_other_by = {k: float(v) for k, v in into_other.groupby("grp2014").km2.sum().items()}
    out_other_by = {k: float(v) for k, v in out_other.groupby("grp2021").km2.sum().items()}
    building_to_other = into_other_by.get("building", 0.0)
    h1 = (len(breakdown_cols) == 0
          and not area_table_has_other_transition
          and abs(other_net - float(r1["other_net_change_km2"])) < TOL_KM2
          and abs(other_net - building_to_other) >= CLOSE_KM2)

    forest_loss_by = {k: float(v) for k, v in r1c[(r1c.grp2014 == "forest") & (r1c.grp2021 != "forest")]
                      .groupby("grp2021").km2.sum().items()}
    forest_gain_by = {k: float(v) for k, v in r1c[(r1c.grp2021 == "forest") & (r1c.grp2014 != "forest")]
                      .groupby("grp2014").km2.sum().items()}
    forest_loss = sum(forest_loss_by.values())
    forest_gain = sum(forest_gain_by.values())
    forest_net = forest_gain - forest_loss
    forest_to_building = forest_loss_by.get("building", 0.0)
    forest_to_non_building = forest_loss - forest_to_building
    json_reverse = float(focus["building->forest"]["reverse_area_km2"])
    h2 = (abs(forest_net - float(r1["forest_net_change_km2"])) < TOL_KM2
          and abs(forest_to_building - json_reverse) < TOL_KM2
          and abs(abs(forest_net) - forest_to_building) < CLOSE_KM2
          and forest_to_non_building >= MATERIAL_OTHER_KM2)

    tz = r1c[r1c.muni_name == "横浜市都筑区"]
    tz_json = next(row for row in munis if row["muni_name"] == "横浜市都筑区")
    type_nets = {}
    for landscape, part in tz.groupby("landscape"):
        gain = float(part[(part.grp2021 == "forest") & (part.grp2014 != "forest")].km2.sum())
        loss = float(part[(part.grp2014 == "forest") & (part.grp2021 != "forest")].km2.sum())
        type_nets[str(landscape)] = {"net_km2": gain - loss, "gain_km2": gain, "loss_km2": loss,
                                     "land_km2": float(part.km2.sum())}
    tz_net = sum(v["net_km2"] for v in type_nets.values())
    positive = {k: v["net_km2"] for k, v in type_nets.items() if v["net_km2"] > 0}
    top_type, top_net = max(positive.items(), key=lambda kv: kv[1]) if positive else ("", 0.0)
    top_share = (top_net / tz_net) if tz_net else 0.0
    h3 = (abs(tz_net - float(tz_json["forest_net_change_km2"])) < TOL_KM2
          and top_share > SINGLE_TYPE_SHARE)

    kw = r1c[r1c.muni_name == "川崎市川崎区"]
    kw_json = next(row for row in munis if row["muni_name"] == "川崎市川崎区")
    bloss = kw[(kw.grp2014 == "building") & (kw.grp2021 != "building")]
    bloss_km2 = float(bloss.km2.sum())
    bloss_by = {k: float(v) for k, v in bloss.groupby("grp2021").km2.sum().items()}
    other_share = bloss_by.get("other", 0.0) / bloss_km2 if bloss_km2 else 0.0
    fw_share = (bloss_by.get("forest", 0.0) + bloss_by.get("wasteland", 0.0)) / bloss_km2 if bloss_km2 else 0.0
    h4 = (abs(bloss_km2 - float(kw_json["building_loss_km2"])) < TOL_KM2
          and float(kw_json["building_to_forest_km2"]) == 0.0
          and float(kw_json["building_to_wasteland_km2"]) == 0.0
          and other_share > OTHER_SHARE_MIN
          and fw_share < FOREST_WASTE_SHARE_MAX)

    s1, s2, s34, s5 = comp["share_1"], comp["share_2"], comp["share_3-4"], comp["share_>=5"]
    changed = float(comp["changed_km2"])
    complement = 1.0 - s1 - s2
    h5 = (abs(s5 - GE5_CITED) < GE5_MATCH
          and abs(s5 * changed - GE5_CITED_KM2) < GE5_KM2_MATCH
          and (complement - s5) >= COMPLEMENT_GAP
          and float(focus["building->forest"]["size_>=5_share"]) == 0.0
          and float(focus["agri->forest"]["size_>=5_share"]) == 0.0)

    agri_to_building = flow_km2(r1c, "agri", "building")
    bf_cells = int(((r1c.grp2014 == "building") & (r1c.grp2021 == "forest")).sum())
    af_cells = int(((r1c.grp2014 == "agri") & (r1c.grp2021 == "forest")).sum())
    if (bf_cells, af_cells) != (int(focus["building->forest"]["cells"]), int(focus["agri->forest"]["cells"])):
        raise SystemExit(f"focus cell counts {bf_cells} {af_cells}")

    # --- 現行地図側。旧版タイルは取らない。 ---
    admin = gpd.read_parquet(DRIVE / "data/processed/phase1a/vectors/admin__n03__2026_kanagawa.parquet")
    admin["code"] = admin["N03_007"].astype(str)
    r1_admin = admin[admin.code.isin(R1_CODES)].copy()
    if r1_admin.code.nunique() != 25:
        raise SystemExit(f"N03 ward codes {r1_admin.code.nunique()} != 25")
    code_to_ward = {str(code): name for code, name in
                    r1c[["muni_code", "muni_name"]].drop_duplicates().itertuples(index=False)}
    if len(code_to_ward) != 25:
        raise SystemExit("ward code map is not 25")

    bbox = (35.30, 139.44, 35.65, 139.85)  # south, west, north, east
    osm_path = TMP / "osm_r1_extract.json"
    if osm_path.exists() and osm_path.stat().st_size > 0:
        osm_rows = json.loads(osm_path.read_text())
        relations_without_node = 0
    else:
        if not PBF.exists():
            raise SystemExit(f"missing {PBF}")
        handler = OsmWindow()
        handler.apply_file(str(PBF), locations=True)
        osm_rows = handler.rows
        relations_without_node = handler.relations_without_node
        osm_path.write_text(json.dumps(osm_rows, ensure_ascii=False))
    osm_gdf = gpd.GeoDataFrame(osm_rows, geometry=[Point(r["lon"], r["lat"]) for r in osm_rows], crs="EPSG:4326")
    osm_m = osm_gdf.to_crs(r1_admin.crs)
    osm_in = gpd.sjoin(osm_m, r1_admin[["code", "geometry"]], how="inner", predicate="within")
    osm_in = osm_in[~osm_in.index.duplicated(keep="first")]
    worship_in = osm_in[osm_in.kind == "worship"]

    sparql = """
SELECT ?item ?itemLabel ?coord ?end ?typeLabel WHERE {
  ?item wdt:P131* wd:Q127513 .
  ?item wdt:P625 ?coord .
  { ?item wdt:P576 ?end } UNION { ?item wdt:P582 ?end }
  OPTIONAL { ?item wdt:P31 ?type . ?type rdfs:label ?typeLabel FILTER(LANG(?typeLabel)="ja") }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ja,en". }
}
"""
    wd_path = TMP / "wikidata_ended_kanagawa.json"
    wd_url = WIKIDATA + "?query=" + urllib.parse.quote(sparql)
    wd_raw = None
    for attempt in range(4):
        wd_raw = fetch_bytes(wd_url, wd_path, timeout=180)
        if wd_raw is not None:
            break
        time.sleep(70)
    if wd_raw is None:
        raise SystemExit("Wikidata fetch failed")
    wd = json.loads(wd_raw)
    items = {}
    for row in wd["results"]["bindings"]:
        iid = row["item"]["value"].rsplit("/", 1)[-1]
        slot = items.setdefault(iid, {"id": iid, "label": row.get("itemLabel", {}).get("value", ""),
                                      "end": (row.get("end", {}).get("value") or "")[:10],
                                      "coord": row.get("coord", {}).get("value", ""), "types": set()})
        if "typeLabel" in row:
            slot["types"].add(row["typeLabel"]["value"])
    shrine_items = []
    for item in items.values():
        if not any(any(token in t for token in SHRINE_TYPES) for t in item["types"]):
            continue
        if not str(item["coord"]).startswith("Point("):
            continue
        lon_s, lat_s = item["coord"][len("Point("):-1].split()
        shrine_items.append({**item, "lon": float(lon_s), "lat": float(lat_s),
                             "types": "/".join(sorted(item["types"]))})
    if shrine_items:
        shrine_gdf = gpd.GeoDataFrame(shrine_items, geometry=[Point(r["lon"], r["lat"]) for r in shrine_items], crs="EPSG:4326").to_crs(r1_admin.crs)
        shrine_in = gpd.sjoin(shrine_gdf, r1_admin[["code", "geometry"]], how="inner", predicate="within")
        shrine_in = shrine_in[~shrine_in.index.duplicated(keep="first")]
    else:
        shrine_in = gpd.GeoDataFrame(columns=["id", "label", "code", "geometry"])

    p32 = gpd.read_parquet(DRIVE / "data/processed/phase1a/vectors/cultural__mlit_cultural_properties_kanagawa__2014.parquet")
    p32_in = gpd.sjoin(p32.to_crs(r1_admin.crs), r1_admin[["code", "geometry"]], how="inner", predicate="within")
    p32_in = p32_in[~p32_in.index.duplicated(keep="first")]
    p32_names = []
    for _, row in p32_in.iterrows():
        p32_names.append({"stem": stem_of(str(row.get("P32_006") or "")), "geometry": row.geometry,
                          "code": str(row["code"])})

    # 注記。焦点セルは重心のタイルだけ。候補点は 200 m バッファが交わるタイル。
    cell_geom = gpd.read_parquet(
        DRIVE / "data/processed/phase1c/claude/phase1c2-claude-0.2.0/geoparquet/cells_landuse_change_2014_2021.parquet",
        columns=["region", "grp2014", "grp2021", "geometry"])
    r1g = cell_geom[cell_geom.region == "R1_yokohama_kawasaki"]
    focus_cells = r1g[((r1g.grp2014 == "building") & (r1g.grp2021 == "forest"))
                      | ((r1g.grp2014 == "agri") & (r1g.grp2021 == "forest"))].copy()
    focus_ll = gpd.GeoDataFrame(focus_cells.drop(columns="geometry"),
                                geometry=focus_cells.geometry.centroid, crs=focus_cells.crs).to_crs(4326)
    tiles: dict[tuple[int, int], str] = {}
    for geom in focus_ll.geometry:
        tiles[tile_xy(float(geom.x), float(geom.y))] = "focus"
    prev = list(csv.DictReader((DRIVE / "data/private_findings/2026-11-05_special_R1-R4/candidates.csv").open()))
    prev_r1 = [row for row in prev if row["region"] == "R1"]
    if len(prev_r1) != 24:
        raise SystemExit(f"R1 candidates {len(prev_r1)} != 24")
    for row in prev_r1:
        for key in tiles_for_buffer(float(row["lon"]), float(row["lat"])):
            tiles.setdefault(key, "candidate")
    anno_feats = []
    tile_status = []
    for (x, y), role in sorted(tiles.items()):
        time.sleep(0.02)
        payload = fetch_anno(x, y)
        ok = payload is not None
        tile_status.append({"z": 15, "x": x, "y": y, "role": role, "ok": ok,
                            "features": 0 if not ok else len(payload.get("features", []))})
        if not ok:
            continue
        for feat in payload.get("features", []):
            props = feat.get("properties") or {}
            geom = feat.get("geometry")
            if not geom:
                continue
            anno_feats.append({"knj": props.get("knj") or "", "ftCode": str(props.get("ftCode") or ""),
                               "annoCtg": props.get("annoCtg") or "", "geometry": shape(geom)})
    anno = gpd.GeoDataFrame(anno_feats, geometry="geometry", crs="EPSG:4326").to_crs(r1_admin.crs) if anno_feats else gpd.GeoDataFrame(geometry=[], crs=r1_admin.crs)
    shrine_note = anno[anno["knj"].fillna("").str.contains("神社|寺院|鳥居")] if len(anno) else anno
    shrine_cells = 0
    shrine_cells_verified = 0
    failed_tiles = {(t["x"], t["y"]) for t in tile_status if not t["ok"]}
    focus_failed = 0
    if len(focus_ll):
        for geom in focus_ll.geometry:
            if tile_xy(float(geom.x), float(geom.y)) in failed_tiles:
                focus_failed += 1
    if len(shrine_note):
        hit = gpd.sjoin(focus_cells, shrine_note[["geometry"]], how="inner", predicate="intersects")
        shrine_cells = int(hit.index.nunique()) if len(hit) else 0
    # 検証できた焦点セルは、404 タイルの重心セルを除いた数。神社注記の交差は返ったタイルに限る。
    shrine_cells_verified = int(len(focus_cells) - focus_failed)

    osm_named = [{"stem": stem_of(name), "geometry": geom}
                 for name, geom in zip(osm_in["name"], osm_in.geometry)]
    anno_named = []
    if len(anno):
        for _, row in anno.iterrows():
            ctg = str(row["annoCtg"])
            if str(row["ftCode"]) in PLACE_FT or ctg.startswith("居住地名") or ctg.startswith("行政区画"):
                continue
            anno_named.append({"stem": stem_of(str(row["knj"])), "geometry": row.geometry, "ctg": ctg})

    reval = []
    for row in prev_r1:
        pt = gpd.GeoSeries([Point(float(row["lon"]), float(row["lat"]))], crs="EPSG:4326").to_crs(r1_admin.crs).iloc[0]
        pt_stem = stem_of(row["name"])
        osm_hit = any(rec["stem"] and rec["stem"] == pt_stem and pt.distance(rec["geometry"]) <= OSM_MATCH_M for rec in osm_named)
        p32_hit = any(rec["stem"] and rec["stem"] == pt_stem and pt.distance(rec["geometry"]) <= OSM_MATCH_M for rec in p32_names)
        needed = tiles_for_buffer(float(row["lon"]), float(row["lat"]))
        anno_unverified = any(key in failed_tiles for key in needed)
        anno_hit = any(rec["stem"] and rec["stem"] == pt_stem and pt.distance(rec["geometry"]) <= ANNO_MATCH_M for rec in anno_named)
        if osm_hit:
            outcome, reason = "棄却", "2026-11-09のOSMに同じ語幹が400m以内にある"
        elif p32_hit:
            outcome, reason = "棄却", "P32（2014-01-31）に同じ語幹が400m以内にある"
        elif anno_hit:
            outcome, reason = "棄却", "現行の地理院注記（居住地名・行政区画以外）に同じ語幹が200m以内にある。地図から消えていない"
        elif anno_unverified:
            outcome, reason = "維持", "OSMとP32には同じ語幹が無い。注記タイルが404で、注記は未確認。旧版記号は未照合のため中のまま。格上げしない"
        else:
            outcome, reason = "維持", "OSM・P32・取得できた現行注記に同じ語幹が無い。注記は文字であり旧版の記号ではないので中のまま。格上げしない"
        reval.append({"id": row["id"], "muni_name": row["muni_name"], "name": row["name"],
                      "lat": float(row["lat"]), "lon": float(row["lon"]), "category": row["category"],
                      "prior_confidence": row["confidence"], "outcome": outcome, "confidence": "中" if outcome == "維持" else "",
                      "reason": reason, "lu2014": row["lu2014"], "lu2021": row["lu2021"],
                      "anno_unverified": anno_unverified and outcome == "維持",
                      "evidence_present": row["evidence_present"], "evidence_absent": row["evidence_absent"]})

    new_candidates = []
    new_rejected = []
    if len(shrine_in):
        for _, rec in shrine_in.iterrows():
            pt_stem = stem_of(str(rec["label"]))
            if len(pt_stem) < 2:
                continue
            pt = rec.geometry
            osm_hit = any(r["stem"] and r["stem"] == pt_stem and pt.distance(r["geometry"]) <= OSM_MATCH_M for r in osm_named)
            p32_hit = any(r["stem"] and r["stem"] == pt_stem and pt.distance(r["geometry"]) <= OSM_MATCH_M for r in p32_names)
            ward = code_to_ward.get(str(rec["code"]), "")
            if osm_hit or p32_hit or not ward:
                new_rejected.append({"label": rec["label"], "id": rec["id"], "ward": ward,
                                     "why": "osm" if osm_hit else ("p32" if p32_hit else "no_ward")})
                continue
            new_candidates.append({
                "muni_name": ward, "name": str(rec["label"]), "lat": float(rec["lat"]), "lon": float(rec["lon"]),
                "category": "shrine", "confidence": "中",
                "reason": "Wikidataの終了日と座標がR1の区内にあり、2026-11-09のOSMとP32に同じ語幹が400m以内に無い。旧版の鳥居記号は未照合のため高にしない。",
                "present": f"Wikidata {rec['id']} 終了日 {rec['end']} 型 {rec['types']}",
                "absent": "現行OSMとP32に同じ語幹が400m以内に無い。旧版地形図は見ていない。",
                "lu2014": "", "lu2021": "", "source_id": rec["id"],
            })
    for i, cand in enumerate(sorted(new_candidates, key=lambda c: (c["muni_name"], c["source_id"])), start=25):
        cand["id"] = f"R1-{i:03d}"

    maintained = [r for r in reval if r["outcome"] == "維持"]
    rejected = [r for r in reval if r["outcome"] == "棄却"]
    adopted = maintained + new_candidates

    lit_paths = [
        DRIVE / "data/literature/papers/Fujita2007_ShrineLocationGIS.pdf",
        DRIVE / "data/literature/papers/Oda2015_ShrineMerger.pdf",
        DRIVE / "data/literature/papers/Kanaki2003_AbandonedSettlements.pdf",
        DRIVE / "data/literature/papers/Wood2024_MapReader.pdf",
        DRIVE / "data/literature/papers/Tani2017_KonjakuMap.pdf",
        DRIVE / "data/literature/papers/Tabayashi2026_OldMapGeoreferencingAI.pdf",
        DRIVE / "data/literature/papers/Luft2021_HistoricalMapGeoreferencing.pdf",
        DRIVE / "data/raw/cultural_properties/kanagawa_bunkazai_mokuroku_r07.pdf",
    ]
    literature = [pdf_signals(path) for path in lit_paths]
    manifest = json.loads((DRIVE / "data/literature/historical_documents/Shinpen_Sagami_Fudokiko_Vol5_IIIF_manifest.json").read_text())
    manifest_has_coord = "Point(" in json.dumps(manifest)[:2000] or any(
        isinstance(v, str) and re.search(r"1[23]9\.\d{4}", v) for v in manifest.values() if isinstance(v, str))

    by_outcome = Counter(r["outcome"] for r in reval)
    reason_counts = Counter(r["reason"].split("。")[0] for r in rejected)
    muni_rows = []
    for name in sorted({r["muni_name"] for r in reval}):
        ids = [r["id"] for r in reval if r["muni_name"] == name]
        muni_rows.append({
            "muni_name": name,
            "input": len(ids),
            "maintained": sum(1 for r in reval if r["muni_name"] == name and r["outcome"] == "維持"),
            "rejected": sum(1 for r in reval if r["muni_name"] == name and r["outcome"] == "棄却"),
            "upgraded": 0,
            "ids": ids,
        })
    new_by_muni = []
    for name, count in sorted(Counter(c["muni_name"] for c in new_candidates).items()):
        new_by_muni.append({"muni_name": name, "total": count,
                            "ids": [c["id"] for c in new_candidates if c["muni_name"] == name]})

    numbers = {
        "rotation": {"start": "2026-10-26", "date": "2026-11-09", "elapsed_days": 14,
                     "week": 14 // 7 + 1, "region_index": 14 % 7, "region": "R1"},
        "thresholds": {
            "tol_km2": TOL_KM2, "close_km2": CLOSE_KM2, "material_other_km2": MATERIAL_OTHER_KM2,
            "single_type_share": SINGLE_TYPE_SHARE, "other_share_min": OTHER_SHARE_MIN,
            "forest_waste_share_max": FOREST_WASTE_SHARE_MAX, "ge5_cited": GE5_CITED,
            "ge5_match": GE5_MATCH, "complement_gap": COMPLEMENT_GAP,
        },
        "h1_other_net_closed_by_cells_not_by_public_table": h1,
        "h2_forest_net_not_equal_to_forest_to_building": h2,
        "h3_tsuzuki_forest_gain_one_type_over_half": h3,
        "h4_kawasaki_building_loss_mostly_other": h4,
        "h5_week2_9_6_is_share_ge5": h5,
        "other": {
            "json_net_km2": float(r1["other_net_change_km2"]),
            "cell_gain_km2": other_gain, "cell_loss_km2": other_loss, "cell_net_km2": other_net,
            "gain_by_source_km2": into_other_by, "loss_by_destination_km2": out_other_by,
            "building_to_other_km2": building_to_other,
            "net_minus_building_to_other_km2": other_net - building_to_other,
            "breakdown_columns": breakdown_cols,
            "area_table_has_other_transition": area_table_has_other_transition,
        },
        "forest": {
            "json_net_km2": float(r1["forest_net_change_km2"]),
            "cell_gain_km2": forest_gain, "cell_loss_km2": forest_loss, "cell_net_km2": forest_net,
            "loss_by_destination_km2": forest_loss_by, "gain_by_source_km2": forest_gain_by,
            "to_building_km2": forest_to_building, "to_non_building_km2": forest_to_non_building,
            "json_reverse_building_to_forest_km2": json_reverse,
            "abs_net_minus_to_building_km2": abs(forest_net) - forest_to_building,
        },
        "tsuzuki": {
            "json_forest_net_km2": float(tz_json["forest_net_change_km2"]),
            "cell_forest_net_km2": tz_net, "by_landscape": type_nets,
            "top_type": top_type, "top_share": top_share,
        },
        "kawasaki_ward": {
            "json_building_loss_km2": float(kw_json["building_loss_km2"]),
            "cell_building_loss_km2": bloss_km2, "by_destination_km2": bloss_by,
            "other_share": other_share, "forest_wasteland_share": fw_share,
            "building_to_forest_km2": float(kw_json["building_to_forest_km2"]),
            "building_to_wasteland_km2": float(kw_json["building_to_wasteland_km2"]),
        },
        "components": {
            "share_1": s1, "share_2": s2, "share_3_4": s34, "share_ge5": s5,
            "changed_km2": changed, "ge5_km2": s5 * changed,
            "complement_of_1_2": complement, "complement_km2": complement * changed,
            "gap": complement - s5,
            "focus_building_to_forest_ge5": float(focus["building->forest"]["size_>=5_share"]),
            "focus_agri_to_forest_ge5": float(focus["agri->forest"]["size_>=5_share"]),
            "focus_building_cells": bf_cells, "focus_agri_cells": af_cells,
        },
        "published_agri_to_building_km2": 3.73,
        "cell_agri_to_building_km2": agri_to_building,
        "gsi_anno": {
            "zoom": 15, "unique_tiles": len(tiles),
            "tiles_ok": sum(1 for t in tile_status if t["ok"]),
            "tiles_failed": sum(1 for t in tile_status if not t["ok"]),
            "focus_cells": int(len(focus_cells)),
            "focus_cells_on_failed_centroid_tile": focus_failed,
            "focus_cells_whose_centroid_tile_returned": shrine_cells_verified,
            "focus_cells_intersecting_shrine_annotation": shrine_cells,
            "note": "現行注記。404は未確認。旧版の鳥居記号ではない。居住地名ftCode 0210は施設記号に使わない。",
        },
        "osm_worship_unique_in_r1_admin": int(len(worship_in)),
        "osm_features_unique_in_r1_admin": int(len(osm_in)),
        "p32_in_r1_admin": int(len(p32_in)),
        "wikidata_ended_with_coord": len(items),
        "wikidata_shrine_like_with_coord": len(shrine_items),
        "wikidata_shrine_like_in_r1": int(len(shrine_in)) if shrine_items else 0,
        "literature_keyword_counts": literature,
        "fudoki_manifest_has_coordinate": manifest_has_coord,
        "old_map_torii_compared": False,
        "lost_sites": {
            "prior_r1": 24,
            "maintained": len(maintained),
            "maintained_anno_unverified": sum(1 for r in maintained if r["anno_unverified"]),
            "upgraded": 0,
            "rejected": len(rejected),
            "reject_reason_counts": dict(reason_counts),
            "new_shrine": len(new_candidates),
            "new_shrine_rejected_still_named": len(new_rejected),
            "adopted": len(adopted),
            "高": 0,
            "中": sum(1 for c in adopted if (c.get("confidence") or "中") == "中"),
            "低": 0,
            "shrine_adopted": len(new_candidates),
            "by_municipality_revalidation": muni_rows,
            "by_municipality_new": new_by_muni,
        },
    }
    def contains_name(obj, name: str) -> bool:
        if isinstance(obj, dict):
            return any(contains_name(v, name) for k, v in obj.items() if k != "muni_name")
        if isinstance(obj, list):
            return any(contains_name(v, name) for v in obj)
        if isinstance(obj, str):
            return bool(name) and name in obj
        return False

    for row in prev_r1:
        if contains_name(numbers, row["name"]):
            raise SystemExit("public json contains a prior site name")
    for cand in new_candidates:
        if contains_name(numbers, cand["name"]):
            raise SystemExit("public json contains a new site name")
    PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC.write_text(json.dumps(numbers, ensure_ascii=False, indent=2) + "\n")

    OUT_PRIV.mkdir(parents=True, exist_ok=True)
    fields = ["id", "muni_name", "name", "lat", "lon", "category", "outcome", "confidence",
              "reason", "lu2014", "lu2021", "anno_unverified", "evidence_present", "evidence_absent"]
    with (OUT_PRIV / "candidates.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in reval:
            out = dict(row)
            out["lat"] = f"{row['lat']:.7f}"
            out["lon"] = f"{row['lon']:.7f}"
            writer.writerow({k: out.get(k, "") for k in fields})
        for cand in new_candidates:
            writer.writerow({
                "id": cand["id"], "muni_name": cand["muni_name"], "name": cand["name"],
                "lat": f"{cand['lat']:.7f}", "lon": f"{cand['lon']:.7f}", "category": cand["category"],
                "outcome": "新規", "confidence": cand["confidence"], "reason": cand["reason"],
                "lu2014": "", "lu2021": "", "anno_unverified": "",
                "evidence_present": cand["present"], "evidence_absent": cand["absent"],
            })
    lines = [
        "# 非公開: R1 2026-11-09 消失候補",
        "",
        "名称と座標を含む。リポジトリと PR には置かない。",
        f"特別回 R1 の再検証 {len(reval)} 件。維持 {len(maintained)}、棄却 {len(rejected)}、格上げ 0。",
        f"新規の神社候補 {len(new_candidates)} 件。高確度は旧版地形図未照合のため 0。",
        "旧版ラスタ、今昔マップ、迅速測図のタイルは取得していない。",
        "津久井窓の OSM worship / historic parquet は R1 に使っていない。",
        "",
        "## 再検証",
        "",
    ]
    for row in reval:
        lines += [
            f"## {row['id']}",
            "",
            f"- 市区町村: {row['muni_name']}",
            f"- 名称: {row['name']}",
            f"- 緯度: {row['lat']:.7f}",
            f"- 経度: {row['lon']:.7f}",
            f"- 種別: {row['category']}",
            f"- 特別回の確度: {row['prior_confidence']}",
            f"- 今回: {row['outcome']} {row['confidence']}".rstrip(),
            f"- 理由: {row['reason']}",
            f"- 土地利用（特別回の記録）: {row['lu2014'] or '（空）'} → {row['lu2021'] or '（空）'}",
            f"- あった資料: {row['evidence_present']}",
            "",
        ]
    lines += ["## 新規", ""]
    if not new_candidates:
        lines.append("Wikidata の終了日付きで、神社・寺院の型を持ち、R1 の区内に落ち、現行 OSM と P32 に同じ語幹が無い地点は 0 件。")
    for cand in new_candidates:
        lines += [
            f"## {cand['id']}",
            "",
            f"- 市区町村: {cand['muni_name']}",
            f"- 名称: {cand['name']}",
            f"- 緯度: {cand['lat']:.7f}",
            f"- 経度: {cand['lon']:.7f}",
            f"- 確度: {cand['confidence']}",
            f"- 理由: {cand['reason']}",
            f"- あった資料: {cand['present']}",
            f"- 無い資料: {cand['absent']}",
            "",
        ]
    if new_rejected:
        lines += ["## 新規にはしなかった終了日付きの社寺（現行資料に名称が残る、または区名に落ちない）", ""]
        for rec in new_rejected:
            lines.append(f"- {rec['ward']} {rec['label']} {rec['id']} ({rec['why']})")
        lines.append("")
    (OUT_PRIV / "findings.md").write_text("\n".join(lines) + "\n")

    prov_rows = [
        {
            "source_id": "geofabrik_kanto_latest_r1_extract_2026-11-09",
            "source_url": PBF_URL,
            "source_page": "https://download.geofabrik.de/asia/japan/kanto.html",
            "retrieved": RETRIEVED,
            "license": "OpenStreetMap contributors, ODbL 1.0",
            "md5_file": "https://download.geofabrik.de/asia/japan/kanto-latest.osm.pbf.md5",
            "md5": Path("/tmp/kanto-latest.osm.pbf.md5").read_text().split()[0] if Path("/tmp/kanto-latest.osm.pbf.md5").exists() else "",
            "query_bbox_south_west_north_east": list(bbox),
            "scope": "関東PBFから、R1を覆う矩形の place_of_worship、historic=wayside_shrine|ruins|shrine、railway=station|halt|stop|tram_stop|abandoned|disused|razed を抽出。集計は N03 2026 の横浜18区・川崎7区の内側だけ。津久井窓の parquet は使っていない。PBF本体は20MBを超えるため tar に入れず、抽出JSONだけを残す。Overpass はタイムアウトしたため使っていない。",
            "elements_in_bbox": len(osm_rows),
            "relations_without_node_location": relations_without_node,
        },
        {
            "source_id": "wikidata_ended_kanagawa_2026-11-09",
            "source_url": WIKIDATA,
            "retrieved": RETRIEVED,
            "license": "CC0",
            "scope": "神奈川県に含まれ、座標と終了日（P576 または P582）がある項目。神社候補は型ラベルに神社・廃社・神宮・寺院・廃寺を含むものだけを R1 の区内で見た。",
            "items": len(items),
        },
        {
            "source_id": "gsi_experimental_anno_z15_r1_focus_and_candidates",
            "source_url_pattern": "https://cyberjapandata.gsi.go.jp/xyz/experimental_anno/15/{x}/{y}.geojson",
            "source_page": "https://maps.gsi.go.jp/development/ichiran.html",
            "retrieved": RETRIEVED,
            "license": "国土地理院コンテンツ利用規約（出典明示）",
            "scope": "建物用地→森林と農地→森林の重心タイル、および特別回 R1 候補の 200m バッファが交わるタイル。旧版地形図・今昔マップ・迅速測図ではない。404 は未確認。",
            "tiles": tile_status,
        },
    ]
    prov = TMP / "provenance_supplemental.jsonl"
    prov.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in prov_rows))
    if TAR.exists():
        TAR.unlink()
    with tarfile.open(TAR, "w:gz") as archive:
        archive.add(prov, arcname="provenance_supplemental.jsonl")
        archive.add(osm_path, arcname="osm_r1_extract.json")
        archive.add(wd_path, arcname="wikidata_ended_kanagawa.json")
        for path in sorted(TMP.glob("15_*.geojson")):
            archive.add(path, arcname=f"gsi_experimental_anno_z15/{path.name}")
    summary = {
        "h1": h1, "h2": h2, "h3": h3, "h4": h4, "h5": h5,
        "other_net": round(other_net, 4), "building_to_other": round(building_to_other, 4),
        "forest_loss": round(forest_loss, 4), "forest_to_building": round(forest_to_building, 4),
        "forest_non_building": round(forest_to_non_building, 4),
        "tz_net": round(tz_net, 4), "tz_top": top_type, "tz_share": round(top_share, 4),
        "kw_loss": round(bloss_km2, 4), "kw_other_share": round(other_share, 4), "kw_fw": round(fw_share, 4),
        "ge5": round(s5, 5), "ge5_km2": round(s5 * changed, 4), "complement": round(complement, 5),
        "agri_to_building": round(agri_to_building, 4),
        "tiles": len(tiles), "tiles_ok": sum(1 for t in tile_status if t["ok"]),
        "focus_failed": focus_failed, "shrine_cells": shrine_cells,
        "worship": int(len(worship_in)), "maintained": len(maintained), "rejected": len(rejected),
        "new_shrines": len(new_candidates), "shrine_like_r1": int(len(shrine_in)) if shrine_items else 0,
        "tar_bytes": TAR.stat().st_size,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
