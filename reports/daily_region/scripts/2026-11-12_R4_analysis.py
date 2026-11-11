"""R4（県央、相模原市を除く）3週目。2026-11-12。

主目的は廃神社・廃寺・消滅集落・廃道・廃施設の探索と検証。
土地利用は、2026-11-05の申し送りが既存集計でまだ言えるかの確認に限る。

公開JSONには件数、市区町村、候補ID、3軸、確度だけを書く。
名称と緯度経度は PRIVATE_LEADS_JSON と既存CSVから読み、
/opt/cursor/artifacts/kanagawa_private/2026-11-12_R4/ に出す。
スクリプトには地点の緯度経度も候補名も書かない。

評価は件数を数える前に固定した。

- 過去に存在した根拠、廃止・消失の根拠、物理的遺構が残る可能性は別の欄にする。
- 現行の地図に名称が無いこと、森林化、神社庁の検索に出ないことは、消失の根拠にしない。
- 座標は、既存CSVか、取得した項目の座標欄にあるものだけを使う。
  字名や住所からは点を作らない。
- 駅は、現行の旅客駅（railway=station または halt）と同じ語幹が1km以内なら棄却する。
  1kmは動かさない。語幹は完全一致。要望や計画だけの新駅は現行駅に数えない。
- 400m以内の historic、または P32 の同じ語幹は、遺構の欄を中にする。廃止は取り消さない。
- 総合確度の高は、旧版地形図の記号を見ていない限り付けない。
- 廃駅カテゴリの記事で、リード文かカテゴリに廃駅があり、廃止の年月日と
  Wikidataの終了日があり、1km規則を満たすものは、総合確度を中にする。
  中は旧版地形図を見たという意味ではない。
- 学校、病院、事件、架空の国家、軍の部隊、行政合併そのものはIDを付けない。
- 外部の神社リードは、公的な廃止・実行された合祀の記録が無い限り廃社にしない。
  探訪記の「廃」「旧」は管理状態の手がかりであり、廃止の欄を上げない。
  存在の強は、この回に開いた公的文書があるときだけ付ける。
  ブログと資料の引用だけでは中までとする。遺構はブログでは未確認のままとする。
- 県央史談会の史跡めぐりPDFはテキストを検査したあと削除し、再配布しない。
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq
import pyproj
from shapely import from_wkb
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parents[3]
DRIVE = Path(os.environ.get("RUINS_DRIVE_DIR", "/tmp/r4work"))
LEADS_PATH = Path(os.environ.get("PRIVATE_LEADS_JSON", ""))
EXISTING_CSV = Path(os.environ.get("PRIVATE_CANDIDATES_CSV", ""))
OUT_PRIV = Path("/opt/cursor/artifacts/kanagawa_private/2026-11-12_R4")
PUBLIC = ROOT / "reports" / "daily_region" / "data" / "2026-11-12_R4_week3_public.json"
RESULTS = ROOT / "reports" / "phase1c2_results.json"
SUPP = Path(os.environ.get("R4_WORK_DIR", "/tmp/r4_supp_20261112"))
RETRIEVED = "2026-11-12"
UA = "kanagawa-ruins-search/2026-11-12"
R4_CODES = {"14212", "14213", "14215", "14216", "14218", "14401", "14402"}
MUNI_Q = {
    "Q389711": "14212",
    "Q386697": "14213",
    "Q734390": "14215",
    "Q145333": "14216",
    "Q792819": "14218",
    "Q1203267": "14401",
    "Q1344386": "14402",
}
OSM_MATCH_M = 400.0
STATION_LIVE_M = 1000.0
ANNO_MATCH_M = 200.0
PLACE_FT = {"0210", "0220"}
FORMER_STATION = "Q4663385"
CELL_FLOOR = 0.5
TEN = 0.10
GE5_MAX = 0.10
KENOU_PDF = "http://kenou.stars.ne.jp/20241103/Phot/20241103.pdf"
ARCHIVE_LIST = "https://wwwy4.musetheque.jp/kanagawa_archives/list"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
WIKI_API = "https://ja.wikipedia.org/w/api.php"
OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
GSI_LIST = "https://maps.gsi.go.jp/development/ichiran.html"
ANNO_URL = "https://cyberjapandata.gsi.go.jp/xyz/experimental_anno/15/{x}/{y}.geojson"
AERIAL_URL = "https://cyberjapandata.gsi.go.jp/xyz/ort_old10/17/{x}/{y}.png"
CAT_JA = {
    "station": "駅",
    "town_name": "集落",
    "facility": "施設",
    "shrine": "神社",
    "temple": "寺院",
    "settlement": "集落",
    "road": "廃道",
    "神社": "神社",
    "駅": "駅",
    "集落": "集落",
}

TO_6677 = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:6677", always_xy=True)
TO_WGS = pyproj.Transformer.from_crs("EPSG:6677", "EPSG:4326", always_xy=True)
GEOD = pyproj.Geod(ellps="WGS84")
KANAGAWA_COARSE_LAT = (35.10, 35.70)
KANAGAWA_COARSE_LON = (138.90, 139.80)
COORD_RE = re.compile(r"(?:3[45]|13[89])\.[0-9]{3,}")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def stem_of(value) -> str:
    if not isinstance(value, str) or not value:
        return ""
    text = unicodedata.normalize("NFKC", value)
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"（[^）]*）", "", text)
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"\[[^\]]*\]", "", text)
    return re.sub(
        r"(神社|神宮|大社|停留場|乗降場|駅|跡|小学校|中学校|高等学校|高校|大学|病院|信号所|信号場|仮乗降場)$",
        "",
        text,
    )


def html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<script[\s\S]*?</script>", " ", raw)
    raw = re.sub(r"(?is)<style[\s\S]*?</style>", " ", raw)
    raw = re.sub(r"(?is)<img\b[^>]*>", " ", raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", raw).strip()


def fetch(url: str, dest: Path | None, data: bytes | None = None, timeout: int = 90,
          accept: str = "*/*") -> bytes | None:
    req = urllib.request.Request(
        url,
        data=data,
        headers={"User-Agent": UA, "Accept": accept},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except Exception as exc:  # noqa: BLE001 — 取得失敗は未取得として残す
        if dest is not None:
            dest.with_suffix(dest.suffix + ".err").write_text(repr(exc), encoding="utf-8")
        return None
    if dest is not None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
    return raw


def append_prov(rows: list[dict], **item) -> None:
    rows.append(item)


def tile_xy(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    n = 2 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    lat_r = math.radians(lat)
    y = int((1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r)) / math.pi) / 2.0 * n)
    return x, y


def tiles_for_buffer(lon: float, lat: float) -> set[tuple[int, int]]:
    dlat = ANNO_MATCH_M / 111_320.0
    dlon = ANNO_MATCH_M / (111_320.0 * max(0.2, math.cos(math.radians(lat))))
    pts = [
        (lon, lat),
        (lon - dlon, lat - dlat),
        (lon + dlon, lat - dlat),
        (lon - dlon, lat + dlat),
        (lon + dlon, lat + dlat),
    ]
    return {tile_xy(x, y, 15) for x, y in pts}


def project_point(lon: float, lat: float) -> Point:
    x, y = TO_6677.transform(lon, lat)
    return Point(x, y)


def dist_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    return float(GEOD.inv(lon1, lat1, lon2, lat2)[2])


def _projected_coords(geom):
    if geom.is_empty:
        return
    if geom.geom_type == "Polygon":
        rings = [geom.exterior, *geom.interiors]
        for ring in rings:
            yield from ring.coords
    elif geom.geom_type in {"MultiPolygon", "GeometryCollection"}:
        for part in geom.geoms:
            yield from _projected_coords(part)
    else:
        yield from geom.coords


def load_admin():
    path = DRIVE / "data/processed/phase1a/vectors/admin__n03__2026_kanagawa.parquet"
    table = pq.read_table(path, columns=["muni_code", "muni", "geometry"])
    polys = []
    meta = []
    r4 = []
    for code, name, geom in zip(
        table.column("muni_code").to_pylist(),
        table.column("muni").to_pylist(),
        table.column("geometry").to_pylist(),
    ):
        if not code or geom is None:
            continue
        poly = from_wkb(geom)
        polys.append(poly)
        meta.append((code, name))
        if code in R4_CODES:
            r4.append(poly)
    if not r4:
        raise SystemExit("R4 admin polygons are empty")
    return polys, meta


def assert_admin_crs(polys) -> dict:
    xs: list[float] = []
    ys: list[float] = []
    for poly in polys:
        coords = list(_projected_coords(poly))
        if not coords:
            continue
        lons, lats = TO_WGS.transform([c[0] for c in coords], [c[1] for c in coords])
        xs.extend(lons)
        ys.extend(lats)
    if not xs:
        raise SystemExit("CRS check failed: admin polygons have no coordinates")
    west = round(min(xs), 2)
    south = round(min(ys), 2)
    east = round(max(xs), 2)
    north = round(max(ys), 2)
    lat0, lat1 = KANAGAWA_COARSE_LAT
    lon0, lon1 = KANAGAWA_COARSE_LON
    if not (lat0 <= south and north <= lat1 and lon0 <= west and east <= lon1):
        raise SystemExit("CRS check failed: admin extent is outside the coarse Kanagawa range")
    return {"west": west, "south": south, "east": east, "north": north}


def which_muni(polys, meta, lon: float, lat: float):
    pt = project_point(lon, lat)
    for poly, (code, name) in zip(polys, meta):
        if poly.covers(pt):
            return code, name
    return None, None


def load_p32():
    path = DRIVE / "data/processed/phase1a/vectors/cultural__mlit_cultural_properties_kanagawa__2014.parquet"
    table = pq.read_table(path, columns=["P32_006", "geometry"])
    out = []
    for name, geom in zip(table.column("P32_006").to_pylist(), table.column("geometry").to_pylist()):
        if geom is None or not name:
            continue
        out.append({"stem": stem_of(name), "geometry": from_wkb(geom)})
    return out


def p32_hits(rows, lon: float, lat: float, stem: str) -> int:
    if not stem:
        return 0
    pt = project_point(lon, lat)
    n = 0
    for row in rows:
        if row["stem"] != stem:
            continue
        if row["geometry"].distance(pt) <= OSM_MATCH_M:
            n += 1
    return n


def load_existing() -> list[dict]:
    if not EXISTING_CSV.is_file():
        raise SystemExit("PRIVATE_CANDIDATES_CSV is missing")
    with EXISTING_CSV.open(encoding="utf-8", newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if r.get("region") == "R4"]
    if len(rows) != 4:
        raise SystemExit(f"expected 4 existing R4 rows, got {len(rows)}")
    return rows


def wd_time(value) -> str:
    if not isinstance(value, dict):
        return ""
    raw = value.get("time") or ""
    m = re.search(r"([+-]\d{4,}-\d{2}-\d{2})", raw)
    if not m:
        return ""
    return m.group(1).lstrip("+")


def entity_summary(qid: str, prov: list[dict]) -> dict | None:
    url = f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
    dest = SUPP / "wikidata" / f"{qid}.json"
    raw = fetch(url, dest, accept="application/json")
    time.sleep(0.3)
    if raw is None:
        append_prov(prov, url=url, retrieved=RETRIEVED, license="CC0", status="failed", sha256="")
        return None
    append_prov(prov, url=url, retrieved=RETRIEVED, license="CC0", status="ok",
                sha256=sha256_bytes(raw), bytes=len(raw), kind="wikidata")
    data = json.loads(raw)
    ent = data["entities"][qid]
    claims = ent.get("claims", {})

    def mains(pid):
        vals = []
        for claim in claims.get(pid, []):
            vals.append(claim.get("mainsnak", {}).get("datavalue", {}).get("value"))
        return vals

    coord = None
    for value in mains("P625"):
        if isinstance(value, dict) and "latitude" in value and "longitude" in value:
            coord = (float(value["longitude"]), float(value["latitude"]))
            break
    ends = [wd_time(v) for v in mains("P576") + mains("P582")]
    ends = [e for e in ends if e]
    types = []
    for value in mains("P31"):
        if isinstance(value, dict) and value.get("id"):
            types.append(value["id"])
    label = (ent.get("labels") or {}).get("ja", {}).get("value") or ""
    return {
        "qid": qid,
        "label": label,
        "coord": coord,
        "ends": ends,
        "types": types,
        "sitelinks": list((ent.get("sitelinks") or {}).keys()),
    }


def sparql_ended(prov: list[dict]) -> list[dict] | None:
    values = " ".join(f"wd:{qid}" for qid in MUNI_Q)
    query = f"""
