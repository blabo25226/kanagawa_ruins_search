"""R7（県西）4週目。2026-11-22。

主目的は、前回申し送りの未確認を公式の公開資料で試し、
新しい証拠がある行だけを再検証することである。
土地利用は 2026-11-15 の申し送りがまだ成り立つかの確認に限る。

公開 JSON には件数、市区町村、候補 ID、3軸、確度、リード ID だけを書く。
名称と緯度経度は、環境変数で渡した非公開ファイルから読み、
/opt/cursor/artifacts/kanagawa_private/2026-11-22_R7/ に出す。
スクリプトには地点の緯度経度も候補名も書かない。

評価は件数を数える前に固定した。

- 過去に存在した根拠、廃止・消失の根拠、物理的遺構が残る可能性は別の欄にする。
- 現行の地図に名称が無いこと、森林化、神社庁の検索に出ないことは、消失の根拠にしない。
- 座標は、入力 CSV に列があるときだけ読む。字名や住所からは点を作らない。
- 総合確度の高は、旧版地形図の記号を見ていない限り付けない。今日は付けない。
- 遷座先、合祀先、分離後の復祀、現在の社、現在の史跡道は廃社・廃道にしない。
- 合祀された側は、分離の文が無ければ状態変化にする。廃社にはしない。
- 明細帳の目録、合祀の記録、駅名の列挙だけでは新規の廃社・廃駅にしない。
- 探訪記、投稿、空撮、歩行記録は二次である。画像は保存しない。
- 画像 PDF のテキスト層が空のときは、地区名の分割に使わない。
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
JUDGMENTS = Path(os.environ["PRIVATE_JUDGMENTS_CSV"])
PRIOR = Path(os.environ["PRIVATE_PRIOR_CANDIDATES"])
ATTEMPTS = Path(os.environ["ATTEMPT_SUMMARY_JSON"])
OUT_PRIV = Path("/opt/cursor/artifacts/kanagawa_private/2026-11-22_R7")
PUBLIC = ROOT / "reports" / "daily_region" / "data" / "2026-11-22_R7_week4_public.json"
RESULTS = ROOT / "reports" / "phase1c2_results.json"
START = date(2026, 10, 26)
TODAY = date(2026, 11, 22)
REGIONS = ["R1", "R2", "R3", "R4", "R5", "R6", "R7"]
COORD_RE = re.compile(r"(?:3[4-6]|13[89])\.[0-9]{3,}")
AXIS_FIELDS = ("axis_existence", "axis_loss", "axis_remains", "confidence", "status", "type")
PUBLISHED_AGRI_TO_BUILDING_KM2 = 0.49
GE5_CITED = 0.113
GE5_MATCH = 0.01
COMPLEMENT_GAP = 0.10
MOUNTAIN = ("山北町", "松田町")
PLAIN = ("中井町", "大井町", "開成町")
MISSING = ("小田原市", "箱根町", "真鶴町", "湯河原町")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def rotation() -> dict:
    elapsed = (TODAY - START).days
    return {
        "start": START.isoformat(),
        "date": TODAY.isoformat(),
        "elapsed_days": elapsed,
        "day_number": elapsed + 1,
        "week": elapsed // 7 + 1,
        "mod": elapsed % 7,
        "region": REGIONS[elapsed % 7],
    }


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
    mcols = data["aggregates"]["municipality"]["columns"]
    munis = []
    for row in data["aggregates"]["municipality"]["data"]:
        rec = dict(zip(mcols, row))
        if rec.get("region") == "R7_kensei":
            munis.append(rec)
    return {"r7": reg["R7_kensei"], "comp": comp["R7_kensei"], "focus": focus, "munis": munis}


def landuse_check(tables: dict) -> dict:
    r7 = tables["r7"]
    comp = tables["comp"]
    focus = tables["focus"]
    s1, s2, s5 = comp["share_1"], comp["share_2"], comp["share_>=5"]
    complement = 1 - s1 - s2
    agri_gain = r7["agri_net_change_km2"] + r7["agri_loss_km2"]
    forest_to_agri = focus["agri->forest"]["reverse_area_km2"]
    waste_to_agri = focus["agri->wasteland"]["reverse_area_km2"]
    agri_remainder = agri_gain - forest_to_agri - waste_to_agri
    b_gain = r7["building_gain_km2"]
    forest_to_b = focus["building->forest"]["reverse_area_km2"]
    waste_to_b = focus["building->wasteland"]["reverse_area_km2"]
    b_remainder = b_gain - forest_to_b - waste_to_b

    def group_sum(names, key):
        return sum(row[key] for row in tables["munis"] if row["muni_name"] in names)

    plain_agri_net = group_sum(PLAIN, "agri_net_change_km2")
    mountain_agri_net = group_sum(MOUNTAIN, "agri_net_change_km2")
    checks = {
        "share_ge5": s5,
        "share_ge5_km2": comp["changed_km2"] * s5,
        "complement_1_2": complement,
        "agri_remainder_km2": agri_remainder,
        "building_remainder_km2": b_remainder,
        "published_agri_to_building_km2": PUBLISHED_AGRI_TO_BUILDING_KM2,
        "plain_agri_net_km2": plain_agri_net,
        "mountain_agri_net_km2": mountain_agri_net,
        "agri_to_forest_cells": focus["agri->forest"]["cells"],
        "building_to_forest_cells": focus["building->forest"]["cells"],
        "missing_muni_rows": sum(1 for row in tables["munis"] if row["muni_name"] in MISSING),
    }
    if abs(s5 - GE5_CITED) >= GE5_MATCH:
        raise SystemExit("5セル以上の割合が週1の引用と合わない")
    if (complement - s5) < COMPLEMENT_GAP:
        raise SystemExit("補集合と5セル以上の差が週2の関係を外れた")
    if abs(agri_remainder - PUBLISHED_AGRI_TO_BUILDING_KM2) < 0.01:
        raise SystemExit("農地の残りを公開表の減少先と等置してしまった")
    if not (plain_agri_net > mountain_agri_net):
        raise SystemExit("平野側の農地純増が山間側を上回る関係が崩れた")
    if checks["missing_muni_rows"] != 0:
        raise SystemExit("未収録の市町が市町村行に現れた")
    return checks


def public_row(row: dict, changed: bool) -> dict:
    return {
        "id": row["id"],
        "status": row["status"],
        "muni_name": row["muni_name"],
        "category": row["type"],
        "role": row.get("role", ""),
        "axis_existed": row["axis_existence"],
        "axis_abolished": row["axis_loss"],
        "axis_remains": row["axis_remains"],
        "confidence": row["confidence"],
        "lead_id": row.get("lead_id", ""),
        "in_region_count": row.get("in_r7_count", ""),
        "axis_changed_today": "1" if changed else "0",
    }


def main() -> None:
    rot = rotation()
    if rot["region"] != "R7" or rot["week"] != 4 or rot["elapsed_days"] != 27:
        raise SystemExit(f"rotation mismatch: {rot}")
    prior = load_csv(PRIOR)
    current = load_csv(JUDGMENTS)
    prior_by = {row["id"]: row for row in prior}
    if len(prior_by) != 22:
        raise SystemExit("prior R7 rows are not 22")
    ids = [row["id"] for row in current]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate id")
    expected_prior = [row["id"] for row in prior]
    known = [f"R7-{i:03d}" for i in range(1, 21)] + ["HOLD-1", "HOLD-2"]
    if sorted(expected_prior) != sorted(known) or len(expected_prior) != 22:
        raise SystemExit("prior id set changed")
    expected_new = [f"R7-{i:03d}" for i in range(21, 29)]
    if ids != expected_prior + expected_new:
        raise SystemExit("id sequence is not prior plus R7-021 through R7-028")
    changed = []
    for row in current:
        if row["id"] not in prior_by:
            continue
        old = prior_by[row["id"]]
        if any(row[field] != old[field] for field in AXIS_FIELDS):
            changed.append(row["id"])
    if changed:
        raise SystemExit("existing axes changed without a recorded evidence file rule")
    high = [row["id"] for row in current if row["confidence"] == "高"]
    if high:
        raise SystemExit("high confidence is not allowed without an old-map symbol")
    adopted_shrines = [
        row["id"]
        for row in current
        if row["type"] == "神社"
        and row["status"] in {"新規", "再検証", "既存"}
        and row["confidence"] in {"高", "中", "低"}
    ]
    if adopted_shrines:
        raise SystemExit("an adopted lost shrine was created")
    in_count = [row for row in current if row.get("in_r7_count") == "yes"]
    attempts = json.loads(ATTEMPTS.read_text(encoding="utf-8"))
    land = landuse_check(load_results())
    public = {
        "date": TODAY.isoformat(),
        "region": "R7",
        "week": rot["week"],
        "elapsed_days": rot["elapsed_days"],
        "day_number": rot["day_number"],
        "rotation": "27 mod 7 = 6, floor(27/7)+1 = 4",
        "prior_candidate_rows": len(prior),
        "rows_today": len(current),
        "in_region_count_rows": len(in_count),
        "outside_count_rows": len(current) - len(in_count),
        "new_ids": expected_new,
        "axis_updates": len(changed),
        "adopted_lost_shrines": 0,
        "high_confidence": 0,
        "by_status": dict(Counter(row["status"] for row in current)),
        "by_type": dict(Counter(row["type"] for row in current)),
        "by_confidence": dict(Counter(row["confidence"] for row in current)),
        "new_by_status": dict(Counter(row["status"] for row in current if row["id"] in expected_new)),
        "landuse_reconfirmed": {
            "share_ge5": round(land["share_ge5"], 4),
            "complement_1_2": round(land["complement_1_2"], 4),
            "agri_remainder_km2": round(land["agri_remainder_km2"], 3),
            "building_remainder_km2": round(land["building_remainder_km2"], 3),
            "published_agri_to_building_km2": land["published_agri_to_building_km2"],
            "plain_agri_net_exceeds_mountain": land["plain_agri_net_km2"] > land["mountain_agri_net_km2"],
            "agri_to_forest_cells": land["agri_to_forest_cells"],
            "building_to_forest_cells": land["building_to_forest_cells"],
        },
        "source_attempts": attempts,
        "rows": [public_row(row, False) for row in current],
    }
    blob = json.dumps(public, ensure_ascii=False, indent=2)
    if COORD_RE.search(blob):
        raise SystemExit("public json contains a coordinate-like number")
    for row in current:
        name = (row.get("name") or "").strip()
        if name and name in blob:
            raise SystemExit("public json contains a candidate name")
    PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC.write_text(blob + "\n", encoding="utf-8")
    OUT_PRIV.mkdir(parents=True, exist_ok=True)
    target = OUT_PRIV / "candidates.csv"
    target.write_text(JUDGMENTS.read_text(encoding="utf-8"), encoding="utf-8")
    print(
        json.dumps(
            {
                "rows": len(current),
                "new": expected_new,
                "axis_updates": changed,
                "high": high,
                "adopted_shrines": adopted_shrines,
                "by_status": public["by_status"],
                "new_by_status": public["new_by_status"],
                "landuse": public["landuse_reconfirmed"],
                "candidates_sha256": sha256_file(target),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
