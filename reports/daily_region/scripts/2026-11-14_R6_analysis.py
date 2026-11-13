"""R6（津久井、旧津久井郡4町）3週目。2026-11-14。

主目的は、外部調査のリードを3軸で評価し、企画展の画像が旧津久井郡の
合祀文書かを確認すること。土地利用は、2026-11-07 の申し送りが
既存集計でまだ言えるかの確認に限る。

公開 JSON には件数、市区町村、候補 ID、3軸、確度、リード ID だけを書く。
名称と緯度経度は、環境変数で渡した非公開 CSV から読み、
/opt/cursor/artifacts/kanagawa_private/2026-11-14_R6/ に出す。
スクリプトには地点の緯度経度も候補名も書かない。

評価は件数を数える前に固定した。

- 過去に存在した根拠、廃止・消失の根拠、物理的遺構が残る可能性は別の欄にする。
- 現行の地図に名称が無いこと、森林化、神社庁の検索に出ないことは、消失の根拠にしない。
- 座標は、入力 CSV に列があるときだけ読む。字名や住所からは点を作らない。
- 総合確度の高は、旧版地形図の記号を見ていない限り付けない。今日は付けない。
- 遷座先、合祀先、現在の社は廃社にしない。役割がそれらなら廃止は「なし」、状態は負例。
- 旧社地と遷座先は別の行にする。
- 探訪記と個人サイトは二次。原書を開いていなければ、その書名を本文を読んだことにしない。
- 画像 PDF の OCR が崩れているときは、社名の新規採番に使わない。
- 通行規制は路線の廃止ではない。
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
FUDOKI_DIR = Path(os.environ.get("FUDOKI_IMAGE_DIR", ""))
OUT_PRIV = Path("/opt/cursor/artifacts/kanagawa_private/2026-11-14_R6")
PUBLIC = ROOT / "reports" / "daily_region" / "data" / "2026-11-14_R6_week3_public.json"
RESULTS = ROOT / "reports" / "phase1c2_results.json"
WORK = Path(os.environ.get("R6_WORK_DIR", "/tmp/r6_20261114_fetch"))
SUPPLEMENTAL = Path(
    "/opt/cursor/artifacts/kanagawa_private/supplemental_2026-11-14.tar.gz"
)
RETRIEVED = "2026-11-14"
UA = "kanagawa-ruins-search/2026-11-14"
GE5_MAX = 0.20
COMPLEMENT_GAP = 0.10
AUX_GAP_KM2 = 0.05
PUBLISHED_AGRI_TO_BUILDING_KM2 = 0.70
FLOW_TOL_KM2 = 0.01
COORD_RE = re.compile(r"(?:3[4-6]|13[89])\.[0-9]{3,}")
NEGATIVE_ROLES = {"遷座先", "合祀先", "現社"}
ALLOWED_STATUS = {"新規", "既存", "再検証", "棄却", "負例", "状態変化"}
ALLOWED_AXIS = {"強", "中", "低", "なし", "未確認", "対象外"}


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


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
        "landscape_names": sorted({idx[1] for idx in rl["index"] if idx[0] == "R6_tsukui"}),
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
    max_out = max(flows, key=lambda k: flows[k]["outflow_km2"])
    max_rate = max(flows, key=lambda k: flows[k]["forestation_rate"])
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


def prior_data_rows() -> int:
    with PRIOR_CANDIDATES.open(encoding="utf-8", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def osm_name_hits(names: list[str]) -> tuple[int, int, dict[str, int]]:
    import pandas as pd

    frames = []
    for path in sorted(OSM_DIR.glob("osm__worship__*.parquet")):
        frames.append(pd.read_parquet(path, columns=["osm_id", "name"]))
    if not frames:
        raise SystemExit("no worship parquet")
    frame = pd.concat(frames, ignore_index=True)
    unique = frame.drop_duplicates("osm_id")
    counts = {}
    for name in names:
        if not name:
            counts[name] = 0
            continue
        counts[name] = int((unique["name"].fillna("") == name).sum())
    return int(len(frame)), int(unique["osm_id"].nunique()), counts


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
            with urllib.request.urlopen(req, timeout=60) as resp:
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


def add_fudoki(records: list[dict]) -> None:
    if not FUDOKI_DIR or not FUDOKI_DIR.exists():
        return
    for path in sorted(FUDOKI_DIR.rglob("*.jpg")):
        rel = path.relative_to(FUDOKI_DIR)
        dest = WORK / "fudoki" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        raw = path.read_bytes()
        dest.write_bytes(raw)
        records.append(
            {
                "dest": f"fudoki/{rel.as_posix()}",
                "url": "https://dl.ndl.go.jp/pid/763971",
                "retrieved": RETRIEVED,
                "sha256": sha256_bytes(raw),
                "bytes": len(raw),
                "http_status": 200,
                "license": "https://dl.ndl.go.jp/ja/help_iiif",
                "era": "編纂は天保期、この画像は明治21年刊の第5輯",
                "note": "NDL IIIF。縦書きの社名行は本文として採用していない。",
                "error": None,
            }
        )


def validate_leads(rows: list[dict], hits: dict[str, int]) -> list[dict]:
    seen = set()
    out = []
    for index, row in enumerate(rows, start=1):
        cid = row["id"].strip()
        if cid in seen:
            raise SystemExit(f"duplicate id {cid}")
        seen.add(cid)
        expected = f"R6-{index:03d}"
        if cid != expected:
            raise SystemExit(f"id {cid} is not {expected}")
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
        if COORD_RE.search(json.dumps(row, ensure_ascii=False)):
            raise SystemExit(f"coordinate-like text in lead {cid}")
        copied = dict(row)
        copied["osm_name_hits"] = hits.get(row.get("osm_match_name", ""), 0)
        copied["region"] = "R6"
        out.append(copied)
    return out


def write_private_csv(rows: list[dict]) -> None:
    OUT_PRIV.mkdir(parents=True, exist_ok=True)
    fields = [
        "id",
        "status",
        "region",
        "muni_name",
        "name",
        "category",
        "role",
        "axis_existed",
        "axis_abolished",
        "axis_remains",
        "confidence",
        "lead_id",
        "source",
        "retrieved",
        "license",
        "era",
        "verification",
        "reject_reason",
        "osm_match_name",
        "osm_name_hits",
    ]
    with (OUT_PRIV / "candidates.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_public(rows: list[dict], land: dict, bunka: tuple[int, int], osm_rows: int, osm_unique: int, prior_n: int) -> None:
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
            }
        )
    by_status = dict(Counter(row["status"] for row in rows))
    by_category = dict(Counter(row["category"] for row in rows))
    payload = {
        "date": "2026-11-14",
        "region": "R6",
        "week": 3,
        "elapsed_days": 19,
        "day_number": 20,
        "rotation": "19 mod 7 = 5, floor(19/7)+1 = 3",
        "prior_candidate_rows": prior_n,
        "adopted_lost_sites": 0,
        "high_confidence": 0,
        "rows": public_rows,
        "by_status": by_status,
        "by_category": by_category,
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
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if COORD_RE.search(text):
        raise SystemExit("public json contains a coordinate-like number")
    for row in public_rows:
        if "name" in row or "lat" in row or "lon" in row:
            raise SystemExit("public row has a name or coordinate field")
    PUBLIC.write_text(text + "\n", encoding="utf-8")


def write_supplemental(records: list[dict]) -> None:
    prov = WORK / "provenance_supplemental.jsonl"
    with prov.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    SUPPLEMENTAL.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(SUPPLEMENTAL, "w:gz") as tar:
        tar.add(WORK, arcname="supplemental_2026-11-14")


def main() -> None:
    tables = load_tables()
    land = landuse_check(tables)
    bunka = bunkazai_lat_nonempty()
    if bunka[1] != 0:
        raise SystemExit(f"bunkazai latitude nonempty {bunka[1]}")
    prior_n = prior_data_rows()
    if prior_n != 0:
        raise SystemExit(f"prior R6 rows {prior_n}; ids would collide")
    with LEADS_CSV.open(encoding="utf-8", newline="") as handle:
        leads = list(csv.DictReader(handle))
    names = [row.get("osm_match_name", "") for row in leads]
    osm_rows, osm_unique, hits = osm_name_hits(names)
    rows = validate_leads(leads, hits)
    write_private_csv(rows)
    write_public(rows, land, bunka, osm_rows, osm_unique, prior_n)
    findings = FINDINGS_SRC.read_text(encoding="utf-8")
    if COORD_RE.search(findings):
        raise SystemExit("findings contain a coordinate-like number")
    (OUT_PRIV / "findings.md").write_text(findings, encoding="utf-8")
    records = fetch_all()
    add_fudoki(records)
    write_supplemental(records)
    failed = [r for r in records if r["error"]]
    print(
        json.dumps(
            {
                "rows": len(rows),
                "by_status": dict(Counter(r["status"] for r in rows)),
                "bunkazai": bunka,
                "osm_rows": osm_rows,
                "osm_unique": osm_unique,
                "fetch_ok": len(records) - len(failed),
                "fetch_fail": len(failed),
                "share_ge5": land["share_ge5"],
                "residual": land["residual_unnamed_km2"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
