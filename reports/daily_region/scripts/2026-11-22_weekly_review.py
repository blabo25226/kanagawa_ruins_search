"""Week-4 review and the four-week stock, 2026-11-16 through 2026-11-22.

The script reads private candidate CSV files from a directory passed at
runtime, plus today's candidate CSV. It writes a public JSON of counts,
IDs, municipalities, types and confidence. It does not write coordinates
or candidate names into the public JSON. Names are written only to the
private markdown path.

2026-11-19 and 2026-11-20 were not run. A missing file on those dates is
「未実施」 and is not counted as zero rows. If a CSV appears there, the
script stops instead of filling the gap.
"""

from __future__ import annotations

import csv
import json
import os
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FINDINGS = Path(os.environ["PRIVATE_FINDINGS_DIR"])
TODAY = Path(os.environ["TODAY_CANDIDATES"])
PUBLIC = Path(
    os.environ.get(
        "WEEKLY_PUBLIC_JSON",
        ROOT
        / "reports"
        / "daily_region"
        / "data"
        / "2026-11-22_weekly_review_week4_public.json",
    )
)
PRIVATE_MD = Path(os.environ["WEEKLY_PRIVATE_MD"])
REPORTS = ROOT / "reports" / "daily_region"
COORD_RE = re.compile(r"(?:3[4-6]|13[89])\.[0-9]{3,}")
START = date(2026, 10, 26)
END = date(2026, 11, 22)
REGIONS = ["R1", "R2", "R3", "R4", "R5", "R6", "R7"]
WEEK = [f"2026-11-{day:02d}" for day in range(16, 23)]
PREV = [f"2026-11-{day:02d}" for day in range(9, 16)]
NOT_CONDUCTED = {"2026-11-19", "2026-11-20"}
LATEST = {
    "R1": "2026-11-16",
    "R2": "2026-11-17",
    "R3": "2026-11-18",
    "R4": "2026-11-12",
    "R5": "2026-11-13",
    "R6": "2026-11-21",
    "R7": "2026-11-22",
}
TYPE_MAP = {
    "station": "廃駅・廃線",
    "駅": "廃駅・廃線",
    "廃駅": "廃駅・廃線",
    "信号場": "廃駅・廃線",
    "神社": "廃社",
    "寺院": "廃寺・廃堂",
    "集落": "消失集落",
    "town_name": "消失集落",
    "消失集落": "消失集落",
    "廃道": "廃道",
    "隧道": "隧道",
    "施設": "廃施設",
    "facility": "廃施設",
    "廃施設": "廃施設",
    "鉄道施設": "廃施設",
    "石造物": "石造物",
    "地形": "地形",
}
STATUS_CLASS = {"負例", "状態変化", "棄却", "保留"}


def axis_of(row: dict, *keys: str) -> str:
    for key in keys:
        if row.get(key):
            return row[key]
    return ""


def norm_status(row: dict, day: str) -> str:
    status = (row.get("status") or "").strip()
    outcome = (row.get("outcome") or "").strip()
    if status:
        return status
    if outcome == "維持":
        return "再検証"
    if day <= "2026-11-08":
        return "既存"
    return "不明"


def norm_conf(row: dict) -> str:
    conf = (row.get("confidence") or "").strip()
    if conf:
        return conf
    if norm_status(row, "") == "棄却":
        return "棄却"
    return "空欄"


def load_day(path: Path, day: str) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["_day"] = day
        row["_status"] = norm_status(row, day)
        row["_conf"] = norm_conf(row)
        row["_type_raw"] = (row.get("type") or row.get("category") or "").strip()
        row["_axis_existence"] = axis_of(row, "axis_existence", "axis_existed")
        row["_axis_loss"] = axis_of(row, "axis_loss", "axis_abolished")
        row["_axis_remains"] = axis_of(row, "axis_remains")
        if row["_status"] in STATUS_CLASS:
            row["_class"] = row["_status"]
        else:
            row["_class"] = TYPE_MAP.get(row["_type_raw"], "その他")
        row["_region"] = region_of(row, day)
    return rows


