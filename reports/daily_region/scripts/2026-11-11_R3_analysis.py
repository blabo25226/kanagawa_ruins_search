"""R3（湘南）3週目。改訂方針（2026-11-09、2026-11-10から適用）の2回目。

主目的は廃神社・廃寺・消滅集落・廃道・廃施設の探索と検証。
土地利用は、前回同地域の宿題が既存集計で言えるかの棚卸しに限る。

公開JSONには件数・市区町村・候補ID・3軸の内訳だけを書く。
名称・緯度経度・大字は /opt/cursor/artifacts/kanagawa_private/2026-11-11_R3/ に出す。
新規取得の実体は supplemental 用の作業ディレクトリに入れ、リポジトリには置かない。

評価は集計の前に固定した。

- 過去に存在した根拠、廃止・消失の根拠、物理的遺構が残る可能性を別々に書く。
- 現行OSMに名称が無いこと、森林化したことだけでは消失にしない。
- 名称が現行資料に残っていても、終了日は消さない。
- 駅は、現行の旅客駅（railway=station または halt）と同じ語幹が1km以内なら、
  取り違えとして棄却する。この1kmは動かさない。
- 400m以内の historic または P32 の同じ語幹は、遺構の欄を中にする。
  廃止の欄は取り消さない。place の地名は駅の残存と読まない。
- 語幹は完全一致。部分一致に広げない。
- 座標は、入力CSVか、取得した項目の座標欄にあるものだけを使う。
  字名や住所から点を作らない。現行駅の記事の座標を、廃駅の座標として保存しない。
- 明細帳の概要文に、合併・抹消・移転・改称の語が無い項は候補にしない。
- 廃止年月日の欄が無い記事は、現行の旅客駅の記事として扱い、廃駅にしない。
- 総合確度「高」は、旧版地形図の記号照合が無い限り付けない。
- 座標があり、終了日があり、現行旅客駅との取り違えが無い駅は、総合確度を中にする。
  中は旧版地形図を見たという意味ではない。
- 行政合併、個人の住居、OSMのタグだけの地物、学校・病院はIDを付けない。
- 対象地域の外に落ちた点は、R3のIDを付けない。
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
from datetime import date
from pathlib import Path

import pyarrow.parquet as pq
import pyproj
from shapely import from_wkb
from shapely.geometry import Point, shape

ROOT = Path(__file__).resolve().parents[3]
DRIVE = Path(os.environ.get("RUINS_DRIVE_DIR", "/tmp/r3_drive"))
OUT_PRIV = Path("/opt/cursor/artifacts/kanagawa_private/2026-11-11_R3")
PUBLIC = ROOT / "reports" / "daily_region" / "data" / "2026-11-11_R3_week3_public.json"
RESULTS = ROOT / "reports" / "phase1c2_results.json"
TMP = Path(os.environ.get("R3_WORK_DIR", "/tmp/r3_supp_20261111"))
RETRIEVED = "2026-11-11"
UA = "kanagawa-ruins-search/2026-11-11"
R3_CODES = {"14203", "14205", "14207", "14211", "14214", "14321", "14341", "14342"}
OSM_MATCH_M = 400.0
STATION_LIVE_M = 1000.0
ANNO_MATCH_M = 200.0
PLACE_FT = {"0210", "0220"}

ARCHIVES = [
    (
        "ashigara_kami",
        "https://wwwy4.musetheque.jp/kanagawa_archives/detail?cls=04_collect_arch_folder&pkey=1199401719",
        "明治12年 神社明細帳。足柄上郡役所。資料ID 1199401719。請求記号 郡-8-1。",
    ),
    (
        "kamakura",
        "https://wwwy4.musetheque.jp/kanagawa_archives/detail?cls=04_collect_arch_folder&pkey=1199400839",
        "明治12年 神社明細帳。鎌倉郡役所。資料ID 1199400839。請求記号 郡-5-1。",
    ),
]
ARCHIVE_SEARCH = (
    "https://wwwy4.musetheque.jp/kanagawa_archives/list?cls=04_collect_arch_folder"
    "&secIdx=0&pn=1&c4_f=%E7%A5%9E%E7%A4%BE%E6%98%8E%E7%B4%B0%E5%B8%B3"
    "&c4_a=1&c4_l=1&dispnum=100"
)
WIKI_API = "https://ja.wikipedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
OVERPASS = "https://overpass-api.de/api/interpreter"
GSI_TERMS = "https://www.gsi.go.jp/kikakuchousei/kikakuchousei40182.html"
GSI_LIST = "https://maps.gsi.go.jp/development/ichiran.html"
ANNO_URL = "https://cyberjapandata.gsi.go.jp/xyz/experimental_anno/15/{x}/{y}.geojson"
AERIAL_URL = "https://cyberjapandata.gsi.go.jp/xyz/ort_old10/{z}/{x}/{y}.png"
LINE_PAGE = "湘南軌道"

TO_6677 = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:6677", always_xy=True)
TO_WGS = pyproj.Transformer.from_crs("EPSG:6677", "EPSG:4326", always_xy=True)
GEOD = pyproj.Geod(ellps="WGS84")
KANAGAWA_COARSE_LAT = (35.10, 35.70)
KANAGAWA_COARSE_LON = (138.90, 139.80)

CAT_JA = {
    "facility": "施設",
    "station": "駅",
    "shrine": "神社",
    "temple": "寺院",
    "settlement": "集落",
    "road": "廃道",
}


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
        r"(駅|跡|小学校|中学校|高等学校|高校|大学|病院|信号所|信号場|仮乗降場)$",
        "",
        text,
    )


def tile_xy(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    n = 2 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    lat_r = math.radians(lat)
    y = int((1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r)) / math.pi) / 2.0 * n)
    return x, y


def tiles_for_buffer(lon: float, lat: float, radius_m: float = ANNO_MATCH_M) -> set[tuple[int, int]]:
    dlat = radius_m / 111_320.0
    dlon = radius_m / (111_320.0 * max(0.2, math.cos(math.radians(lat))))
    pts = [
        (lon, lat),
        (lon - dlon, lat - dlat),
        (lon + dlon, lat - dlat),
        (lon - dlon, lat + dlat),
        (lon + dlon, lat + dlat),
    ]
    return {tile_xy(x, y, 15) for x, y in pts}


def fetch(url: str, dest: Path, data: bytes | None = None, timeout: int = 120,
          accept: str = "*/*") -> bytes | None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0 and dest.suffix != ".error":
        return dest.read_bytes()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"User-Agent": UA, "Accept": accept},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            status = getattr(resp, "status", 200)
    except Exception as exc:  # noqa: BLE001 — 失敗は未取得として残す
        dest.with_suffix(dest.suffix + ".error").write_text(
            f"{type(exc).__name__}: {exc}\n{url}\n", encoding="utf-8")
        return None
    if status == 404:
        dest.with_suffix(dest.suffix + ".error").write_text(f"404\n{url}\n", encoding="utf-8")
        return None
    dest.write_bytes(raw)
    return raw


def project_point(lon: float, lat: float) -> Point:
    x, y = TO_6677.transform(lon, lat)
    return Point(x, y)


def load_admin():
    path = DRIVE / "data/processed/phase1a/vectors/admin__n03__2026_kanagawa.parquet"
    table = pq.read_table(path, columns=["muni_code", "muni", "geometry"])
    codes = table.column("muni_code").to_pylist()
    names = table.column("muni").to_pylist()
    geoms = table.column("geometry").to_pylist()
    polys = []
    meta = []
    r3 = []
    r3_meta = []
    for code, name, geom in zip(codes, names, geoms):
        if geom is None or not code:
            continue
        poly = from_wkb(geom)
        polys.append(poly)
        meta.append((code, name))
        if code in R3_CODES:
            r3.append(poly)
            r3_meta.append((code, name))
    if not r3:
        raise SystemExit("R3 admin polygons are empty")
    return polys, meta, r3, r3_meta


def which_muni(polys, meta, lon: float, lat: float):
    pt = project_point(lon, lat)
    for poly, (code, name) in zip(polys, meta):
        if poly.covers(pt):
            return code, name
    return None, None


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


def assert_admin_crs(polys) -> None:
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


def check_private_candidates(polys, meta, path: Path) -> None:
    if not path.is_file():
        raise SystemExit("CRS check failed: PRIVATE_CANDIDATES_CSV is not a file")
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    checked = 0
    for row in rows:
        code = (row.get("muni_code") or "").strip()
        lat_s = (row.get("lat") or "").strip()
        lon_s = (row.get("lon") or "").strip()
        if code not in R3_CODES or not lat_s or not lon_s:
            continue
        got, _name = which_muni(polys, meta, float(lon_s), float(lat_s))
        if got != code:
            cid = row.get("id") or "?"
            raise SystemExit(f"CRS check failed for {cid}: got {got}, expected {code}")
        checked += 1
    if checked == 0:
        raise SystemExit("CRS check failed: PRIVATE_CANDIDATES_CSV has no R3 coordinate rows")


def load_existing(path: Path) -> list[dict]:
    rows = [r for r in csv.DictReader(path.open(encoding="utf-8")) if r["id"].startswith("R3-")]
    ids = [r["id"] for r in rows]
    if ids != [f"R3-{i:03d}" for i in range(1, 7)]:
        raise SystemExit(f"existing R3 ids changed: {ids}")
    return rows


def load_p32():
    path = (
        DRIVE / "data/processed/phase1a/vectors"
        / "cultural__mlit_cultural_properties_kanagawa__2014.parquet"
    )
    table = pq.read_table(path, columns=["P32_006", "geometry"])
    out = []
    for name, geom in zip(table.column("P32_006").to_pylist(), table.column("geometry").to_pylist()):
        if not geom:
            continue
        stem = stem_of(name or "")
        if len(stem) < 2:
            continue
        out.append({"stem": stem, "geometry": from_wkb(geom), "name": name})
    return out


def nearest(records, pt: Point, meters: float, stem: str, predicate=None):
    if not stem:
        return []
    hits = []
    for rec in records:
        if predicate and not predicate(rec):
            continue
        if rec.get("stem") != stem:
            continue
        if pt.distance(rec["geometry"]) <= meters:
            hits.append(rec)
    return hits


def html_text(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="replace")
    text = re.sub(r"<[^>]+>", " ", text)
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u3000", " ")
    return re.sub(r"\s+", " ", text)


def archive_counts(text: str) -> dict:
    return {
        "entries": len(re.findall(r"神奈川県管下", text)),
        "merge": text.count("合併"),
        "strike": text.count("抹消"),
        "relocate": text.count("移転"),
        "rename": text.count("改称"),
        "abolished_word": text.count("廃絶"),
        "enshrine_merge": text.count("合祀"),
        "osumi": text.count("大住郡"),
        "yurugi": text.count("淘綾郡"),
        "koza": text.count("高座郡"),
        "kamakura": text.count("鎌倉郡"),
        "ashigara_kami": text.count("足柄上郡"),
    }


def wiki_get(params: dict, dest: Path) -> dict | None:
    url = WIKI_API + "?" + urllib.parse.urlencode(params)
    raw = fetch(url, dest, timeout=90, accept="application/json")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def line_station_titles(wikitext: str) -> list[str]:
    section = re.search(r"==\s*駅一覧\s*==(.+?)(?:\n==[^=]|\Z)", wikitext, re.S)
    if not section:
        raise SystemExit("station list section was not found")
    titles = []
    for line in section.group(1).splitlines():
        if not line.startswith(":"):
            continue
        if " - " not in line and " – " not in line:
            continue
        for target, _label in re.findall(r"\[\[([^|\]]+)(?:\|([^\]]+))?\]\]", line):
            title = target.strip()
            if title.endswith("駅") or "駅 (" in title or title.endswith("駅)"):
                titles.append(title)
    # 重複は先に出た方を残す。
    seen = set()
    ordered = []
    for title in titles:
        if title in seen:
            continue
        seen.add(title)
        ordered.append(title)
    if len(ordered) < 8:
        raise SystemExit(f"station list parsed {len(ordered)} titles, expected 8")
    return ordered


def plain_address(wikitext: str) -> str:
    match = re.search(r"\|\s*所在地\s*=\s*([^\n]+)", wikitext)
    if not match:
        return ""
    text = re.sub(r"\[\[[^|\]]*\|([^\]]+)\]\]", r"\1", match.group(1))
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    return unicodedata.normalize("NFKC", text)


def has_abolition_field(wikitext: str) -> bool:
    return re.search(r"\|\s*廃止年月日\s*=", wikitext) is not None


def wd_entities(qids: list[str], prefix: str = "wd_entities") -> dict:
    out = {}
    uniq = [q for q in dict.fromkeys(qids) if q]
    for i in range(0, len(uniq), 40):
        chunk = uniq[i:i + 40]
        url = WIKIDATA_API + "?" + urllib.parse.urlencode({
            "action": "wbgetentities",
            "ids": "|".join(chunk),
            "props": "claims|labels|descriptions",
            "languages": "ja",
            "format": "json",
        })
        dest = TMP / f"{prefix}_{i}.json"
        raw = fetch(url, dest, timeout=90, accept="application/json")
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        out.update(payload.get("entities") or {})
    return out


def claim_time(entity: dict, pid: str) -> str:
    for claim in (entity.get("claims") or {}).get(pid) or []:
        try:
            return claim["mainsnak"]["datavalue"]["value"]["time"]
        except (KeyError, TypeError):
            continue
    return ""


def claim_coord(entity: dict) -> tuple[float, float] | None:
    for claim in (entity.get("claims") or {}).get("P625") or []:
        try:
            value = claim["mainsnak"]["datavalue"]["value"]
            return float(value["longitude"]), float(value["latitude"])
        except (KeyError, TypeError, ValueError):
            continue
    return None


def claim_type_labels(entity: dict, label_map: dict[str, str]) -> list[str]:
    labels = []
    for claim in (entity.get("claims") or {}).get("P31") or []:
        try:
            qid = claim["mainsnak"]["datavalue"]["value"]["id"]
        except (KeyError, TypeError):
            continue
        labels.append(label_map.get(qid, qid))
    return labels


def resolve_muni_qids(names: list[str]) -> dict[str, str]:
    found = {}
    for name in names:
        url = WIKIDATA_API + "?" + urllib.parse.urlencode({
            "action": "wbsearchentities",
            "search": name,
            "language": "ja",
            "uselang": "ja",
            "type": "item",
            "limit": 8,
            "format": "json",
        })
        dest = TMP / f"wd_search_{name}.json"
        raw = fetch(url, dest, timeout=60, accept="application/json")
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        chosen = ""
        for row in payload.get("search") or []:
            desc = row.get("description") or ""
            label = row.get("label") or ""
            if label == name and ("神奈川" in desc or "Kanagawa" in desc):
                chosen = row.get("id") or ""
                break
        if not chosen:
            for row in payload.get("search") or []:
                desc = row.get("description") or ""
                if "神奈川" in desc or "Kanagawa" in desc:
                    chosen = row.get("id") or ""
                    break
        if chosen:
            found[name] = chosen
        time.sleep(0.2)
    return found


def sparql_one(qid: str) -> dict | None:
    # P131* とラベルサービスを含む一括は 504 になった。直接の P131 を市町ごとに取る。
    query = f"""
    SELECT ?item ?coord ?end WHERE {{
      ?item wdt:P131 wd:{qid} .
      ?item wdt:P625 ?coord .
      {{ ?item wdt:P576 ?end . }} UNION {{ ?item wdt:P582 ?end . }}
    }}
    LIMIT 200
    """
    url = WIKIDATA_SPARQL + "?query=" + urllib.parse.quote(query)
    dest = TMP / f"wikidata_ended_{qid}.json"
    raw = fetch(url, dest, timeout=90, accept="application/sparql-results+json")
    if raw is None:
        time.sleep(65)
        if dest.exists() and dest.stat().st_size == 0:
            dest.unlink()
        raw = fetch(url, dest, timeout=90, accept="application/sparql-results+json")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def wikidata_ended(qids: dict[str, str]) -> dict | None:
    if len(qids) < 8:
        return None
    bindings = []
    failed = []
    capped = []
    for name, qid in qids.items():
        payload = sparql_one(qid)
        time.sleep(2)
        if payload is None:
            failed.append(name)
            continue
        rows = payload.get("results", {}).get("bindings", [])
        if len(rows) >= 200:
            capped.append(name)
        for row in rows:
            row["muniLabel"] = {"type": "literal", "value": name}
            bindings.append(row)
    item_ids = [row["item"]["value"].rsplit("/", 1)[-1] for row in bindings]
    entities = wd_entities(item_ids, prefix="wd_ended_entities")
    type_ids = []
    for ent in entities.values():
        for claim in (ent.get("claims") or {}).get("P31") or []:
            try:
                type_ids.append(claim["mainsnak"]["datavalue"]["value"]["id"])
            except (KeyError, TypeError):
                continue
    type_entities = wd_entities(type_ids, prefix="wd_type_labels")
    type_labels = {}
    for tqid, ent in type_entities.items():
        type_labels[tqid] = ((ent.get("labels") or {}).get("ja") or {}).get("value") or tqid
    out = []
    for row in bindings:
        item = row["item"]["value"].rsplit("/", 1)[-1]
        ent = entities.get(item) or {}
        label = ((ent.get("labels") or {}).get("ja") or {}).get("value") or item
        types = []
        for claim in (ent.get("claims") or {}).get("P31") or []:
            try:
                tqid = claim["mainsnak"]["datavalue"]["value"]["id"]
            except (KeyError, TypeError):
                continue
            types.append(type_labels.get(tqid, tqid))
        if not types:
            types = ["型不明"]
        for type_label in types:
            out.append({
                "item": row["item"],
                "itemLabel": {"type": "literal", "value": label},
                "coord": row.get("coord"),
                "end": row.get("end"),
                "typeLabel": {"type": "literal", "value": type_label},
                "muniLabel": row["muniLabel"],
            })
    if not out and failed and len(failed) == len(qids):
        return None
    return {
        "results": {"bindings": out},
        "failed_muni": failed,
        "capped_muni": capped,
    }


def classify_types(labels: list[str]) -> str:
    blob = " ".join(labels)
    if any(k in blob for k in ("廃止市区町村", "廃止された郡", "日本の郡")) and not any(
        k in blob for k in ("駅", "神社", "寺院", "廃寺", "集落", "廃村")
    ):
        return "admin"
    if any(k in blob for k in ("学校", "病院", "大学", "企業", "人間")) and not any(
        k in blob for k in ("駅", "神社", "寺院", "廃寺")
    ):
        return "institution"
    if any(k in blob for k in ("神社", "神宮", "廃社")):
        return "shrine"
    if any(k in blob for k in ("寺院", "廃寺", "寺")):
        return "temple"
    if any(k in blob for k in ("廃村", "集落")):
        return "settlement"
    if "町・字" in blob or "大字" in blob:
        return "chomei"
    if any(k in blob for k in ("廃道", "旧道")):
        return "road"
    if "駅" in blob or "信号場" in blob:
        return "station"
    if any(k in blob for k in ("灯台", "窯", "台場", "飛行場", "要塞", "陣屋")):
        return "facility"
    return "other"


def overpass_query(bounds: tuple[float, float, float, float]) -> dict | None:
    south, west, north, east = bounds
    query = f"""
    [out:json][timeout:90];
    (
      node["amenity"="place_of_worship"]({south},{west},{north},{east});
      way["amenity"="place_of_worship"]({south},{west},{north},{east});
      node["historic"]({south},{west},{north},{east});
      way["historic"]({south},{west},{north},{east});
      node["railway"~"^(station|halt|abandoned|disused|razed)$"]({south},{west},{north},{east});
      way["railway"~"^(abandoned|disused|razed)$"]({south},{west},{north},{east});
      way["highway"="abandoned"]({south},{west},{north},{east});
      node["abandoned:amenity"="place_of_worship"]({south},{west},{north},{east});
      node["disused:amenity"="place_of_worship"]({south},{west},{north},{east});
    );
    out tags center;
    """
    raw = fetch(OVERPASS, TMP / "overpass_r3.json", data=query.encode("utf-8"), timeout=180)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def element_point(el: dict) -> tuple[float, float] | None:
    if "lon" in el and "lat" in el:
        return float(el["lon"]), float(el["lat"])
    center = el.get("center") or {}
    if "lon" in center and "lat" in center:
        return float(center["lon"]), float(center["lat"])
    return None


def distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    _az1, _az2, dist = GEOD.inv(lon1, lat1, lon2, lat2)
    return float(dist)


def live_station_within(live: list[dict], lon: float, lat: float, stem: str) -> bool:
    if not stem:
        return False
    for rec in live:
        if rec["stem"] != stem:
            continue
        if distance_m(lon, lat, rec["lon"], rec["lat"]) <= STATION_LIVE_M:
            return True
    return False


def split_table(table: dict) -> list[dict]:
    cols = table["columns"]
    return [dict(zip(cols, row)) for row in table["data"]]


def landuse_inventory() -> dict:
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    agg_names = list(data["aggregates"].keys())
    cross = [name for name in agg_names if "municipality" in name and "landscape" in name]
    region = {row_id: dict(zip(data["aggregates"]["region"]["columns"], row))
              for row_id, row in zip(data["aggregates"]["region"]["index"], data["aggregates"]["region"]["data"])}
    r3 = region["R3_shonan"]
    cols = data["aggregates"]["region"]["columns"]
    focus_rows = [
        row for row in split_table(data["transitions"]["focus_by_region"])
        if row["region"] == "R3_shonan"
    ]
    reverse_into_agri = []
    for row in focus_rows:
        if str(row["transition"]).startswith("agri->"):
            reverse_into_agri.append({
                "forward": row["transition"],
                "reverse_area_km2": row["reverse_area_km2"],
            })
    loss = float(r3["agri_loss_km2"])
    net = float(r3["agri_net_change_km2"])
    gain = loss + net
    named = sum(item["reverse_area_km2"] for item in reverse_into_agri)
    landscapes = []
    rl = data["aggregates"]["region_landscape"]
    for idx, row in zip(rl["index"], rl["data"]):
        if not (isinstance(idx, list) and idx[0] == "R3_shonan"):
            continue
        raw = dict(zip(rl["columns"], row))
        land = float(raw["land_km2"])
        changed = raw.get("changed_km2")
        landscapes.append({
            "landscape": idx[1],
            "land_km2": land,
            "changed_km2": None if changed is None else float(changed),
            "agri_2014_km2": land * float(raw["agri_2014_share"]),
            "agri_net_change_km2": float(raw["agri_net_change_km2"]),
        })
    changed_known = [item["changed_km2"] for item in landscapes if item["changed_km2"] is not None]
    changed_total = sum(changed_known) if changed_known and all(v is not None for v in changed_known) else None
    max_share = None
    if changed_total:
        shares = [v / changed_total for v in changed_known]
        max_share = max(shares) if shares else None
    files = {
        "2026-11-02": (ROOT / "reports/daily_region/2026-11-02_R1_week2.md").is_file(),
        "2026-11-03": (ROOT / "reports/daily_region/2026-11-03_R2_week2.md").is_file(),
    }
    return {
        "cross_tab_tables": cross,
        "agri_to_building_column_present": any("agri_to_building" in c or "building_from_agri" in c for c in cols),
        "agri_loss_km2": loss,
        "agri_net_change_km2": net,
        "agri_gross_gain_km2_derived": gain,
        "gain_formula": "agri_loss_km2 + agri_net_change_km2",
        "reverse_into_agri": reverse_into_agri,
        "named_reverse_into_agri_km2": named,
        "unnamed_gain_km2": gain - named,
        "landscape_max_changed_share": max_share,
        "landscapes": landscapes,
        "threshold_50_not_moved": True,
        "backfill_reports_present": files,
        "wasteland_destination_column_present": any(c.startswith("wasteland_to_") for c in cols),
    }


def public_is_clean(payload: dict) -> None:
    text = json.dumps(payload, ensure_ascii=False)
    if re.search(r"3[45]\.\d{3,}", text) or re.search(r"13[89]\.\d{3,}", text):
        raise SystemExit("public json contains a coordinate-like number")
    for row in payload.get("candidates") or []:
        for key in ("name", "lat", "lon", "latitude", "longitude", "village", "shrine"):
            if key in row:
                raise SystemExit(f"public candidate has {key}")


def main() -> None:
    TMP.mkdir(parents=True, exist_ok=True)
    OUT_PRIV.mkdir(parents=True, exist_ok=True)
    elapsed = (date(2026, 11, 11) - date(2026, 10, 26)).days
    if elapsed != 16 or elapsed % 7 != 2 or elapsed // 7 + 1 != 3:
        raise SystemExit(f"rotation mismatch: elapsed={elapsed}")

    private_csv = Path(os.environ["PRIVATE_CANDIDATES_CSV"])
    polys, meta, r3_polys, _r3_meta = load_admin()
    assert_admin_crs(r3_polys)
    check_private_candidates(polys, meta, private_csv)
    existing = load_existing(private_csv)
    existing_q = {}
    for row in existing:
        qid = (row.get("source_ids") or "").strip()
        if qid:
            existing_q[qid] = row["id"]
    p32 = load_p32()
    muni_names = []
    seen_names = set()
    for code, name in meta:
        if code in R3_CODES and name not in seen_names:
            seen_names.add(name)
            muni_names.append(name)
    name_to_code = {}
    for code, name in meta:
        name_to_code.setdefault(name, code)

    provenance = []

    def add_prov(url: str, raw: bytes | None, license_note: str, era: str, note: str, path: Path | None = None):
        provenance.append({
            "url": url,
            "file": "" if path is None else path.name,
            "retrieved": RETRIEVED,
            "license": license_note,
            "era": era,
            "sha256": sha256_bytes(raw) if raw else "",
            "bytes": 0 if raw is None else len(raw),
            "note": note,
            "fetched": raw is not None,
        })

    archive_summary = {}
    for key, url, note in ARCHIVES:
        dest = TMP / f"archives_{key}.html"
        raw = fetch(url, dest, timeout=60)
        add_prov(
            url, raw,
            "神奈川県立公文書館の収蔵資料検索。ページにオープンライセンスの明示は確認できない。概要文の件数だけを使い、再配布しない。",
            "明治12年から明治13年の明細帳。概要文の注記時期は帳面による。",
            note + " マイクロフィルムの画像は未取得。",
            dest if raw else None,
        )
        if not raw:
            raise SystemExit(f"archives page missing: {key}")
        archive_summary[key] = archive_counts(html_text(raw))

    search_raw = fetch(ARCHIVE_SEARCH, TMP / "archives_search_meisai.html", timeout=60)
    add_prov(
        ARCHIVE_SEARCH, search_raw,
        "神奈川県立公文書館の収蔵資料検索。オープンライセンスの明示は確認できない。",
        "検索時点の目録",
        "資料名に神社明細帳を含む簿冊の検索。",
        TMP / "archives_search_meisai.html" if search_raw else None,
    )
    search_text = html_text(search_raw) if search_raw else ""
    search_info = {
        "fetched": search_raw is not None,
        "mentions_osumi": "大住郡" in search_text,
        "mentions_yurugi": "淘綾郡" in search_text,
        "mentions_koza": "高座郡" in search_text,
        "mentions_kamakura": "鎌倉郡" in search_text,
        "mentions_ashigara": "足柄上郡" in search_text,
        "mentions_miura": "三浦郡" in search_text,
        "title_hits": len(re.findall(r"神社明細帳", search_text)),
    }

    line = wiki_get({
        "action": "parse",
        "page": LINE_PAGE,
        "prop": "wikitext",
        "format": "json",
    }, TMP / "wiki_line.json")
    line_raw = (TMP / "wiki_line.json").read_bytes() if (TMP / "wiki_line.json").exists() else None
    add_prov(
        WIKI_API, line_raw,
        "Wikipedia のテキストは CC BY-SA 4.0。記事の本文は転載しない。",
        "路線の廃止は1937-08-25と記事が書く。個別駅の対象年代は各記事の欄。",
        "湘南軌道の駅一覧節。駅の個別記事へ進むための目次。",
        TMP / "wiki_line.json" if line_raw else None,
    )
    if not line:
        raise SystemExit("line page was not fetched")
    titles = line_station_titles(line["parse"]["wikitext"]["*"])
    pages = wiki_get({
        "action": "query",
        "prop": "revisions|pageprops",
        "rvprop": "content",
        "rvslots": "main",
        "ppprop": "wikibase_item",
        "titles": "|".join(titles),
        "format": "json",
        "redirects": "1",
    }, TMP / "wiki_station_pages.json")
    pages_raw = (TMP / "wiki_station_pages.json").read_bytes() if (TMP / "wiki_station_pages.json").exists() else None
    add_prov(
        WIKI_API, pages_raw,
        "Wikipedia のテキストは CC BY-SA 4.0。本文は転載しない。",
        "各記事の廃止年月日欄。",
        "駅一覧のリンク先。現行駅の記事が混じるので、廃止年月日欄の有無で分ける。",
        TMP / "wiki_station_pages.json" if pages_raw else None,
    )
    if not pages:
        raise SystemExit("station pages were not fetched")

    by_title = {}
    for page in (pages.get("query") or {}).get("pages", {}).values():
        revs = page.get("revisions") or []
        wikitext = ""
        if revs:
            wikitext = revs[0].get("slots", {}).get("main", {}).get("*") or ""
        by_title[page.get("title")] = {
            "qid": (page.get("pageprops") or {}).get("wikibase_item") or "",
            "wikitext": wikitext,
            "title": page.get("title") or "",
        }
    # リダイレクト後のタイトルで引く。
    redirects = {(row.get("from")): row.get("to") for row in (pages.get("query") or {}).get("redirects") or []}

    qids = [info["qid"] for info in by_title.values() if info["qid"]]
    qids.extend(existing_q.keys())
    entities = wd_entities(qids)
    ent_blob = b"".join(p.read_bytes() for p in sorted(TMP.glob("wd_entities_*.json")))
    add_prov(
        WIKIDATA_API, ent_blob or None,
        "CC0",
        "P576 の終了日と P625。",
        "駅記事のQIDと、既存6件のQID。座標は公開JSONへ写さない。",
        None,
    )

    minx = min(p.bounds[0] for p in r3_polys)
    miny = min(p.bounds[1] for p in r3_polys)
    maxx = max(p.bounds[2] for p in r3_polys)
    maxy = max(p.bounds[3] for p in r3_polys)
    west, south = TO_WGS.transform(minx, miny)
    east, north = TO_WGS.transform(maxx, maxy)
    bounds = (south - 0.02, west - 0.02, north + 0.02, east + 0.02)
    overpass = overpass_query(bounds)
    op_raw = (TMP / "overpass_r3.json").read_bytes() if overpass is not None and (TMP / "overpass_r3.json").exists() else None
    add_prov(
        OVERPASS, op_raw,
        "ODbL（OpenStreetMap）。Overpass API の抽出。",
        "取得日時点の現行OSM",
        "R3の外接に0.02度。礼拝、historic、鉄道、abandoned highway。失敗なら未確認であり0件ではない。",
        TMP / "overpass_r3.json" if op_raw else None,
    )

    osm_records = []
    live_stations = []
    osm_counts = Counter()
    if overpass:
        for el in overpass.get("elements") or []:
            tags = el.get("tags") or {}
            loc = element_point(el)
            if not loc:
                continue
            lon, lat = loc
            code, muni_name = which_muni(polys, meta, lon, lat)
            if code not in R3_CODES:
                osm_counts["outside_r3"] += 1
                continue
            name = tags.get("name") or tags.get("name:ja") or ""
            stem = stem_of(name)
            railway = tags.get("railway") or ""
            historic = tags.get("historic") or ""
            kind = ""
            if tags.get("amenity") == "place_of_worship" or tags.get("abandoned:amenity") == "place_of_worship" or tags.get("disused:amenity") == "place_of_worship":
                kind = "worship"
            elif historic:
                kind = "historic"
            elif railway:
                kind = "railway"
            elif tags.get("highway") == "abandoned":
                kind = "abandoned_road"
            if historic == "ruins":
                osm_counts["historic_ruins"] += 1
            if tags.get("abandoned:amenity") == "place_of_worship" or tags.get("disused:amenity") == "place_of_worship":
                osm_counts["worship_abandoned_tag"] += 1
            if tags.get("highway") == "abandoned":
                osm_counts["abandoned_highway"] += 1
            osm_counts[f"kind_{kind or 'other'}"] += 1
            rec = {
                "stem": stem,
                "name": name,
                "geometry": project_point(lon, lat),
                "lon": lon,
                "lat": lat,
                "railway": railway,
                "historic": historic,
                "kind": kind,
                "muni_name": muni_name,
            }
            osm_records.append(rec)
            if railway in {"station", "halt"} and name:
                live_stations.append(rec)

    # 注記と空中写真は、座標が入力または項目にある点だけ。
    # 旧版地形図の層名は、一覧HTMLに無いときは取得しない。
    list_raw = fetch(GSI_LIST, TMP / "gsi_ichiran.html", timeout=60)
    add_prov(
        GSI_LIST, list_raw,
        "国土地理院コンテンツ利用規約。",
        "一覧の取得日時点",
        "旧版地形図のXYZ層があるかの確認。層が無ければタイルは取らない。",
        TMP / "gsi_ichiran.html" if list_raw else None,
    )
    list_text = list_raw.decode("utf-8", errors="replace") if list_raw else ""
    old_topo_mentioned = ("旧版" in list_text) and ("xyz" in list_text or "タイル" in list_text)
    # 一覧に「旧版」の文字があっても、今日使う層IDをここへは書かない。
    # 記号照合に使える層URLを決めていないので、旧版地形図は未取得のままにする。
    old_topo_fetched = False

    def gather_points(rows_with_coords: list[dict]) -> None:
        for row in rows_with_coords:
            lon = row.get("lon")
            lat = row.get("lat")
            if lon is None or lat is None:
                continue
            cid = row["id"]
            for x, y in sorted(tiles_for_buffer(lon, lat)):
                dest = TMP / f"anno_15_{x}_{y}.geojson"
                raw = fetch(ANNO_URL.format(x=x, y=y), dest, timeout=30)
                time.sleep(0.05)
                row.setdefault("_anno_fetched", 0)
                row.setdefault("_anno_failed", 0)
                if raw is None:
                    row["_anno_failed"] += 1
                else:
                    row["_anno_fetched"] += 1
            zx, zy = tile_xy(lon, lat, 17)
            adest = TMP / f"ort_old10_17_{zx}_{zy}.png"
            araw = fetch(AERIAL_URL.format(z=17, x=zx, y=zy), adest, timeout=30)
            row["_aerial_ok"] = araw is not None and len(araw) > 100
            err = adest.with_suffix(adest.suffix + ".error")
            row["_aerial_404"] = err.exists() and "404" in err.read_text(encoding="utf-8")

    anno_features = []

    def load_anno_features() -> None:
        for path in sorted(TMP.glob("anno_15_*.geojson")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            for feat in payload.get("features") or []:
                props = feat.get("properties") or {}
                geom = feat.get("geometry")
                if not geom:
                    continue
                gj = shape(geom)
                px, py = TO_6677.transform(gj.x, gj.y)
                anno_features.append({
                    "stem": stem_of(props.get("knj") or ""),
                    "ftCode": str(props.get("ftCode") or ""),
                    "annoCtg": props.get("annoCtg") or "",
                    "geometry": Point(px, py),
                })

    def anno_hit(pt: Point, stem: str) -> bool:
        for rec in anno_features:
            if rec["ftCode"] in PLACE_FT or str(rec["annoCtg"]).startswith("居住地名") or str(rec["annoCtg"]).startswith("行政区画"):
                continue
            if rec["stem"] == stem and pt.distance(rec["geometry"]) <= ANNO_MATCH_M:
                return True
        return False

    # 既存6件。
    reviewed = []
    for row in existing:
        lat_s = (row.get("lat") or "").strip()
        lon_s = (row.get("lon") or "").strip()
        lat = float(lat_s) if lat_s else None
        lon = float(lon_s) if lon_s else None
        qid = (row.get("source_ids") or "").strip()
        entity = entities.get(qid) or {}
        end = claim_time(entity, "P576") or claim_time(entity, "P582")
        stem = stem_of(row.get("name") or "")
        pt = project_point(lon, lat) if lon is not None and lat is not None else None
        hist = nearest(osm_records, pt, OSM_MATCH_M, stem, lambda rec: rec["kind"] == "historic") if pt is not None and overpass else []
        p32_hits = nearest(p32, pt, OSM_MATCH_M, stem) if pt is not None else []
        remains = "中" if hist or p32_hits else "未確認"
        abolished = "中"
        if not entity:
            abolished = "中"
            end_note = "Wikidataの再取得は失敗した。終了日が無い、とは書かない。"
        elif end:
            end_note = "終了日の値は項目に残っている。出典ページは開いていないので、廃止は中のまま。"
        else:
            end_note = "再取得した項目に終了日の欄が無かった。2026-11-05の値は消さず、廃止は中のまま。"
        reviewed.append({
            "id": row["id"],
            "status": "再検証",
            "region": "R3",
            "muni_code": row["muni_code"],
            "muni_name": row["muni_name"],
            "name": row["name"],
            "lat": lat,
            "lon": lon,
            "category": CAT_JA.get(row["category"], row["category"]),
            "axis_existed": "強",
            "axis_abolished": abolished,
            "axis_remains": remains,
            "confidence": "中",
            "source": f"2026-11-05の候補を維持。QID {qid}。",
            "retrieved": RETRIEVED,
            "license": "Wikidata は CC0。OSM は ODbL。P32 は国土数値情報。",
            "era": "終了日は2026-11-05取得の項目。再取得は2026-11-11。",
            "verification": end_note,
            "osm_historic": len(hist),
            "p32_hits": len(p32_hits),
            "live_conflict": False,
            "stem": stem,
        })

    # 路線の駅。既存QIDは再検証側に残し、ここでは新規か棄却か対象外だけを切る。
    station_decisions = []
    outside = []
    unresolved = []
    for title in titles:
        info = by_title.get(title) or by_title.get(redirects.get(title, ""))
        if info is None:
            unresolved.append({"reason": "page_missing"})
            continue
        qid = info["qid"]
        if qid and qid in existing_q:
            continue
        wikitext = info["wikitext"]
        entity = entities.get(qid) or {}
        label = ((entity.get("labels") or {}).get("ja") or {}).get("value") or info["title"]
        end = claim_time(entity, "P576") or claim_time(entity, "P582")
        coord = claim_coord(entity)
        abolished_field = has_abolition_field(wikitext)
        address = plain_address(wikitext)
        code, muni_name = (None, "")
        if coord:
            code, muni_name = which_muni(polys, meta, coord[0], coord[1])
        if code is None:
            for name, name_code in sorted(name_to_code.items(), key=lambda item: len(item[0]), reverse=True):
                if name and name in address:
                    code, muni_name = name_code, name
                    break
        record = {
            "title": info["title"],
            "name": label,
            "qid": qid,
            "lon": None if coord is None else coord[0],
            "lat": None if coord is None else coord[1],
            "muni_code": code or "",
            "muni_name": muni_name,
            "end": end,
            "abolished_field": abolished_field,
            "address_text": address,
            "stem": stem_of(label),
        }
        if not abolished_field:
            record["decision"] = "reject_live_page"
            station_decisions.append(record)
            continue
        if code not in R3_CODES:
            record["decision"] = "outside"
            outside.append(record)
            continue
        if coord is None:
            record["decision"] = "no_coord"
            unresolved.append(record)
            continue
        if overpass and live_station_within(live_stations, coord[0], coord[1], record["stem"]):
            record["decision"] = "reject_live_1km"
            station_decisions.append(record)
            continue
        if not overpass:
            record["decision"] = "distance_unchecked"
            record["confidence"] = "低"
        else:
            record["decision"] = "new"
            record["confidence"] = "中"
        station_decisions.append(record)

    # 追加の Wikidata。駅一覧で見たQIDと既存QIDは除く。
    muni_q = resolve_muni_qids(sorted(seen_names))
    wd = wikidata_ended(muni_q)
    ended_paths = sorted(TMP.glob("wikidata_ended_Q*.json"))
    ended_blob = b"".join(path.read_bytes() for path in ended_paths)
    add_prov(
        WIKIDATA_SPARQL,
        ended_blob or None,
        "CC0",
        "終了日（P576またはP582）と座標がある項目",
        "8市町のQIDは wbsearchentities でラベルと説明を見て決めた。直接のP131だけ。P131*の一括は504だった。市町ごとの失敗は0件と書かない。",
        None,
    )
    extra_skipped = Counter()
    extras = []
    seen_extra = set(existing_q) | {row["qid"] for row in station_decisions if row.get("qid")}
    seen_extra |= {info["qid"] for info in by_title.values() if info.get("qid")}
    if wd is None:
        extra_skipped["query_failed"] += 1
    else:
        for name in wd.get("failed_muni") or []:
            extra_skipped[f"muni_failed:{name}"] += 1
        for name in wd.get("capped_muni") or []:
            extra_skipped[f"muni_capped:{name}"] += 1
        grouped: dict[str, dict] = {}
        for binding in wd.get("results", {}).get("bindings", []):
            item = binding["item"]["value"].rsplit("/", 1)[-1]
            slot = grouped.setdefault(item, {
                "qid": item,
                "name": binding.get("itemLabel", {}).get("value", ""),
                "end": binding.get("end", {}).get("value", ""),
                "coord": binding.get("coord", {}).get("value", ""),
                "types": [],
                "muni": binding.get("muniLabel", {}).get("value", ""),
            })
            type_label = binding.get("typeLabel", {}).get("value", "")
            if type_label and type_label not in slot["types"]:
                slot["types"].append(type_label)
        for item, slot in sorted(grouped.items()):
            if item in seen_extra:
                extra_skipped["already"] += 1
                continue
            kind = classify_types(slot["types"])
            if kind in {"admin", "institution", "other", "chomei"}:
                extra_skipped[kind] += 1
                continue
            try:
                lon_s, lat_s = slot["coord"].replace("Point(", "").replace(")", "").split()
                lon, lat = float(lon_s), float(lat_s)
            except ValueError:
                extra_skipped["bad_coord"] += 1
                continue
            code, muni_name = which_muni(polys, meta, lon, lat)
            if code not in R3_CODES:
                extra_skipped["outside"] += 1
                continue
            stem = stem_of(slot["name"])
            pt = project_point(lon, lat)
            if kind in {"shrine", "temple"}:
                worship_hits = nearest(
                    osm_records, pt, OSM_MATCH_M, stem,
                    lambda rec: rec["kind"] == "worship",
                ) if overpass else []
                if worship_hits:
                    extra_skipped["worship_still_named"] += 1
                    continue
            if kind == "station" and overpass and live_station_within(live_stations, lon, lat, stem):
                extras.append({
                    "decision": "reject_live_1km",
                    "name": slot["name"],
                    "qid": item,
                    "lon": lon,
                    "lat": lat,
                    "muni_code": code,
                    "muni_name": muni_name,
                    "end": slot["end"],
                    "stem": stem,
                    "kind": kind,
                    "confidence": None,
                    "types": slot["types"],
                })
                continue
            if kind == "station" and not overpass:
                confidence = "低"
                decision = "new"
            elif kind == "station":
                confidence = "中"
                decision = "new"
            else:
                confidence = "中" if kind in {"shrine", "temple", "facility", "settlement", "road"} else "低"
                decision = "new"
            extras.append({
                "decision": decision,
                "name": slot["name"],
                "qid": item,
                "lon": lon,
                "lat": lat,
                "muni_code": code,
                "muni_name": muni_name,
                "end": slot["end"],
                "stem": stem,
                "kind": kind,
                "confidence": confidence,
                "types": slot["types"],
            })

    # IDは路線順の決定、その後にWikidataのQID順。
    next_n = 7
    new_rows = []

    def add_row(row: dict) -> None:
        nonlocal next_n
        row["id"] = f"R3-{next_n:03d}"
        next_n += 1
        new_rows.append(row)

    for record in station_decisions:
        if record["decision"] == "reject_live_page":
            add_row({
                "id": "",
                "status": "棄却",
                "region": "R3",
                "muni_code": record["muni_code"],
                "muni_name": record["muni_name"],
                "name": record["name"],
                "lat": "",
                "lon": "",
                "category": "駅",
                "axis_existed": "強",
                "axis_abolished": "なし",
                "axis_remains": "未確認",
                "confidence": "",
                "source": f"Wikipedia「{LINE_PAGE}」の駅一覧がこの記事へリンクする。QID {record['qid']}。廃止年月日の欄は無い。",
                "retrieved": RETRIEVED,
                "license": "Wikipedia は CC BY-SA 4.0。Wikidata は CC0。",
                "era": "記事が書く開業日から、取得日時点の現行駅。",
                "verification": "現行の旅客駅の記事である。その座標は廃駅の座標として保存しない。",
                "stem": record["stem"],
                "reject_reason": "live_station_page",
            })
        elif record["decision"] == "reject_live_1km":
            add_row({
                "id": "",
                "status": "棄却",
                "region": "R3",
                "muni_code": record["muni_code"],
                "muni_name": record["muni_name"],
                "name": record["name"],
                "lat": record["lat"],
                "lon": record["lon"],
                "category": "駅",
                "axis_existed": "強",
                "axis_abolished": "強",
                "axis_remains": "未確認",
                "confidence": "",
                "source": f"Wikipediaの廃止年月日欄と、Wikidata {record['qid']} のP625・P576。",
                "retrieved": RETRIEVED,
                "license": "Wikipedia は CC BY-SA 4.0。Wikidata は CC0。OSM は ODbL。",
                "era": record["end"] or "1937年を記事が書く",
                "verification": "同じ語幹の現行旅客駅が1km以内にある。1kmは動かさない。出典が別地点と書いていても、今日は採用しない。",
                "stem": record["stem"],
                "reject_reason": "live_station_within_1km",
            })
        elif record["decision"] in {"new", "distance_unchecked"}:
            add_row({
                "id": "",
                "status": "新規",
                "region": "R3",
                "muni_code": record["muni_code"],
                "muni_name": record["muni_name"],
                "name": record["name"],
                "lat": record["lat"],
                "lon": record["lon"],
                "category": "駅",
                "axis_existed": "強",
                "axis_abolished": "強" if record["end"] or record["abolished_field"] else "中",
                "axis_remains": "未確認",
                "confidence": record["confidence"],
                "source": f"Wikipediaの廃止年月日欄と、Wikidata {record['qid']} のP625・P576。",
                "retrieved": RETRIEVED,
                "license": "Wikipedia は CC BY-SA 4.0。Wikidata は CC0。",
                "era": record["end"] or "記事の廃止年月日欄",
                "verification": (
                    "Overpassが失敗し、現行旅客駅との距離は未測定。総合は低。旧版地形図は未照合。"
                    if record["decision"] == "distance_unchecked"
                    else "現行旅客駅と同じ語幹は1km以内に無かった。旧版地形図は未照合。総合の高は付けない。"
                ),
                "stem": record["stem"],
                "reject_reason": "",
            })

    for record in extras:
        cat = CAT_JA.get(record["kind"], record["kind"])
        if record["decision"] == "reject_live_1km":
            add_row({
                "id": "",
                "status": "棄却",
                "region": "R3",
                "muni_code": record["muni_code"],
                "muni_name": record["muni_name"],
                "name": record["name"],
                "lat": record["lat"],
                "lon": record["lon"],
                "category": cat,
                "axis_existed": "強",
                "axis_abolished": "強" if record["end"] else "中",
                "axis_remains": "未確認",
                "confidence": "",
                "source": f"Wikidata {record['qid']}。型: {' / '.join(record['types'])}",
                "retrieved": RETRIEVED,
                "license": "CC0",
                "era": record["end"],
                "verification": "同じ語幹の現行旅客駅が1km以内。",
                "stem": record["stem"],
                "reject_reason": "live_station_within_1km",
            })
            continue
        add_row({
            "id": "",
            "status": "新規",
            "region": "R3",
            "muni_code": record["muni_code"],
            "muni_name": record["muni_name"],
            "name": record["name"],
            "lat": record["lat"],
            "lon": record["lon"],
            "category": cat,
            "axis_existed": "強",
            "axis_abolished": "強" if record["end"] else "中",
            "axis_remains": "未確認",
            "confidence": record["confidence"],
            "source": f"Wikidata {record['qid']}。型: {' / '.join(record['types'])}。路線の駅一覧には無い。",
            "retrieved": RETRIEVED,
            "license": "CC0",
            "era": record["end"],
            "verification": "旧版地形図は未照合。現行の礼拝施設と同じ語幹が400m以内の神社・寺院は、ここに来ない（除外済み）。",
            "stem": record["stem"],
            "reject_reason": "",
        })

    # 遺構欄。座標がある新規・棄却・再検証。
    coord_rows = [row for row in reviewed + new_rows if row.get("lat") not in ("", None) and row.get("lon") not in ("", None)]
    for row in coord_rows:
        row["lat"] = float(row["lat"])
        row["lon"] = float(row["lon"])
    gather_points(coord_rows)
    load_anno_features()
    anno_blob = b"".join(p.read_bytes() for p in sorted(TMP.glob("anno_15_*.geojson")))
    aerial_blob = b"".join(p.read_bytes() for p in sorted(TMP.glob("ort_old10_17_*.png")))
    add_prov(
        ANNO_URL, anno_blob or None,
        "国土地理院コンテンツ利用規約。",
        "現行の注記（experimental_anno、ズーム15）",
        "座標がある候補の200mが交わるタイル。404は未確認。旧版地形図ではない。",
        None,
    )
    add_prov(
        AERIAL_URL, aerial_blob or None,
        "国土地理院コンテンツ利用規約。一覧HTMLの1961年～1969年。",
        "1961年～1969年",
        "座標がある候補の点を含むズーム17を各1枚。記号の照合には使わない。判読して遺構ありとはしない。",
        None,
    )
    for row in coord_rows:
        pt = project_point(row["lon"], row["lat"])
        stem = row.get("stem") or stem_of(row.get("name") or "")
        hist = nearest(osm_records, pt, OSM_MATCH_M, stem, lambda rec: rec["kind"] == "historic") if overpass else []
        p32_hits = nearest(p32, pt, OSM_MATCH_M, stem)
        anno = anno_hit(pt, stem) if anno_features else False
        if row["status"] != "棄却" and (hist or p32_hits or anno):
            row["axis_remains"] = "中"
        row["osm_historic"] = len(hist)
        row["p32_hits"] = len(p32_hits)
        row["anno_hit"] = anno
        row["anno_fetched"] = row.get("_anno_fetched", 0)
        row["anno_failed"] = row.get("_anno_failed", 0)
        row["aerial_ok"] = bool(row.get("_aerial_ok"))
        row["aerial_404"] = bool(row.get("_aerial_404"))

    all_rows = reviewed + new_rows
    # 公開側。
    public_candidates = []
    for row in all_rows:
        public_candidates.append({
            "id": row["id"],
            "status": row["status"],
            "category": row["category"],
            "muni_name": row["muni_name"],
            "axis_existed": row["axis_existed"],
            "axis_abolished": row["axis_abolished"],
            "axis_remains": row["axis_remains"],
            "confidence": row["confidence"] or None,
        })
    by_status = Counter(row["status"] for row in all_rows)
    by_cat = Counter(row["category"] for row in all_rows if row["status"] != "棄却")
    by_conf = Counter((row["confidence"] or "なし") for row in all_rows if row["status"] != "棄却")
    by_muni_new = Counter(row["muni_name"] for row in all_rows if row["status"] == "新規")
    landuse = landuse_inventory()
    anno_failed = sum(int(row.get("anno_failed") or 0) for row in coord_rows)
    anno_fetched = sum(int(row.get("anno_fetched") or 0) for row in coord_rows)
    aerial_404 = sum(1 for row in coord_rows if row.get("aerial_404"))
    aerial_ok = sum(1 for row in coord_rows if row.get("aerial_ok"))

    public = {
        "date": RETRIEVED,
        "region": "R3",
        "week": 3,
        "elapsed_days": elapsed,
        "rotation": "16 mod 7 = 2, floor(16/7)+1 = 3",
        "rules": {
            "live_station_m": STATION_LIVE_M,
            "historic_or_p32_m": OSM_MATCH_M,
            "high_confidence_without_old_topo": False,
            "old_topo_fetched": old_topo_fetched,
            "old_topo_phrase_in_tile_list": old_topo_mentioned,
        },
        "archives": archive_summary,
        "archive_search": search_info,
        "stations_on_line_page": len(titles),
        "outside_region_stations": len(outside),
        "outside_muni_counts": dict(Counter(row["muni_name"] or "未解決" for row in outside)),
        "unresolved_stations": len(unresolved),
        "wikidata": {
            "muni_qids_resolved": len(muni_q),
            "fetched": wd is not None,
            "extra_skipped": dict(extra_skipped),
            "extra_rows": len(extras),
        },
        "osm": {
            "fetched": overpass is not None,
            "counts": dict(osm_counts),
            "live_stations_in_r3": len(live_stations),
        },
        "tiles": {
            "anno_fetched": anno_fetched,
            "anno_failed": anno_failed,
            "aerial_ok": aerial_ok,
            "aerial_404": aerial_404,
            "points": len(coord_rows),
        },
        "candidates": public_candidates,
        "counts": {
            "ids": len(all_rows),
            "by_status": dict(by_status),
            "adopted_by_category": dict(by_cat),
            "adopted_by_confidence": dict(by_conf),
            "new_by_muni": dict(by_muni_new),
        },
        "landuse_inventory": landuse,
    }
    public_is_clean(public)
    PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC.write_text(json.dumps(public, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # 非公開。
    fieldnames = [
        "id", "status", "region", "muni_code", "muni_name", "name", "lat", "lon",
        "category", "axis_existed", "axis_abolished", "axis_remains", "confidence",
        "source", "retrieved", "license", "era", "verification", "reject_reason",
        "osm_historic", "p32_hits", "anno_hit", "anno_fetched", "anno_failed",
        "aerial_ok", "aerial_404",
    ]
    with (OUT_PRIV / "candidates.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in all_rows:
            out = dict(row)
            if out.get("lat") in ("", None):
                out["lat"] = ""
            if out.get("lon") in ("", None):
                out["lon"] = ""
            writer.writerow(out)

    lines = [
        "# 非公開メモ 2026-11-11 R3",
        "",
        "リポジトリには置かない。名称と座標を含む。",
        "",
        "## 既存",
        "",
    ]
    for row in reviewed:
        lines.append(
            f"- {row['id']} {row['muni_name']} {row['category']} {row['name']} "
            f"存在{row['axis_existed']} 廃止{row['axis_abolished']} 遺構{row['axis_remains']} "
            f"総合{row['confidence']}。{row['verification']}"
        )
    lines.append("")
    lines.append("## 今日の決定")
    lines.append("")
    for row in new_rows:
        lines.append(
            f"- {row['id']} {row['status']} {row['muni_name']} {row['category']} {row['name']} "
            f"存在{row['axis_existed']} 廃止{row['axis_abolished']} 遺構{row['axis_remains']} "
            f"総合{row['confidence'] or 'なし'}。{row['verification']}"
        )
    lines.append("")
    lines.append("## 対象外")
    lines.append("")
    for row in outside:
        lines.append(f"- 対象外 {row['muni_name'] or '未解決'} {row['name']} QID {row['qid']}")
    lines.append("")
    lines.append("## 明細帳")
    lines.append("")
    lines.append(json.dumps(archive_summary, ensure_ascii=False, indent=2))
    lines.append("")
    lines.append("合併・抹消・移転・改称が0の概要文からは、社名を候補にしていない。")
    lines.append("マイクロフィルムの画像は未取得。")
    (OUT_PRIV / "findings.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (TMP / "provenance_supplemental.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in provenance),
        encoding="utf-8",
    )
    print(json.dumps({
        "ids": len(all_rows),
        "by_status": dict(by_status),
        "new_by_muni": dict(by_muni_new),
        "adopted_by_category": dict(by_cat),
        "adopted_by_confidence": dict(by_conf),
        "outside": len(outside),
        "outside_muni": dict(Counter(row["muni_name"] or "?" for row in outside)),
        "unresolved": len(unresolved),
        "osm_fetched": overpass is not None,
        "wd_fetched": wd is not None,
        "extra_skipped": dict(extra_skipped),
        "archives": archive_summary,
        "search": search_info,
        "tiles": public["tiles"],
        "candidates": public_candidates,
        "landuse_unnamed_gain": landuse["unnamed_gain_km2"],
        "landuse_named": landuse["named_reverse_into_agri_km2"],
        "agri_to_building_column": landuse["agri_to_building_column_present"],
        "cross": landuse["cross_tab_tables"],
        "backfill": landuse["backfill_reports_present"],
        "wasteland_dest": landuse["wasteland_destination_column_present"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
