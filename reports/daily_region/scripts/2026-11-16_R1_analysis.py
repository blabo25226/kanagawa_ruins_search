"""R1（横浜・川崎）4週目。2026-11-16。

主目的は、既存候補の再検証と、震災誌の焼失・崩壊一覧の現存照合である。
土地利用は 2026-11-09 の申し送りがまだ成り立つかの確認に限る。

公開 JSON には件数、市区町村、候補 ID、3軸、確度、リード ID、検証コードだけを書く。
名称と緯度経度は、環境変数で渡した非公開ファイルから読み、
/opt/cursor/artifacts/kanagawa_private/2026-11-16_R1/ に出す。
スクリプトには地点の緯度経度も候補名も書かない。

評価は件数を数える前に固定した。

- 過去に存在した根拠、廃止・消失の根拠、物理的遺構が残る可能性は別の欄にする。
- 現行の地図に名称が無いこと、森林化、神社庁の検索が0件であることは、消失の根拠にしない。
- 座標は、入力 CSV に列があるときだけ読む。字名や住所からは点を作らない。
- 総合確度の高は、旧版地形図の記号を見ていない限り付けない。今日は付けない。
- 焼失・崩壊・全潰・半潰は、廃社ではない。
- 現存、再建、遷座先、合祀先は廃社にしない。旧地は状態変化にする。
- 投稿と寄稿は二次である。画像は保存しない。画像から位置を推定しない。
- 投稿者名やプロフィールの地名は、所在のヒットにしない。
- 旧版地形図の交付 TIFF は取得していない。空中写真は地形図記号ではない。
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pyarrow.parquet as pq
import pyproj
from shapely import wkb

ROOT = Path(__file__).resolve().parents[3]
JUDGMENTS = Path(os.environ["PRIVATE_JUDGMENTS_CSV"])
PRIOR = Path(os.environ["PRIVATE_PRIOR_CANDIDATES"])
SPECIAL = Path(os.environ["PRIVATE_SPECIAL_CANDIDATES"])
CELLS = Path(os.environ["CELLS_PARQUET"])
AGG = Path(os.environ["AGG_REGION_CSV"])
TEXT_DIR = Path(os.environ["TEXT_SOURCE_DIR"])
TEXT_MANIFEST = Path(os.environ["TEXT_MANIFEST_CSV"])
SUPP = Path(os.environ["SUPP_DIR"])
OUT_PRIV = Path("/opt/cursor/artifacts/kanagawa_private/2026-11-16_R1")
PUBLIC = ROOT / "reports" / "daily_region" / "data" / "2026-11-16_R1_week4_public.json"
RESULTS = ROOT / "reports" / "phase1c2_results.json"
WORK = Path(os.environ.get("R1_WORK_DIR", "/tmp/r1_20261116"))
RETRIEVED = "2026-11-16"
UA = "kanagawa-ruins-search/2026-11-16"
TOL_KM2 = 0.015
CLOSE_KM2 = 0.05
SINGLE_TYPE_SHARE = 0.50
OTHER_SHARE_MIN = 0.50
FOREST_WASTE_SHARE_MAX = 0.15
GE5_CITED = 0.096
GE5_MATCH = 0.01
COMPLEMENT_GAP = 0.10
ANNO_MATCH_M = 200.0
PLACE_FT = {"0210", "0220"}
AERIAL_CAP = 40
COORD_RE = re.compile(r"(?:3[4-6]|13[89])\.[0-9]{3,}")
ALLOWED_STATUS = {"新規", "既存", "再検証", "棄却", "負例", "状態変化", "保留"}
ALLOWED_AXIS = {"強", "中", "低", "なし", "未確認", "対象外"}
ALLOWED_CONF = {"中", "低", "負例"}
ANNO_URL = "https://cyberjapandata.gsi.go.jp/xyz/experimental_anno/15/{x}/{y}.geojson"
AERIAL_URL = "https://cyberjapandata.gsi.go.jp/xyz/ort_old10/17/{x}/{y}.png"
GSI_TERMS = "https://maps.gsi.go.jp/help/termsofuse.html"


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
    return re.sub(r"(駅|跡|信号所|信号場|旧地|旧境内|の一時遷座)$", "", text)


def tile_xy(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    n = 2**zoom
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


def fetch(url: str, dest: Path) -> tuple[bool, int]:
    if dest.exists() and dest.stat().st_size > 0:
        return True, dest.stat().st_size
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            raw = resp.read()
    except Exception as exc:
        dest.with_suffix(dest.suffix + ".error").write_text(
            f"{type(exc).__name__}: {exc}\n", encoding="utf-8"
        )
        return False, 0
    dest.write_bytes(raw)
    return True, len(raw)


def load_results() -> dict:
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    reg = {
        name: dict(zip(data["aggregates"]["region"]["columns"], row))
        for name, row in zip(data["aggregates"]["region"]["index"], data["aggregates"]["region"]["data"])
    }
    cc = data["transitions"]["component_class_share_by_region"]
    comp = {name: dict(zip(cc["columns"], row)) for name, row in zip(cc["index"], cc["data"])}
    focus = {}
    block = data["transitions"]["focus_by_region"]
    for row in block["data"]:
        rec = dict(zip(block["columns"], row))
        if rec["region"] == "R1_yokohama_kawasaki":
            focus[rec["transition"]] = rec
    munis = []
    mcols = data["aggregates"]["municipality"]["columns"]
    for row in data["aggregates"]["municipality"]["data"]:
        rec = dict(zip(mcols, row))
        if rec.get("region") == "R1_yokohama_kawasaki":
            munis.append(rec)
    return {"r1": reg["R1_yokohama_kawasaki"], "comp": comp["R1_yokohama_kawasaki"], "focus": focus, "munis": munis}


def read_r1_cells():
    table = pq.read_table(
        CELLS,
        columns=["region", "muni_name", "grp2014", "grp2021", "landscape", "area_m2", "geometry"],
        filters=[("region", "=", "R1_yokohama_kawasaki")],
    )
    return table


def landuse_check(tables: dict, cells) -> dict:
    r1 = tables["r1"]
    n = cells.num_rows
    if n != int(r1["n_cells"]):
        raise SystemExit(f"cell count {n} != {r1['n_cells']}")
    area = cells.column("area_m2")
    g1 = cells.column("grp2014")
    g2 = cells.column("grp2021")
    muni = cells.column("muni_name")
    landscape = cells.column("landscape")
    land_km2 = 0.0
    other_gain = 0.0
    other_loss = 0.0
    other_gain_by = Counter()
    other_loss_by = Counter()
    forest_loss_by = Counter()
    forest_gain_by = Counter()
    tz = defaultdict(lambda: {"gain": 0.0, "loss": 0.0, "gain_n": 0, "loss_n": 0})
    kw_loss = Counter()
    kw_loss_km2 = 0.0
    bf_n = 0
    af_n = 0
    for i in range(n):
        km2 = float(area[i].as_py()) / 1e6
        land_km2 += km2
        a = g1[i].as_py()
        b = g2[i].as_py()
        if b == "other" and a != "other":
            other_gain += km2
            other_gain_by[a] += km2
        elif a == "other" and b != "other":
            other_loss += km2
            other_loss_by[b] += km2
        if a == "forest" and b != "forest":
            forest_loss_by[b] += km2
        elif b == "forest" and a != "forest":
            forest_gain_by[a] += km2
        if muni[i].as_py() == "横浜市都筑区" and a != b and (a == "forest" or b == "forest"):
            slot = tz[landscape[i].as_py()]
            if b == "forest" and a != "forest":
                slot["gain"] += km2
                slot["gain_n"] += 1
            elif a == "forest" and b != "forest":
                slot["loss"] += km2
                slot["loss_n"] += 1
        if muni[i].as_py() == "川崎市川崎区" and a == "building" and b != "building":
            kw_loss[b] += km2
            kw_loss_km2 += km2
        if a == "building" and b == "forest":
            bf_n += 1
        elif a == "agri" and b == "forest":
            af_n += 1
    if abs(land_km2 - float(r1["land_km2"])) > TOL_KM2:
        raise SystemExit("cell land area disagrees with the region row")
    with AGG.open(encoding="utf-8", newline="") as handle:
        agg_rows = list(csv.DictReader(handle))
    agg = next(row for row in agg_rows if row["region"] == "R1_yokohama_kawasaki")
    if abs(float(agg["other_net_change_km2"]) - float(r1["other_net_change_km2"])) > 1e-6:
        raise SystemExit("agg_region other_net disagrees with results.json")
    other_net = other_gain - other_loss
    building_to_other = other_gain_by["building"]
    forest_loss = sum(forest_loss_by.values())
    forest_gain = sum(forest_gain_by.values())
    forest_net = forest_gain - forest_loss
    forest_to_building = forest_loss_by["building"]
    forest_to_non_building = forest_loss - forest_to_building
    if abs(other_net - float(r1["other_net_change_km2"])) > TOL_KM2:
        raise SystemExit("other net disagrees")
    if abs(other_net - building_to_other) < CLOSE_KM2:
        raise SystemExit("other net was treated as building-to-other")
    if abs(forest_net - float(r1["forest_net_change_km2"])) > TOL_KM2:
        raise SystemExit("forest net disagrees")
    if abs(abs(forest_net) - forest_to_building) >= CLOSE_KM2 and forest_to_non_building < 1.0:
        raise SystemExit("forest outflow check failed")
    if round(other_net, 3) != 5.193 or round(forest_net, 3) != -4.373:
        raise SystemExit(f"handoff rounding drifted {other_net} {forest_net}")
    if round(building_to_other, 3) != 6.555 or round(forest_to_building, 3) != 4.362:
        raise SystemExit("handoff parts drifted")
    if round(other_gain, 3) != 10.268 or round(other_loss, 3) != 5.075:
        raise SystemExit("other flow rounding drifted")
    if round(forest_loss, 3) != 6.847 or round(forest_to_non_building, 3) != 2.485:
        raise SystemExit("forest flow rounding drifted")
    tz_net = sum(v["gain"] - v["loss"] for v in tz.values())
    positive = {k: v["gain"] - v["loss"] for k, v in tz.items() if v["gain"] - v["loss"] > 0}
    top_type, top_net = max(positive.items(), key=lambda kv: kv[1])
    top_share = top_net / tz_net if tz_net else 0.0
    if top_type != "urban" or not (top_share > SINGLE_TYPE_SHARE):
        raise SystemExit("tsuzuki share failed")
    if round(top_share * 100, 1) != 70.0:
        raise SystemExit(f"tsuzuki percent drifted {top_share}")
    urban_cells = tz["urban"]["gain_n"] - tz["urban"]["loss_n"]
    agri_cells = tz["agri_mixed"]["gain_n"] - tz["agri_mixed"]["loss_n"]
    other_cell_nets = {
        k: v["gain_n"] - v["loss_n"] for k, v in tz.items() if k not in {"urban", "agri_mixed"}
    }
    if urban_cells != 7 or agri_cells != 3 or any(other_cell_nets.values()):
        raise SystemExit(f"tsuzuki cells drifted {urban_cells} {agri_cells} {other_cell_nets}")
    agri_share = (tz["agri_mixed"]["gain"] - tz["agri_mixed"]["loss"]) / tz_net
    if round(agri_share * 100, 1) != 30.0:
        raise SystemExit(f"agri share drifted {agri_share}")
    kw_json = next(row for row in tables["munis"] if row["muni_name"] == "川崎市川崎区")
    if abs(kw_loss_km2 - float(kw_json["building_loss_km2"])) > TOL_KM2:
        raise SystemExit("kawasaki building loss disagrees")
    other_share = kw_loss["other"] / kw_loss_km2
    transport_share = kw_loss["transport"] / kw_loss_km2
    fw_share = (kw_loss["forest"] + kw_loss["wasteland"]) / kw_loss_km2
    if other_share <= OTHER_SHARE_MIN or fw_share >= FOREST_WASTE_SHARE_MAX:
        raise SystemExit("kawasaki shares failed")
    if round(other_share * 100, 1) != 81.7 or round(transport_share * 100, 1) != 16.2:
        raise SystemExit(f"kawasaki rounding drifted {other_share} {transport_share}")
    if round(kw_loss_km2, 3) != 1.488:
        raise SystemExit("kawasaki km2 rounding drifted")
    comp = tables["comp"]
    s5 = float(comp["share_>=5"])
    s1 = float(comp["share_1"])
    s2 = float(comp["share_2"])
    changed = float(comp["changed_km2"])
    complement = 1.0 - s1 - s2
    focus = tables["focus"]
    if abs(s5 - GE5_CITED) >= GE5_MATCH or (complement - s5) < COMPLEMENT_GAP:
        raise SystemExit("component share check failed")
    if float(focus["building->forest"]["size_>=5_share"]) != 0.0:
        raise SystemExit("focus ge5 is not zero")
    if float(focus["agri->forest"]["size_>=5_share"]) != 0.0:
        raise SystemExit("focus agri ge5 is not zero")
    if round(s5 * 100, 3) != 9.632 or round(complement * 100, 3) != 21.108:
        raise SystemExit(f"component rounding drifted {s5} {complement}")
    if bf_n != int(focus["building->forest"]["cells"]) or af_n != int(focus["agri->forest"]["cells"]):
        raise SystemExit(f"focus counts {bf_n} {af_n}")
    if bf_n != 103 or af_n != 47:
        raise SystemExit("focus cell handoff drifted")
    return {
        "other_net_km2": other_net,
        "other_gain_km2": other_gain,
        "other_loss_km2": other_loss,
        "building_to_other_km2": building_to_other,
        "forest_net_km2": forest_net,
        "forest_loss_km2": forest_loss,
        "forest_to_building_km2": forest_to_building,
        "forest_to_non_building_km2": forest_to_non_building,
        "forest_loss_by_km2": dict(forest_loss_by),
        "tsuzuki_top_share": top_share,
        "tsuzuki_agri_share": agri_share,
        "tsuzuki_urban_net_cells": urban_cells,
        "tsuzuki_agri_net_cells": agri_cells,
        "tsuzuki_urban_gain_cells": tz["urban"]["gain_n"],
        "tsuzuki_urban_loss_cells": tz["urban"]["loss_n"],
        "tsuzuki_agri_gain_cells": tz["agri_mixed"]["gain_n"],
        "tsuzuki_agri_loss_cells": tz["agri_mixed"]["loss_n"],
        "tsuzuki_net_km2": tz_net,
        "kawasaki_building_loss_km2": kw_loss_km2,
        "kawasaki_other_share": other_share,
        "kawasaki_transport_share": transport_share,
        "kawasaki_forest_wasteland_share": fw_share,
        "share_ge5": s5,
        "ge5_km2": s5 * changed,
        "complement_of_1_2": complement,
        "complement_km2": complement * changed,
        "building_to_forest_cells": bf_n,
        "agri_to_forest_cells": af_n,
        "r1_cells": n,
        "land_km2": land_km2,
    }


def max_r1_number(path: Path) -> int:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    nums = []
    for row in rows:
        ident = row["id"]
        if ident.startswith("R1-"):
            nums.append(int(ident.split("-")[1]))
    return max(nums) if nums else 0


def load_prior() -> list[dict]:
    with PRIOR.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if max_r1_number(PRIOR) != 24 or max_r1_number(SPECIAL) != 24:
        raise SystemExit("prior R1 id ceiling is not 24")
    out = []
    for row in rows:
        if "終了日" not in (row.get("evidence_present") or ""):
            raise SystemExit(f"prior row lacks an end date marker {row['id']}")
        kind = "信号場" if "信号場" in (row.get("evidence_present") or "") else (
            "廃駅" if row["category"] == "station" else "施設"
        )
        out.append({
            "id": row["id"],
            "status": "再検証",
            "type": kind,
            "muni_name": row["muni_name"],
            "name": row["name"],
            "lat": row["lat"],
            "lon": row["lon"],
            "axis_existence": "強",
            "axis_loss": "強",
            "axis_remains": "未確認",
            "confidence": "中",
            "lead_id": "PRIOR",
            "role": kind,
            "sources": row.get("evidence_present") or "",
            "retrieved": RETRIEVED,
            "license": "Wikidata CC0。終了日は 2026-11-05 の入力を再読した。",
            "period": "入力CSVの終了日",
            "verification": "REV-ANNO",
            "notes": "2026-11-09 の維持を再検証した。旧版地形図の記号は見ていないので高にしない。",
            "anno_unverified_prior": row.get("anno_unverified") == "True",
        })
    if len(out) != 24:
        raise SystemExit(f"prior rows {len(out)}")
    return out


def load_judgments() -> list[dict]:
    with JUDGMENTS.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate judgment ids")
    nums = [int(i.split("-")[1]) for i in ids]
    if nums != list(range(25, 25 + len(rows))):
        raise SystemExit("new ids are not the next contiguous block")
    for row in rows:
        if row["status"] not in ALLOWED_STATUS:
            raise SystemExit(f"bad status {row['id']}")
        for key in ("axis_existence", "axis_loss", "axis_remains"):
            if row[key] not in ALLOWED_AXIS:
                raise SystemExit(f"bad axis {row['id']} {key}")
        if row["confidence"] not in ALLOWED_CONF:
            raise SystemExit(f"bad confidence {row['id']}")
        if row["confidence"] == "高" or row["type"] == "廃社":
            raise SystemExit("high confidence or 廃社 is not allowed")
        if row["lat"] or row["lon"]:
            raise SystemExit("new rows must not carry coordinates")
    return rows


def focus_centroids(cells) -> list[tuple[float, float, str, str]]:
    to_geo = pyproj.Transformer.from_crs("EPSG:6677", "EPSG:4326", always_xy=True)
    g1 = cells.column("grp2014")
    g2 = cells.column("grp2021")
    geom = cells.column("geometry")
    out = []
    for i in range(cells.num_rows):
        a = g1[i].as_py()
        b = g2[i].as_py()
        if (a, b) not in {("building", "forest"), ("agri", "forest")}:
            continue
        shape = wkb.loads(geom[i].as_py())
        c = shape.centroid
        lon, lat = to_geo.transform(c.x, c.y)
        out.append((lon, lat, a, b))
    return out


def download_tiles(prior: list[dict], centroids: list[tuple[float, float, str, str]]) -> dict:
    WORK.mkdir(parents=True, exist_ok=True)
    anno_dir = WORK / "anno"
    aerial_dir = WORK / "aerial"
    focus_tiles: dict[tuple[int, int], list[int]] = defaultdict(list)
    for j, (lon, lat, _a, _b) in enumerate(centroids):
        focus_tiles[tile_xy(lon, lat, 15)].append(j)
    candidate_tiles: dict[str, set[tuple[int, int]]] = {}
    for row in prior:
        lon = float(row["lon"])
        lat = float(row["lat"])
        candidate_tiles[row["id"]] = tiles_for_buffer(lon, lat)
    anno_keys = set(focus_tiles) | {xy for group in candidate_tiles.values() for xy in group}
    jobs = []
    for x, y in sorted(anno_keys):
        dest = anno_dir / f"15_{x}_{y}.geojson"
        jobs.append((ANNO_URL.format(x=x, y=y), dest, (x, y), "anno"))
    ok_tiles = set()
    failed_tiles = set()

    def run(job):
        url, dest, key, kind = job
        ok, nbytes = fetch(url, dest)
        return kind, key, ok, nbytes, dest

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(run, job) for job in jobs]
        for fut in as_completed(futures):
            kind, key, ok, _nbytes, _dest = fut.result()
            if ok:
                ok_tiles.add(key)
            else:
                failed_tiles.add(key)
    failed_focus = []
    for key, members in focus_tiles.items():
        if key not in ok_tiles:
            failed_focus.extend(members)
    geod = pyproj.Geod(ellps="WGS84")
    stem_hits = []
    anno_failed_ids = []
    for row in prior:
        keys = candidate_tiles[row["id"]]
        if any(key not in ok_tiles for key in keys):
            anno_failed_ids.append(row["id"])
        stem = stem_of(row["name"])
        lon0 = float(row["lon"])
        lat0 = float(row["lat"])
        hit = False
        for key in keys:
            if key not in ok_tiles:
                continue
            dest = anno_dir / f"15_{key[0]}_{key[1]}.geojson"
            payload = json.loads(dest.read_text(encoding="utf-8"))
            for feat in payload.get("features") or []:
                props = feat.get("properties") or {}
                ft = str(props.get("ftCode") or "")
                ctg = str(props.get("annoCtg") or "")
                if ft in PLACE_FT or ctg.startswith("居住地名") or ctg.startswith("行政区画"):
                    continue
                knj = props.get("knj") or ""
                if not stem or stem_of(knj) != stem:
                    continue
                geom = feat.get("geometry") or {}
                if geom.get("type") != "Point":
                    continue
                lon1, lat1 = geom["coordinates"][:2]
                _az1, _az2, dist = geod.inv(lon0, lat0, lon1, lat1)
                if abs(dist) <= ANNO_MATCH_M:
                    hit = True
        if hit:
            stem_hits.append(row["id"])
            row["notes"] += " 居住地名と行政区画を除いた現行注記に、200m以内で同じ語幹があった。注記は旧版記号ではない。中のまま。"
        elif row["id"] in anno_failed_ids:
            row["notes"] += " 注記タイルが失敗し、注記は未確認。失敗を注記なしとは書かない。"
        else:
            row["notes"] += " 取得できた現行注記のうち、居住地名と行政区画以外に同じ語幹は200m以内に無かった。これは旧版記号の不在ではない。"
    shrine_words = 0
    for key, members in focus_tiles.items():
        if key not in ok_tiles or not members:
            continue
        dest = anno_dir / f"15_{key[0]}_{key[1]}.geojson"
        payload = json.loads(dest.read_text(encoding="utf-8"))
        for feat in payload.get("features") or []:
            knj = ((feat.get("properties") or {}).get("knj")) or ""
            if any(word in knj for word in ("神社", "寺院", "鳥居")):
                shrine_words += 1
    r017_keys = candidate_tiles.get("R1-017", set())
    r017_ok = bool(r017_keys) and all(key in ok_tiles for key in r017_keys)
    aerial_targets = []
    for row in prior:
        aerial_targets.append((float(row["lon"]), float(row["lat"]), row["id"]))
    for j in failed_focus:
        lon, lat, _a, _b = centroids[j]
        aerial_targets.append((lon, lat, "focus"))
    aerial_jobs = []
    seen = set()
    for lon, lat, label in aerial_targets:
        key = tile_xy(lon, lat, 17)
        if key in seen:
            continue
        if len(seen) >= AERIAL_CAP:
            break
        seen.add(key)
        dest = aerial_dir / f"ort_old10_17_{key[0]}_{key[1]}.png"
        aerial_jobs.append((AERIAL_URL.format(x=key[0], y=key[1]), dest, key, "aerial"))
    aerial_ok = 0
    aerial_fail = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(run, job) for job in aerial_jobs]
        for fut in as_completed(futures):
            _kind, _key, ok, _nbytes, _dest = fut.result()
            if ok:
                aerial_ok += 1
            else:
                aerial_fail += 1
    return {
        "focus_cells": len(centroids),
        "anno_tiles_requested": len(anno_keys),
        "anno_tiles_ok": len(ok_tiles),
        "anno_tiles_failed": len(failed_tiles),
        "focus_cells_on_failed_tiles": len(failed_focus),
        "candidates_with_failed_anno": anno_failed_ids,
        "candidates_with_stem_hit": stem_hits,
        "r1_017_anno_ok": r017_ok,
        "aerial_tiles_requested": len(aerial_jobs),
        "aerial_tiles_ok": aerial_ok,
        "aerial_tiles_failed": aerial_fail,
        "aerial_period": "1961-1969",
        "old_topo_tiff": "not_acquired",
        "focus_tile_shrine_words": shrine_words,
    }


def copy_texts() -> list[dict]:
    SUPP.mkdir(parents=True, exist_ok=True)
    dest_root = SUPP / "sources"
    dest_root.mkdir(parents=True, exist_ok=True)
    with TEXT_MANIFEST.open(encoding="utf-8", newline="") as handle:
        manifest = list(csv.DictReader(handle))
    records = []
    for row in manifest:
        src = TEXT_DIR / row["filename"]
        if not src.exists():
            raise SystemExit(f"missing text source {row['filename']}")
        dest = dest_root / row["filename"]
        dest.write_bytes(src.read_bytes())
        records.append({
            "path": f"sources/{row['filename']}",
            "url": row["url"],
            "retrieved": RETRIEVED,
            "license": row["license"],
            "period": row["period"],
            "sha256": sha256_file(dest),
            "bytes": dest.stat().st_size,
            "note": row["note"],
        })
    return records


def tile_provenance(tile_info: dict) -> list[dict]:
    records = []
    for folder, layer, period in (
        (WORK / "anno", "gsi_experimental_anno_z15", "現行注記"),
        (WORK / "aerial", "gsi_ort_old10_z17", "1961-1969"),
    ):
        if not folder.exists():
            continue
        copied = SUPP / folder.name
        copied.mkdir(parents=True, exist_ok=True)
        for path in sorted(folder.iterdir()):
            if path.suffix == ".error":
                continue
            target = copied / path.name
            if not target.exists():
                target.write_bytes(path.read_bytes())
            url = ANNO_URL if folder.name == "anno" else AERIAL_URL
            records.append({
                "path": f"{folder.name}/{path.name}",
                "url_pattern": url,
                "retrieved": RETRIEVED,
                "license": f"国土地理院コンテンツ利用規約 {GSI_TERMS}",
                "period": period,
                "layer": layer,
                "sha256": sha256_file(target),
                "bytes": target.stat().st_size,
                "note": "焦点セルと候補の周囲だけ。タイル番号は非公開側に置く。",
            })
    records.append({
        "path": "",
        "url": "",
        "retrieved": RETRIEVED,
        "license": "国土地理院の旧版地形図TIFFは有料交付。今日は申請も購入もしていない。",
        "period": "旧版地形図",
        "sha256": "",
        "bytes": 0,
        "note": "未取得。取得済みと書かない。",
        "counts": {k: v for k, v in tile_info.items() if k != "candidates_with_stem_hit" and k != "candidates_with_failed_anno"},
    })
    return records


def public_row(row: dict) -> dict:
    return {
        "id": row["id"],
        "status": row["status"],
        "muni_name": row["muni_name"],
        "type": row["type"],
        "role": row["role"],
        "axis_existence": row["axis_existence"],
        "axis_loss": row["axis_loss"],
        "axis_remains": row["axis_remains"],
        "confidence": row["confidence"],
        "lead_id": row["lead_id"],
        "verification": row["verification"],
    }


def write_private(rows: list[dict]) -> None:
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
        for row in rows:
            writer.writerow(row)
    lines = ["# R1 2026-11-16 非公開メモ", "", "名称と座標はここだけ。リポジトリには置かない。", ""]
    for row in rows:
        lines.append(f"## {row['id']}")
        lines.append(f"- 状態: {row['status']} / 種別: {row['type']} / 役割: {row['role']} / リード: {row['lead_id']}")
        lines.append(f"- 市区町村: {row['muni_name']}")
        lines.append(f"- 名称: {row['name']}")
        if row.get("lat") and row.get("lon"):
            lines.append(f"- 緯度経度: {row['lat']}, {row['lon']}")
        else:
            lines.append("- 緯度経度: なし（住所からは作っていない）")
        lines.append(f"- 存在: {row['axis_existence']} / 廃止: {row['axis_loss']} / 遺構: {row['axis_remains']} / 総合: {row['confidence']}")
        lines.append(f"- 検証: {row['verification']}")
        lines.append(f"- 情報源: {row['sources']}")
        lines.append(f"- 取得日: {row['retrieved']} / 条件: {row['license']} / 年代: {row['period']}")
        lines.append(f"- メモ: {row['notes']}")
        lines.append("")
    (OUT_PRIV / "findings.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    tables = load_results()
    cells = read_r1_cells()
    stats = landuse_check(tables, cells)
    prior = load_prior()
    judgments = load_judgments()
    centroids = focus_centroids(cells)
    tile_info = download_tiles(prior, centroids)
    rows = prior + judgments
    if any(row["confidence"] == "高" for row in rows):
        raise SystemExit("high confidence leaked")
    if any(row["type"] == "廃社" for row in rows):
        raise SystemExit("廃社 row leaked")
    names = [row["name"] for row in rows if row.get("name")]
    by_status = Counter(row["status"] for row in rows)
    by_type = Counter(row["type"] for row in rows)
    by_lead = Counter(row["lead_id"] for row in rows)
    adopted = [row["id"] for row in rows if row["status"] == "再検証" and row["confidence"] == "中"]
    public = {
        "date": "2026-11-16",
        "region": "R1",
        "week": 4,
        "elapsed_days": 21,
        "day_number": 22,
        "rotation": "21 mod 7 = 0, floor(21/7)+1 = 4",
        "prior_ids_max": 24,
        "new_id_first": 25,
        "new_id_last": 65,
        "high_confidence": 0,
        "adopted_lost_shrines": 0,
        "reverified_medium": len(adopted),
        "rows": len(rows),
        "by_status": dict(by_status),
        "by_type": dict(by_type),
        "by_lead": dict(by_lead),
        "landuse": {
            "other_net_km2": round(stats["other_net_km2"], 3),
            "other_gain_km2": round(stats["other_gain_km2"], 3),
            "other_loss_km2": round(stats["other_loss_km2"], 3),
            "building_to_other_km2": round(stats["building_to_other_km2"], 3),
            "forest_net_km2": round(stats["forest_net_km2"], 3),
            "forest_loss_km2": round(stats["forest_loss_km2"], 3),
            "forest_to_building_km2": round(stats["forest_to_building_km2"], 3),
            "forest_to_non_building_km2": round(stats["forest_to_non_building_km2"], 3),
            "tsuzuki_urban_share": round(stats["tsuzuki_top_share"], 3),
            "tsuzuki_agri_share": round(stats["tsuzuki_agri_share"], 3),
            "tsuzuki_urban_net_cells": stats["tsuzuki_urban_net_cells"],
            "tsuzuki_agri_net_cells": stats["tsuzuki_agri_net_cells"],
            "kawasaki_building_loss_km2": round(stats["kawasaki_building_loss_km2"], 3),
            "kawasaki_other_share": round(stats["kawasaki_other_share"], 3),
            "kawasaki_transport_share": round(stats["kawasaki_transport_share"], 3),
            "kawasaki_forest_wasteland_share": stats["kawasaki_forest_wasteland_share"],
            "share_ge5": round(stats["share_ge5"], 5),
            "complement_of_1_2": round(stats["complement_of_1_2"], 5),
            "focus_building_to_forest_cells": stats["building_to_forest_cells"],
            "focus_agri_to_forest_cells": stats["agri_to_forest_cells"],
            "focus_ge5": 0,
        },
        "maps": {
            "anno_tiles_requested": tile_info["anno_tiles_requested"],
            "anno_tiles_ok": tile_info["anno_tiles_ok"],
            "anno_tiles_failed": tile_info["anno_tiles_failed"],
            "focus_cells": tile_info["focus_cells"],
            "focus_cells_on_failed_tiles": tile_info["focus_cells_on_failed_tiles"],
            "prior_stem_hits": len(tile_info["candidates_with_stem_hit"]),
            "prior_anno_failed_ids": [
                ident for ident in tile_info["candidates_with_failed_anno"]
            ],
            "r1_017_anno_ok": tile_info["r1_017_anno_ok"],
            "aerial_tiles_ok": tile_info["aerial_tiles_ok"],
            "aerial_tiles_failed": tile_info["aerial_tiles_failed"],
            "focus_tile_shrine_words": tile_info["focus_tile_shrine_words"],
            "aerial_period": tile_info["aerial_period"],
            "old_topo_tiff": "not_acquired",
            "osm_pbf_reread": False,
            "worship_control_not_refreshed": 1304,
        },
        "quake_list": {
            "summary_says": 16,
            "named_in_summary_sentence": 14,
            "unnamed_in_etc": 2,
            "collapsed_named": 6,
            "unharmed_named": 9,
            "named_not_equated_to_etc": True,
        },
        "rows_public": [public_row(row) for row in rows],
    }
    blob = json.dumps(public, ensure_ascii=False, indent=2)
    if COORD_RE.search(blob):
        raise SystemExit("public json contains a coordinate-like number")
    for name in names:
        if name and name in blob:
            raise SystemExit("public json contains a candidate name")
    PUBLIC.write_text(blob + "\n", encoding="utf-8")
    write_private(rows)
    text_records = copy_texts()
    tile_records = tile_provenance(tile_info)
    prov_path = SUPP / "provenance_supplemental.jsonl"
    with prov_path.open("w", encoding="utf-8") as handle:
        for rec in text_records + tile_records:
            handle.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(json.dumps({
        "rows": len(rows),
        "by_status": dict(by_status),
        "by_type": dict(by_type),
        "maps": public["maps"],
        "landuse_ok": True,
        "stem_hit_ids": tile_info["candidates_with_stem_hit"],
        "anno_failed_ids": tile_info["candidates_with_failed_anno"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