def region_of(row: dict, day: str) -> str:
    folder = row.get("region") or ""
    if folder in REGIONS:
        return folder
    if day == "2026-11-22":
        counted = (row.get("in_r7_count") or "").strip()
        return "R7" if counted == "yes" else "件数外"
    parent = ""
    # The day directory name carries the region after the date.
    return ""


def discover() -> dict[str, list[dict]]:
    found: dict[str, list[dict]] = {}
    for path in FINDINGS.glob("*/candidates.csv"):
        day = path.parent.name[:10]
        if day in NOT_CONDUCTED:
            raise SystemExit("a not-conducted day has a candidate file")
        found[day] = load_day(path, day)
    if TODAY.exists():
        found["2026-11-22"] = load_day(TODAY, "2026-11-22")
    for day in NOT_CONDUCTED:
        if day in found:
            raise SystemExit("not-conducted day was loaded")
    return found


def summarize(rows: list[dict]) -> dict:
    return {
        "rows": len(rows),
        "by_status": dict(Counter(row["_status"] for row in rows)),
        "by_class": dict(Counter(row["_class"] for row in rows)),
        "by_confidence": dict(Counter(row["_conf"] for row in rows)),
        "by_raw_type": dict(Counter(row["_type_raw"] or "空欄" for row in rows)),
        "axis_existence": dict(Counter(row["_axis_existence"] or "軸なし" for row in rows)),
        "axis_loss": dict(Counter(row["_axis_loss"] or "軸なし" for row in rows)),
        "axis_remains": dict(Counter(row["_axis_remains"] or "軸なし" for row in rows)),
        "high": sum(1 for row in rows if row["_conf"] == "高"),
        "mid": sum(1 for row in rows if row["_conf"] == "中"),
        "low": sum(1 for row in rows if row["_conf"] == "低"),
    }


