"""R6（津久井、旧津久井郡4町）4週目。2026-11-21。

主目的は、ダム湖の水没・移転の公式記録を集落名まで読めるか試し、
前回申し送りの未開地区を3軸で評価すること。
土地利用は、2026-11-07 の申し送りが既存集計でまだ言えるかの確認に限る。

公開 JSON には件数、市区町村、候補 ID、3軸、確度、リード ID だけを書く。
名称と緯度経度は、環境変数で渡した非公開 CSV から読み、
/opt/cursor/artifacts/kanagawa_private/2026-11-21_R6/ に出す。
スクリプトには地点の緯度経度も候補名も書かない。取得 URL は
環境変数 FETCH_MANIFEST の非公開 JSON から読む。

評価は件数を数える前に固定した。

- 過去に存在した根拠、廃止・消失の根拠、物理的遺構が残る可能性は別の欄にする。
- 現行の地図に名称が無いこと、森林化、神社庁の検索に出ないことは、消失の根拠にしない。
- 座標は、入力 CSV に列があるときだけ読む。字名や住所からは点を作らない。
- 総合確度の高は、旧版地形図の記号を見ていない限り付けない。今日は付けない。
- 遷座先、合祀先、現在の社は廃社にしない。役割がそれらなら廃止は「なし」、状態は負例。
- 旧社地と遷座先は別の行にする。
- 探訪記と個人サイトは二次。原書を開いていなければ、その書名を本文を読んだことにしない。
- 画像 PDF のテキスト層が空のときは、社名の新規採番に使わない。
- 通行規制は路線の廃止ではない。
- ダムの公式頁が戸数や面積だけで集落名を分けないときは、その総数を集落の件数にしない。
- 市町村に分かれていない移転戸数は、R6 の件数にしない。
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import tarfile
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LEADS_CSV = Path(os.environ["PRIVATE_LEADS_CSV"])
PRIOR_CANDIDATES = Path(os.environ["PRIVATE_PRIOR_CANDIDATES"])
BUNKAZAI_CSV = Path(os.environ["BUNKAZAI_CSV"])
FOCUS_CSV = Path(os.environ["FOCUS_CSV"])
OSM_DIR = Path(os.environ["OSM_WORSHIP_DIR"])
FETCH_MANIFEST = Path(os.environ["FETCH_MANIFEST"])
FINDINGS_SRC = Path(os.environ["PRIVATE_FINDINGS_MD"])
OUT_PRIV = Path("/opt/cursor/artifacts/kanagawa_private/2026-11-21_R6")
PUBLIC = ROOT / "reports" / "daily_region" / "data" / "2026-11-21_R6_week4_public.json"
RESULTS = ROOT / "reports" / "phase1c2_results.json"
WORK = Path(os.environ.get("R6_WORK_DIR", "/tmp/r6_20261121_fetch"))
SUPPLEMENTAL_DIR = Path("/opt/cursor/artifacts/kanagawa_private")
RETRIEVED = "2026-11-21"
UA = "kanagawa-ruins-search/2026-11-21"
GE5_MAX = 0.20
COMPLEMENT_GAP = 0.10
AUX_GAP_KM2 = 0.05
PUBLISHED_AGRI_TO_BUILDING_KM2 = 0.70
FLOW_TOL_KM2 = 0.01
PART_LIMIT = 19 * 1024 * 1024
COORD_RE = re.compile(r"(?:3[4-6]|13[89])\.[0-9]{3,}")
NEGATIVE_ROLES = {"遷座先", "合祀先", "現社"}
ALLOWED_STATUS = {"新規", "既存", "再検証", "棄却", "負例", "状態変化"}
ALLOWED_AXIS = {"強", "中", "低", "なし", "未確認", "対象外"}
PRIOR_EXPECTED = {
    "R6-001": ("負例", "遷座先", "なし"),
    "R6-002": ("状態変化", "旧社地", "中"),
    "R6-003": ("状態変化", "通行止め", "なし"),
    "R6-004": ("棄却", "動画", "未確認"),
    "R6-005": ("棄却", "旧橋", "未確認"),
    "R6-006": ("負例", "遷座先", "なし"),
    "R6-007": ("状態変化", "旧社地", "中"),
    "R6-008": ("状態変化", "旧社地", "中"),
    "R6-009": ("負例", "現社", "なし"),
    "R6-010": ("負例", "合祀先", "なし"),
    "R6-011": ("負例", "遷座先", "なし"),
    "R6-012": ("状態変化", "旧社地候補", "未確認"),
    "R6-013": ("状態変化", "祭祀場", "中"),
    "R6-014": ("状態変化", "旧社地", "中"),
    "R6-015": ("負例", "現社", "なし"),
}


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_tables() -> dict:
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


def landuse_check(tables: dict) -> dict:
    r6 = tables["reg"]
    comp = tables["comp"]
    s1, s2, s34, s5 = (
        comp["share_1"],
        comp["share_2"],
        comp["share_3-4"],
        comp["share_>=5"],
    )
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
        }
    sum_out = sum(v["outflow_km2"] for v in flows.values())
    if abs(sum_out - outflow) > FLOW_TOL_KM2:
        raise SystemExit(f"forest outflow identity failed: {sum_out} {outflow}")
    max_out = max(flows, key=lambda key: flows[key]["outflow_km2"])
    max_rate = max(flows, key=lambda key: flows[key]["forestation_rate"])
    h1 = (
        PUBLISHED_AGRI_TO_BUILDING_KM2 > a2f
        and PUBLISHED_AGRI_TO_BUILDING_KM2 < loss
        and abs(residual - PUBLISHED_AGRI_TO_BUILDING_KM2) >= AUX_GAP_KM2
    )
    h2 = max_out != max_rate and abs(sum_out - outflow) <= FLOW_TOL_KM2
    focus = tables["focus"]
    h3 = (
        s5 < GE5_MAX
        and (complement - s5) >= COMPLEMENT_GAP
        and focus["building->forest"]["size_>=5_share"] == 0
        and focus["agri->forest"]["size_>=5_share"] == 0
    )
    h4 = set(flows) == {"urban", "agri_mixed", "other_mixed", "forest_dominant"}
    if not all((h1, h2, h3, h4)):
        raise SystemExit(f"handoff assertions failed: {h1, h2, h3, h4}")
    if tables["has_r6_coverage_row"]:
        raise SystemExit("coverage has an R6 row; week-1 assertion failed")
    with FOCUS_CSV.open(encoding="utf-8", newline="") as handle:
        focus_rows = [
            row
            for row in csv.DictReader(handle)
            if row.get("region") == "R6_tsukui"
            and row.get("transition") in {"building->forest", "agri->forest"}
        ]
    if len(focus_rows) != 2:
        raise SystemExit(f"focus csv rows {len(focus_rows)}")
    for row in focus_rows:
        if float(row["size_>=5_share"]) != 0:
            raise SystemExit("focus ge5 is no longer 0")
    return {
        "h1": h1,
        "h2": h2,
        "h3": h3,
        "h4": h4,
        "agri_loss_km2": loss,
        "agri_to_forest_km2": a2f,
        "residual_unnamed_km2": residual,
        "published_agri_to_building_km2": PUBLISHED_AGRI_TO_BUILDING_KM2,
        "residual_minus_published_km2": residual - PUBLISHED_AGRI_TO_BUILDING_KM2,
        "forest_inflow_km2": inflow,
        "forest_net_km2": forest_net,
        "forest_outflow_km2": outflow,
        "max_outflow_landscape": max_out,
        "max_forestation_rate_landscape": max_rate,
        "share_ge5": s5,
        "ge5_km2": s5 * changed,
        "complement_of_1_2": complement,
        "complement_km2": complement * changed,
        "gap_pp": (complement - s5) * 100,
        "share_3_4": s34,
        "building_to_forest_cells": focus["building->forest"]["cells"],
        "agri_to_forest_cells": focus["agri->forest"]["cells"],
        "building_max_component": focus["building->forest"]["max_component_cells"],
        "agri_max_component": focus["agri->forest"]["max_component_cells"],
        "n_cells": r6["n_cells"],
        "land_km2": r6["land_km2"],
    }


def bunkazai_lat_nonempty() -> tuple[int, int]:
    with BUNKAZAI_CSV.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    nonempty = 0
    for row in rows:
        raw = (row.get("緯度") or "").strip()
        if raw and raw.lower() != "nan":
            nonempty += 1
    return len(rows), nonempty


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def osm_name_hits(names: list[str]) -> tuple[int, int, dict[str, int]]:
    import duckdb

    paths = sorted(OSM_DIR.glob("osm__worship__*.parquet"))
    if not paths:
        raise SystemExit("no worship parquet")
    con = duckdb.connect()
    union = " union all ".join(
        f"select osm_id, name from read_parquet('{path}')" for path in paths
    )
    rows, unique = con.execute(
        f"select count(*), count(distinct osm_id) from ({union})"
    ).fetchone()
    counts = {}
    for name in names:
        if not name:
            counts[name] = 0
            continue
        counts[name] = con.execute(
            f"select count(*) from (select distinct osm_id, name from ({union})) "
            "where name = ?",
            [name],
        ).fetchone()[0]
    return int(rows), int(unique), counts


def check_row(row: dict, expected_id: str) -> None:
    cid = row["id"].strip()
    if cid != expected_id:
        raise SystemExit(f"id {cid} is not {expected_id}")
    status = row["status"].strip()
    role = row["role"].strip()
    if status not in ALLOWED_STATUS:
        raise SystemExit(f"bad status {status}")
    for axis in ("axis_existed", "axis_abolished", "axis_remains"):
        if row[axis].strip() not in ALLOWED_AXIS:
            raise SystemExit(f"bad axis {cid} {axis}")
    if row["confidence"].strip() == "高":
        raise SystemExit("high confidence is not allowed today")
    if role in NEGATIVE_ROLES:
        if row["axis_abolished"].strip() != "なし" or status != "負例":
            raise SystemExit(f"{cid} destination registered as lost")
    if status == "棄却" and row["confidence"].strip() != "棄却":
        raise SystemExit(f"{cid} reject confidence")
    if (row.get("lat") or "").strip() or (row.get("lon") or "").strip():
        raise SystemExit(f"{cid} has a coordinate; addresses are not geocoded")
    blob = json.dumps(row, ensure_ascii=False)
    if COORD_RE.search(blob):
        raise SystemExit(f"coordinate-like text in row {cid}")


def validate(prior: list[dict], new_rows: list[dict], hits: dict[str, int]) -> list[dict]:
    if len(prior) != 15:
        raise SystemExit(f"prior rows {len(prior)}")
    out = []
    for index, row in enumerate(prior, start=1):
        expected = f"R6-{index:03d}"
        check_row(row, expected)
        status, role, abolished = PRIOR_EXPECTED[expected]
        if (
            row["status"].strip() != status
            or row["role"].strip() != role
            or row["axis_abolished"].strip() != abolished
        ):
            raise SystemExit(f"prior row changed {expected}")
        copied = dict(row)
        copied["lat"] = ""
        copied["lon"] = ""
        copied["osm_name_hits"] = hits.get(row.get("osm_match_name", ""), 0)
        copied["axis_changed_today"] = "0"
        out.append(copied)
    for offset, row in enumerate(new_rows, start=16):
        expected = f"R6-{offset:03d}"
        check_row(row, expected)
        copied = dict(row)
        copied["lat"] = ""
        copied["lon"] = ""
        copied["region"] = "R6"
        copied["osm_name_hits"] = hits.get(row.get("osm_match_name", ""), 0)
        copied["axis_changed_today"] = "0"
        out.append(copied)
    ids = [row["id"] for row in out]
    if ids != [f"R6-{i:03d}" for i in range(1, len(out) + 1)]:
        raise SystemExit("ids are not contiguous")
    if any(row["confidence"] == "高" for row in out):
        raise SystemExit("high confidence")
    return out


def write_private_csv(rows: list[dict]) -> None:
    OUT_PRIV.mkdir(parents=True, exist_ok=True)
    fields = [
        "id",
        "status",
        "type",
        "region",
        "muni_name",
        "name",
        "lat",
        "lon",
        "category",
        "role",
        "axis_existence",
        "axis_loss",
        "axis_remains",
        "axis_existed",
        "axis_abolished",
        "confidence",
        "lead_id",
        "sources",
        "source",
        "retrieved",
        "license",
        "period",
        "era",
        "verification",
        "notes",
        "reject_reason",
        "osm_match_name",
        "osm_name_hits",
        "axis_changed_today",
    ]
    prepared = []
    for row in rows:
        item = dict(row)
        item["type"] = row.get("category", "")
        item["axis_existence"] = row.get("axis_existed", "")
        item["axis_loss"] = row.get("axis_abolished", "")
        item["sources"] = row.get("source", "")
        item["period"] = row.get("era", "")
        note = (row.get("verification") or "").strip()
        reason = (row.get("reject_reason") or "").strip()
        item["notes"] = note if not reason else f"{note} 棄却理由: {reason}"
        item["lat"] = ""
        item["lon"] = ""
        prepared.append(item)
    with (OUT_PRIV / "candidates.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(prepared)


def write_public(
    rows: list[dict],
    land: dict,
    bunka: tuple[int, int],
    osm_rows: int,
    osm_unique: int,
    names: list[str],
) -> None:
    public_rows = []
    for row in rows:
        public_rows.append(
            {
                "id": row["id"],
                "status": row["status"],
                "muni_name": row["muni_name"],
                "category": row["category"],
                "role": row["role"],
                "axis_existed": row["axis_existed"],
                "axis_abolished": row["axis_abolished"],
                "axis_remains": row["axis_remains"],
                "confidence": row["confidence"],
                "lead_id": row["lead_id"],
                "axis_changed_today": row["axis_changed_today"],
            }
        )
    new_ids = [row["id"] for row in rows if row["id"] >= "R6-016"]
    payload = {
        "date": "2026-11-21",
        "region": "R6",
        "week": 4,
        "elapsed_days": 26,
        "day_number": 27,
        "rotation": "26 mod 7 = 5, floor(26/7)+1 = 4",
        "prior_candidate_rows": 15,
        "new_ids": new_ids,
        "axis_updates": 0,
        "adopted_lost_shrines": 0,
        "adopted_lost_settlements": 0,
        "high_confidence": 0,
        "rows": public_rows,
        "by_status": dict(Counter(row["status"] for row in rows)),
        "by_category": dict(Counter(row["category"] for row in rows)),
        "landuse_handoff_still_holds": True,
        "landuse": {
            "land_km2": land["land_km2"],
            "n_cells": land["n_cells"],
            "agri_loss_km2": land["agri_loss_km2"],
            "agri_to_forest_km2": land["agri_to_forest_km2"],
            "residual_unnamed_km2": land["residual_unnamed_km2"],
            "published_agri_to_building_km2": land["published_agri_to_building_km2"],
            "residual_minus_published_km2": land["residual_minus_published_km2"],
            "forest_inflow_km2": land["forest_inflow_km2"],
            "forest_net_km2": land["forest_net_km2"],
            "forest_outflow_km2": land["forest_outflow_km2"],
            "max_outflow_landscape": land["max_outflow_landscape"],
            "max_forestation_rate_landscape": land["max_forestation_rate_landscape"],
            "share_ge5": land["share_ge5"],
            "ge5_km2": land["ge5_km2"],
            "complement_of_1_2": land["complement_of_1_2"],
            "complement_km2": land["complement_km2"],
            "building_to_forest_cells": land["building_to_forest_cells"],
            "agri_to_forest_cells": land["agri_to_forest_cells"],
            "building_max_component": land["building_max_component"],
            "agri_max_component": land["agri_max_component"],
            "focus_ge5": 0,
        },
        "bunkazai_rows": bunka[0],
        "bunkazai_lat_nonempty": bunka[1],
        "osm_worship_rows_before_cell_clip": osm_rows,
        "osm_worship_unique_ids_before_cell_clip": osm_unique,
        "osm_worship_in_r6_cells_week2": 12,
        "osm_r6_cell_clip_rerun": False,
        "old_map_compared": False,
        "fudoki_lines_adopted_as_read": False,
        "shrine_volume_1987_opened": False,
        "town_history_text_opened": False,
        "dam_settlement_ids": 0,
        "image_pamphlet_text_layer_empty": True,
        "image_pamphlet_names_transcribed": False,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if COORD_RE.search(text):
        raise SystemExit("public json contains a coordinate-like number")
    for name in names:
        if name and name in text:
            raise SystemExit("public json contains a candidate name")
    for row in public_rows:
        if "name" in row or "lat" in row or "lon" in row:
            raise SystemExit("public row has a name or coordinate field")
    PUBLIC.write_text(text + "\n", encoding="utf-8")


def fetch_all() -> list[dict]:
    WORK.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(FETCH_MANIFEST.read_text(encoding="utf-8"))
    records = []
    for item in manifest:
        dest = WORK / item["dest"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(
            item["url"], headers={"User-Agent": UA, "Accept": "*/*"}
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                raw = resp.read()
                status = getattr(resp, "status", 200)
        except Exception as exc:  # noqa: BLE001 — 失敗は未取得として残す
            dest.with_suffix(dest.suffix + ".err").write_text(
                f"{type(exc).__name__}: {exc}\n", encoding="utf-8"
            )
            records.append(
                {
                    "dest": item["dest"],
                    "url": item["url"],
                    "retrieved": RETRIEVED,
                    "sha256": None,
                    "bytes": 0,
                    "http_status": None,
                    "license": item.get("license", ""),
                    "era": item.get("era", ""),
                    "note": item.get("note", ""),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        dest.write_bytes(raw)
        records.append(
            {
                "dest": item["dest"],
                "url": item["url"],
                "retrieved": RETRIEVED,
                "sha256": sha256_bytes(raw),
                "bytes": len(raw),
                "http_status": status,
                "license": item.get("license", ""),
                "era": item.get("era", ""),
                "note": item.get("note", ""),
                "error": None,
            }
        )
    return records


def write_supplemental(records: list[dict]) -> list[str]:
    prov = WORK / "provenance_supplemental.jsonl"
    with prov.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    files = [path for path in sorted(WORK.rglob("*")) if path.is_file()]
    SUPPLEMENTAL_DIR.mkdir(parents=True, exist_ok=True)
    parts: list[list[Path]] = [[]]
    sizes = [0]
    for path in files:
        size = path.stat().st_size
        if parts[-1] and sizes[-1] + size > PART_LIMIT:
            parts.append([])
            sizes.append(0)
        parts[-1].append(path)
        sizes[-1] += size
    written = []
    for index, group in enumerate(parts, start=1):
        name = (
            "supplemental_2026-11-21.tar.gz"
            if len(parts) == 1
            else f"supplemental_2026-11-21_part{index}.tar.gz"
        )
        dest = SUPPLEMENTAL_DIR / name
        with tarfile.open(dest, "w:gz") as tar:
            for path in group:
                tar.add(path, arcname=f"supplemental_2026-11-21/{path.relative_to(WORK)}")
        written.append(str(dest))
    return written


def main() -> None:
    tables = load_tables()
    land = landuse_check(tables)
    bunka = bunkazai_lat_nonempty()
    if bunka != (179, 0):
        raise SystemExit(f"bunkazai changed {bunka}")
    prior = read_csv(PRIOR_CANDIDATES)
    new_rows = read_csv(LEADS_CSV)
    names = [row.get("name", "") for row in prior + new_rows]
    names += [row.get("osm_match_name", "") for row in prior + new_rows]
    source = Path(__file__).read_text(encoding="utf-8")
    for name in names:
        if name and name in source:
            raise SystemExit("script source contains a candidate name")
    osm_rows, osm_unique, hits = osm_name_hits(
        [row.get("osm_match_name", "") for row in prior + new_rows]
    )
    if (osm_rows, osm_unique) != (39, 21):
        raise SystemExit(f"osm counts changed {(osm_rows, osm_unique)}")
    rows = validate(prior, new_rows, hits)
    shrine_lost = [
        row
        for row in rows
        if row["category"] == "神社"
        and row["status"] not in {"負例", "状態変化", "棄却"}
        and row["confidence"] in {"高", "中"}
    ]
    if shrine_lost:
        raise SystemExit("a shrine was adopted as lost")
    write_private_csv(rows)
    write_public(rows, land, bunka, osm_rows, osm_unique, names)
    findings = FINDINGS_SRC.read_text(encoding="utf-8")
    if COORD_RE.search(findings):
        raise SystemExit("findings contain a coordinate-like number")
    OUT_PRIV.mkdir(parents=True, exist_ok=True)
    (OUT_PRIV / "findings.md").write_text(findings, encoding="utf-8")
    records = fetch_all()
    archives = write_supplemental(records)
    failed = [record for record in records if record["error"]]
    print(
        json.dumps(
            {
                "rows": len(rows),
                "by_status": dict(Counter(row["status"] for row in rows)),
                "by_category": dict(Counter(row["category"] for row in rows)),
                "new_ids": [row["id"] for row in rows if row["id"] >= "R6-016"],
                "bunkazai": bunka,
                "osm_rows": osm_rows,
                "osm_unique": osm_unique,
                "fetch_ok": len(records) - len(failed),
                "fetch_fail": len(failed),
                "share_ge5": round(land["share_ge5"], 4),
                "residual": round(land["residual_unnamed_km2"], 3),
                "archives": archives,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