SELECT ?item ?itemLabel ?muni ?muniLabel ?end ?coord ?typeLabel WHERE {{
  VALUES ?muni {{ {values} }}
  ?item wdt:P131 ?muni .
  {{ ?item wdt:P576 ?end }} UNION {{ ?item wdt:P582 ?end }}
  OPTIONAL {{ ?item wdt:P625 ?coord }}
  OPTIONAL {{ ?item wdt:P31 ?type }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "ja,en". }}
}}
"""
    data = urllib.parse.urlencode({"query": query, "format": "json"}).encode()
    dest = SUPP / "wikidata" / "ended_direct.json"
    raw = fetch(WIKIDATA_SPARQL, dest, data=data, accept="application/sparql-results+json", timeout=120)
    if raw is None:
        append_prov(prov, url=WIKIDATA_SPARQL, retrieved=RETRIEVED, license="CC0", status="failed", sha256="")
        return None
    append_prov(prov, url=WIKIDATA_SPARQL, retrieved=RETRIEVED, license="CC0", status="ok",
                sha256=sha256_bytes(raw), bytes=len(raw), kind="sparql")
    bindings = json.loads(raw)["results"]["bindings"]
    grouped: dict[str, dict] = {}
    for row in bindings:
        qid = row["item"]["value"].rsplit("/", 1)[-1]
        item = grouped.setdefault(qid, {
            "qid": qid,
            "label": row.get("itemLabel", {}).get("value", ""),
            "muni_qid": row.get("muni", {}).get("value", "").rsplit("/", 1)[-1],
            "muni_label": row.get("muniLabel", {}).get("value", ""),
            "ends": set(),
            "types": set(),
            "coord": None,
        })
        if "end" in row:
            item["ends"].add(row["end"]["value"][:10])
        if "typeLabel" in row:
            item["types"].add(row["typeLabel"]["value"])
        if "coord" in row and item["coord"] is None:
            point = row["coord"]["value"]
            m = re.match(r"Point\(([-\d.]+) ([-\d.]+)\)", point)
            if m:
                item["coord"] = (float(m.group(1)), float(m.group(2)))
    out = []
    for item in grouped.values():
        item["ends"] = sorted(item["ends"])
        item["types"] = sorted(item["types"])
        out.append(item)
    return out


def classify_ended(item: dict) -> str:
    types = " ".join(item["types"])
    if any(word in types for word in ("高等学校", "短期大学", "高等専門学校", "学校", "カレッジ")):
        return "school"
    if any(word in types for word in ("事件", "罪")):
        return "incident"
    if any(word in types for word in ("架空", "ミニ独立国")):
        return "fiction"
    if "軍" in types:
        return "military_unit"
    if any(word in types for word in ("鉄道駅", "廃駅")):
        return "station"
    if any(word in types for word in ("町", "字", "集落")):
        return "place_name"
    return "other"


def category_members(prov: list[dict]) -> list[str] | None:
    url = WIKI_API + "?" + urllib.parse.urlencode({
        "action": "query",
        "list": "categorymembers",
        "cmtitle": "Category:神奈川県の廃駅",
        "cmlimit": "500",
        "format": "json",
    })
    dest = SUPP / "wikipedia" / "category_haieki.json"
    raw = fetch(url, dest, accept="application/json")
    if raw is None:
        append_prov(prov, url=url, retrieved=RETRIEVED, license="CC BY-SA 4.0", status="failed", sha256="")
        return None
    append_prov(prov, url="https://ja.wikipedia.org/wiki/Category:神奈川県の廃駅",
                retrieved=RETRIEVED, license="CC BY-SA 4.0", status="ok",
                sha256=sha256_bytes(raw), bytes=len(raw), kind="wikipedia_category")
    data = json.loads(raw)
    titles = []
    for member in data["query"]["categorymembers"]:
        if member.get("ns") == 0:
            titles.append(member["title"])
    return titles


def qids_for_titles(titles: list[str], prov: list[dict]) -> dict[str, str]:
    found = {}
    for i in range(0, len(titles), 20):
        chunk = titles[i:i + 20]
        url = WIKI_API + "?" + urllib.parse.urlencode({
            "action": "query",
            "titles": "|".join(chunk),
            "prop": "pageprops",
            "ppprop": "wikibase_item",
            "format": "json",
            "redirects": 1,
        })
        raw = fetch(url, SUPP / "wikipedia" / f"pageprops_{i}.json", accept="application/json")
        time.sleep(0.3)
        if raw is None:
            append_prov(prov, url=url, retrieved=RETRIEVED, license="CC BY-SA 4.0", status="failed", sha256="")
            continue
        append_prov(prov, url=url, retrieved=RETRIEVED, license="CC BY-SA 4.0", status="ok",
                    sha256=sha256_bytes(raw), bytes=len(raw), kind="wikipedia_pageprops")
        pages = json.loads(raw)["query"]["pages"]
        for page in pages.values():
            qid = (page.get("pageprops") or {}).get("wikibase_item")
            title = page.get("title")
            if qid and title:
                found[title] = qid
    return found


def wiki_text(title: str, prov: list[dict]) -> str | None:
    url = WIKI_API + "?" + urllib.parse.urlencode({
        "action": "parse",
        "page": title,
        "prop": "wikitext",
        "format": "json",
        "redirects": 1,
    })
    safe = re.sub(r"[^\w]+", "_", title)[:40]
    raw = fetch(url, SUPP / "wikipedia" / f"wt_{safe}.json", accept="application/json")
    time.sleep(0.3)
    if raw is None:
        append_prov(prov, url=url, retrieved=RETRIEVED, license="CC BY-SA 4.0", status="failed", sha256="")
        return None
    append_prov(prov, url=url, retrieved=RETRIEVED, license="CC BY-SA 4.0", status="ok",
                sha256=sha256_bytes(raw), bytes=len(raw), kind="wikipedia_wikitext")
    data = json.loads(raw)
    return (data.get("parse") or {}).get("wikitext", {}).get("*")


def overpass(query: str, name: str, prov: list[dict]) -> dict | None:
    payload = urllib.parse.urlencode({"data": query}).encode()
    for base in OVERPASS_URLS:
        raw = fetch(base, SUPP / "osm" / f"{name}.json", data=payload, accept="application/json", timeout=180)
        if raw is None:
            continue
        append_prov(prov, url=base, retrieved=RETRIEVED, license="ODbL", status="ok",
                    sha256=sha256_bytes(raw), bytes=len(raw), kind=name)
        return json.loads(raw)
    append_prov(prov, url=OVERPASS_URLS[0], retrieved=RETRIEVED, license="ODbL", status="failed", sha256="", kind=name)
    return None


def element_point(el: dict) -> tuple[float, float] | None:
    if "lon" in el and "lat" in el:
        return float(el["lon"]), float(el["lat"])
    center = el.get("center") or {}
    if "lon" in center and "lat" in center:
        return float(center["lon"]), float(center["lat"])
    return None


def live_stations(bbox: dict, prov: list[dict]) -> list[dict] | None:
    south, west, north, east = bbox["south"], bbox["west"], bbox["north"], bbox["east"]
    query = f"""
