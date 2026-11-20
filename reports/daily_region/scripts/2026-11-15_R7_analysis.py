"""R7（県西）3週目。2026-11-15。

主目的は、前回候補の再検証、外部リードの3軸評価、
明細帳目録とダム・旧鉄道の公開資料による探索である。
土地利用は 2026-11-08 の申し送りがまだ成り立つかの確認に限る。

公開 JSON には件数、市区町村、候補 ID、3軸、確度、リード ID だけを書く。
名称と緯度経度は、環境変数で渡した非公開ファイルから読み、
/opt/cursor/artifacts/kanagawa_private/2026-11-15_R7/ に出す。
スクリプトには地点の緯度経度も候補名も書かない。

評価は件数を数える前に固定した。

- 過去に存在した根拠、廃止・消失の根拠、物理的遺構が残る可能性は別の欄にする。
- 現行の地図に名称が無いこと、森林化、神社庁の検索に出ないことは、消失の根拠にしない。
- 座標は、入力 CSV に列があるときだけ読む。字名や住所からは点を作らない。
- 総合確度の高は、旧版地形図の記号を見ていない限り付けない。今日は付けない。
- 遷座先、合祀先、現在の社・現在のトンネルは廃社・廃道にしない。
- 旧地と移転先は別の行にする。
- 探訪記、投稿、空撮は二次である。画像は保存しない。
- 明細帳の目録概要に社名が並んでいても、廃止の語が無ければ廃社にしない。
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import urllib.request
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq
import pyproj
from shapely import wkb
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parents[3]
JUDGMENTS = Path(os.environ["PRIVATE_JUDGMENTS_CSV"])
PRIOR = Path(os.environ["PRIVATE_PRIOR_CANDIDATES"])
CELLS = Path(os.environ["CELLS_PARQUET"])
CATALOG = Path(os.environ["CATALOG_HTML"])
SUPP = Path(os.environ["SUPP_DIR"])
OUT_PRIV = Path("/opt/cursor/artifacts/kanagawa_private/2026-11-15_R7")
PUBLIC = ROOT / "reports" / "daily_region" / "data" / "2026-11-15_R7_week3_public.json"
RESULTS = ROOT / "reports" / "phase1c2_results.json"
WORK = Path(os.environ.get("R7_WORK_DIR", "/tmp/r7_20261115"))
RETRIEVED = "2026-11-15"
UA = "kanagawa-ruins-search/2026-11-15"
GE5_CITED = 0.113
GE5_MATCH = 0.01
COMPLEMENT_GAP = 0.10
PUBLISHED_AGRI_TO_BUILDING_KM2 = 0.49
MIN_RATE_BASE_KM2 = 0.50
MOUNTAIN = ("山北町", "松田町")
PLAIN = ("中井町", "大井町", "開成町")
MISSING = ("小田原市", "箱根町", "真鶴町", "湯河原町")
COORD_RE = re.compile(r"(?:3[4-6]|13[89])\.[0-9]{3,}")
ALLOWED_STATUS = {"新規", "既存", "再検証", "棄却", "負例", "状態変化", "保留"}
ALLOWED_AXIS = {"強", "中", "低", "なし", "未確認", "対象外"}
TAG_RE = re.compile(r"<[^>]+>")
ANNO_URL = "https://cyberjapandata.gsi.go.jp/xyz/experimental_anno/15/{x}/{y}.geojson"
AERIAL_URL = "https://cyberjapandata.gsi.go.jp/xyz/ort_old10/17/{x}/{y}.png"
AERIAL_CAP = 8


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def plain(html: str) -> str:
    return re.sub(r"\s+", " ", TAG_RE.sub(" ", html))


def load_results() -> dict:
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    reg = {
        name: dict(zip(data["aggregates"]["region"]["columns"], row))
        for name, row in zip(
            data["aggregates"]["region"]["index"],
            data["aggregates"]["region"]["data"],
        )
    }
    cc = data["transitions"]["component_class_share_by_region"]
    comp = {
        name: dict(zip(cc["columns"], row))
        for name, row in zip(cc["index"], cc["data"])
    }
    focus = {}
    block = data["transitions"]["focus_by_region"]
    for row in block["data"]:
        rec = dict(zip(block["columns"], row))
        if rec["region"] == "R7_kensei":
            focus[rec["transition"]] = rec
    rl = data["aggregates"]["region_landscape"]
    gain_cols = [
        c
        for c in rl["columns"]
        if "forest_to_agri" in c or str(c).startswith("agri_from")
    ]
    mcols = data["aggregates"]["municipality"]["columns"]
    munis = []
    for row in data["aggregates"]["municipality"]["data"]:
        rec = dict(zip(mcols, row))
        if rec.get("region") == "R7_kensei":
            munis.append(rec)
    return {
        "r7": reg["R7_kensei"],
        "comp": comp["R7_kensei"],
        "focus": focus,
        "gain_cols": gain_cols,
        "munis": munis,
        "muni_names": {rec["muni_name"] for rec in munis},
    }


def landuse_check(tables: dict) -> dict:
    r7 = tables["r7"]
    comp = tables["comp"]
    focus = tables["focus"]
    s1, s2, s5 = comp["share_1"], comp["share_2"], comp["share_>=5"]
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

    def group_sum(names, key):
        return sum(row[key] for row in tables["munis"] if row["muni_name"] in names)

    mountain_land = group_sum(MOUNTAIN, "land_km2")
    plain_agri_net = group_sum(PLAIN, "agri_net_change_km2")
    mountain_agri_net = group_sum(MOUNTAIN, "agri_net_change_km2")
    mountain_agri_base = sum(
        row["agri_2014_share"] * row["land_km2"]
        for row in tables["munis"]
        if row["muni_name"] in MOUNTAIN
    )
    plain_agri_base = sum(
        row["agri_2014_share"] * row["land_km2"]
        for row in tables["munis"]
        if row["muni_name"] in PLAIN
    )
    missing_rows = [row for row in tables["munis"] if row["muni_name"] in MISSING]
    h1 = (
        len(tables["gain_cols"]) == 0
        and agri_remainder > 0
        and abs(agri_remainder - PUBLISHED_AGRI_TO_BUILDING_KM2) >= 0.01
    )
    h2 = b_remainder > 0 and forest_to_b < b_gain * 0.5
    h3 = (
        abs(s5 - GE5_CITED) < GE5_MATCH
        and (complement - s5) >= COMPLEMENT_GAP
        and focus["building->forest"]["size_>=5_share"] == 0
        and focus["agri->forest"]["size_>=5_share"] == 0
    )
    h4 = (
        mountain_land / r7["land_km2"] >= 0.80
        and plain_agri_net > mountain_agri_net
        and mountain_agri_base >= MIN_RATE_BASE_KM2
        and plain_agri_base >= MIN_RATE_BASE_KM2
        and len(missing_rows) == 0
    )
    if not all((h1, h2, h3, h4)):
        raise SystemExit(f"handoff assertions failed: {h1, h2, h3, h4}")
    return {
        "h1": h1,
        "h2": h2,
        "h3": h3,
        "h4": h4,
        "coverage_ratio": r7["coverage_ratio"] if "coverage_ratio" in r7 else None,
        "land_km2": r7["land_km2"],
        "n_cells": r7["n_cells"],
        "agri_gain_km2": agri_gain,
        "agri_remainder_km2": agri_remainder,
        "published_agri_to_building_km2": PUBLISHED_AGRI_TO_BUILDING_KM2,
        "building_gain_km2": b_gain,
        "building_remainder_km2": b_remainder,
        "forest_to_building_km2": forest_to_b,
        "share_ge5": s5,
        "ge5_km2": s5 * changed,
        "complement_of_1_2": complement,
        "complement_km2": complement * changed,
        "gap_pp": (complement - s5) * 100,
        "building_to_forest_cells": focus["building->forest"]["cells"],
        "agri_to_forest_cells": focus["agri->forest"]["cells"],
        "building_ge5": focus["building->forest"]["size_>=5_share"],
        "agri_ge5": focus["agri->forest"]["size_>=5_share"],
        "mountain_land_share": mountain_land / r7["land_km2"],
        "mountain_agri_net_km2": mountain_agri_net,
        "plain_agri_net_km2": plain_agri_net,
        "forest_net_km2": r7["forest_net_change_km2"],
        "forestation_rate": r7["forestation_rate"],
    }


def tile_xy(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    n = 2**zoom
    x = int((lon + 180.0) / 360.0 * n)
    lat_r = math.radians(lat)
    y = int((1.0 - math.log(math.tan(lat_r) + 1 / math.cos(lat_r)) / math.pi) / 2.0 * n)
    return x, y


def fetch(url: str, dest: Path) -> tuple[bool, int]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            raw = resp.read()
            code = getattr(resp, "status", 200)
    except Exception as exc:
        dest.with_suffix(dest.suffix + ".error").write_text(
            f"{type(exc).__name__}: {exc}\n", encoding="utf-8"
        )
        return False, 0
    dest.write_bytes(raw)
    return True, len(raw)


def focus_and_anno(prior_ll: tuple[float, float] | None) -> dict:
    table = pq.read_table(
        CELLS,
        columns=["region", "muni_name", "grp2014", "grp2021", "geometry"],
        filters=[("region", "=", "R7_kensei")],
    )
    n = table.num_rows
    to_geo = pyproj.Transformer.from_crs("EPSG:6677", "EPSG:6668", always_xy=True)
    to_xy = pyproj.Transformer.from_crs("EPSG:6668", "EPSG:6677", always_xy=True)
    # The parquet names the projected CRS JGD2024 zone IX and remarks that
    # coordinate values are unchanged from the JGD2011 definition.
    focus_idx = []
    centroids_ll = []
    geoms = []
    groups = []
    munis = []
    for i in range(n):
        g2014 = table.column("grp2014")[i].as_py()
        g2021 = table.column("grp2021")[i].as_py()
        geom = wkb.loads(table.column("geometry")[i].as_py())
        geoms.append(geom)
        groups.append((g2014, g2021))
        munis.append(table.column("muni_name")[i].as_py())
        if (g2014, g2021) in {("building", "forest"), ("agri", "forest")}:
            focus_idx.append(i)
            c = geom.centroid
            lon, lat = to_geo.transform(c.x, c.y)
            centroids_ll.append((lon, lat))
    n_bf = sum(1 for i in focus_idx if groups[i] == ("building", "forest"))
    n_af = sum(1 for i in focus_idx if groups[i] == ("agri", "forest"))
    tiles: dict[tuple[int, int], list[int]] = {}
    for j, (lon, lat) in enumerate(centroids_ll):
        tiles.setdefault(tile_xy(lon, lat, 15), []).append(j)
    WORK.mkdir(parents=True, exist_ok=True)
    anno_dir = WORK / "anno"
    shrine_hits = 0
    failed_focus = []
    ok_tiles = 0
    for (x, y), members in sorted(tiles.items()):
        dest = anno_dir / f"15_{x}_{y}.geojson"
        ok, _nbytes = fetch(ANNO_URL.format(x=x, y=y), dest)
        if not ok:
            for j in members:
                failed_focus.append(j)
            continue
        ok_tiles += 1
        payload = json.loads(dest.read_text(encoding="utf-8"))
        for feat in payload.get("features") or []:
            props = feat.get("properties") or {}
            knj = props.get("knj") or ""
            if not any(word in knj for word in ("神社", "寺院", "鳥居")):
                continue
            shrine_hits += 1
    station_classes = None
    if prior_ll is not None:
        px, py = to_xy.transform(prior_ll[0], prior_ll[1])
        pt = Point(px, py)
        station_classes = "outside"
        for geom, pair in zip(geoms, groups):
            if geom.covers(pt):
                station_classes = f"{pair[0]}->{pair[1]}"
                break
    aerial_ok = 0
    aerial_fail = 0
    aerial_targets = []
    for j in failed_focus:
        aerial_targets.append(centroids_ll[j])
    if prior_ll is not None:
        aerial_targets.append(prior_ll)
    seen_tiles = set()
    aerial_dir = WORK / "aerial"
    for lon, lat in aerial_targets:
        key = tile_xy(lon, lat, 17)
        if key in seen_tiles:
            continue
        if len(seen_tiles) >= AERIAL_CAP:
            break
        seen_tiles.add(key)
        dest = aerial_dir / f"ort_old10_17_{key[0]}_{key[1]}.png"
        ok, _nbytes = fetch(AERIAL_URL.format(x=key[0], y=key[1]), dest)
        if ok:
            aerial_ok += 1
        else:
            aerial_fail += 1
    return {
        "r7_cells": n,
        "focus_cells": len(focus_idx),
        "building_to_forest_cells": n_bf,
        "agri_to_forest_cells": n_af,
        "anno_tiles_requested": len(tiles),
        "anno_tiles_ok": ok_tiles,
        "anno_tiles_404": len(tiles) - ok_tiles,
        "focus_cells_on_failed_tiles": len(failed_focus),
        "shrine_annotation_features": shrine_hits,
        "station_cell_classes": station_classes,
        "aerial_tiles_ok": aerial_ok,
        "aerial_tiles_failed": aerial_fail,
        "aerial_period": "1961-1969",
        "aerial_note": "廃止後の空中写真であり、営業期の地形図記号ではない。",
    }


def catalog_counts() -> dict:
    text = plain(CATALOG.read_text(encoding="utf-8", errors="replace"))
    return {
        "ashigarakami_mentions": text.count("足柄上郡"),
        "osu_mentions": text.count("大住郡"),
        "goushi": text.count("合祀"),
        "hai": text.count("廃"),
        "gappei": text.count("合併"),
        "sonsha": text.count("村社"),
        "mukaku": text.count("無格社"),
        "gosha": text.count("郷社"),
    }


def load_judgments() -> list[dict]:
    with JUDGMENTS.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate judgment ids")
    for row in rows:
        if row["status"] not in ALLOWED_STATUS:
            raise SystemExit(f"bad status {row['id']}")
        for key in ("axis_existence", "axis_loss", "axis_remains"):
            if row[key] not in ALLOWED_AXIS:
                raise SystemExit(f"bad axis {row['id']} {key}")
        if row["confidence"] == "高":
            raise SystemExit("high confidence is not allowed without an old-map symbol")
        if row["type"] == "廃社":
            raise SystemExit("廃社 row is not allowed in this round")
        if row["status"] == "負例" and row["axis_loss"] != "なし":
            raise SystemExit(f"negative example has a loss axis {row['id']}")
        if row["status"] == "保留":
            if not all(
                row[key] == "未確認"
                for key in ("axis_existence", "axis_loss", "axis_remains")
            ):
                # L2 bowl is 新規, not 保留. Retained holds must stay unconfirmed.
                if row["id"].startswith("HOLD") or row["lead_id"] in {"L1", "L3", "L4"}:
                    if row["confidence"] == "保留" and row["axis_loss"] == "未確認":
                        pass
                    else:
                        raise SystemExit(f"hold row is partly confirmed {row['id']}")
        if row["in_r7_count"] not in {"yes", "no"}:
            raise SystemExit("in_r7_count")
        snippet = row["evidence_snippet"]
        path = row["evidence_file"]
        if path:
            body = plain(Path(path).read_text(encoding="utf-8", errors="replace"))
            if snippet and snippet not in body:
                raise SystemExit(f"evidence snippet missing for {row['id']}")
        elif row["in_r7_count"] == "yes" and row["lead_id"] not in {"L1", "L4"}:
            if row["id"] not in {"R7-016"}:
                raise SystemExit(f"missing evidence file {row['id']}")
    return rows


def prior_station() -> dict:
    with PRIOR.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 1 or rows[0]["id"] != "R7-001":
        raise SystemExit("prior R7 candidate set changed")
    row = rows[0]
    lat = float(row["lat"])
    lon = float(row["lon"])
    return {"lat": lat, "lon": lon, "name": row["name"], "category": row["category"]}


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
        "in_r7_count": row["in_r7_count"] == "yes",
    }


def write_private(rows: list[dict], prior: dict, anno: dict, catalog: dict) -> None:
    OUT_PRIV.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "id",
        "status",
        "type",
        "muni_name",
        "name",
        "lat",
        "lon",
        "axis_existence",
        "axis_loss",
        "axis_remains",
        "confidence",
        "sources",
        "retrieved",
        "license",
        "period",
        "verification",
        "notes",
        "role",
        "lead_id",
        "in_r7_count",
    ]
    out_rows = []
    for row in rows:
        lat = ""
        lon = ""
        if row["id"] == "R7-001":
            if row["name"] != prior["name"]:
                raise SystemExit("prior name and judgment name differ")
            lat = f"{prior['lat']:.7f}"
            lon = f"{prior['lon']:.7f}"
        out_rows.append(
            {
                "id": row["id"],
                "status": row["status"],
                "type": row["type"],
                "muni_name": row["muni_name"],
                "name": row["name"],
                "lat": lat,
                "lon": lon,
                "axis_existence": row["axis_existence"],
                "axis_loss": row["axis_loss"],
                "axis_remains": row["axis_remains"],
                "confidence": row["confidence"],
                "sources": row["sources"],
                "retrieved": row["retrieved"],
                "license": row["license"],
                "period": row["period"],
                "verification": row["verification"],
                "notes": row["notes"],
                "role": row["role"],
                "lead_id": row["lead_id"],
                "in_r7_count": row["in_r7_count"],
            }
        )
    with (OUT_PRIV / "candidates.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)
    lines = [
        "# 非公開メモ 2026-11-15 R7 県西",
        "",
        "公開レポートには名称と座標を書かない。このファイルは artifacts だけに置く。",
        "",
        "## 候補",
        "",
    ]
    for row in out_rows:
        lines.append(
            f"- {row['id']} {row['status']} {row['muni_name']} {row['type']} "
            f"{row['name']} 存在{row['axis_existence']} 廃止{row['axis_loss']} "
            f"遺構{row['axis_remains']} 総合{row['confidence']} {row['lead_id']}"
        )
        lines.append(f"  検証: {row['verification']}")
        lines.append(f"  注記: {row['notes']}")
    lines.extend(
        [
            "",
            "## 注記タイルと空中写真",
            "",
            f"- 焦点セル {anno['focus_cells']}（建物用地→森林 {anno['building_to_forest_cells']}、農地→森林 {anno['agri_to_forest_cells']}）",
            f"- 注記タイル要求 {anno['anno_tiles_requested']}、取得 {anno['anno_tiles_ok']}、失敗 {anno['anno_tiles_404']}",
            f"- 失敗タイル上の焦点セル {anno['focus_cells_on_failed_tiles']}",
            f"- 神社・寺院・鳥居を含む注記フィーチャ {anno['shrine_annotation_features']}",
            f"- 前回候補のセル区分 {anno['station_cell_classes']}",
            f"- 空中写真 ort_old10（{anno['aerial_period']}）取得 {anno['aerial_tiles_ok']}、失敗 {anno['aerial_tiles_failed']}",
            f"- {anno['aerial_note']}",
            "",
            "## 明細帳目録",
            "",
            f"- 足柄上郡の出現 {catalog['ashigarakami_mentions']}、大住郡 {catalog['osu_mentions']}",
            f"- 村社 {catalog['sonsha']}、無格社 {catalog['mukaku']}、郷社 {catalog['gosha']}",
            f"- 合祀 {catalog['goushi']}、廃 {catalog['hai']}、合併 {catalog['gappei']}",
            "- 概要の社名からは廃社を採番していない。帳面の画像は未取得。",
            "",
            "## 採らなかったもの",
            "",
            "- 熱海軌道の駅は、事業者沿革を開いて駅ごとに確認していない。0件。",
            "- 明細帳の個々の社は、廃止の語が無いので廃社にしていない。",
            "- ダムの地区名は百科が列挙するが、引用された本を開いていないので分割していない。",
            "- haikyo.org の索引にある他の神奈川見出しは、今日の指定リードではないので採番していない。",
            "- 旧版地形図の正規タイルは、公開タイル一覧の1936–1942年が東京・大阪に限られ、県西の図幅は未取得。",
            "",
        ]
    )
    (OUT_PRIV / "findings.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    tables = load_results()
    land = landuse_check(tables)
    prior = prior_station()
    rows = load_judgments()
    if not any(row["id"] == "R7-001" and row["status"] == "再検証" for row in rows):
        raise SystemExit("R7-001 must stay a revalidation row")
    anno = focus_and_anno((prior["lon"], prior["lat"]))
    if anno["r7_cells"] != int(tables["r7"]["n_cells"]):
        raise SystemExit("cell count drifted")
    if (anno["building_to_forest_cells"], anno["agri_to_forest_cells"]) != (
        land["building_to_forest_cells"],
        land["agri_to_forest_cells"],
    ):
        raise SystemExit("focus cell counts drifted")
    if anno["building_to_forest_cells"] != 24 or anno["agri_to_forest_cells"] != 14:
        raise SystemExit("focus cell totals are no longer 24 and 14")
    catalog = catalog_counts()
    if catalog["goushi"] != 0 or catalog["gappei"] != 0:
        raise SystemExit("catalog summary now contains merger language; re-read before promoting")
    counted = [row for row in rows if row["in_r7_count"] == "yes"]
    outside = [row for row in rows if row["in_r7_count"] == "no"]
    by_status = Counter(row["status"] for row in counted)
    by_type = Counter(row["type"] for row in counted)
    adopted = [
        row
        for row in counted
        if row["status"] in {"新規", "再検証", "既存"}
        and row["type"] in {"廃駅", "廃施設", "消失集落", "廃道", "廃社", "廃寺"}
    ]
    public = {
        "date": RETRIEVED,
        "region": "R7",
        "week": 3,
        "elapsed_days": 20,
        "day_number": 21,
        "rotation": "20 mod 7 = 6, floor(20/7)+1 = 3",
        "prior_candidate_rows": 1,
        "high_confidence": 0,
        "adopted_lost_shrines": 0,
        "rows_in_r7_count": len(counted),
        "rows_out_of_count": len(outside),
        "by_status": dict(by_status),
        "by_type": dict(by_type),
        "adopted_ids": [row["id"] for row in adopted],
        "rows": [public_row(row) for row in counted],
        "out_of_count": [public_row(row) for row in outside],
        "landuse_recheck": {
            "h1": land["h1"],
            "h2": land["h2"],
            "h3": land["h3"],
            "h4": land["h4"],
            "share_ge5": round(land["share_ge5"], 5),
            "ge5_km2": round(land["ge5_km2"], 3),
            "complement_of_1_2": round(land["complement_of_1_2"], 5),
            "complement_km2": round(land["complement_km2"], 3),
            "agri_remainder_km2": round(land["agri_remainder_km2"], 3),
            "published_agri_to_building_km2": land["published_agri_to_building_km2"],
            "building_remainder_km2": round(land["building_remainder_km2"], 3),
            "forest_to_building_km2": round(land["forest_to_building_km2"], 3),
            "building_to_forest_cells": land["building_to_forest_cells"],
            "agri_to_forest_cells": land["agri_to_forest_cells"],
            "focus_ge5_both_zero": land["building_ge5"] == 0 and land["agri_ge5"] == 0,
            "mountain_land_share": round(land["mountain_land_share"], 4),
            "mountain_agri_net_km2": round(land["mountain_agri_net_km2"], 3),
            "plain_agri_net_km2": round(land["plain_agri_net_km2"], 3),
            "forestation_rate": round(land["forestation_rate"], 4),
            "forest_net_km2": round(land["forest_net_km2"], 3),
        },
        "annotation": {
            "tiles_requested": anno["anno_tiles_requested"],
            "tiles_ok": anno["anno_tiles_ok"],
            "tiles_failed": anno["anno_tiles_404"],
            "focus_cells_on_failed_tiles": anno["focus_cells_on_failed_tiles"],
            "shrine_annotation_features": anno["shrine_annotation_features"],
            "aerial_tiles_ok": anno["aerial_tiles_ok"],
            "aerial_tiles_failed": anno["aerial_tiles_failed"],
            "aerial_period": anno["aerial_period"],
            "old_topo_acquired": False,
        },
        "catalog": catalog,
        "station_cell_same_building": anno["station_cell_classes"] == "building->building",
        "meiji_promoted_to_lost_shrines": 0,
    }
    blob = json.dumps(public, ensure_ascii=False, indent=2)
    names = {row["name"] for row in rows}
    names.add(prior["name"])
    for name in names:
        if name and name in blob:
            raise SystemExit("public json contains a candidate name")
    if COORD_RE.search(blob):
        raise SystemExit("public json contains a coordinate-like number")
    PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC.write_text(blob + "\n", encoding="utf-8")
    write_private(rows, prior, anno, catalog)
    prov = SUPP / "provenance_supplemental.jsonl"
    records = []
    for path in sorted(SUPP.rglob("*")):
        if not path.is_file() or path.name == "provenance_supplemental.jsonl":
            continue
        records.append(
            {
                "path": str(path.relative_to(SUPP)),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
                "retrieved": RETRIEVED,
            }
        )
    for path in sorted(WORK.rglob("*")):
        if path.is_file() and path.suffix in {".geojson", ".png"}:
            records.append(
                {
                    "path": f"gsi/{path.name}",
                    "sha256": sha256_file(path),
                    "bytes": path.stat().st_size,
                    "retrieved": RETRIEVED,
                    "license": "政府標準利用規約（第2.0版）。出典: 国土地理院",
                    "url_pattern": ANNO_URL if path.suffix == ".geojson" else AERIAL_URL,
                    "period": "現行注記" if path.suffix == ".geojson" else "1961-1969",
                }
            )
    prov.write_text(
        "".join(json.dumps(rec, ensure_ascii=False) + "\n" for rec in records),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "rows": len(rows),
                "adopted": [row["id"] for row in adopted],
                "anno_failed_tiles": anno["anno_tiles_404"],
                "failed_focus_cells": anno["focus_cells_on_failed_tiles"],
                "shrine_notes": anno["shrine_annotation_features"],
                "aerial_ok": anno["aerial_tiles_ok"],
                "station_cell": anno["station_cell_classes"],
                "share_ge5": round(land["share_ge5"], 5),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
