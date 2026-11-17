"""R3（湘南）4週目。2026-11-18。

主目的は、既存候補の出典頁を開いて廃止の欄を見直すことと、
合祀の再興と旧軍用地の頁を廃社と分けて数えること。
土地利用は、前回同地域の集計がまだ同じかを確認するだけに限る。

公開 JSON には件数、市区町村、候補 ID、3軸、確度、リード ID、検証コードだけを書く。
名称と緯度経度は、環境変数で渡した非公開ファイルから読み、
/opt/cursor/artifacts/kanagawa_private/2026-11-18_R3/ に出す。
スクリプトには地点の緯度経度も候補名も書かない。

評価は件数を数える前に固定した。

- 過去に存在した根拠、廃止・消失の根拠、物理的遺構が残る可能性は別の欄にする。
- 現行の地図に名称が無いこと、森林化、目録の概要、投稿は、消失の根拠にしない。
- 座標は、入力 CSV に列があるときだけ読む。字名や住所からは点を作らない。
- 総合確度の高は、旧版地形図の記号を見ていない限り付けない。今日は付けない。
- 遷座先、合祀先、再興した現社は廃社にしない。建物の撤去で神体が残るものは状態変化にする。
- 投稿は二次である。画像は保存しない。画像から位置を推定しない。
- 官報本文を開いていない廃止は、記事の日付欄までであり、高にはしない。
- 旧版地形図の交付 TIFF は取得していない。空中写真は地形図記号ではない。
- 1928年頃の空中写真は、タイル一覧の代表点がこの地域の外なら要求しない。
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import pyarrow.parquet as pq
import pyproj
from shapely import from_wkb
from shapely.geometry import Point
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[3]
JUDGMENTS = Path(os.environ["PRIVATE_JUDGMENTS_CSV"])
UPDATES = Path(os.environ["PRIVATE_AXIS_UPDATES_CSV"])
NOT_ASSIGNED = Path(os.environ["PRIVATE_NOT_ASSIGNED_CSV"])
PRIOR = Path(os.environ["PRIVATE_PRIOR_CANDIDATES"])
SPECIAL = Path(os.environ["PRIVATE_SPECIAL_CANDIDATES"])
N03 = Path(os.environ["N03_PARQUET"])
MANIFEST = Path(os.environ["SOURCE_MANIFEST_CSV"])
SUPP = Path(os.environ["SUPP_DIR"])
OUT_PRIV = Path("/opt/cursor/artifacts/kanagawa_private/2026-11-18_R3")
PUBLIC = ROOT / "reports" / "daily_region" / "data" / "2026-11-18_R3_week4_public.json"
RESULTS = ROOT / "reports" / "phase1c2_results.json"
RETRIEVED = "2026-11-18"
UA = "kanagawa-ruins-search/2026-11-18"
R3_CODES = {"14203", "14205", "14207", "14211", "14214", "14321", "14341", "14342"}
PRIOR_MAX = 10
SPECIAL_MAX = 6
NEW_FIRST = 11
NEW_LAST = 34
POINTED_N = 9
ANNO_MATCH_M = 200.0
OSM_MATCH_M = 400.0
PLACE_FT = {"0210", "0220"}
COORD_RE = re.compile(r"(?:3[4-6]|13[89])\.[0-9]{3,}")
QID_RE = re.compile(r"Q\d+")
ALLOWED_STATUS = {"新規", "既存", "再検証", "棄却", "負例", "状態変化", "保留"}
ALLOWED_AXIS = {"強", "中", "低", "なし", "未確認", "対象外"}
ALLOWED_CONF = {"中", "低", "負例", ""}
ALLOWED_REASON = {"OUT", "UNCLEAR", "OTHER"}
ANNO_URL = "https://cyberjapandata.gsi.go.jp/xyz/experimental_anno/15/{x}/{y}.geojson"
AERIAL = {
    "ort_old10": ("https://cyberjapandata.gsi.go.jp/xyz/ort_old10/17/{x}/{y}.png", 17),
    "ort_USA10": ("https://cyberjapandata.gsi.go.jp/xyz/ort_USA10/17/{x}/{y}.png", 17),
}
LAYERS_URL = "https://maps.gsi.go.jp/layers_txt/layers1.txt"
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
WIKIDATA = "https://query.wikidata.org/sparql"
GSI_TERMS = "https://www.gsi.go.jp/kikakuchousei/kikakuchousei40182.html"
TO_6677 = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:6677", always_xy=True)
TO_WGS = pyproj.Transformer.from_crs("EPSG:6677", "EPSG:4326", always_xy=True)
REQUIRED_KEYS = {
    "wikisource_notice",
    "jinja_current",
    "jinja_revived",
    "city_memorial",
    "wikipedia_query",
    "tourism_branch",
    "prefecture_line",
    "town_newsletter",
    "note_excerpt",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stem_of(value: str) -> str:
    text = re.sub(r"\s+", "", value or "")
    text = re.sub(r"（[^）]*）", "", text)
    text = re.sub(r"\([^)]*\)", "", text)
    return re.sub(r"(駅|停留場|跡|信号所|信号場|仮乗降場|古址)$", "", text)


def tile_xy(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    n = 2**zoom
    x = int((lon + 180.0) / 360.0 * n)
    lat_r = math.radians(lat)
    y = int((1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r)) / math.pi) / 2.0 * n)
    return x, y


def tiles_for_buffer(lon: float, lat: float, zoom: int, radius_m: float) -> set[tuple[int, int]]:
    dlat = radius_m / 111_320.0
    dlon = radius_m / (111_320.0 * max(0.2, math.cos(math.radians(lat))))
    pts = [
        (lon, lat),
        (lon - dlon, lat - dlat),
        (lon + dlon, lat - dlat),
        (lon - dlon, lat + dlat),
        (lon + dlon, lat + dlat),
    ]
    return {tile_xy(x, y, zoom) for x, y in pts}


def fetch(url: str, dest: Path, data: bytes | None = None, timeout: int = 90,
          accept: str = "*/*") -> bytes | None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return dest.read_bytes()
    req = urllib.request.Request(
        url, data=data, headers={"User-Agent": UA, "Accept": accept},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except Exception as exc:  # noqa: BLE001 — 失敗は未取得として残す
        dest.with_suffix(dest.suffix + ".error").write_text(
            f"{type(exc).__name__}: {exc}\n", encoding="utf-8",
        )
        return None
    dest.write_bytes(raw)
    return raw


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def max_r3(path: Path) -> int:
    nums = []
    for row in read_csv(path):
        ident = row.get("id") or ""
        if ident.startswith("R3-"):
            nums.append(int(ident.split("-")[1]))
    return max(nums) if nums else 0


def verify_manifest() -> list[dict]:
    rows = read_csv(MANIFEST)
    if not rows:
        raise SystemExit("source manifest is empty")
    checked = []
    copied = SUPP / "sources"
    copied.mkdir(parents=True, exist_ok=True)
    for row in rows:
        path = Path(row["path"])
        if not path.exists():
            raise SystemExit(f"missing source {row['key']}")
        digest = sha256_file(path)
        if digest != row["sha256"]:
            raise SystemExit(f"hash mismatch {row['key']}")
        target = copied / path.name
        if not target.exists():
            shutil.copy2(path, target)
        text = ""
        if path.suffix in {".html", ".txt", ".json"}:
            text = path.read_text(encoding="utf-8", errors="replace")
        elif path.suffix == ".pdf":
            proc = subprocess.run(
                ["pdftotext", "-layout", str(path), "-"],
                check=False, capture_output=True, text=True,
            )
            if proc.returncode != 0:
                raise SystemExit("town newsletter text could not be read")
            text = proc.stdout
            (SUPP / "town_newsletter.txt").write_text(text, encoding="utf-8")
        phrase = row.get("phrase") or ""
        if phrase and phrase not in text:
            raise SystemExit(f"phrase missing in {row['key']}")
        checked.append({
            "key": row["key"],
            "sha256": digest,
            "bytes": path.stat().st_size,
            "url": row.get("url") or "",
            "retrieved": row.get("retrieved") or RETRIEVED,
            "license": row.get("license") or "",
            "period": row.get("period") or "",
        })
    keys = {row["key"] for row in checked}
    missing = REQUIRED_KEYS - keys
    if missing:
        raise SystemExit(f"manifest missing {sorted(missing)}")
    return checked


def split_table(table: dict) -> list[dict]:
    cols = table["columns"]
    return [dict(zip(cols, row)) for row in table["data"]]


def landuse_inventory() -> dict:
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    agg_names = list(data["aggregates"].keys())
    cross = [name for name in agg_names if "municipality" in name and "landscape" in name]
    region = {
        row_id: dict(zip(data["aggregates"]["region"]["columns"], row))
        for row_id, row in zip(
            data["aggregates"]["region"]["index"], data["aggregates"]["region"]["data"],
        )
    }
    r3 = region["R3_shonan"]
    cols = data["aggregates"]["region"]["columns"]
    focus_rows = [
        row for row in split_table(data["transitions"]["focus_by_region"])
        if row["region"] == "R3_shonan"
    ]
    reverse_into_agri = []
    for row in focus_rows:
        if str(row["transition"]).startswith("agri->"):
            reverse_into_agri.append(float(row["reverse_area_km2"]))
    loss = float(r3["agri_loss_km2"])
    net = float(r3["agri_net_change_km2"])
    gain = loss + net
    named = sum(reverse_into_agri)
    landscapes = []
    rl = data["aggregates"]["region_landscape"]
    for idx, row in zip(rl["index"], rl["data"]):
        if not (isinstance(idx, list) and idx[0] == "R3_shonan"):
            continue
        raw = dict(zip(rl["columns"], row))
        changed = raw.get("changed_km2")
        if changed is None:
            continue
        landscapes.append(float(changed))
    changed_total = sum(landscapes) if landscapes else None
    max_share = max(v / changed_total for v in landscapes) if changed_total else None
    cov_table = data["coverage"]["by_region"]
    cov = dict(zip(
        cov_table["index"],
        [dict(zip(cov_table["columns"], row)) for row in cov_table["data"]],
    ))["R3_shonan"]
    not_covered = set(data["coverage"].get("not_covered") or [])
    return {
        "cross_tab_count": len(cross),
        "agri_to_building_column_present": any(
            "agri_to_building" in c or "building_from_agri" in c for c in cols
        ),
        "agri_loss_km2": loss,
        "agri_net_change_km2": net,
        "agri_gross_gain_km2_derived": gain,
        "named_reverse_into_agri_km2": named,
        "unnamed_gain_km2": gain - named,
        "landscape_max_changed_share": max_share,
        "wasteland_destination_column_present": any(c.startswith("wasteland_to_") for c in cols),
        "coverage": float(cov["coverage"]),
        "scope": cov["scope"],
        "area_km2": float(cov["area_km2"]),
        "covered_km2": float(cov["covered_km2"]),
        "oiso_still_uncovered": "大磯町" in not_covered,
        "ninomiya_still_uncovered": "二宮町" in not_covered,
    }


def load_prior() -> list[dict]:
    if max_r3(PRIOR) != PRIOR_MAX or max_r3(SPECIAL) != SPECIAL_MAX:
        raise SystemExit("prior R3 id ceiling is not 10, or the special round is not 6")
    rows = read_csv(PRIOR)
    if len(rows) != PRIOR_MAX:
        raise SystemExit(f"prior rows {len(rows)}")
    updates = {row["id"]: row for row in read_csv(UPDATES)}
    if set(updates) != {f"R3-{n:03d}" for n in (1, 2, 3, 4, 5, 6, 8, 10)}:
        raise SystemExit("axis updates are not the eight rows whose pages were opened")
    out = []
    for row in rows:
        number = int(row["id"].split("-")[1])
        status = "棄却" if row["status"] == "棄却" else "再検証"
        if number in {7, 9} and status != "棄却":
            raise SystemExit(f"{row['id']} must stay rejected")
        qids = QID_RE.findall(row.get("source") or "")
        item = {
            "id": row["id"],
            "status": status,
            "type": row["category"],
            "muni_name": row["muni_name"],
            "name": row["name"],
            "lat": row.get("lat") or "",
            "lon": row.get("lon") or "",
            "axis_existence": row["axis_existed"],
            "axis_loss": row["axis_abolished"],
            "axis_remains": row["axis_remains"],
            "confidence": row["confidence"] if row["confidence"] in ALLOWED_CONF else "",
            "lead_id": "PRIOR",
            "role": row["category"],
            "sources": row.get("source") or "",
            "retrieved": RETRIEVED,
            "license": row.get("license") or "",
            "period": row.get("era") or "",
            "verification": "REV-HOLD",
            "notes": "2026-11-11の評価を再検証した。旧版地形図の記号は見ていないので高にしない。",
            "qid": qids[0] if qids else "",
        }
        if row["id"] in updates:
            upd = updates[row["id"]]
            for key in ("axis_existence", "axis_loss", "axis_remains"):
                if upd[key] not in ALLOWED_AXIS:
                    raise SystemExit(f"bad update axis {row['id']}")
                item[key] = upd[key]
            if upd["confidence"] not in ALLOWED_CONF or upd["confidence"] == "高":
                raise SystemExit(f"bad update confidence {row['id']}")
            item["confidence"] = upd["confidence"]
            item["verification"] = upd["verification"]
            item["notes"] = upd["notes"]
        if status == "棄却":
            item["verification"] = "REV-REJECT"
            item["notes"] += " 棄却は維持する。1km規則も、現行の旅客駅の記事も、今日は戻さない。"
            item["confidence"] = ""
        if item["confidence"] == "高" or item["axis_remains"] == "強":
            raise SystemExit("update raised a row to high")
        out.append(item)
    pointed = [row for row in out if row["lat"] and row["lon"]]
    if len(pointed) != POINTED_N:
        raise SystemExit("coordinate-bearing prior rows changed")
    if any(row["lat"] or row["lon"] for row in out if row["id"] in {"R3-009"}):
        raise SystemExit("rejected live station gained coordinates")
    return out


def load_judgments() -> list[dict]:
    rows = read_csv(JUDGMENTS)
    ids = [row["id"] for row in rows]
    if ids != [f"R3-{n:03d}" for n in range(NEW_FIRST, NEW_LAST + 1)]:
        raise SystemExit("new ids are not the next contiguous block")
    for row in rows:
        if row["status"] not in ALLOWED_STATUS:
            raise SystemExit(f"bad status {row['id']}")
        for key in ("axis_existence", "axis_loss", "axis_remains"):
            if row[key] not in ALLOWED_AXIS:
                raise SystemExit(f"bad axis {row['id']} {key}")
        if row["confidence"] not in ALLOWED_CONF or row["confidence"] == "高":
            raise SystemExit(f"bad confidence {row['id']}")
        if row["lat"] or row["lon"]:
            raise SystemExit("new row has coordinates")
        if row["status"] == "負例" and row["axis_loss"] != "なし":
            raise SystemExit(f"negative example has a loss axis {row['id']}")
        if row["status"] == "状態変化" and row["type"] == "神社" and row["axis_loss"] != "なし":
            raise SystemExit(f"shrine state change was marked abolished {row['id']}")
        if row["status"] == "新規" and row["confidence"] != "中":
            raise SystemExit(f"new adopted row is not medium {row['id']}")
        row.setdefault("lead_id", "")
        row.setdefault("role", "")
    return rows


def load_not_assigned() -> dict:
    rows = read_csv(NOT_ASSIGNED)
    if len(rows) != 8:
        raise SystemExit("not-assigned list changed")
    counts = Counter(row["reason"] for row in rows)
    if set(counts) - ALLOWED_REASON:
        raise SystemExit("unexpected not-assigned reason")
    return dict(counts)


def admin_union():
    table = pq.read_table(N03, columns=["muni_code", "geometry"])
    geoms = []
    seen = set()
    for code, geom in zip(table.column("muni_code").to_pylist(), table.column("geometry").to_pylist()):
        if code in R3_CODES and geom is not None:
            geoms.append(from_wkb(geom))
            seen.add(code)
    if seen != R3_CODES:
        raise SystemExit("R3 admin polygons are incomplete")
    union = unary_union(geoms)
    minx, miny, maxx, maxy = union.bounds
    if max(abs(minx), abs(miny), abs(maxx), abs(maxy)) < 1000:
        raise SystemExit("admin geometry is not in projected metres")
    west, south = TO_WGS.transform(minx, miny)
    east, north = TO_WGS.transform(maxx, maxy)
    pref = unary_union([
        from_wkb(geom) for geom in table.column("geometry").to_pylist() if geom is not None
    ])
    if not pref.covers(union.representative_point()):
        raise SystemExit("R3 union is outside the prefecture polygons")
    return union, (south, west, north, east)


def overpass_part(query: str, dest: Path) -> tuple[dict | None, str]:
    if dest.exists() and dest.stat().st_size > 0:
        try:
            return json.loads(dest.read_text(encoding="utf-8")), "cache"
        except json.JSONDecodeError:
            dest.unlink()
    body = urllib.parse.urlencode({"data": query}).encode("utf-8")
    for endpoint in OVERPASS_ENDPOINTS:
        err = dest.with_suffix(dest.suffix + ".error")
        if err.exists():
            err.unlink()
        if dest.exists():
            dest.unlink()
        raw = fetch(endpoint, dest, data=body, timeout=100)
        if not raw:
            continue
        try:
            return json.loads(raw), endpoint
        except json.JSONDecodeError:
            continue
    return None, ""


def overpass_counts(union, bbox) -> dict:
    south, west, north, east = bbox
    box = f"({south},{west},{north},{east})"
    parts = {
        "worship": f"""
    [out:json][timeout:90];
    (
      node["amenity"="place_of_worship"]{box};
      way["amenity"="place_of_worship"]{box};
    );
    out tags center;
    """,
        "historic": f"""
    [out:json][timeout:90];
    (
      node["historic"]{box};
      way["historic"]{box};
    );
    out tags center;
    """,
        "abandoned": f"""
    [out:json][timeout:60];
    (
      node["abandoned:amenity"="place_of_worship"]{box};
      way["abandoned:amenity"="place_of_worship"]{box};
      way["highway"="abandoned"]{box};
    );
    out tags center;
    """,
    }
    merged = []
    seen = set()
    used = []
    part_ok = {}
    for name, query in parts.items():
        payload, endpoint = overpass_part(query, SUPP / f"overpass_r3_{name}.json")
        part_ok[name] = payload is not None
        if payload is None:
            continue
        used.append(endpoint)
        for el in payload.get("elements") or []:
            key = (el.get("type"), el.get("id"))
            if key in seen:
                continue
            seen.add(key)
            merged.append(el)
    if not any(part_ok.values()):
        return {"ok": False, "endpoint": "", "part_ok": part_ok}
    (SUPP / "overpass_r3.json").write_text(
        json.dumps({"elements": merged}, ensure_ascii=False), encoding="utf-8",
    )
    payload = {"elements": merged}
    worship = ruins = abandoned_worship = abandoned_highway = historic = 0
    inside_elements = []
    for el in payload.get("elements") or []:
        if "lat" in el and "lon" in el:
            lon, lat = float(el["lon"]), float(el["lat"])
        elif "center" in el:
            lon, lat = float(el["center"]["lon"]), float(el["center"]["lat"])
        else:
            continue
        x, y = TO_6677.transform(lon, lat)
        if not union.covers(Point(x, y)):
            continue
        tags = el.get("tags") or {}
        inside_elements.append(el)
        if tags.get("amenity") == "place_of_worship":
            worship += 1
        if tags.get("abandoned:amenity") == "place_of_worship":
            abandoned_worship += 1
        if tags.get("historic") == "ruins":
            ruins += 1
        if tags.get("historic"):
            historic += 1
        if tags.get("highway") == "abandoned":
            abandoned_highway += 1
    (SUPP / "overpass_r3_inside.json").write_text(
        json.dumps({"elements": inside_elements}, ensure_ascii=False), encoding="utf-8",
    )
    return {
        "ok": all(part_ok.values()),
        "part_ok": part_ok,
        "worship_control": worship if part_ok.get("worship") else None,
        "historic": historic if part_ok.get("historic") else None,
        "historic_ruins": ruins if part_ok.get("historic") else None,
        "abandoned_worship": abandoned_worship if part_ok.get("abandoned") else None,
        "abandoned_highway": abandoned_highway if part_ok.get("abandoned") else None,
        "inside_elements": inside_elements,
        "endpoint": ",".join(used),
    }


def gsi_layers(union) -> dict:
    dest = SUPP / "gsi_layers1.txt"
    raw = fetch(LAYERS_URL, dest, timeout=60)
    catalog = fetch(
        "https://maps.gsi.go.jp/development/ichiran.html",
        SUPP / "gsi_ichiran.html",
        timeout=60,
    )
    if not raw:
        return {"ok": False}
    text = raw.decode("utf-8", errors="replace")
    if catalog:
        text += "\n" + catalog.decode("utf-8", errors="replace")
    rapid = text.count("迅速")
    old = text.count("旧版")
    wetland = "低湿地" in text
    cover_1928 = "not_parsed"
    match = re.search(
        r'"id"\s*:\s*"ort_1928".{0,800}?"lat"\s*:\s*([0-9.]+).{0,80}?"lng"\s*:\s*([0-9.]+)',
        text, flags=re.S,
    )
    if match:
        lat = float(match.group(1))
        lon = float(match.group(2))
        x, y = TO_6677.transform(lon, lat)
        cover_1928 = "inside_r3" if union.covers(Point(x, y)) else "listed_coverage_is_not_this_region"
    return {
        "ok": True,
        "rapid_count": rapid,
        "old_topo_count": old,
        "wetland_listed": wetland,
        "aerial_1928": cover_1928,
    }


def wikidata_end_dates(prior: list[dict]) -> dict:
    qids = [row["qid"] for row in prior if row.get("qid")]
    if len(qids) != PRIOR_MAX:
        raise SystemExit("expected a qid on every prior row")
    values = " ".join(f"wd:{qid}" for qid in qids)
    query = (
        "SELECT ?item ?end WHERE { VALUES ?item { " + values + " } "
        "OPTIONAL { ?item wdt:P576 ?end } }"
    )
    url = WIKIDATA + "?" + urllib.parse.urlencode({"query": query, "format": "json"})
    dest = SUPP / "wikidata_prior.json"
    raw = fetch(url, dest, timeout=60, accept="application/sparql-results+json")
    if not raw:
        return {"ok": False, "found": {}}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": False, "found": {}}
    found = {}
    for row in payload.get("results", {}).get("bindings", []):
        item = row.get("item", {}).get("value", "")
        end = row.get("end", {}).get("value", "")
        qid = item.rsplit("/", 1)[-1]
        if end:
            found[qid] = True
    return {"ok": True, "found": found}


def apply_live_checks(prior: list[dict], osm: dict, wiki: dict, layers: dict) -> dict:
    anno_dir = SUPP / "anno"
    geod = pyproj.Geod(ellps="WGS84")
    pointed = [row for row in prior if row["lat"] and row["lon"]]
    anno_keys: set[tuple[int, int]] = set()
    per_id = {}
    for row in pointed:
        lon, lat = float(row["lon"]), float(row["lat"])
        keys = tiles_for_buffer(lon, lat, 15, ANNO_MATCH_M)
        per_id[row["id"]] = keys
        anno_keys |= keys
    jobs = [(ANNO_URL.format(x=x, y=y), anno_dir / f"15_{x}_{y}.geojson") for x, y in sorted(anno_keys)]
    aerial_jobs = []
    for layer, (template, zoom) in AERIAL.items():
        seen = set()
        for row in pointed:
            key = tile_xy(float(row["lon"]), float(row["lat"]), zoom)
            if key in seen:
                continue
            seen.add(key)
            dest = SUPP / "aerial" / f"{layer}_{zoom}_{key[0]}_{key[1]}.png"
            aerial_jobs.append((template.format(x=key[0], y=key[1]), dest, layer))

    def run(job):
        return fetch(job[0], job[1]) is not None

    anno_ok = anno_fail = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        for fut in as_completed([pool.submit(run, job) for job in jobs]):
            if fut.result():
                anno_ok += 1
            else:
                anno_fail += 1
    aerial_counts = {layer: {"ok": 0, "fail": 0} for layer in AERIAL}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [(layer, pool.submit(fetch, url, dest)) for url, dest, layer in aerial_jobs]
        for layer, fut in futures:
            if fut.result() is not None:
                aerial_counts[layer]["ok"] += 1
            else:
                aerial_counts[layer]["fail"] += 1

    stem_hits = []
    anno_failed_ids = []
    for row in pointed:
        keys = per_id[row["id"]]
        if any(not (anno_dir / f"15_{x}_{y}.geojson").exists() for x, y in keys):
            anno_failed_ids.append(row["id"])
        stem = stem_of(row["name"])
        lon0, lat0 = float(row["lon"]), float(row["lat"])
        hit = False
        for x, y in keys:
            dest = anno_dir / f"15_{x}_{y}.geojson"
            if not dest.exists():
                continue
            try:
                payload = json.loads(dest.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                anno_failed_ids.append(row["id"])
                continue
            for feat in payload.get("features") or []:
                props = feat.get("properties") or {}
                ft = str(props.get("ftCode") or "")
                ctg = str(props.get("annoCtg") or "")
                if ft in PLACE_FT or ctg.startswith("居住地名") or ctg.startswith("行政区画"):
                    continue
                if stem_of(props.get("knj") or "") != stem:
                    continue
                geom = feat.get("geometry") or {}
                if geom.get("type") != "Point":
                    continue
                lon1, lat1 = geom["coordinates"][:2]
                _a, _b, dist = geod.inv(lon0, lat0, lon1, lat1)
                if abs(dist) <= ANNO_MATCH_M:
                    hit = True
        if hit:
            stem_hits.append(row["id"])
            row["notes"] += " 現行注記に200m以内で同じ語幹があった。旧版記号ではないので高にしない。"
        elif row["id"] in anno_failed_ids:
            row["notes"] += " 注記タイルの一部が失敗し、注記は未確認。"
        else:
            row["notes"] += " 取得できた現行注記に、居住地名と行政区画以外の同じ語幹は200m以内に無かった。"

    osm_hits = []
    if osm.get("part_ok", {}).get("historic"):
        for row in pointed:
            stem = stem_of(row["name"])
            lon0, lat0 = float(row["lon"]), float(row["lat"])
            for el in osm["inside_elements"]:
                tags = el.get("tags") or {}
                if not tags.get("historic"):
                    continue
                name = tags.get("name") or tags.get("name:ja") or ""
                if stem_of(name) != stem:
                    continue
                if "lat" in el:
                    lon1, lat1 = float(el["lon"]), float(el["lat"])
                else:
                    lon1, lat1 = float(el["center"]["lon"]), float(el["center"]["lat"])
                _a, _b, dist = geod.inv(lon0, lat0, lon1, lat1)
                if abs(dist) <= OSM_MATCH_M:
                    osm_hits.append(row["id"])
                    row["notes"] += " 現行OSMのhistoricに同じ語幹が400m以内にある。現地確認ではない。"
                    if row["status"] != "棄却" and row["axis_remains"] == "未確認":
                        row["axis_remains"] = "中"
                    break
            else:
                row["notes"] += " 現行OSMのhistoricに同じ語幹は400m以内に無かった。"
    else:
        for row in pointed:
            row["notes"] += " OSMの再取得は失敗した。0件とは書かない。"

    reopened = []
    if wiki.get("ok"):
        by_qid = {row["qid"]: row for row in prior if row.get("qid")}
        for qid in wiki["found"]:
            row = by_qid.get(qid)
            if row is None:
                continue
            reopened.append(row["id"])
            row["notes"] += " 廃止日のプロパティは項目に残っていた。軸は開いた頁の方を使い、プロパティだけでは動かさない。"
        for row in prior:
            if row["qid"] and row["id"] not in reopened:
                row["notes"] += " 今日のSPARQLでは廃止日のプロパティが応答に無かった。前回の終了日の記録は消さない。"
    else:
        for row in prior:
            row["notes"] += " Wikidataは再取得できなかった。0件とは書かない。"

    for row in prior:
        if row["confidence"] == "高" or row["axis_remains"] == "強":
            raise SystemExit("live check raised a row to high")
    return {
        "anno_tiles_requested": len(jobs),
        "anno_tiles_ok": anno_ok,
        "anno_tiles_failed": anno_fail,
        "anno_stem_hits": stem_hits,
        "anno_failed_ids": sorted(set(anno_failed_ids)),
        "aerial": aerial_counts,
        "osm_historic_stem_hits": osm_hits,
        "wikidata_enddate_ids": reopened,
        "layers": layers,
    }


def public_records(rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        out.append({
            "id": row["id"],
            "muni_name": row["muni_name"],
            "type": row["type"],
            "status": row["status"],
            "role": row.get("role") or "",
            "axis_existence": row["axis_existence"],
            "axis_loss": row["axis_loss"],
            "axis_remains": row["axis_remains"],
            "confidence": row["confidence"],
            "lead_id": row["lead_id"],
            "verification": row["verification"],
        })
    return out


def assert_public(payload: dict, names: list[str]) -> None:
    text = json.dumps(payload, ensure_ascii=False)
    if COORD_RE.search(text):
        raise SystemExit("public json contains a coordinate-like number")
    for name in names:
        if name and name in text:
            raise SystemExit("public json contains a candidate name")
    if "高" in text:
        raise SystemExit("public json contains high confidence")


def write_private(rows: list[dict], provenance: list[dict]) -> None:
    OUT_PRIV.mkdir(parents=True, exist_ok=True)
    fields = [
        "id", "status", "type", "muni_name", "name", "lat", "lon",
        "axis_existence", "axis_loss", "axis_remains", "confidence",
        "sources", "retrieved", "license", "period", "verification", "notes",
        "lead_id", "role",
    ]
    with (OUT_PRIV / "candidates.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    lines = ["# 非公開メモ 2026-11-18 R3", "", "リポジトリには置かない。名称と座標を含む。", ""]
    for row in rows:
        lines.append(
            f"- {row['id']} {row['status']} {row['muni_name']} {row['type']} {row['name']} "
            f"存在{row['axis_existence']} 廃止{row['axis_loss']} 遺構{row['axis_remains']} "
            f"総合{row['confidence'] or '空'} {row['verification']} {row.get('lead_id') or ''} "
            f"{row.get('notes') or ''}"
        )
    (OUT_PRIV / "findings.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with (SUPP / "provenance_supplemental.jsonl").open("w", encoding="utf-8") as handle:
        for row in provenance:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    SUPP.mkdir(parents=True, exist_ok=True)
    elapsed = (date(2026, 11, 18) - date(2026, 10, 26)).days
    if elapsed != 23 or elapsed % 7 != 2 or elapsed // 7 + 1 != 4:
        raise SystemExit(f"rotation mismatch: elapsed={elapsed}")
    manifest = verify_manifest()
    land = landuse_inventory()
    if not (land["landscape_max_changed_share"] < 0.5):
        raise SystemExit("max landscape share crossed 50 percent")
    if not land["oiso_still_uncovered"] or not land["ninomiya_still_uncovered"]:
        raise SystemExit("coverage gap changed")
    prior = load_prior()
    judgments = load_judgments()
    skipped = load_not_assigned()
    union, bbox = admin_union()
    osm = overpass_counts(union, bbox)
    layers = gsi_layers(union)
    wiki = wikidata_end_dates(prior)
    maps = apply_live_checks(prior, osm, wiki, layers)
    rows = prior + judgments
    if [row["id"] for row in rows] != [f"R3-{n:03d}" for n in range(1, NEW_LAST + 1)]:
        raise SystemExit("combined ids are not contiguous")
    names = [row["name"] for row in rows]
    names.extend(row["name"] for row in read_csv(NOT_ASSIGNED))
    public_rows = public_records(rows)
    by_status = Counter(row["status"] for row in rows)
    by_type = Counter(row["type"] for row in rows)
    by_conf = Counter(row["confidence"] or "空" for row in rows)
    by_lead = Counter(row["lead_id"] for row in rows)
    new_rows = [row for row in rows if row["lead_id"] != "PRIOR"]
    by_muni_new = Counter(row["muni_name"] for row in new_rows)
    adopted = [
        row["id"] for row in rows
        if row["type"] == "神社" and row["status"] in {"新規", "再検証"} and row["confidence"] in {"中", "高"}
    ]
    if adopted:
        raise SystemExit("a shrine was adopted")
    if any(row["confidence"] == "高" for row in rows):
        raise SystemExit("high confidence was assigned")
    aerial_1928 = maps["layers"].get("aerial_1928")
    if aerial_1928 == "inside_r3":
        raise SystemExit("1928 layer was parsed as covering this region; do not assume Osaka")
    payload = {
        "date": RETRIEVED,
        "region": "R3",
        "week": 4,
        "elapsed_days": elapsed,
        "day_number": elapsed + 1,
        "rotation": "23 mod 7 = 2, floor(23/7)+1 = 4",
        "prior_ids_max": PRIOR_MAX,
        "new_id_first": NEW_FIRST,
        "new_id_last": NEW_LAST,
        "rows": len(rows),
        "high_confidence": 0,
        "adopted_lost_shrines": 0,
        "reverified_medium": sum(1 for row in prior if row["confidence"] == "中"),
        "by_status": dict(by_status),
        "by_type": dict(by_type),
        "by_confidence": dict(by_conf),
        "by_lead": dict(by_lead),
        "new_by_muni": dict(by_muni_new),
        "new_by_status": dict(Counter(row["status"] for row in new_rows)),
        "not_assigned": skipped,
        "catalogs_opened_today": 0,
        "landuse": land,
        "maps": {
            "anno_tiles_requested": maps["anno_tiles_requested"],
            "anno_tiles_ok": maps["anno_tiles_ok"],
            "anno_tiles_failed": maps["anno_tiles_failed"],
            "anno_stem_hits": maps["anno_stem_hits"],
            "anno_failed_ids": maps["anno_failed_ids"],
            "aerial_1961_1969_ok": maps["aerial"]["ort_old10"]["ok"],
            "aerial_1961_1969_fail": maps["aerial"]["ort_old10"]["fail"],
            "aerial_1945_1950_ok": maps["aerial"]["ort_USA10"]["ok"],
            "aerial_1945_1950_fail": maps["aerial"]["ort_USA10"]["fail"],
            "aerial_1928": aerial_1928,
            "old_topo_tiles": "not_in_tile_list" if maps["layers"].get("old_topo_count") == 0 else "listed",
            "rapid_survey_tiles": "not_in_tile_list" if maps["layers"].get("rapid_count") == 0 else "listed",
            "old_topo_tiff": "not_acquired",
            "meiji_wetland_tiles": "listed_not_used" if maps["layers"].get("wetland_listed") else "not_listed",
            "gsi_terms": GSI_TERMS,
        },
        "osm": {
            "ok": osm.get("ok", False),
            "part_ok": osm.get("part_ok") or {},
            "worship_control": osm.get("worship_control"),
            "historic": osm.get("historic"),
            "historic_ruins": osm.get("historic_ruins"),
            "abandoned_worship": osm.get("abandoned_worship"),
            "abandoned_highway": osm.get("abandoned_highway"),
            "historic_stem_hits": maps["osm_historic_stem_hits"],
            "endpoint_used": bool(osm.get("endpoint")),
            "tsukui_parquet_used": False,
            "geofabrik_pbf_stored": False,
        },
        "wikidata": {
            "ok": wiki.get("ok", False),
            "enddate_ids": maps["wikidata_enddate_ids"],
        },
        "ids": public_rows,
    }
    osm.pop("inside_elements", None)
    assert_public(payload, names)
    PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    provenance = manifest + [{
        "key": "overpass_r3",
        "sha256": sha256_file(SUPP / "overpass_r3.json") if (SUPP / "overpass_r3.json").exists() else "",
        "url": osm.get("endpoint") or OVERPASS_ENDPOINTS[0],
        "retrieved": RETRIEVED,
        "license": "ODbL",
        "period": "query date",
    }, {
        "key": "wikidata_prior",
        "sha256": sha256_file(SUPP / "wikidata_prior.json") if (SUPP / "wikidata_prior.json").exists() else "",
        "url": WIKIDATA,
        "retrieved": RETRIEVED,
        "license": "CC0",
        "period": "P576",
    }, {
        "key": "gsi_layers",
        "sha256": sha256_file(SUPP / "gsi_layers1.txt") if (SUPP / "gsi_layers1.txt").exists() else "",
        "url": LAYERS_URL,
        "retrieved": RETRIEVED,
        "license": "国土地理院コンテンツ利用規約",
        "period": "tile list",
    }, {
        "key": "gsi_ichiran",
        "sha256": sha256_file(SUPP / "gsi_ichiran.html") if (SUPP / "gsi_ichiran.html").exists() else "",
        "url": "https://maps.gsi.go.jp/development/ichiran.html",
        "retrieved": RETRIEVED,
        "license": "国土地理院コンテンツ利用規約",
        "period": "tile catalog",
    }]
    write_private(rows, provenance)
    print(json.dumps({
        "rows": payload["rows"],
        "by_status": payload["by_status"],
        "by_type": payload["by_type"],
        "by_confidence": payload["by_confidence"],
        "new_by_status": payload["new_by_status"],
        "new_by_muni": payload["new_by_muni"],
        "high": payload["high_confidence"],
        "adopted_lost_shrines": payload["adopted_lost_shrines"],
        "reverified_medium": payload["reverified_medium"],
        "osm_ok": payload["osm"]["ok"],
        "worship_control": payload["osm"]["worship_control"],
        "historic": payload["osm"]["historic"],
        "abandoned_highway": payload["osm"]["abandoned_highway"],
        "wikidata_ok": payload["wikidata"]["ok"],
        "enddate_ids": payload["wikidata"]["enddate_ids"],
        "anno_stem_hits": payload["maps"]["anno_stem_hits"],
        "aerial_1961": [payload["maps"]["aerial_1961_1969_ok"], payload["maps"]["aerial_1961_1969_fail"]],
        "aerial_1945": [payload["maps"]["aerial_1945_1950_ok"], payload["maps"]["aerial_1945_1950_fail"]],
        "aerial_1928": payload["maps"]["aerial_1928"],
        "old_topo": payload["maps"]["old_topo_tiles"],
        "rapid": payload["maps"]["rapid_survey_tiles"],
        "max_share": payload["landuse"]["landscape_max_changed_share"],
        "unnamed_gain": payload["landuse"]["unnamed_gain_km2"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
