"""R2（三浦半島）4週目。2026-11-17。

主目的は、既存候補の再検証と、合祀・軍用地・復祀の記録を廃社と分けて数えること。
土地利用は、前回同地域の集計がまだ同じかを確認するだけに限る。

公開 JSON には件数、市区町村、候補 ID、3軸、確度、リード ID、検証コードだけを書く。
名称と緯度経度は、環境変数で渡した非公開ファイルから読み、
/opt/cursor/artifacts/kanagawa_private/2026-11-17_R2/ に出す。
スクリプトには地点の緯度経度も候補名も書かない。

評価は件数を数える前に固定した。

- 過去に存在した根拠、廃止・消失の根拠、物理的遺構が残る可能性は別の欄にする。
- 現行の地図に名称が無いこと、森林化、目録の概要は、消失の根拠にしない。
- 座標は、入力 CSV に列があるときだけ読む。字名や住所からは点を作らない。
- 総合確度の高は、旧版地形図の記号を見ていない限り付けない。今日は付けない。
- 遷座先、合祀先、復祀、現社は廃社にしない。旧地と移転は状態変化にする。
- 投稿は二次である。画像は保存しない。画像から位置を推定しない。
- 明細帳の存在リストや合祀の記録だけでは、低確度の既存行を格上げしない。
- 短い共通名の新規は、判断 CSV に既に区別がある行だけを数える。
- 旧版地形図の交付 TIFF は取得していない。空中写真は地形図記号ではない。
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pyarrow.parquet as pq
import pyproj
from shapely import from_wkb
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[3]
JUDGMENTS = Path(os.environ["PRIVATE_JUDGMENTS_CSV"])
PRIOR = Path(os.environ["PRIVATE_PRIOR_CANDIDATES"])
SPECIAL = Path(os.environ["PRIVATE_SPECIAL_CANDIDATES"])
CELLS = Path(os.environ["CELLS_PARQUET"])
N03 = Path(os.environ["N03_PARQUET"])
MANIFEST = Path(os.environ["SOURCE_MANIFEST_CSV"])
SUPP = Path(os.environ["SUPP_DIR"])
OUT_PRIV = Path("/opt/cursor/artifacts/kanagawa_private/2026-11-17_R2")
PUBLIC = ROOT / "reports" / "daily_region" / "data" / "2026-11-17_R2_week4_public.json"
RESULTS = ROOT / "reports" / "phase1c2_results.json"
WORK = Path(os.environ.get("R2_WORK_DIR", "/tmp/r2_20261117"))
RETRIEVED = "2026-11-17"
UA = "kanagawa-ruins-search/2026-11-17"
R2_CODES = {"14201", "14204", "14208", "14210", "14301"}
PRIOR_MAX = 23
NEW_FIRST = 24
NEW_LAST = 48
ANNO_MATCH_M = 200.0
OSM_MATCH_M = 400.0
PLACE_FT = {"0210", "0220"}
COORD_RE = re.compile(r"(?:3[4-6]|13[89])\.[0-9]{3,}")
ALLOWED_STATUS = {"新規", "既存", "再検証", "棄却", "負例", "状態変化", "保留"}
ALLOWED_AXIS = {"強", "中", "低", "なし", "未確認", "対象外"}
ALLOWED_CONF = {"中", "低", "負例", ""}
ANNO_URL = "https://cyberjapandata.gsi.go.jp/xyz/experimental_anno/15/{x}/{y}.geojson"
# 1928年頃の層はタイル一覧の提供範囲が大阪市域なので、R2では要求しない。
AERIAL = {
    "ort_old10": ("https://cyberjapandata.gsi.go.jp/xyz/ort_old10/17/{x}/{y}.png", 17),
}
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
WIKIDATA = "https://query.wikidata.org/sparql"
GSI_TERMS = "https://www.gsi.go.jp/kikakuchousei/kikakuchousei40182.html"
TO_6677 = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:6677", always_xy=True)
TO_WGS = pyproj.Transformer.from_crs("EPSG:6677", "EPSG:4326", always_xy=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def stem_of(value: str) -> str:
    text = re.sub(r"\s+", "", value or "")
    text = re.sub(r"（[^）]*）", "", text)
    text = re.sub(r"\([^)]*\)", "", text)
    return re.sub(r"(駅|跡|信号所|信号場|仮乗降場|古址)$", "", text)


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


def max_r2(path: Path) -> int:
    nums = []
    for row in read_csv(path):
        ident = row.get("id") or ""
        if ident.startswith("R2-"):
            nums.append(int(ident.split("-")[1]))
    return max(nums) if nums else 0


def verify_manifest() -> list[dict]:
    rows = read_csv(MANIFEST)
    if not rows:
        raise SystemExit("source manifest is empty")
    checked = []
    for row in rows:
        path = Path(row["path"])
        if not path.exists():
            raise SystemExit(f"missing source {row['key']}")
        digest = sha256_file(path)
        if digest != row["sha256"]:
            raise SystemExit(f"hash mismatch {row['key']}")
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
    required = {
        "jinja_hashirimizu", "city_hashirimizu", "miura_kaminari",
        "mokuroku_pdf", "gsi_ichiran", "city_base_return",
        "suzuki_1982", "suzuki_1997", "oppama_showa",
    }
    missing = required - keys
    if missing:
        raise SystemExit(f"manifest missing {sorted(missing)}")
    return checked


def load_results() -> dict:
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    region = {
        name: dict(zip(data["aggregates"]["region"]["columns"], row))
        for name, row in zip(data["aggregates"]["region"]["index"], data["aggregates"]["region"]["data"])
    }
    rl = data["aggregates"]["region_landscape"]
    by_key = {
        tuple(idx): dict(zip(rl["columns"], row))
        for idx, row in zip(rl["index"], rl["data"])
    }
    cov = {
        name: dict(zip(data["coverage"]["by_region"]["columns"], row))
        for name, row in zip(data["coverage"]["by_region"]["index"], data["coverage"]["by_region"]["data"])
    }
    return {"r2": region["R2_miura"], "by_key": by_key, "cov": cov["R2_miura"]}


def landuse_check(tables: dict) -> dict:
    cells = pq.read_table(CELLS, columns=["region", "landscape"], filters=[("region", "=", "R2_miura")])
    n = cells.num_rows
    r2 = tables["r2"]
    if n != int(r2["n_cells"]):
        raise SystemExit(f"cell count {n} != {r2['n_cells']}")
    landscapes = Counter(cells.column("landscape").to_pylist())
    if landscapes.get("forest_dominant") != 32:
        raise SystemExit(f"forest_dominant cells {landscapes.get('forest_dominant')}")
    cell_km2 = r2["land_km2"] / r2["n_cells"]
    urban = tables["by_key"][("R2_miura", "urban")]
    forest = tables["by_key"][("R2_miura", "forest_dominant")]
    gain_cells = urban["building_gain_km2"] / cell_km2
    loss_cells = urban["building_loss_km2"] / cell_km2
    net = urban["building_gain_km2"] - urban["building_loss_km2"]
    out = {
        "n_cells": int(r2["n_cells"]),
        "land_km2": round(r2["land_km2"], 2),
        "coverage": tables["cov"]["coverage"],
        "scope": tables["cov"]["scope"],
        "urban_building_gain_km2": round(urban["building_gain_km2"], 4),
        "urban_building_loss_km2": round(urban["building_loss_km2"], 4),
        "urban_building_gain_cells": round(gain_cells, 1),
        "urban_building_loss_cells": round(loss_cells, 1),
        "urban_building_net_km2": round(net, 4),
        "forest_dominant_km2": round(forest["land_km2"], 4),
        "forest_dominant_changed_km2": round(forest["changed_km2"], 4),
        "forest_dominant_cells": int(round(forest["land_km2"] / cell_km2)),
        "forest_dominant_cell_count_in_parquet": landscapes["forest_dominant"],
    }
    if out["urban_building_gain_cells"] != 23.0 or out["urban_building_loss_cells"] != 15.0:
        raise SystemExit("urban building cell counts moved")
    if abs(out["urban_building_net_km2"] - 0.0840) > 0.0002:
        raise SystemExit("urban building net moved")
    if out["scope"] != "excluded":
        raise SystemExit("R2 scope is not excluded")
    return out


def load_prior() -> list[dict]:
    if max_r2(PRIOR) != PRIOR_MAX or max_r2(SPECIAL) != 4:
        raise SystemExit("prior R2 id ceiling is not 23, or the special round is not 4")
    rows = read_csv(PRIOR)
    if len(rows) != PRIOR_MAX:
        raise SystemExit(f"prior rows {len(rows)}")
    out = []
    for row in rows:
        number = int(row["id"].split("-")[1])
        status = "棄却" if row["status"] == "棄却" else "再検証"
        if number == 7 and status != "棄却":
            raise SystemExit("R2-007 must stay rejected")
        if 5 <= number <= 23 and number != 7:
            if row["confidence"] != "低" or row["category"] != "神社":
                raise SystemExit(f"low shrine row changed before review {row['id']}")
            if row["axis_remains"] != "未確認" or row.get("lat") or row.get("lon"):
                raise SystemExit(f"low shrine row has remains or coordinates {row['id']}")
        conf = row["confidence"] if row["confidence"] in ALLOWED_CONF else ""
        if status != "棄却" and conf not in {"中", "低"}:
            raise SystemExit(f"bad prior confidence {row['id']}")
        out.append({
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
            "confidence": conf,
            "lead_id": "PRIOR",
            "role": row["category"],
            "sources": row.get("source") or "",
            "retrieved": RETRIEVED,
            "license": row.get("license") or "",
            "period": row.get("era") or "",
            "verification": "REV-HOLD",
            "notes": "2026-11-10の評価を再検証した。旧版地形図の記号は見ていないので高にしない。",
            "qid": row.get("qid") or "",
        })
    return out


def load_judgments() -> list[dict]:
    rows = read_csv(JUDGMENTS)
    ids = [row["id"] for row in rows]
    if ids != [f"R2-{n:03d}" for n in range(NEW_FIRST, NEW_LAST + 1)]:
        raise SystemExit("new ids are not the next contiguous block")
    for row in rows:
        if row["status"] not in ALLOWED_STATUS:
            raise SystemExit(f"bad status {row['id']}")
        for key in ("axis_existence", "axis_loss", "axis_remains"):
            if row[key] not in ALLOWED_AXIS:
                raise SystemExit(f"bad axis {row['id']} {key}")
        if row["confidence"] not in ALLOWED_CONF or row["confidence"] == "高":
            raise SystemExit(f"bad confidence {row['id']}")
        if row["type"] == "廃社" or row["lat"] or row["lon"]:
            raise SystemExit("new row has 廃社 or coordinates")
        if row["status"] == "負例" and row["axis_loss"] != "なし":
            raise SystemExit(f"negative example has a loss axis {row['id']}")
        if row["status"] == "状態変化" and row["type"] == "神社" and row["axis_loss"] != "なし":
            raise SystemExit(f"shrine state change was marked abolished {row['id']}")
    return rows


def admin_union():
    table = pq.read_table(N03, columns=["muni_code", "geometry"])
    geoms = []
    for code, geom in zip(table.column("muni_code").to_pylist(), table.column("geometry").to_pylist()):
        if code in R2_CODES and geom is not None:
            geoms.append(from_wkb(geom))
    if len(geoms) < 5:
        raise SystemExit("R2 admin polygons are incomplete")
    union = unary_union(geoms)
    minx, miny, maxx, maxy = union.bounds
    # 幾何はメートル値。original_crs 列は変換前の地理座標系で、幾何のCRSではない。
    # 2026-11-16 と同じく EPSG:6677 として経緯度に戻す。メタデータの世代名との差はタイル特定に使わない。
    if max(abs(minx), abs(miny), abs(maxx), abs(maxy)) < 1000:
        raise SystemExit("admin geometry is not in projected metres")
    west, south = TO_WGS.transform(minx, miny)
    east, north = TO_WGS.transform(maxx, maxy)
    # 県のポリゴンの内側にあることだけを確認する。経緯度は公開しない。
    pref = unary_union([
        from_wkb(geom) for geom in table.column("geometry").to_pylist() if geom is not None
    ])
    if not pref.covers(union.representative_point()):
        raise SystemExit("R2 union is outside the prefecture polygons")
    return union, (south, west, north, east)


def overpass_counts(union, bbox) -> dict:
    south, west, north, east = bbox
    query = f"""
    [out:json][timeout:80];
    (
      node["amenity"="place_of_worship"]({south},{west},{north},{east});
      way["amenity"="place_of_worship"]({south},{west},{north},{east});
      node["abandoned:amenity"="place_of_worship"]({south},{west},{north},{east});
      way["abandoned:amenity"="place_of_worship"]({south},{west},{north},{east});
      node["historic"="ruins"]({south},{west},{north},{east});
      way["historic"="ruins"]({south},{west},{north},{east});
      way["highway"="abandoned"]({south},{west},{north},{east});
      node["historic"]({south},{west},{north},{east});
      way["historic"]({south},{west},{north},{east});
    );
    out tags center;
    """
    dest = SUPP / "overpass_r2.json"
    raw = None
    used = ""
    body = query.encode("utf-8")
    for endpoint in OVERPASS_ENDPOINTS:
        raw = fetch(endpoint, dest, data=body, timeout=120)
        if raw:
            used = endpoint
            break
        err = dest.with_suffix(dest.suffix + ".error")
        if err.exists():
            err.unlink()
    if not raw:
        return {"ok": False, "endpoint": ""}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": False}
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
        from shapely.geometry import Point
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
    (SUPP / "overpass_r2_inside.json").write_text(
        json.dumps({"elements": inside_elements}, ensure_ascii=False), encoding="utf-8",
    )
    return {
        "ok": True,
        "worship_control": worship,
        "historic": historic,
        "historic_ruins": ruins,
        "abandoned_worship": abandoned_worship,
        "abandoned_highway": abandoned_highway,
        "inside_elements": inside_elements,
        "endpoint": used,
    }


def wikidata_end_dates(prior: list[dict]) -> dict:
    qids = [row["qid"] for row in prior if row.get("qid")]
    if len(qids) != 4:
        raise SystemExit("expected four prior qids")
    values = " ".join(f"wd:{qid}" for qid in qids)
    query = (
        "SELECT ?item ?end WHERE { VALUES ?item { " + values + " } "
        "OPTIONAL { ?item wdt:P582 ?end } }"
    )
    url = WIKIDATA + "?" + urllib.parse.urlencode({"query": query, "format": "json"})
    dest = SUPP / "wikidata_prior.json"
    raw = fetch(url, dest, timeout=60, accept="application/json")
    found = {}
    if not raw:
        return {"ok": False, "found": found}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": False, "found": found}
    for binding in payload.get("results", {}).get("bindings", []):
        item = binding.get("item", {}).get("value", "")
        qid = item.rsplit("/", 1)[-1]
        end = binding.get("end", {}).get("value")
        if end:
            found[qid] = end[:10]
    return {"ok": True, "found": found}


def apply_live_checks(prior: list[dict], osm: dict, wiki: dict) -> dict:
    anno_dir = SUPP / "anno"
    geod = pyproj.Geod(ellps="WGS84")
    pointed = [row for row in prior if row["lat"] and row["lon"]]
    if len(pointed) != 4:
        raise SystemExit("coordinate-bearing prior rows are not the known four")
    anno_keys: set[tuple[int, int]] = set()
    per_id = {}
    for row in pointed:
        lon, lat = float(row["lon"]), float(row["lat"])
        keys = tiles_for_buffer(lon, lat, 15, ANNO_MATCH_M)
        per_id[row["id"]] = keys
        anno_keys |= keys
    jobs = []
    for x, y in sorted(anno_keys):
        jobs.append((ANNO_URL.format(x=x, y=y), anno_dir / f"15_{x}_{y}.geojson"))
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
        url, dest = job[0], job[1]
        return fetch(url, dest) is not None

    anno_ok = 0
    anno_fail = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(run, job) for job in jobs]
        for fut in as_completed(futures):
            if fut.result():
                anno_ok += 1
            else:
                anno_fail += 1
    aerial_counts = {layer: {"ok": 0, "fail": 0} for layer in AERIAL}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = []
        for url, dest, layer in aerial_jobs:
            futures.append((layer, pool.submit(fetch, url, dest)))
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
            payload = json.loads(dest.read_text(encoding="utf-8"))
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
    if osm.get("ok"):
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
                    break
        for row in pointed:
            if row["id"] in osm_hits and row["axis_remains"] == "未確認":
                row["axis_remains"] = "中"
                row["notes"] += " 現行OSMのhistoricに同じ語幹が400m以内にある。現地確認ではない。"
            elif row["id"] == "R2-001":
                row["notes"] += " 2026-11-10に遺構を中にした現行のhistoric照合は維持する。今日のクエリだけで下げない。"
    else:
        for row in pointed:
            row["notes"] += " OSMの再取得は失敗した。0件とは書かない。"

    reopened = []
    if wiki.get("ok"):
        by_qid = {row["qid"]: row for row in prior if row.get("qid")}
        for qid, _end in wiki["found"].items():
            row = by_qid.get(qid)
            if row is None:
                continue
            row["axis_loss"] = "強"
            row["verification"] = "REV-ENDDATE"
            row["notes"] += " 2026-11-17のSPARQLで終了日を再読した。遺構は動かさず、高にはしない。"
            reopened.append(row["id"])
        for row in pointed:
            if row["id"] not in reopened:
                row["notes"] += " 2026-11-17のSPARQLでは直接の終了日プロパティが応答に無かった。2026-11-05の終了日の記録は消さない。廃止は中のまま。"
    else:
        for row in pointed:
            row["notes"] += " Wikidataは再取得できなかった。廃止は中のまま。0件とは書かない。"

    for row in prior:
        if row["confidence"] == "低":
            row["verification"] = "REV-LOW"
            row["notes"] += " 目録の概要のまま。所在目録と論文と投稿では格上げしない。"
        if row["status"] == "棄却":
            row["verification"] = "REV-REJECT"
            row["notes"] += " 移転新築の棄却を維持する。廃止に戻さない。"
        if row["confidence"] == "高" or row["axis_remains"] == "強":
            raise SystemExit("live check raised a row to high")
    return {
        "anno_tiles_requested": len(jobs),
        "anno_tiles_ok": anno_ok,
        "anno_tiles_failed": anno_fail,
        "anno_stem_hits": stem_hits,
        "anno_failed_ids": anno_failed_ids,
        "aerial": aerial_counts,
        "osm_historic_stem_hits": osm_hits,
        "wikidata_enddate_ids": reopened,
        "old_topo_tiff": "not_acquired",
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
    with (SUPP / "provenance_supplemental.jsonl").open("w", encoding="utf-8") as handle:
        for row in provenance:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    SUPP.mkdir(parents=True, exist_ok=True)
    manifest = verify_manifest()
    tables = load_results()
    land = landuse_check(tables)
    prior = load_prior()
    judgments = load_judgments()
    union, bbox = admin_union()
    osm = overpass_counts(union, bbox)
    wiki = wikidata_end_dates(prior)
    maps = apply_live_checks(prior, osm, wiki)
    rows = prior + judgments
    if [row["id"] for row in rows] != [f"R2-{n:03d}" for n in range(1, NEW_LAST + 1)]:
        raise SystemExit("combined ids are not contiguous")
    names = [row["name"] for row in rows]
    public_rows = public_records(rows)
    by_status = Counter(row["status"] for row in rows)
    by_type = Counter(row["type"] for row in rows)
    by_conf = Counter(row["confidence"] or "空" for row in rows)
    by_lead = Counter(row["lead_id"] for row in rows)
    by_muni = Counter(row["muni_name"] for row in rows if row["lead_id"] != "PRIOR")
    adopted = [
        row["id"] for row in rows
        if row["type"] == "神社" and row["status"] in {"新規", "再検証"} and row["confidence"] in {"中", "高"}
    ]
    payload = {
        "date": RETRIEVED,
        "region": "R2",
        "week": 4,
        "elapsed_days": 22,
        "day_number": 23,
        "rotation": "22 mod 7 = 1, floor(22/7)+1 = 4",
        "prior_ids_max": PRIOR_MAX,
        "new_id_first": NEW_FIRST,
        "new_id_last": NEW_LAST,
        "rows": len(rows),
        "high_confidence": 0,
        "adopted_lost_shrines": len(adopted),
        "reverified_medium": sum(1 for row in prior if row["confidence"] == "中"),
        "reverified_low_shrines": sum(1 for row in prior if row["confidence"] == "低"),
        "by_status": dict(by_status),
        "by_type": dict(by_type),
        "by_confidence": dict(by_conf),
        "by_lead": dict(by_lead),
        "new_by_muni": dict(by_muni),
        "landuse": land,
        "maps": {
            "anno_tiles_requested": maps["anno_tiles_requested"],
            "anno_tiles_ok": maps["anno_tiles_ok"],
            "anno_tiles_failed": maps["anno_tiles_failed"],
            "anno_stem_hits": maps["anno_stem_hits"],
            "anno_failed_ids": maps["anno_failed_ids"],
            "aerial_1961_1969_ok": maps["aerial"]["ort_old10"]["ok"],
            "aerial_1961_1969_fail": maps["aerial"]["ort_old10"]["fail"],
            "aerial_1928": "listed_coverage_is_not_this_region",
            "old_topo_tiff": "not_acquired",
            "meiji_wetland_tiles": "listed_not_used",
            "gsi_terms": GSI_TERMS,
        },
        "osm": {
            "ok": osm.get("ok", False),
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
    # 公開 JSON から要素本体を落とす。カウントだけ残す。
    osm.pop("inside_elements", None)
    assert_public(payload, names)
    PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    provenance = manifest + [{
        "key": "overpass_r2",
        "sha256": sha256_file(SUPP / "overpass_r2.json") if (SUPP / "overpass_r2.json").exists() else "",
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
        "period": "end date property",
    }]
    write_private(rows, provenance)
    print(json.dumps({
        "rows": payload["rows"],
        "by_status": payload["by_status"],
        "high": payload["high_confidence"],
        "adopted_lost_shrines": payload["adopted_lost_shrines"],
        "osm_ok": payload["osm"]["ok"],
        "worship_control": payload["osm"]["worship_control"],
        "wikidata_ok": payload["wikidata"]["ok"],
        "enddate_ids": payload["wikidata"]["enddate_ids"],
        "anno_stem_hits": payload["maps"]["anno_stem_hits"],
        "aerial_1961_1969": [
            payload["maps"]["aerial_1961_1969_ok"],
            payload["maps"]["aerial_1961_1969_fail"],
        ],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