[out:json][timeout:120];
(
  node["railway"~"^(station|halt)$"]({south},{west},{north},{east});
  way["railway"~"^(station|halt)$"]({south},{west},{north},{east});
);
out center tags;
"""
    data = overpass(query, "live_stations", prov)
    if data is None:
        return None
    out = []
    for el in data.get("elements", []):
        tags = el.get("tags") or {}
        if tags.get("railway") not in {"station", "halt"}:
            continue
        pt = element_point(el)
        if pt is None:
            continue
        name = tags.get("name") or tags.get("name:ja") or ""
        out.append({"stem": stem_of(name), "lon": pt[0], "lat": pt[1]})
    return out


def historic_named(bbox: dict, prov: list[dict]) -> list[dict] | None:
    south, west, north, east = bbox["south"], bbox["west"], bbox["north"], bbox["east"]
    query = f"""
[out:json][timeout:120];
(
  node["historic"]["name"]({south},{west},{north},{east});
  way["historic"]["name"]({south},{west},{north},{east});
);
out center tags;
"""
    data = overpass(query, "historic_named", prov)
    if data is None:
        return None
    out = []
    for el in data.get("elements", []):
        tags = el.get("tags") or {}
        pt = element_point(el)
        if pt is None:
            continue
        name = tags.get("name") or ""
        out.append({"stem": stem_of(name), "lon": pt[0], "lat": pt[1], "historic": tags.get("historic", "")})
    return out


def count_tags(bbox: dict, prov: list[dict], polys, meta) -> dict:
    south, west, north, east = bbox["south"], bbox["west"], bbox["north"], bbox["east"]
    query = f"""
