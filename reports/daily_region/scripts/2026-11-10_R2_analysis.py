"""R2（三浦半島）3週目。改訂方針（2026-11-09、2026-11-10から適用）の初回。

主目的は廃神社・廃寺・消滅集落・廃道・廃施設の探索と検証。
土地利用は、前回同地域の宿題が既存集計で言えるかの棚卸しに限る。

公開JSONには件数・市区町村・候補ID・3軸の内訳だけを書く。
名称・緯度経度・大字は `/opt/cursor/artifacts/kanagawa_private/2026-11-10_R2/` に出す。
新規取得の実体は supplemental tar に入れ、リポジトリには置かない。

評価は集計の前に固定した。

- 過去に存在した根拠、廃止・消失の根拠、物理的遺構が残る可能性を別々に書く。
- 現行OSMに名称が無いこと、森林化したことだけでは消失にしない。
- 名称が現行資料に残っていても、終了日や合併注記を消さない。駅だけは、
  現行の旅客駅と同じ語幹が1km以内なら取り違えとして棄却する。
- 語幹は完全一致。部分一致に広げない。
- 座標は入力データにあるものだけを使う。住所や字名から点を作らない。
- 明細帳の画像を読んでいない項を、読んだことにしない。
- 注記タイルと空中写真の404は未確認であり、地物が無いという意味にしない。
- 総合確度「高」は、旧版地形図の記号照合が無い限り付けない。
- カタログ概要文だけの神社候補は、位置が無いので総合確度を低にする。
  廃止文言が強くても、総合確度は上げない。
- 合併・抹消・移転・改称の語が無い項は候補にしない。
- 本文が次の項番と接触して合併の語が欠ける項は候補にしない。
- 行政合併、個人の住居、OSMのタグだけの地物はIDを付けない。
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
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[3]
DRIVE = Path("/tmp/kanagawa_drive_20261110")
OUT_PRIV = Path("/opt/cursor/artifacts/kanagawa_private/2026-11-10_R2")
PUBLIC = ROOT / "reports" / "daily_region" / "data" / "2026-11-10_R2_week3_public.json"
TMP = Path("/tmp/r2_supp_20261110")
RETRIEVED = "2026-11-10"
UA = "kanagawa-ruins-search/2026-11-10"
R2_CODES = {"14201", "14204", "14208", "14210", "14301"}
EXISTING_Q = {
    "Q11569242": "R2-001",
    "Q2880345": "R2-002",
    "Q136482216": "R2-003",
    "Q11582180": "R2-004",
}
OSM_MATCH_M = 400.0
STATION_LIVE_M = 1000.0
ANNO_MATCH_M = 200.0
PLACE_FT = {"0210", "0220"}

# 旧村・旧町の先頭一致。長いものから試す。三浦郡の明細帳を現行5市町へ付けるための表。
VILLAGE_MUNI = [
    ("八幡久里浜", "横須賀市", "14201"),
    ("南下浦", "三浦市", "14210"),
    ("下宮田", "三浦市", "14210"),
    ("上宮田", "三浦市", "14210"),
    ("高円坊", "三浦市", "14210"),
    ("小網代", "三浦市", "14210"),
    ("城ケ島", "三浦市", "14210"),
    ("城ヶ島", "三浦市", "14210"),
    ("昆沙門", "三浦市", "14210"),
    ("毘沙門", "三浦市", "14210"),
    ("木古庭", "葉山町", "14301"),
    ("上山口", "葉山町", "14301"),
    ("下山口", "葉山町", "14301"),
    ("須軽谷", "横須賀市", "14201"),
    ("太田和", "横須賀市", "14201"),
    ("大田和", "横須賀市", "14201"),
    ("内川", "横須賀市", "14201"),
    ("船越", "横須賀市", "14201"),
    ("不入斗", "横須賀市", "14201"),
    ("久里浜", "横須賀市", "14201"),
    ("横須賀", "横須賀市", "14201"),
    ("浦郷", "横須賀市", "14201"),
    ("田浦", "横須賀市", "14201"),
    ("長浦", "横須賀市", "14201"),
    ("逸見", "横須賀市", "14201"),
    ("深田", "横須賀市", "14201"),
    ("中里", "横須賀市", "14201"),
    ("豊島", "横須賀市", "14201"),
    ("佐野", "横須賀市", "14201"),
    ("公郷", "横須賀市", "14201"),
    ("大津", "横須賀市", "14201"),
    ("走水", "横須賀市", "14201"),
    ("鴨居", "横須賀市", "14201"),
    ("浦賀", "横須賀市", "14201"),
    ("久村", "横須賀市", "14201"),
    ("佐原", "横須賀市", "14201"),
    ("岩戸", "横須賀市", "14201"),
    ("衣笠", "横須賀市", "14201"),
    ("大矢部", "横須賀市", "14201"),
    ("小矢部", "横須賀市", "14201"),
    ("森崎", "横須賀市", "14201"),
    ("金谷", "横須賀市", "14201"),
    ("平作", "横須賀市", "14201"),
    ("野比", "横須賀市", "14201"),
    ("長沢", "横須賀市", "14201"),
    ("津久井", "横須賀市", "14201"),
    ("長井", "横須賀市", "14201"),
    ("長坂", "横須賀市", "14201"),
    ("佐島", "横須賀市", "14201"),
    ("芦名", "横須賀市", "14201"),
    ("蘆名", "横須賀市", "14201"),
    ("秋谷", "横須賀市", "14201"),
    ("一色", "葉山町", "14301"),
    ("堀内", "葉山町", "14301"),
    ("長柄", "葉山町", "14301"),
    ("桜山", "逗子市", "14208"),
    ("沼間", "逗子市", "14208"),
    ("逗子", "逗子市", "14208"),
    ("池子", "逗子市", "14208"),
    ("山根", "逗子市", "14208"),
    ("久木", "逗子市", "14208"),
    ("小坪", "逗子市", "14208"),
    ("菊名", "三浦市", "14210"),
    ("金田", "三浦市", "14210"),
    ("松輪", "三浦市", "14210"),
    ("諸磯", "三浦市", "14210"),
    ("三戸", "三浦市", "14210"),
    ("和田", "三浦市", "14210"),
    ("入江", "三浦市", "14210"),
    ("六合", "三浦市", "14210"),
    ("三崎", "三浦市", "14210"),
    ("林", "横須賀市", "14201"),
    ("武", "横須賀市", "14201"),
]
VILLAGE_MUNI.sort(key=lambda row: len(row[0]), reverse=True)

ARCHIVES_URL = (
    "https://wwwy4.musetheque.jp/kanagawa_archives/detail"
    "?cls=04_collect_arch_folder&pkey=1199400735"
)
WIKIDATA = "https://query.wikidata.org/sparql"
OVERPASS = "https://overpass-api.de/api/interpreter"
GSI_TERMS = "https://www.gsi.go.jp/kikakuchousei/kikakuchousei40182.html"
ANNO_URL = "https://cyberjapandata.gsi.go.jp/xyz/experimental_anno/15/{x}/{y}.geojson"
# 地理院タイル一覧（2026-11-10にHTMLを取得）の「1961年～1969年」。
AERIAL_URL = "https://cyberjapandata.gsi.go.jp/xyz/ort_old10/{z}/{x}/{y}.png"
NDL_MANIFEST = (
    DRIVE / "data/literature/historical_documents"
    / "Shinpen_Sagami_Fudokiko_Vol5_IIIF_manifest.json"
)

TO_6677 = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:6677", always_xy=True)
TO_WGS = pyproj.Transformer.from_crs("EPSG:6677", "EPSG:4326", always_xy=True)
# 神奈川県のおおよその範囲。小数第2位までの粗い値で、地点は特定しない。
KANAGAWA_COARSE_LAT = (35.10, 35.70)
KANAGAWA_COARSE_LON = (138.90, 139.80)


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def stem_of(value) -> str:
    if not isinstance(value, str) or not value:
        return ""
    text = unicodedata.normalize("NFKC", value)
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"（[^）]*）", "", text)
    text = re.sub(r"\([^)]*\)", "", text)
    return re.sub(r"(駅|跡|小学校|中学校|高等学校|高校|大学|病院|信号所|信号場|仮乗降場)$", "", text)


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
    if dest.exists() and dest.stat().st_size > 0:
        return dest.read_bytes()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"User-Agent": UA, "Accept": accept},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except Exception as exc:  # noqa: BLE001 — 失敗は未取得として残す
        dest.with_suffix(dest.suffix + ".error").write_text(
            f"{type(exc).__name__}: {exc}\n{url}\n", encoding="utf-8")
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
    for code, name, geom in zip(codes, names, geoms):
        if code not in R2_CODES or geom is None:
            continue
        polys.append(from_wkb(geom))
        meta.append((code, name))
    if not polys:
        raise SystemExit("R2 admin polygons are empty")
    return polys, meta


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
    """測地系の取り違えを、地点の緯度経度を置かずに止める。

    行政界ポリゴンを EPSG:4326 に変換し、外接を小数第2位に丸めた値が
    神奈川のおおよその範囲に収まることを確認する。軸の入れ替えや、
    度とメートルの混同は、この範囲から外れる。
    """
    xs: list[float] = []
    ys: list[float] = []
    for poly in polys:
        coords = list(_projected_coords(poly))
        if not coords:
            continue
        lons, lats = TO_WGS.transform(
            [c[0] for c in coords],
            [c[1] for c in coords],
        )
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
    """非公開CSVの点が、その行の市区町村コードへ落ちるかを見る。

    PRIVATE_CANDIDATES_CSV が無いときは呼ばない。座標はスクリプトに書かない。
    """
    if not path.is_file():
        raise SystemExit("CRS check failed: PRIVATE_CANDIDATES_CSV is not a file")
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    checked = 0
    for row in rows:
        code = (row.get("muni_code") or "").strip()
        lat_s = (row.get("lat") or "").strip()
        lon_s = (row.get("lon") or "").strip()
        if code not in R2_CODES or not lat_s or not lon_s:
            continue
        got, _name = which_muni(polys, meta, float(lon_s), float(lat_s))
        if got != code:
            cid = row.get("id") or "?"
            raise SystemExit(f"CRS check failed for {cid}: got {got}, expected {code}")
        checked += 1
    if checked == 0:
        raise SystemExit("CRS check failed: PRIVATE_CANDIDATES_CSV has no R2 coordinate rows")


def load_existing_r2() -> list[dict]:
    path = DRIVE / "data/private_findings/2026-11-05_special_R1-R4/candidates.csv"
    rows = [r for r in csv.DictReader(path.open(encoding="utf-8")) if r["id"].startswith("R2-")]
    if [r["id"] for r in rows] != ["R2-001", "R2-002", "R2-003", "R2-004"]:
        raise SystemExit("existing R2 ids changed")
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


def parse_archives(html: str) -> list[dict]:
    text = re.sub(r"<[^>]+>", " ", html)
    text = (text.replace("&nbsp;", " ").replace("\u3000", " ")
            .replace("&#12539;", "・"))
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    parts = re.split(r"(?<!\d)(\d{1,3}) 神奈川県管下相模国三浦郡", text)
    entries = []
    # parts: preamble, num, body, num, body, ...
    if len(parts) < 3:
        raise SystemExit("archives catalog did not split into entries")
    for i in range(1, len(parts), 2):
        num = int(parts[i])
        body = parts[i + 1]
        body = re.split(r"原資料・複製の区分|請求記号", body)[0]
        body = strip_officials(body).strip(" ・")
        place = body.split("・")[0].strip()
        place = re.split(r"村社|無格社|郷社|式外里社|県社", place)[0].strip()
        muni_name, muni_code, village = muni_of(place)
        shrine = shrine_name(body)
        kind = entry_kind(body)
        entries.append({
            "catalog_no": num,
            "body_redacted": body[:240],
            "place": place[:80],
            "village": village,
            "shrine": shrine,
            "muni_name": muni_name,
            "muni_code": muni_code,
            "kind": kind,
        })
    return entries


def strip_officials(body: str) -> str:
    body = re.sub(r"(祠掌|祝掌|社掌|戸長|試補佐|試補)[一-龥々〆ヶ]{1,8}", "", body)
    return body


def muni_of(place: str):
    for village, muni_name, muni_code in VILLAGE_MUNI:
        if place.startswith(village):
            return muni_name, muni_code, village
    return "", "", ""


def shrine_name(body: str) -> str:
    # 合併注記より前だけを見る。「日付天神社へ」を社名にしない。
    head = re.split(r"(明治|大正|昭和)\d+年", body)[0]
    head = re.sub(r"祭神\s*\S+", " ", head)
    headed = re.search(
        r"(?:式外里社|無格社|村社|郷社|県社)\s+"
        r"([一-龥々〆ヶァ-ヶー]{1,16}(?:神社|社|宮|権現|大神))",
        head,
    )
    if headed:
        return headed.group(1)
    names = re.findall(
        r"([一-龥々〆ヶァ-ヶー]{2,16}(?:神社|社|宮|権現|大神))",
        head,
    )
    skip = {"村社", "無格社", "郷社", "県社", "式外里社"}
    names = [name for name in names if name not in skip]
    return names[-1] if names else ""


def entry_kind(body: str) -> str:
    tail = body.strip()
    truncated = re.search(
        r"(明治|大正|昭和)\d+年\d+月\d+日[^\s。]{1,16}$", tail)
    if "合併" in body and "抹消" in body:
        return "strike"
    if "移転" in body and "合併" not in body:
        return "relocate"
    if "合併" in body and "改称" in body:
        return "rename"
    if "合併" in body:
        return "merge"
    if truncated and ("合併" not in body):
        return "truncated"
    if re.search(r"(神社|社)へ$", tail) and "合併" not in body:
        return "truncated"
    return "listed"


def classify_wikidata(types: set[str]) -> str:
    blob = " ".join(types)
    if any(k in blob for k in ("廃止市区町村", "廃止された郡", "日本の郡", "郡")) and not any(
        k in blob for k in ("駅", "神社", "寺院", "廃寺", "集落", "廃村", "灯台", "窯", "砲台")
    ):
        return "admin"
    if any(k in blob for k in ("学校", "病院", "大学", "企業", "人間", "人物")) and not any(
        k in blob for k in ("駅", "神社", "寺院", "廃寺")
    ):
        return "institution"
    if any(k in blob for k in ("神社", "神宮", "廃社")):
        return "shrine"
    if any(k in blob for k in ("寺院", "廃寺", "寺跡")):
        return "temple"
    if any(k in blob for k in ("廃村", "集落", "町・字", "大字")):
        return "settlement"
    if any(k in blob for k in ("廃道", "旧道", "街道")):
        return "road"
    if "駅" in blob or "信号場" in blob or "乗降場" in blob:
        return "station"
    if any(k in blob for k in ("灯台", "窯", "御所", "台場", "飛行場", "砲台", "要塞", "陣屋", "城跡")):
        return "facility"
    return "other"


def wikidata_query() -> dict | None:
    # P429（団体コード）の照合は空応答だったため使わない。
    # 市町のQIDは 2026-11-10 の wbsearchentities でラベルを確認した。
    query = """
    SELECT ?item ?itemLabel ?coord ?end ?typeLabel WHERE {
      VALUES ?muni { wd:Q200578 wd:Q200267 wd:Q230843 wd:Q823886 wd:Q1342807 }
      ?item wdt:P131* ?muni .
      ?item wdt:P625 ?coord .
      { ?item wdt:P576 ?end . } UNION { ?item wdt:P582 ?end . }
      OPTIONAL { ?item wdt:P31 ?type . }
      SERVICE wikibase:label { bd:serviceParam wikibase:language "ja,en". }
    }
    """
    url = WIKIDATA + "?query=" + urllib.parse.quote(query)
    for path in TMP.glob("wikidata_ended_r2*"):
        path.unlink()
    dest = TMP / "wikidata_ended_r2.json"
    raw = fetch(
        url, dest, timeout=180,
        accept="application/sparql-results+json",
    )
    if raw is None:
        time.sleep(70)
        raw = fetch(
            url, dest, timeout=180,
            accept="application/sparql-results+json",
        )
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def overpass_query(bounds: tuple[float, float, float, float]) -> dict | None:
    south, west, north, east = bounds
    query = f"""
    [out:json][timeout:90];
    (
      node["amenity"="place_of_worship"]({south},{west},{north},{east});
      way["amenity"="place_of_worship"]({south},{west},{north},{east});
      node["historic"]({south},{west},{north},{east});
      way["historic"]({south},{west},{north},{east});
      node["railway"~"^(station|halt|stop|tram_stop|abandoned|disused|razed)$"]({south},{west},{north},{east});
      way["railway"~"^(abandoned|disused|razed)$"]({south},{west},{north},{east});
      way["highway"="abandoned"]({south},{west},{north},{east});
      node["abandoned:amenity"="place_of_worship"]({south},{west},{north},{east});
      node["disused:amenity"="place_of_worship"]({south},{west},{north},{east});
    );
    out tags center;
    """
    raw = fetch(OVERPASS, TMP / "overpass_r2.json", data=query.encode("utf-8"), timeout=180)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def element_point(el: dict):
    if "lat" in el and "lon" in el:
        return float(el["lon"]), float(el["lat"])
    center = el.get("center") or {}
    if "lat" in center and "lon" in center:
        return float(center["lon"]), float(center["lat"])
    return None


def rows_of(table):
    return [dict(zip(table["columns"], row)) for row in table["data"]]


def landscape_inventory(results: dict) -> dict:
    """既存集計の棚卸し。セルの空間分布は作らない。"""
    rl = results["aggregates"]["region_landscape"]
    by_key = {
        tuple(idx): dict(zip(rl["columns"], row))
        for idx, row in zip(rl["index"], rl["data"])
    }
    region = {
        name: dict(zip(results["aggregates"]["region"]["columns"], row))
        for name, row in zip(results["aggregates"]["region"]["index"],
                             results["aggregates"]["region"]["data"])
    }
    r2 = region["R2_miura"]
    cell_km2 = r2["land_km2"] / r2["n_cells"]
    urban = by_key[("R2_miura", "urban")]
    gain_cells = urban["building_gain_km2"] / cell_km2
    loss_cells = urban["building_loss_km2"] / cell_km2
    forests = []
    for (reg, kind), row in by_key.items():
        if kind != "forest_dominant":
            continue
        forests.append({
            "region": reg,
            "n_cells": int(round(row["land_km2"] / cell_km2)) if reg == "R2_miura" else None,
            "land_km2": round(row["land_km2"], 4),
            "changed_km2": round(row["changed_km2"], 4),
            "forest_net_change_km2": round(row["forest_net_change_km2"], 4),
            "rate_usable": row["land_km2"] >= 0.5,
        })
    # R2のセル数は週2の32と突き合わせる。他地域のセル数は分母が違うので出さない。
    r2_forest = by_key[("R2_miura", "forest_dominant")]
    r2_forest_cells = r2_forest["land_km2"] / cell_km2
    cov = {
        name: dict(zip(results["coverage"]["by_region"]["columns"], row))
        for name, row in zip(results["coverage"]["by_region"]["index"],
                             results["coverage"]["by_region"]["data"])
    }["R2_miura"]
    return {
        "cell_km2": cell_km2,
        "r2_land_km2": r2["land_km2"],
        "r2_n_cells": r2["n_cells"],
        "r2_coverage": cov["coverage"],
        "r2_scope": cov["scope"],
        "urban_land_km2": round(urban["land_km2"], 4),
        "urban_building_gain_km2": round(urban["building_gain_km2"], 4),
        "urban_building_loss_km2": round(urban["building_loss_km2"], 4),
        "urban_building_gain_cells": round(gain_cells, 2),
        "urban_building_loss_cells": round(loss_cells, 2),
        "urban_spatial_bias_in_aggregate": False,
        "r2_forest_land_km2": round(r2_forest["land_km2"], 4),
        "r2_forest_changed_km2": round(r2_forest["changed_km2"], 4),
        "r2_forest_cells": round(r2_forest_cells, 2),
        "forest_dominant_by_region": forests,
        "formula": (
            "gain_cells = region_landscape[R2, urban].building_gain_km2 "
            "/ (region[R2].land_km2 / region[R2].n_cells). "
            "類型内の増加セルと減少セルの位置の偏りは、この集計の列に無い。"
        ),
    }


def baseline_rows() -> list[dict]:
    files = [
        ("2026-11-05_special", DRIVE / "data/private_findings/2026-11-05_special_R1-R4/candidates.csv"),
        ("2026-11-06_R5", DRIVE / "data/private_findings/2026-11-06_R5/candidates.csv"),
        ("2026-11-07_R6", DRIVE / "data/private_findings/2026-11-07_R6/candidates.csv"),
        ("2026-11-08_R7", DRIVE / "data/private_findings/2026-11-08_R7/candidates.csv"),
        ("2026-11-09_R1", DRIVE / "data/private_findings/2026-11-09_R1/candidates.csv"),
    ]
    rows = []
    for label, path in files:
        with path.open(encoding="utf-8") as fh:
            for rec in csv.DictReader(fh):
                if not rec.get("id"):
                    continue
                status = "既存"
                if label == "2026-11-09_R1" and rec.get("outcome") == "維持":
                    status = "再検証"
                rows.append({
                    "id": rec["id"],
                    "region": rec.get("region") or rec["id"].split("-")[0],
                    "muni_name": rec.get("muni_name", ""),
                    "category": rec.get("category", ""),
                    "confidence": rec.get("confidence", ""),
                    "status": status,
                    "source_file": label,
                    "three_axis": "未評価",
                    "name": rec.get("name", ""),
                    "lat": rec.get("lat", ""),
                    "lon": rec.get("lon", ""),
                })
    return rows


def dedupe_baseline(rows: list[dict]) -> list[dict]:
    """R1は2026-11-09の再検証を残し、特別回の同じIDは履歴側に数えない。"""
    later = {r["id"] for r in rows if r["source_file"] == "2026-11-09_R1"}
    kept = []
    for row in rows:
        if row["source_file"] == "2026-11-05_special" and row["id"] in later:
            continue
        kept.append(row)
    return kept


def fudoki_note() -> dict:
    manifest = json.loads(NDL_MANIFEST.read_text(encoding="utf-8"))
    labels = [s.get("label") for s in manifest.get("structures", [])]
    miura = [lab for lab in labels if isinstance(lab, str) and "三浦郡" in lab]
    return {
        "manifest_id": manifest.get("@id"),
        "license_field": manifest.get("license"),
        "access": "PDM",
        "miura_structure_labels": miura,
        "page_images_fetched": False,
        "transcribed": False,
    }


def nearest(records, pt: Point, meters: float, stem: str, predicate=None):
    hits = []
    for rec in records:
        if predicate and not predicate(rec):
            continue
        if not rec.get("stem") or rec["stem"] != stem:
            continue
        if pt.distance(rec["geometry"]) <= meters:
            hits.append(rec)
    return hits


def main() -> None:
    TMP.mkdir(parents=True, exist_ok=True)
    OUT_PRIV.mkdir(parents=True, exist_ok=True)
    elapsed = (date(2026, 11, 10) - date(2026, 10, 26)).days
    if elapsed != 15 or elapsed % 7 != 1 or elapsed // 7 + 1 != 3:
        raise SystemExit(f"rotation mismatch: elapsed={elapsed}")

    provenance = []

    def add_prov(url: str, path: Path | None, license_note: str, era: str, note: str, raw: bytes | None):
        provenance.append({
            "url": url,
            "path": "" if path is None else str(path.relative_to(TMP)) if path.is_relative_to(TMP) else path.name,
            "retrieved": RETRIEVED,
            "license": license_note,
            "era": era,
            "sha256": sha256_bytes(raw) if raw else "",
            "bytes": 0 if raw is None else len(raw),
            "note": note,
            "fetched": raw is not None,
        })

    archives_raw = fetch(ARCHIVES_URL, TMP / "archives_miura_shrine_register.html", timeout=60)
    add_prov(
        ARCHIVES_URL, TMP / "archives_miura_shrine_register.html",
        "神奈川県立公文書館の収蔵資料検索。ページにオープンライセンスの明示は確認できない。目録の概要文を解析し、再配布しない。",
        "明治12年〜大正9年（概要文に昭和40年の注記が1件）",
        "明治12年神社明細帳〔複写資料〕三浦郡。資料ID 1199400735。請求記号 郡-4-15。マイクロフィルム Miuragunyakusyo-10 の画像は未取得。",
        archives_raw,
    )
    if not archives_raw:
        raise SystemExit("archives catalog was not fetched")
    entries = parse_archives(archives_raw.decode("utf-8", errors="replace"))
    kinds = Counter(e["kind"] for e in entries)
    if kinds["strike"] != 15 or kinds["merge"] + kinds["rename"] < 1:
        raise SystemExit(f"catalog parse unexpected: {kinds}")

    polys, meta = load_admin()
    # 既知点の緯度経度はリポジトリに置かない。測地系の取り違えは、行政界を
    # EPSG:4326 に直した外接が神奈川のおおよその範囲に収まるかで止める。
    # PRIVATE_CANDIDATES_CSV があるときだけ、その非公開CSVの点も市区町村コードと照合する。
    assert_admin_crs(polys)
    private_csv = os.environ.get("PRIVATE_CANDIDATES_CSV", "").strip()
    if private_csv:
        check_private_candidates(polys, meta, Path(private_csv))

    p32 = load_p32()
    minx = min(p.bounds[0] for p in polys)
    miny = min(p.bounds[1] for p in polys)
    maxx = max(p.bounds[2] for p in polys)
    maxy = max(p.bounds[3] for p in polys)
    to_wgs = pyproj.Transformer.from_crs("EPSG:6677", "EPSG:4326", always_xy=True)
    west, south = to_wgs.transform(minx, miny)
    east, north = to_wgs.transform(maxx, maxy)
    # 行政界の外接に0.01度。半島の外の地物は後でポリゴンではじく。
    bounds = (south - 0.01, west - 0.01, north + 0.01, east + 0.01)
    overpass = overpass_query(bounds)
    add_prov(
        OVERPASS, TMP / "overpass_r2.json",
        "ODbL（OpenStreetMap）。Overpass APIの抽出。",
        "取得日時点の現行OSM",
        "R2の外接矩形。礼拝・historic・鉄道・abandoned highway。失敗なら未確認。",
        None if overpass is None else (TMP / "overpass_r2.json").read_bytes(),
    )
    wd = wikidata_query()
    wd_path = next(TMP.glob("wikidata_ended_r2*.json"), None)
    add_prov(
        WIKIDATA, wd_path,
        "CC0",
        "終了日（P576またはP582）のある項目",
        "5市町のQID（wbsearchentitiesで確認）にP131で含まれ、座標と終了日がある項目。429のときは未取得であり、0件ではない。",
        None if wd is None or wd_path is None else wd_path.read_bytes(),
    )

    osm_records = []
    osm_seen = Counter()
    if overpass:
        for el in overpass.get("elements", []):
            tags = el.get("tags") or {}
            loc = element_point(el)
            if not loc:
                continue
            lon, lat = loc
            code, muni_name = which_muni(polys, meta, lon, lat)
            if code is None:
                osm_seen["outside_r2"] += 1
                continue
            name = tags.get("name") or tags.get("name:ja") or ""
            kind = "worship" if tags.get("amenity") == "place_of_worship" or tags.get("abandoned:amenity") == "place_of_worship" or tags.get("disused:amenity") == "place_of_worship" else ""
            if tags.get("historic"):
                kind = kind or "historic"
            if tags.get("railway"):
                kind = kind or "railway"
            if tags.get("highway") == "abandoned":
                kind = kind or "abandoned_road"
            if tags.get("historic") == "ruins":
                osm_seen["in_r2_historic_ruins"] += 1
            if tags.get("abandoned:amenity") == "place_of_worship" or tags.get("disused:amenity") == "place_of_worship":
                osm_seen["in_r2_worship_abandoned_tag"] += 1
            osm_seen[f"in_r2_{kind or 'other'}"] += 1
            osm_seen[f"muni_{muni_name}"] += 1
            osm_records.append({
                "stem": stem_of(name),
                "name": name,
                "geometry": project_point(lon, lat),
                "railway": tags.get("railway") or "",
                "historic": tags.get("historic") or "",
                "kind": kind,
                "muni_name": muni_name,
            })

    # 注記と空中写真は、非公開CSVに座標がある既存4件だけ。新規の合併項は座標が無い。
    # 座標はスクリプトに書かない。
    existing = load_existing_r2()
    anno_by_id = {
        row["id"]: {"unverified": False, "hit": False, "fetched": 0, "failed": 0}
        for row in existing
    }
    aerial_by_id = {row["id"]: {"fetched": False, "http_404": False} for row in existing}
    anno_features = []
    for row in existing:
        cid = row["id"]
        lat_s = (row.get("lat") or "").strip()
        lon_s = (row.get("lon") or "").strip()
        if not lat_s or not lon_s:
            anno_by_id[cid]["unverified"] = True
            continue
        lat, lon = float(lat_s), float(lon_s)
        for x, y in sorted(tiles_for_buffer(lon, lat)):
            dest = TMP / f"anno_15_{x}_{y}.geojson"
            raw = fetch(ANNO_URL.format(x=x, y=y), dest, timeout=30)
            time.sleep(0.05)
            if raw is None:
                anno_by_id[cid]["failed"] += 1
                anno_by_id[cid]["unverified"] = True
                continue
            anno_by_id[cid]["fetched"] += 1
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                anno_by_id[cid]["unverified"] = True
                continue
            for feat in payload.get("features", []):
                props = feat.get("properties") or {}
                geom = feat.get("geometry")
                if not geom:
                    continue
                gj = shape(geom)
                px, py = TO_6677.transform(gj.x, gj.y)
                anno_features.append({
                    "stem": stem_of(props.get("knj") or ""),
                    "knj": props.get("knj") or "",
                    "ftCode": str(props.get("ftCode") or ""),
                    "annoCtg": props.get("annoCtg") or "",
                    "geometry": Point(px, py),
                })
        zx, zy = tile_xy(lon, lat, 17)
        adest = TMP / f"ort_old10_17_{zx}_{zy}.png"
        araw = fetch(AERIAL_URL.format(z=17, x=zx, y=zy), adest, timeout=30)
        aerial_by_id[cid]["fetched"] = araw is not None and len(araw) > 100
        err = adest.with_suffix(adest.suffix + ".error")
        if err.exists() and "404" in err.read_text(encoding="utf-8"):
            aerial_by_id[cid]["http_404"] = True

    anno_blobs = b"".join(p.read_bytes() for p in sorted(TMP.glob("anno_15_*.geojson")))
    aerial_blobs = b"".join(p.read_bytes() for p in sorted(TMP.glob("ort_old10_17_*.png")))
    add_prov(
        ANNO_URL, None, "国土地理院コンテンツ利用規約",
        "現行の注記（experimental_anno、ズーム15）",
        f"既存4候補の200mが交わるタイル。取得{len(list(TMP.glob('anno_15_*.geojson')))}枚。404は未確認。",
        anno_blobs or None,
    )
    add_prov(
        AERIAL_URL, None, "国土地理院コンテンツ利用規約。一覧HTMLの1961年～1969年。",
        "1961年～1969年の空中写真",
        "既存4候補の点を含むズーム17タイル各1枚。旧版地形図の記号ではない。判読して遺構ありとはしない。",
        aerial_blobs or None,
    )

    def anno_hit(pt: Point, stem: str) -> bool:
        for rec in anno_features:
            if rec["ftCode"] in PLACE_FT or str(rec["annoCtg"]).startswith("居住地名") or str(rec["annoCtg"]).startswith("行政区画"):
                continue
            if rec["stem"] and rec["stem"] == stem and pt.distance(rec["geometry"]) <= ANNO_MATCH_M:
                return True
        return False

    candidates = []
    for row in existing:
        lon, lat = float(row["lon"]), float(row["lat"])
        pt = project_point(lon, lat)
        stem = stem_of(row["name"])
        p32_hits = nearest(p32, pt, OSM_MATCH_M, stem)
        osm_hits = nearest(osm_records, pt, OSM_MATCH_M, stem) if overpass else []
        historic_hits = [rec for rec in osm_hits if rec.get("historic")]
        live_station = []
        if row["category"] == "station" and overpass:
            live_station = nearest(
                osm_records, pt, STATION_LIVE_M, stem,
                predicate=lambda rec: rec.get("railway") in {"station", "halt", "stop", "tram_stop"},
            )
        anno = anno_by_id[row["id"]]
        hit_anno = anno_hit(pt, stem) if not anno["unverified"] else False
        if live_station:
            status = "棄却"
            reason = "現行OSMの旅客駅と同じ語幹が1km以内にあり、廃駅との取り違えとして棄却する。"
        else:
            status = "再検証"
            reason = "2026-11-05の終了日は維持する。現行資料に同じ語幹があっても、終了の記録は消さない。旧版地形図の記号は未照合なので高にしない。"
        remains = "未確認"
        if p32_hits:
            remains = "中"
            reason += " P32に同じ語幹が400m以内にある。指定の残存であり、現物の確認ではない。"
        if historic_hits and status != "棄却":
            remains = "中"
            reason += " 現行OSMのhistoric地物に同じ語幹が400m以内にある。地図上の史跡タグであり、現地の遺構確認ではない。"
        elif osm_hits and status != "棄却":
            reason += " 現行OSMに同じ語幹が400m以内にある。名称の残存であり、廃止の否定ではない。"
        if hit_anno:
            reason += " 取得できた現行注記に同じ語幹がある。注記は旧版の記号ではない。"
        if anno["unverified"]:
            reason += " 注記タイルの一部は404で、その範囲は未確認。"
        if not aerial_by_id[row["id"]]["fetched"]:
            reason += " 1961–1969年の空中写真タイルは未取得。"
        else:
            reason += " 空中写真タイルは取得したが、記号判読はしていないので遺構の根拠にしない。"
        axis_abolished = "中"
        candidates.append({
            "id": row["id"],
            "status": status,
            "category": "駅" if row["category"] == "station" else "施設",
            "muni_code": row["muni_code"],
            "muni_name": row["muni_name"],
            "name": row["name"],
            "lat": row["lat"],
            "lon": row["lon"],
            "axis_existed": "強",
            "axis_abolished": "なし" if status == "棄却" else axis_abolished,
            "axis_remains": "未確認" if status == "棄却" else remains,
            "confidence": row["confidence"] if status != "棄却" else "棄却",
            "source": row["evidence_present"],
            "retrieved": "2026-11-05; 再検証の現行資料は2026-11-10",
            "license": "Wikidata CC0。OSMはODbL。P32は国土数値情報。注記と空中写真は国土地理院コンテンツ利用規約。",
            "era": "終了日は2026-11-05取得のWikidata。現行照合は2026-11-10。",
            "verification": reason,
            "catalog_no": "",
            "qid": row["source_ids"],
        })

    next_id = 5
    adopted_catalog = []
    for entry in sorted(entries, key=lambda e: e["catalog_no"]):
        if entry["kind"] not in {"strike", "merge", "rename", "relocate"}:
            continue
        if not entry["muni_code"] or not entry["shrine"]:
            raise SystemExit(
                f"catalog {entry['catalog_no']} has no municipality or shrine name")
        cid = f"R2-{next_id:03d}"
        next_id += 1
        if entry["kind"] == "relocate":
            status = "棄却"
            abolished = "なし"
            category = "神社"
            conf = ""
            verification = (
                f"公文書館目録の項番{entry['catalog_no']}は移転新築と抹消であり、"
                "廃止・消失の記録ではない。座標は目録に無いので作っていない。"
            )
        elif entry["kind"] == "rename":
            status = "新規"
            abolished = "中"
            category = "神社"
            conf = "低"
            verification = (
                f"項番{entry['catalog_no']}は合併のうえ改称と書かれている。"
                "独立の社号は終わるが、祭祀は改称先へ続く、と目録の概要文が書く。"
                "明細帳の画像は未取得。復祀は概要文の時期の外なので未確認。座標は作っていない。"
            )
        elif entry["kind"] == "strike":
            status = "新規"
            abolished = "強"
            category = "神社"
            conf = "低"
            verification = (
                f"項番{entry['catalog_no']}に合併と抹消がある。"
                "総合確度は低。根拠は目録の概要文で、明細帳の画像ではなく、座標も無い。"
                "戦後の復祀はこの概要文の範囲外で未確認。"
            )
        else:
            status = "新規"
            abolished = "中"
            category = "神社"
            conf = "低"
            verification = (
                f"項番{entry['catalog_no']}に合併とある。抹消の語は無い。"
                "明細帳の画像は未取得。座標は作っていない。復祀は未確認。"
            )
        row = {
            "id": cid,
            "status": status,
            "category": category,
            "muni_code": entry["muni_code"],
            "muni_name": entry["muni_name"],
            "name": entry["shrine"],
            "lat": "",
            "lon": "",
            "axis_existed": "強",
            "axis_abolished": abolished,
            "axis_remains": "未確認",
            "confidence": conf,
            "source": "神奈川県立公文書館 明治12年神社明細帳〔複写資料〕三浦郡（資料ID 1199400735）の資料概要。",
            "retrieved": RETRIEVED,
            "license": "公文書館サイトにオープンライセンスの明示は確認できない。目録概要の解析。画像は未取得。",
            "era": "登録は明治12年。合併・移転の注記は概要文に書かれた年月。",
            "verification": verification,
            "catalog_no": entry["catalog_no"],
            "qid": "",
            "kind": entry["kind"],
            "village": entry["village"],
        }
        candidates.append(row)
        adopted_catalog.append(row)

    # Wikidataで既存4件以外の、神社・寺院・集落・廃道・施設・駅。
    wd_counts = Counter()
    wd_new = []
    if wd:
        items: dict[str, dict] = {}
        for binding in wd["results"]["bindings"]:
            iid = binding["item"]["value"].rsplit("/", 1)[-1]
            slot = items.setdefault(iid, {
                "id": iid,
                "label": binding.get("itemLabel", {}).get("value", ""),
                "end": (binding.get("end", {}).get("value") or "")[:10],
                "coord": binding.get("coord", {}).get("value", ""),
                "muni": binding.get("muniLabel", {}).get("value", ""),
                "code": binding.get("code", {}).get("value", ""),
                "types": set(),
            })
            if "typeLabel" in binding:
                slot["types"].add(binding["typeLabel"]["value"])
        for item in sorted(items.values(), key=lambda rec: rec["id"]):
            if item["id"] in EXISTING_Q:
                wd_counts["existing_r2"] += 1
                continue
            group = classify_wikidata(item["types"])
            wd_counts[group] += 1
            if group in {"admin", "institution", "other"}:
                continue
            coord = item["coord"]
            if not coord.startswith("Point("):
                wd_counts["no_point"] += 1
                continue
            lon_s, lat_s = coord[len("Point("):-1].split()
            lon, lat = float(lon_s), float(lat_s)
            code, muni_name = which_muni(polys, meta, lon, lat)
            if code is None:
                wd_counts["outside_polygon"] += 1
                continue
            stem = stem_of(item["label"])
            pt = project_point(lon, lat)
            live = nearest(
                osm_records, pt, STATION_LIVE_M, stem,
                predicate=lambda rec: rec.get("railway") in {"station", "halt", "stop", "tram_stop"},
            ) if group == "station" and overpass else []
            cid = f"R2-{next_id:03d}"
            next_id += 1
            if live:
                status = "棄却"
                abolished = "なし"
                conf = ""
                verification = "Wikidataの終了日があるが、現行OSMの旅客駅と同じ語幹が1km以内にあり取り違えとして棄却する。"
            else:
                status = "新規"
                abolished = "中"
                conf = "中" if group != "shrine" else "低"
                verification = (
                    "Wikidataの終了日と座標。旧版地形図は未照合なので高にしない。"
                    "OSMに同じ語幹があっても終了日は消さない。"
                )
                if group == "shrine":
                    conf = "低"
                    verification += " 神社は終了日だけでは遺構を確認できない。"
            cat = {"shrine": "神社", "temple": "寺院", "settlement": "集落",
                   "road": "廃道", "station": "駅", "facility": "施設"}[group]
            row = {
                "id": cid,
                "status": status,
                "category": cat,
                "muni_code": code,
                "muni_name": muni_name,
                "name": item["label"],
                "lat": f"{lat:.7f}",
                "lon": f"{lon:.7f}",
                "axis_existed": "強",
                "axis_abolished": abolished,
                "axis_remains": "未確認",
                "confidence": conf,
                "source": f"Wikidata {item['id']}。型: {'、'.join(sorted(item['types']))}。終了日: {item['end']}。",
                "retrieved": RETRIEVED,
                "license": "CC0",
                "era": item["end"],
                "verification": verification,
                "catalog_no": "",
                "qid": item["id"],
            }
            # OSM同語幹は注記だけ。
            if overpass and nearest(osm_records, pt, OSM_MATCH_M, stem) and status != "棄却":
                row["verification"] += " 現行OSMに同じ語幹が400m以内にある。"
            candidates.append(row)
            wd_new.append(row)
    else:
        wd_counts["query_failed"] = 1

    # 公開JSONに名称と座標が混ざっていないことを確認してから書く。
    public_candidates = []
    for row in candidates:
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

    results = json.loads((ROOT / "reports/phase1c2_results.json").read_text(encoding="utf-8"))
    land = landscape_inventory(results)
    base = dedupe_baseline(baseline_rows())
    base_summary = {
        "unique_ids": len(base),
        "by_region": dict(Counter(r["region"] if r["region"] in {"R1", "R2", "R3", "R4", "R5", "R6", "R7"} else r["id"].split("-")[0] for r in base)),
        "by_category": dict(Counter(r["category"] for r in base)),
        "by_confidence": dict(Counter(r["confidence"] for r in base)),
        "by_status": dict(Counter(r["status"] for r in base)),
        "three_axis": "未評価",
        "shrine_count": sum(1 for r in base if "社" in r["category"] or r["category"] == "shrine"),
        "rejected_ids": sum(1 for r in base if r["status"] == "棄却"),
        "r5_rows": sum(1 for r in base if r["id"].startswith("R5-")),
        "r6_rows": sum(1 for r in base if r["id"].startswith("R6-")),
    }
    # region field on special file is R1 etc. R7 file has no region. Normalize.
    region_counts = Counter()
    for r in base:
        region_counts[r["id"].split("-")[0]] += 1
    base_summary["by_region"] = dict(region_counts)

    truncated = [e["catalog_no"] for e in entries if e["kind"] == "truncated"]
    listed = kinds["listed"]
    fudoki = fudoki_note()

    public = {
        "date": RETRIEVED,
        "region": "R2",
        "week": 3,
        "elapsed_days": 15,
        "rotation": "15 mod 7 = 1, floor(15/7)+1 = 3",
        "municipalities": ["横須賀市", "鎌倉市", "逗子市", "三浦市", "葉山町"],
        "archives": {
            "entries_parsed": len(entries),
            "kinds": dict(kinds),
            "truncated_catalog_nos": truncated,
            "register_images_fetched": False,
            "new_from_catalog": sum(1 for r in adopted_catalog if r["status"] == "新規"),
            "rejected_from_catalog": sum(1 for r in adopted_catalog if r["status"] == "棄却"),
        },
        "candidates": public_candidates,
        "counts": {
            "reverified": sum(1 for r in candidates if r["status"] == "再検証"),
            "new": sum(1 for r in candidates if r["status"] == "新規"),
            "rejected": sum(1 for r in candidates if r["status"] == "棄却"),
            "by_muni_status": {},
            "by_category_status": {},
            "by_axis_existed": dict(Counter(r["axis_existed"] for r in candidates if r["status"] != "棄却")),
            "by_axis_abolished": dict(Counter(r["axis_abolished"] for r in candidates if r["status"] != "棄却")),
            "by_axis_remains": dict(Counter(r["axis_remains"] for r in candidates if r["status"] != "棄却")),
            "confidence_new": dict(Counter(r["confidence"] for r in candidates if r["status"] == "新規")),
        },
        "osm": {
            "fetched": overpass is not None,
            "counts": dict(osm_seen),
            "adopted_from_osm_tag_alone": 0,
        },
        "wikidata": {
            "fetched": wd is not None,
            "counts": dict(wd_counts),
            "new_ids": [r["id"] for r in wd_new],
        },
        "annotation": anno_by_id,
        "aerial_1961_1969": aerial_by_id,
        "old_topo_tiles_fetched": False,
        "fudoki": {
            "manifest_read": True,
            "miura_volumes": fudoki["miura_structure_labels"],
            "page_images_fetched": False,
            "transcribed": False,
            "used_as_existence_evidence": False,
        },
        "not_adopted_without_id": {
            "catalog_listed_without_merger_language": listed,
            "catalog_truncated": len(truncated),
            "osm_tag_alone": "IDを付けていない。件数は osm.counts。",
            "modern_abandoned_housing": "検索で見た住宅開発の中止地は、消滅集落にしない。ページは保存していない。",
            "personal_blogs": "検索結果の抜粋のみ。全文は未取得。採用の根拠にしていない。",
        },
        "landuse_inventory": land,
        "baseline": base_summary,
        "high_confidence": 0,
    }
    pair_counts = Counter((r["muni_name"], r["status"]) for r in candidates)
    cat_counts = Counter((r["category"], r["status"]) for r in candidates)
    public["counts"]["by_muni_status"] = {f"{a}|{b}": n for (a, b), n in sorted(pair_counts.items())}
    public["counts"]["by_category_status"] = {f"{a}|{b}": n for (a, b), n in sorted(cat_counts.items())}

    blob = json.dumps(public, ensure_ascii=False)
    for row in candidates:
        if row["name"] and row["name"] in blob:
            raise SystemExit(f"name leaked into public json: {row['id']}")
        if row.get("village") and row["village"] in blob:
            raise SystemExit(f"village leaked: {row['id']}")
    PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC.write_text(json.dumps(public, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    fields = ["id", "status", "category", "muni_code", "muni_name", "name", "lat", "lon",
              "axis_existed", "axis_abolished", "axis_remains", "confidence",
              "source", "retrieved", "license", "era", "verification", "catalog_no", "qid"]
    with (OUT_PRIV / "candidates.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(candidates)

    review_fields = ["batch", "id", "region", "muni_name", "category", "confidence", "status",
                     "three_axis", "axis_existed", "axis_abolished", "axis_remains",
                     "source_file", "name", "lat", "lon"]
    with (OUT_PRIV / "all_candidates_reviewed.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=review_fields, extrasaction="ignore")
        writer.writeheader()
        for row in base:
            writer.writerow({
                "batch": "baseline",
                "region": row["id"].split("-")[0],
                "three_axis": "未評価",
                "axis_existed": "",
                "axis_abolished": "",
                "axis_remains": "",
                **row,
            })
        for row in candidates:
            writer.writerow({
                "batch": "2026-11-10",
                "region": "R2",
                "three_axis": "評価済み",
                "source_file": "2026-11-10_R2",
                **row,
            })

    lines = ["# 非公開メモ 2026-11-10 R2", "",
             "公開レポートに出さない名称と座標をここへ書く。原本の台帳は変更していない。", ""]
    lines.append("## 取得")
    for rec in provenance:
        lines.append(f"- fetched={rec['fetched']} bytes={rec['bytes']} era={rec['era']} {rec['note']}")
    lines.append("")
    lines.append("## 候補")
    for row in candidates:
        lines.append(
            f"### {row['id']} {row['status']} {row['muni_name']} {row['category']} {row['name']}"
        )
        lines.append(
            f"- 3軸: 存在{row['axis_existed']} / 廃止{row['axis_abolished']} / 遺構{row['axis_remains']} / 総合{row['confidence'] or '棄却'}"
        )
        if row["lat"]:
            lines.append(f"- 座標: {row['lat']}, {row['lon']}")
        else:
            lines.append("- 座標: なし（ジオコーディングしていない）")
        if row.get("village"):
            lines.append(f"- 旧村: {row['village']} 項番: {row['catalog_no']} 区分: {row.get('kind', '')}")
        lines.append(f"- 検証: {row['verification']}")
        lines.append("")
    lines.append("## 項番が接触して採用しなかったもの")
    lines.append(", ".join(str(n) for n in truncated) or "(なし)")
    lines.append("")
    lines.append("風土記稿の本文画像は取得していない。存在の根拠には使っていない。")
    (OUT_PRIV / "findings.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    (TMP / "provenance_supplemental.jsonl").write_text(
        "".join(json.dumps(rec, ensure_ascii=False) + "\n" for rec in provenance),
        encoding="utf-8",
    )
    print(json.dumps({
        "candidates": len(candidates),
        "new": public["counts"]["new"],
        "rejected": public["counts"]["rejected"],
        "reverified": public["counts"]["reverified"],
        "kinds": dict(kinds),
        "truncated": truncated,
        "by_muni": public["counts"]["by_muni_status"],
        "by_cat": public["counts"]["by_category_status"],
        "axes_abolished": public["counts"]["by_axis_abolished"],
        "axes_remains": public["counts"]["by_axis_remains"],
        "wikidata": public["wikidata"],
        "osm_fetched": overpass is not None,
        "osm_counts": {k: v for k, v in osm_seen.items() if not str(k).startswith("muni_")},
        "anno": anno_by_id,
        "aerial": aerial_by_id,
        "land_gain_cells": land["urban_building_gain_cells"],
        "land_loss_cells": land["urban_building_loss_cells"],
        "forest_cells": land["r2_forest_cells"],
        "forest_changed": land["r2_forest_changed_km2"],
        "baseline": base_summary,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