def name_groups(rows: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for row in rows:
        name = (row.get("name") or "").strip()
        if not name:
            continue
        groups[name].append(row)
    out = []
    for _name, members in groups.items():
        ids = [member.get("id", "") for member in members]
        if len(set(ids)) < 2:
            continue
        out.append(
            {
                "ids": sorted(set(ids)),
                "days": sorted({member["_day"] for member in members}),
                "munis": sorted({member.get("muni_name", "") for member in members}),
                "regions": sorted({member["_region"] for member in members if member["_region"]}),
                "n": len(members),
            }
        )
    return out


def method_bucket(row: dict) -> str:
    """First-seen method. Labels are codes, not place names."""
    lead = (row.get("lead_id") or row.get("lead_key") or "").strip()
    source = (row.get("source_ids") or row.get("source_id") or "").strip()
    day = row["_day"]
    if lead == "METHOD-MERGE":
        return "shrine_agency_origin"
    if lead in {"METHOD-ROAD", "EXT-ROAD"}:
        return "old_road_official"
    if lead == "METHOD-RAIL" or lead.startswith("WIKI") or lead.startswith("MIL"):
        return "operator_or_notice"
    if lead == "METHOD-DAM":
        return "municipal_dam_page"
    if lead.startswith("EV") or lead.startswith("PDF"):
        return "exhibition_merger"
    if lead.startswith("EXT") or lead.startswith("ext") or re.fullmatch(r"L\d+", lead):
        return "external_secondary"
    if source.startswith("Q") or day in {"2026-11-05", "2026-11-08"}:
        return "wikidata_end_date"
    if day == "2026-11-10" and row["_type_raw"] == "神社":
        return "shrine_register_catalog"
    if day == "2026-11-11" and row["_status"] == "新規":
        return "operator_or_notice"
    if day == "2026-11-11" and row["_status"] == "棄却" and row["_type_raw"] in {"駅", "廃駅"}:
        return "near_current_station"
    if day == "2026-11-12" and row["_status"] == "新規" and row["_type_raw"] in {"駅", "廃駅"}:
        return "operator_or_notice"
    if lead.startswith("PRIOR") or row["_status"] in {"再検証", "既存"}:
        return "carried_prior"
    return "other"


def first_seen(days: dict[str, list[dict]]) -> list[dict]:
    earliest: dict[str, dict] = {}
    for day in sorted(days):
        for row in days[day]:
            iid = row.get("id") or ""
            if not iid:
                continue
            if iid not in earliest or day < earliest[iid]["_day"]:
                earliest[iid] = row
    return list(earliest.values())


def schedule(days: dict[str, list[dict]]) -> list[dict]:
    rows = []
    day = START
    while day <= END:
        elapsed = (day - START).days
        key = day.isoformat()
        region = REGIONS[elapsed % 7]
        week = elapsed // 7 + 1
        report = list(REPORTS.glob(f"{key}_*.md"))
        report_names = sorted(path.name for path in report if "weekly" not in path.name and "review" not in path.name)
        if key in NOT_CONDUCTED:
            state = "未実施"
        elif key not in days:
            state = "候補DBなし"
        elif len(days[key]) == 0:
            state = "候補CSVは空"
        else:
            state = "候補DBあり"
        rows.append(
            {
                "date": key,
                "region": region,
                "week": week,
                "elapsed_days": elapsed,
                "state": state,
                "candidate_rows": None if key in NOT_CONDUCTED else len(days.get(key, [])),
                "report_files": report_names,
            }
        )
        day += timedelta(days=1)
    return rows


def latest_rows(days: dict[str, list[dict]]) -> list[dict]:
    rows = []
    for region, day in LATEST.items():
        for row in days.get(day, []):
            if region == "R7" and row.get("in_r7_count") == "no":
                row = dict(row)
                row["_region"] = "件数外"
            elif not row.get("_region"):
                row = dict(row)
                row["_region"] = region
            rows.append(row)
    return rows


def main() -> None:
    days = discover()
    week_rows = [row for day in WEEK for row in days.get(day, [])]
    prev_rows = [row for day in PREV for row in days.get(day, [])]
    by_day = {}
    for day in WEEK:
        if day in NOT_CONDUCTED:
            by_day[day] = {"state": "未実施", "rows": None}
            continue
        rows = days.get(day, [])
        by_day[day] = {
            "state": "実施",
            "rows": len(rows),
            "by_status": dict(Counter(row["_status"] for row in rows)),
            "by_class": dict(Counter(row["_class"] for row in rows)),
            "by_confidence": dict(Counter(row["_conf"] for row in rows)),
            "ids": sorted({row.get("id", "") for row in rows if row.get("id")}),
        }
    stock = latest_rows(days)
    stock_public = []
    for row in stock:
        if row["_conf"] not in {"高", "中"}:
            continue
        stock_public.append(
            {
                "id": row.get("id", ""),
                "region": row.get("_region") or "",
                "muni_name": row.get("muni_name", ""),
                "category": row["_class"],
                "raw_type": row["_type_raw"],
                "status": row["_status"],
                "confidence": row["_conf"],
                "axis_existed": row["_axis_existence"] or "軸なし",
                "axis_abolished": row["_axis_loss"] or "軸なし",
                "axis_remains": row["_axis_remains"] or "軸なし",
            }
        )
    first = first_seen(days)
    method_counts = defaultdict(lambda: Counter())
    for row in first:
        bucket = method_bucket(row)
        method_counts[bucket]["rows"] += 1
        method_counts[bucket][row["_status"]] += 1
        method_counts[bucket]["conf:" + (row["_conf"] or "空欄")] += 1
        if row["_axis_existence"] == "強":
            method_counts[bucket]["existence_strong"] += 1
        if row["_axis_loss"] == "強":
            method_counts[bucket]["loss_strong"] += 1
        if row["_axis_remains"] in {"強", "中"}:
            method_counts[bucket]["remains_mid_or_strong"] += 1
    week_names = name_groups(week_rows)
    cross_name = [
        group
        for group in week_names
        if len({iid.split("-")[0] for iid in group["ids"]}) > 1
    ]
    same_day_name = [group for group in week_names if len(group["days"]) == 1]
    id_days = defaultdict(set)
    for row in week_rows:
        if row.get("id"):
            id_days[row["id"]].add(row["_day"])
    repeated_ids = sorted(iid for iid, seen in id_days.items() if len(seen) > 1)
    public = {
        "date": "2026-11-22",
        "window": WEEK,
        "not_conducted": sorted(NOT_CONDUCTED),
        "previous_window": PREV,
        "week": summarize(week_rows),
        "previous": summarize(prev_rows),
        "by_day": by_day,
        "repeated_ids_across_days_in_week": repeated_ids,
        "cross_region_same_name_groups": [
            {"ids": group["ids"], "munis": group["munis"], "days": group["days"]}
            for group in cross_name
        ],
        "same_day_shared_name_groups": [
            {"ids": group["ids"], "munis": group["munis"], "days": group["days"]}
            for group in same_day_name
        ],
        "schedule": schedule(days),
        "latest_by_region_day": LATEST,
        "latest_stock": summarize(stock),
        "latest_medium_and_high": stock_public,
        "first_seen_method": {key: dict(value) for key, value in sorted(method_counts.items())},
        "high_confidence_week": sum(1 for row in week_rows if row["_conf"] == "高"),
        "high_confidence_stock": sum(1 for row in stock if row["_conf"] == "高"),
    }
    names = []
    for rows in days.values():
        for row in rows:
            name = (row.get("name") or "").strip()
            if name:
                names.append(name)
    blob = json.dumps(public, ensure_ascii=False, indent=2)
    if COORD_RE.search(blob):
        raise SystemExit("weekly public json contains a coordinate-like number")
    for name in names:
        if len(name) >= 2 and name in blob:
            raise SystemExit("weekly public json contains a candidate name")
    PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC.write_text(blob + "\n", encoding="utf-8")

    lines = [
        "# 週次レビュー私有メモ 2026-11-16 から 2026-11-22、および4週の累計",
        "",
        "名称はここだけに書く。公開 JSON には出さない。",
        "2026-11-19 と 2026-11-20 は未実施であり、0件ではない。",
        "",
        "## 週内の行",
        "",
    ]
    for row in week_rows:
        lines.append(
            f"- {row['_day']} {row.get('id','')} {row['_status']} {row.get('muni_name','')} "
            f"{row['_type_raw']} {row.get('name','')} 存在{row['_axis_existence'] or '—'} "
            f"廃止{row['_axis_loss'] or '—'} 遺構{row['_axis_remains'] or '—'} "
            f"総合{row['_conf']} 分類{row['_class']}"
        )
    lines.extend(["", "## 同名で別ID（週内）", ""])
    for group in week_names:
        lines.append(
            "- "
            + "、".join(group["ids"])
            + " / "
            + "、".join(group["munis"])
            + " / "
            + "、".join(group["days"])
        )
    lines.extend(["", "## 累計の高・中（名称付き）", ""])
    for row in stock:
        if row["_conf"] not in {"高", "中"}:
            continue
        lines.append(
            f"- {row.get('id','')} {row.get('_region','')} {row.get('muni_name','')} "
            f"{row['_status']} {row['_type_raw']} {row.get('name','')} 総合{row['_conf']}"
        )
    lines.extend(["", "## 初出の探し方", ""])
    for row in sorted(first, key=lambda item: (item["_day"], item.get("id", ""))):
        lines.append(
            f"- {row['_day']} {row.get('id','')} {method_bucket(row)} {row['_status']} "
            f"{row.get('name','')}"
        )
    PRIVATE_MD.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "week_rows": len(week_rows),
                "prev_rows": len(prev_rows),
                "week_high": public["high_confidence_week"],
                "week_status": public["week"]["by_status"],
                "week_class": public["week"]["by_class"],
                "week_conf": public["week"]["by_confidence"],
                "stock_rows": len(stock),
                "stock": public["latest_stock"],
                "medium_high": len(stock_public),
                "methods": public["first_seen_method"],
                "not_conducted_ok": True,
                "cross_groups": len(cross_name),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