[out:json][timeout:120];
(
  node["amenity"="place_of_worship"]({south},{west},{north},{east});
  way["amenity"="place_of_worship"]({south},{west},{north},{east});
  node["abandoned:amenity"="place_of_worship"]({south},{west},{north},{east});
  node["abandoned:place_of_worship"]({south},{west},{north},{east});
  way["highway"="abandoned"]({south},{west},{north},{east});
);
out ids tags center;
"""
    data = overpass(query, "worship_and_abandoned", prov)
    if data is None:
        return {"fetched": False}
    worship = 0
    abandoned_worship = 0
    abandoned_highway = 0
    for el in data.get("elements", []):
        tags = el.get("tags") or {}
        pt = element_point(el)
        if pt is None:
            continue
        code, _name = which_muni(polys, meta, pt[0], pt[1])
        if code not in R4_CODES:
            continue
        if tags.get("amenity") == "place_of_worship":
            worship += 1
        if tags.get("abandoned:amenity") == "place_of_worship" or "abandoned:place_of_worship" in tags:
            abandoned_worship += 1
        if tags.get("highway") == "abandoned":
            abandoned_highway += 1
    return {
        "fetched": True,
        "worship_inside_r4": worship,
        "abandoned_worship_inside_r4": abandoned_worship,
        "abandoned_highway_inside_r4": abandoned_highway,
    }


def same_stem_within(rows: list[dict] | None, lon: float, lat: float, stem: str, limit: float) -> int | None:
    if rows is None or not stem:
        return None
    n = 0
    for row in rows:
        if row["stem"] != stem:
            continue
        if dist_m(lon, lat, row["lon"], row["lat"]) <= limit:
            n += 1
    return n


def gsi_list(prov: list[dict]) -> dict:
    raw = fetch(GSI_LIST, SUPP / "gsi" / "ichiran.html")
    if raw is None:
        append_prov(prov, url=GSI_LIST, retrieved=RETRIEVED, license="国土地理院タイルの利用条件", status="failed", sha256="")
        return {"fetched": False, "old_edition_string": None}
    text = raw.decode("utf-8", "replace")
    append_prov(prov, url=GSI_LIST, retrieved=RETRIEVED, license="国土地理院コンテンツ利用規約",
                status="ok", sha256=sha256_bytes(raw), bytes=len(raw), kind="gsi_list")
    return {"fetched": True, "old_edition_string": text.count("旧版")}


def anno_for(lon: float, lat: float, stem: str, prov: list[dict], cache: dict) -> dict:
    tiles = tiles_for_buffer(lon, lat)
    fetched = 0
    failed = 0
    hit = False
    for x, y in sorted(tiles):
        key = (x, y)
        if key not in cache:
            url = ANNO_URL.format(x=x, y=y)
            raw = fetch(url, SUPP / "gsi" / f"anno_15_{x}_{y}.geojson", accept="application/json", timeout=60)
            time.sleep(0.15)
            if raw is None:
                cache[key] = None
                append_prov(prov, url=url, retrieved=RETRIEVED, license="国土地理院コンテンツ利用規約",
                            status="failed", sha256="", kind="anno")
            else:
                cache[key] = raw
                append_prov(prov, url=url, retrieved=RETRIEVED, license="国土地理院コンテンツ利用規約",
                            status="ok", sha256=sha256_bytes(raw), bytes=len(raw), kind="anno")
        raw = cache[key]
        if raw is None:
            failed += 1
            continue
        fetched += 1
        if not stem:
            continue
        try:
            geo = json.loads(raw)
        except json.JSONDecodeError:
            failed += 1
            continue
        for feat in geo.get("features", []):
            props = feat.get("properties") or {}
            ftype = str(props.get("ftCode") or props.get("コード") or "")
            if ftype in PLACE_FT:
                continue
            name = props.get("name") or props.get("knj") or ""
            if stem_of(str(name)) == stem:
                hit = True
    return {"fetched": fetched, "failed": failed, "hit": hit}


def aerial_for(lon: float, lat: float, prov: list[dict]) -> dict:
    x, y = tile_xy(lon, lat, 17)
    url = AERIAL_URL.format(x=x, y=y)
    raw = fetch(url, SUPP / "gsi" / f"ort_old10_17_{x}_{y}.png", timeout=60)
    time.sleep(0.15)
    if raw is None:
        append_prov(prov, url=url, retrieved=RETRIEVED, license="国土地理院コンテンツ利用規約",
                    status="failed", sha256="", kind="aerial")
        return {"ok": False, "not_found": False}
    not_found = raw[:8] == b"<!DOCTYP" or len(raw) < 32
    append_prov(prov, url=url, retrieved=RETRIEVED, license="国土地理院コンテンツ利用規約",
                status="404" if not_found else "ok", sha256=sha256_bytes(raw), bytes=len(raw), kind="aerial")
    return {"ok": not not_found, "not_found": not_found}


def archive_name_search(prov: list[dict]) -> dict:
    form = {
        "secIdx": "0",
        "cls": "04_collect_arch_folder",
        "pn": "1",
        "chkCls": "04_collect_arch_folder",
        "c4_f": "神社明細帳",
        "c4_a": "1",
        "c4_l": "1",
        "dispnum": "100",
    }
    raw = fetch(ARCHIVE_LIST, SUPP / "archives" / "meisaicho_name.html",
                data=urllib.parse.urlencode(form).encode())
    if raw is None:
        append_prov(prov, url=ARCHIVE_LIST, retrieved=RETRIEVED, license="神奈川県立公文書館", status="failed", sha256="")
        return {"fetched": False}
    text = raw.decode("utf-8", "replace")
    append_prov(prov, url=ARCHIVE_LIST, retrieved=RETRIEVED, license="神奈川県立公文書館の目録",
                status="ok", sha256=sha256_bytes(raw), bytes=len(raw), kind="archive_search",
                query="資料名 神社明細帳")
    offices = re.findall(r"（戦前期）\s*([^<]{0,40})", text)
    return {
        "fetched": True,
        "hit_sentence": "4件のデータがヒットしました" in text,
        "aiko": "愛甲" in text,
        "koza": "高座" in text,
        "offices": offices,
    }


def kenou_pdf_counts(names: list[str], prov: list[dict]) -> dict:
    raw = fetch(KENOU_PDF, None, timeout=60)
    if raw is None or not raw.startswith(b"%PDF"):
        append_prov(prov, url=KENOU_PDF, retrieved=RETRIEVED, license="県央史談会サイトは無断転載を禁止",
                    status="failed", sha256="", retained=False)
        return {"fetched": False, "retained": False}
    digest = sha256_bytes(raw)
    from pypdf import PdfReader
    import io
    reader = PdfReader(io.BytesIO(raw))
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    counts = {name: text.count(name) for name in names}
    append_prov(
        prov,
        url=KENOU_PDF,
        retrieved=RETRIEVED,
        license="県央史談会。サイトが無断転載を禁止しているためPDFは保存しない。",
        status="viewed_not_retained",
        sha256=digest,
        bytes=len(raw),
        pages=len(reader.pages),
        retained=False,
        kind="kenou_walk_pdf",
    )
    del raw
    return {
        "fetched": True,
        "retained": False,
        "pages": len(reader.pages),
        "sha256": digest,
        "name_counts": counts,
        "inari_mentions": text.count("稲荷"),
        "extant_phrase": "現存" in text,
    }


def check_lead_sources(lead: dict, prov: list[dict]) -> list[str]:
    notes = []
    for i, check in enumerate(lead["checks"]):
        url = check["url"]
        raw = fetch(url, None, timeout=60)
        time.sleep(0.2)
        if raw is None:
            append_prov(prov, url=url, retrieved=RETRIEVED, license=check.get("license", ""),
                        status="failed", sha256="", kind="lead_page")
            raise SystemExit("lead source fetch failed")
        text = html_to_text(raw.decode("utf-8", "replace"))
        dest = SUPP / "leads" / f"lead{lead['order']}_{i}.txt"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        append_prov(prov, url=url, retrieved=RETRIEVED, license=check.get("license", ""),
                    status="ok", sha256=sha256_bytes(dest.read_bytes()), bytes=len(text),
                    kind="lead_text_no_images", images_saved=False)
        missing = [word for word in check["must_contain"] if word not in text]
        if missing:
            raise SystemExit("lead source is missing a required phrase")
        notes.append(check["kind"])
    return notes


def lead_row(lead: dict, new_id: str) -> dict:
    flags = lead["flags"]
    if flags["official_document_opened"]:
        existed = "強"
    elif flags["independent_secondary_at_least_2"]:
        existed = "中"
    else:
        existed = "弱"
    abolished = "強" if flags["official_abolition_or_executed_merger"] else "なし"
    remains = "未確認"
    status = "棄却" if abolished == "なし" else "新規"
    reason = ""
    if status == "棄却":
        reason = "廃止または実行された合祀の公的記録が無い。探訪記の荒廃は管理状態の手がかりであり、廃社として登録しない。"
    return {
        "id": new_id,
        "status": status,
        "region": "R4",
        "muni_code": lead["muni_code"],
        "muni_name": lead["muni_name"],
        "name": lead["name"],
        "lat": "",
        "lon": "",
        "category": "神社",
        "axis_existed": existed,
        "axis_abolished": abolished,
        "axis_remains": remains,
        "confidence": "記録のみ",
        "source": "外部調査2026-11-11のリード。この回に開いた二次情報で3軸を分けた。",
        "retrieved": RETRIEVED,
        "license": "ブログと引用ページの文章。画像は保存していない。",
        "era": lead["era"],
        "verification": lead["private_note"],
        "reject_reason": reason,
        "osm_historic": "",
        "p32_hits": "",
        "anno_hit": "",
        "anno_fetched": "",
        "anno_failed": "",
        "aerial_ok": "",
        "aerial_404": "",
        "wikidata_qid": "",
        "lead_key": f"ext-{lead['order']}",
    }


def blank_spatial() -> dict:
    return {
        "osm_historic": "",
        "p32_hits": "",
        "anno_hit": "",
        "anno_fetched": "",
        "anno_failed": "",
        "aerial_ok": "",
        "aerial_404": "",
    }


def spatial_fill(lon: float, lat: float, stem: str, live, historic, p32, prov, anno_cache) -> dict:
    live_n = same_stem_within(live, lon, lat, stem, STATION_LIVE_M)
    hist_n = same_stem_within(historic, lon, lat, stem, OSM_MATCH_M)
    anno = anno_for(lon, lat, stem, prov, anno_cache)
    air = aerial_for(lon, lat, prov)
    return {
        "live_same_stem_1km": live_n,
        "osm_historic": "" if hist_n is None else hist_n,
        "p32_hits": p32_hits(p32, lon, lat, stem),
        "anno_hit": anno["hit"],
        "anno_fetched": anno["fetched"],
        "anno_failed": anno["failed"],
        "aerial_ok": air["ok"],
        "aerial_404": air["not_found"],
    }


def existing_rows(raw_rows, summaries, polys, meta, live, historic, p32, prov, anno_cache) -> list[dict]:
    out = []
    for raw in raw_rows:
        qid = (raw.get("source_ids") or "").strip()
        summary = summaries.get(qid)
        lat = float(raw["lat"])
        lon = float(raw["lon"])
        code, name = which_muni(polys, meta, lon, lat)
        if code != raw["muni_code"]:
            raise SystemExit("existing point is not inside its recorded municipality")
        stem = stem_of(raw["name"])
        spatial = spatial_fill(lon, lat, stem, live, historic, p32, prov, anno_cache)
        end_ok = bool(summary and summary["ends"])
        cat = CAT_JA.get(raw["category"], raw["category"])
        if cat == "駅":
            existed, abolished, confidence = "強", "中", "中"
            note = "終了日は項目に残っている。" if end_ok else "終了日の再取得に失敗したか、値が無い。格上げしない。"
        else:
            existed, abolished, confidence = "強", "中", "低"
            note = "町名の終了日は行政上の改廃であり、集落が物理的に消えたとは読まない。"
        remains = "中" if (spatial["osm_historic"] not in ("", 0) or spatial["p32_hits"]) else "未確認"
        status = "再検証"
        reason = ""
        if spatial["live_same_stem_1km"] is None and cat == "駅":
            note += "現行駅の1km照合は未取得。未取得を、一致が無かったことにはしない。"
        elif cat == "駅" and spatial["live_same_stem_1km"]:
            status = "棄却"
            reason = "同じ語幹の現行旅客駅が1km以内。1kmは動かさない。廃止の欄は残す。"
        out.append({
            "id": raw["id"],
            "status": status,
            "region": "R4",
            "muni_code": raw["muni_code"],
            "muni_name": raw["muni_name"],
            "name": raw["name"],
            "lat": raw["lat"],
            "lon": raw["lon"],
            "category": cat,
            "axis_existed": existed,
            "axis_abolished": abolished,
            "axis_remains": remains,
            "confidence": confidence,
            "source": "2026-11-05の候補。Wikidata終了日を再取得。",
            "retrieved": RETRIEVED,
            "license": "WikidataはCC0。OSMはODbL。P32は国土数値情報。地理院タイルは出典明記。",
            "era": "終了日は項目の値。対象年代の再解釈はしていない。",
            "verification": note + "旧版地形図の記号は見ていない。空中写真の取得は記号照合ではない。",
            "reject_reason": reason,
            "wikidata_qid": qid,
            "lead_key": "",
            **{k: spatial[k] for k in ("osm_historic", "p32_hits", "anno_hit", "anno_fetched", "anno_failed", "aerial_ok", "aerial_404")},
        })
    return out


def new_station_row(qid: str, summary: dict, wikitext: str, new_id: str, muni_code: str, muni_name: str,
                    spatial: dict) -> dict | None:
    if summary["coord"] is None:
        return None
    text = wikitext or ""
    if "廃駅" not in text:
        return None
    has_date = bool(re.search(r"廃止", text) and re.search(r"1[0-9]{3}年", text))
    has_end = bool(summary["ends"])
    if not (has_date and has_end):
        return None
    lon, lat = summary["coord"]
    live_n = spatial["live_same_stem_1km"]
    status = "新規"
    reason = ""
    if live_n is None:
        return None
    if live_n:
        status = "棄却"
        reason = "同じ語幹の現行旅客駅が1km以内。1kmは動かさない。"
    remains = "中" if (spatial["osm_historic"] not in ("", 0) or spatial["p32_hits"]) else "未確認"
    return {
        "id": new_id,
        "status": status,
        "region": "R4",
        "muni_code": muni_code,
        "muni_name": muni_name,
        "name": summary["label"],
        "lat": f"{lat:.8f}",
        "lon": f"{lon:.8f}",
        "category": "駅",
        "axis_existed": "強",
        "axis_abolished": "強",
        "axis_remains": remains,
        "confidence": "中",
        "source": "Wikipediaの廃駅カテゴリとWikidataの終了日・座標。",
        "retrieved": RETRIEVED,
        "license": "WikipediaはCC BY-SA 4.0。WikidataはCC0。",
        "era": "終了日 " + ",".join(summary["ends"]),
        "verification": "廃止の欄が強なのは、記事に廃駅と廃止の年があり、項目に終了日があることまで。停車場変遷大事典の当該頁は開いていない。旧版地形図は見ていない。要望段階の新駅は現行駅に数えていない。",
        "reject_reason": reason,
        "wikidata_qid": qid,
        "lead_key": "",
        **{k: spatial[k] for k in ("osm_historic", "p32_hits", "anno_hit", "anno_fetched", "anno_failed", "aerial_ok", "aerial_404")},
    }


def landuse() -> dict:
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    reg = {
        name: dict(zip(data["aggregates"]["region"]["columns"], row))
        for name, row in zip(data["aggregates"]["region"]["index"], data["aggregates"]["region"]["data"])
    }
    r4 = reg["R4_kenou"]
    mcols = data["aggregates"]["municipality"]["columns"]
    muni = [dict(zip(mcols, row)) for row in data["aggregates"]["municipality"]["data"]
            if row[mcols.index("region")] == "R4_kenou"]
    by = {row["muni_name"]: row for row in muni}
    cell = r4["land_km2"] / r4["n_cells"]

    def fw(row):
        return row["agri_to_forest_km2"] + row["agri_to_wasteland_km2"]

    atsugi = by["厚木市"]
    ratio = fw(atsugi) / atsugi["agri_loss_km2"]
    region_ratio = fw(r4) / r4["agri_loss_km2"]
    margin = (TEN * r4["agri_loss_km2"] - fw(r4)) / cell
    atsugi_margin = (TEN * atsugi["agri_loss_km2"] - fw(atsugi)) / cell
    names = list(data["aggregates"].keys()) + list(data["transitions"].keys())
    cross = [name for name in names if ("muni" in name and ("land" in name or "landscape" in name))]
    comp = {
        name: dict(zip(data["transitions"]["component_class_share_by_region"]["columns"], row))
        for name, row in zip(
            data["transitions"]["component_class_share_by_region"]["index"],
            data["transitions"]["component_class_share_by_region"]["data"],
        )
    }["R4_kenou"]
    focus = {
        row[1]: dict(zip(data["transitions"]["focus_by_region"]["columns"], row))
        for row in data["transitions"]["focus_by_region"]["data"]
        if row[0] == "R4_kenou"
    }
    south = ["大和市", "座間市", "海老名市", "綾瀬市"]

    def gain(row):
        return row["agri_net_change_km2"] + row["agri_loss_km2"]

    def recovery(nameset):
        loss = sum(by[n]["agri_loss_km2"] for n in nameset)
        got = sum(gain(by[n]) for n in nameset)
        return got / loss

    return {
        "cell_km2": cell,
        "cross_tab_tables": cross,
        "atsugi_agri_to_forest_km2": atsugi["agri_to_forest_km2"],
        "atsugi_agri_loss_km2": atsugi["agri_loss_km2"],
        "atsugi_fw_of_loss": ratio,
        "atsugi_margin_cells": atsugi_margin,
        "region_fw_of_loss": region_ratio,
        "region_margin_cells": margin,
        "share_ge5": comp["share_>=5"],
        "share_ge5_km2": comp["share_>=5"] * comp["changed_km2"],
        "complement_3plus": 1.0 - comp["share_1"] - comp["share_2"],
        "focus_building_to_forest_ge5": focus["building->forest"]["size_>=5_share"],
        "focus_agri_to_forest_ge5": focus["agri->forest"]["size_>=5_share"],
        "recovery_gap_south_minus_atsugi": recovery(south) - recovery(["厚木市"]),
        "forest_net_aikawa": by["愛川町"]["forest_net_change_km2"],
        "forest_net_kiyokawa": by["清川村"]["forest_net_change_km2"],
        "building_to_forest_aikawa": by["愛川町"]["building_to_forest_km2"],
        "building_to_forest_kiyokawa": by["清川村"]["building_to_forest_km2"],
        "thresholds_unchanged": {
            "ten": TEN,
            "ge5_max": GE5_MAX,
            "recovery_gap_line": 0.10,
            "rate_base_floor_km2": CELL_FLOOR,
        },
    }


def public_view(rows: list[dict], extra: dict) -> dict:
    def pack(row):
        return {
            "id": row["id"],
            "status": row["status"],
            "muni_name": row["muni_name"],
            "category": row["category"],
            "axis_existed": row["axis_existed"],
            "axis_abolished": row["axis_abolished"],
            "axis_remains": row["axis_remains"],
            "confidence": row["confidence"],
        }

    return {
        "date": RETRIEVED,
        "region": "R4",
        "week": 3,
        "elapsed_days": 17,
        "rotation": "17 mod 7 = 3, floor(17/7)+1 = 3",
        "rows": [pack(row) for row in rows],
        "counts": dict(Counter(row["status"] for row in rows)),
        "by_category": dict(Counter(row["category"] for row in rows)),
        "by_muni": dict(Counter(row["muni_name"] for row in rows)),
        **extra,
    }


def assert_public_safe(payload: dict, forbidden: list[str]) -> None:
    text = json.dumps(payload, ensure_ascii=False)
    if COORD_RE.search(text):
        raise SystemExit("public json contains a coordinate-like number")
    for word in forbidden:
        if word and word in text:
            raise SystemExit("public json contains a private name")
    for row in payload["rows"]:
        if "name" in row or "lat" in row or "lon" in row:
            raise SystemExit("public row has a private field")


def write_csv(rows: list[dict]) -> None:
    OUT_PRIV.mkdir(parents=True, exist_ok=True)
    fields = [
        "id", "status", "region", "muni_code", "muni_name", "name", "lat", "lon",
        "category", "axis_existed", "axis_abolished", "axis_remains", "confidence",
        "source", "retrieved", "license", "era", "verification", "reject_reason",
        "osm_historic", "p32_hits", "anno_hit", "anno_fetched", "anno_failed",
        "aerial_ok", "aerial_404", "wikidata_qid", "lead_key",
    ]
    with (OUT_PRIV / "candidates.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_findings(rows: list[dict], extra: dict) -> None:
    lines = [
        "# R4 非公開メモ 2026-11-12",
        "",
        "公開レポートには名称と座標を書いていない。このファイルが詳細である。",
        "",
        "## 候補",
        "",
    ]
    for row in rows:
        lines.append(f"### {row['id']} {row['status']} {row['muni_name']} {row['category']}")
        lines.append(f"- 名称: {row['name']}")
        lines.append(f"- 座標: {row['lat'] or 'なし'}, {row['lon'] or 'なし'}")
        lines.append(f"- 3軸: 存在 {row['axis_existed']} / 廃止 {row['axis_abolished']} / 遺構 {row['axis_remains']}")
        lines.append(f"- 総合: {row['confidence']}")
        lines.append(f"- 年代: {row['era']}")
        lines.append(f"- 検証: {row['verification']}")
        if row["reject_reason"]:
            lines.append(f"- 棄却: {row['reject_reason']}")
        lines.append(f"- QID: {row['wikidata_qid'] or 'なし'}")
        lines.append("")
    lines.append("## 機械集計")
    lines.append("")
    lines.append("```json")
    safe = json.loads(json.dumps(extra, ensure_ascii=False, default=str))
    lines.append(json.dumps(safe, ensure_ascii=False, indent=2))
    lines.append("```")
    (OUT_PRIV / "findings.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    if not LEADS_PATH.is_file():
        raise SystemExit("PRIVATE_LEADS_JSON is missing")
    leads_doc = json.loads(LEADS_PATH.read_text(encoding="utf-8"))
    forbidden = leads_doc["forbidden_in_public"]
    SUPP.mkdir(parents=True, exist_ok=True)
    prov: list[dict] = []
    polys, meta = load_admin()
    r4_polys = [poly for poly, (code, _name) in zip(polys, meta) if code in R4_CODES]
    bbox = assert_admin_crs(r4_polys)
    # 地域の外接をタイル取得の範囲にする。0.05度外へ広げ、小数第2位に丸める。
    query_bbox = {
        "south": round(bbox["south"] - 0.05, 2),
        "west": round(bbox["west"] - 0.05, 2),
        "north": round(bbox["north"] + 0.05, 2),
        "east": round(bbox["east"] + 0.05, 2),
    }
    p32 = load_p32()
    existing_raw = load_existing()
    for raw in existing_raw:
        code, _name = which_muni(polys, meta, float(raw["lon"]), float(raw["lat"]))
        if code != raw["muni_code"]:
            raise SystemExit("existing municipality check failed before re-fetch")

    summaries = {}
    for raw in existing_raw:
        qid = raw["source_ids"].strip()
        summaries[qid] = entity_summary(qid, prov)

    ended = sparql_ended(prov)
    ended_counts = Counter()
    if ended is not None:
        for item in ended:
            ended_counts[classify_ended(item)] += 1
    titles = category_members(prov)
    title_q = qids_for_titles(titles, prov) if titles is not None else {}
    known_q = {raw["source_ids"].strip() for raw in existing_raw}

    live = live_stations(query_bbox, prov)
    historic = historic_named(query_bbox, prov)
    tag_counts = count_tags(query_bbox, prov, polys, meta)
    gsi = gsi_list(prov)
    anno_cache: dict = {}

    kept = existing_rows(existing_raw, summaries, polys, meta, live, historic, p32, prov, anno_cache)

    category_inside = 0
    category_outside = 0
    category_no_coord = 0
    new_station_inputs = []
    seen_new = set()
    if titles is not None:
        for title, qid in sorted(title_q.items(), key=lambda kv: kv[1]):
            if qid in known_q or qid in seen_new:
                continue
            summary = entity_summary(qid, prov)
            if summary is None or summary["coord"] is None:
                category_no_coord += 1
                continue
            lon, lat = summary["coord"]
            code, muni_name = which_muni(polys, meta, lon, lat)
            if code not in R4_CODES:
                category_outside += 1
                continue
            category_inside += 1
            seen_new.add(qid)
            new_station_inputs.append((qid, summary, title, code, muni_name))

    next_n = 5
    rows = list(kept)
    lead_rows = []
    for lead in leads_doc["leads"]:
        check_lead_sources(lead, prov)
        new_id = f"R4-{next_n:03d}"
        next_n += 1
        lead_rows.append(lead_row(lead, new_id))
    rows.extend(lead_rows)

    station_added = []
    station_blocked = 0
    station_not_id = 0
    if live is None:
        station_blocked = len(new_station_inputs)
    else:
        for qid, summary, title, code, muni_name in new_station_inputs:
            text = wiki_text(title, prov)
            if text is None:
                station_blocked += 1
                continue
            lon, lat = summary["coord"]
            spatial = spatial_fill(lon, lat, stem_of(summary["label"]), live, historic, p32, prov, anno_cache)
            if spatial["live_same_stem_1km"] is None:
                station_blocked += 1
                continue
            new_id = f"R4-{next_n:03d}"
            built = new_station_row(qid, summary, text, new_id, code, muni_name, spatial)
            if built is None:
                station_not_id += 1
                continue
            next_n += 1
            station_added.append(built)
            rows.append(built)

    kenou = kenou_pdf_counts([lead["name"] for lead in leads_doc["leads"]], prov)
    use = landuse()
    if use["cross_tab_tables"]:
        raise SystemExit("cross tab appeared; do not invent a point estimate, but record it")
    if abs(use["recovery_gap_south_minus_atsugi"] - 0.0425) > 0.005:
        raise SystemExit("recovery gap moved; thresholds stay, check the columns")
    if use["share_ge5"] >= GE5_MAX:
        raise SystemExit("5-cell share is no longer under 10 percent")

    extra = {
        "rules": {
            "live_station_m": STATION_LIVE_M,
            "historic_or_p32_m": OSM_MATCH_M,
            "high_confidence_without_old_topo": False,
        },
        "admin_coarse_bbox": bbox,
        "query_bbox": query_bbox,
        "existing_end_dates_refetched": {
            raw["id"]: bool(summaries.get(raw["source_ids"].strip()) and summaries[raw["source_ids"].strip()]["ends"])
            for raw in existing_raw
        },
        "wikidata_direct_class_counts": dict(ended_counts) if ended is not None else None,
        "wikidata_direct_fetched": ended is not None,
        "category_pages": None if titles is None else len(titles),
        "category_inside_not_already": category_inside,
        "category_outside": category_outside,
        "category_no_coord": category_no_coord,
        "stations_blocked_by_failed_check": station_blocked,
        "stations_inside_without_id": station_not_id,
        "osm_tag_counts": tag_counts,
        "live_stations_fetched": live is not None,
        "historic_fetched": historic is not None,
        "gsi": gsi,
        "kenou_pdf": {
            "fetched": kenou.get("fetched"),
            "retained": False,
            "pages": kenou.get("pages"),
            "priority_names_present": any((kenou.get("name_counts") or {}).values()) if kenou.get("fetched") else None,
            "inari_mentions": kenou.get("inari_mentions"),
            "extant_phrase": kenou.get("extant_phrase"),
        },
        "landuse": use,
        "external_leads_rejected": [row["id"] for row in lead_rows if row["status"] == "棄却"],
        "new_or_rejected_stations": [row["id"] for row in station_added],
    }
    # 目録検索は上で二度呼ばない。ここで一度だけ。
    archives = archive_name_search(prov)
    extra["archives"] = {
        "fetched": archives.get("fetched"),
        "four_hits": archives.get("hit_sentence"),
        "aiko_in_result": archives.get("aiko"),
        "koza_in_result": archives.get("koza"),
        "office_count": len(archives.get("offices") or []),
    }
    payload = public_view(rows, extra)
    assert_public_safe(payload, forbidden)
    PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(rows)
    write_findings(rows, extra)
    (SUPP / "provenance_supplemental.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in prov),
        encoding="utf-8",
    )
    print(json.dumps({
        "rows": len(rows),
        "status": payload["counts"],
        "category": payload["by_category"],
        "stations": extra["new_or_rejected_stations"],
        "leads": extra["external_leads_rejected"],
        "blocked": station_blocked,
        "gsi_old": gsi.get("old_edition_string"),
        "archives_aiko": extra["archives"].get("aiko_in_result"),
        "kenou_names": extra["kenou_pdf"].get("priority_names_present"),
        "share_ge5": round(use["share_ge5"], 4),
        "atsugi_fw": round(use["atsugi_fw_of_loss"], 4),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
