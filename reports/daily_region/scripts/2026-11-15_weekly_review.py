"""Week-3 review, 2026-11-09 through 2026-11-15.

The script reads private candidate CSV files from a directory passed at
runtime, plus today's candidate CSV. It writes a public JSON of counts,
IDs, municipalities, types and confidence. It does not write coordinates
or candidate names into the public JSON. Names are written only to the
private markdown path.
"""

from __future__ import annotations

import csv
import json
import os
import re
from collections import Counter, defaultdict
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
        / "2026-11-15_weekly_review_week3_public.json",
    )
)
PRIVATE_MD = Path(os.environ["WEEKLY_PRIVATE_MD"])
COORD_RE = re.compile(r"(?:3[4-6]|13[89])\.[0-9]{3,}")
WEEK = [f"2026-11-{day:02d}" for day in range(9, 16)]
PREV = [f"2026-11-{day:02d}" for day in range(2, 9)]
TYPE_MAP = {
    "station": "廃駅・廃線",
    "駅": "廃駅・廃線",
    "廃駅": "廃駅・廃線",
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
    if norm_status(row, "") in {"棄却"}:
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
    return rows


def discover() -> dict[str, list[dict]]:
    found: dict[str, list[dict]] = {}
    for path in FINDINGS.glob("*/candidates.csv"):
        day = path.parent.name[:10]
        found[day] = load_day(path, day)
    if TODAY.exists():
        found["2026-11-15"] = load_day(TODAY, "2026-11-15")
    return found


def summarize(rows: list[dict]) -> dict:
    return {
        "rows": len(rows),
        "by_status": dict(Counter(row["_status"] for row in rows)),
        "by_class": dict(Counter(row["_class"] for row in rows)),
        "by_confidence": dict(Counter(row["_conf"] for row in rows)),
        "by_raw_type": dict(Counter(row["_type_raw"] or "空欄" for row in rows)),
        "axis_existence": dict(
            Counter(row["_axis_existence"] or "軸なし" for row in rows)
        ),
        "axis_loss": dict(Counter(row["_axis_loss"] or "軸なし" for row in rows)),
        "axis_remains": dict(
            Counter(row["_axis_remains"] or "軸なし" for row in rows)
        ),
        "high": sum(1 for row in rows if row["_conf"] == "高"),
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
        if len(set(ids)) < 2 and len({member["_day"] for member in members}) < 2:
            continue
        if len(members) < 2:
            continue
        out.append(
            {
                "ids": sorted(set(ids)),
                "days": sorted({member["_day"] for member in members}),
                "munis": sorted({member.get("muni_name", "") for member in members}),
                "n": len(members),
            }
        )
    return out


def main() -> None:
    days = discover()
    week_rows = [row for day in WEEK for row in days.get(day, [])]
    prev_rows = [row for day in PREV for row in days.get(day, [])]
    # Same-day files can repeat an ID across the special round and a later
    # revalidation. Count unique IDs inside each window as well as rows.
    def unique_ids(rows: list[dict]) -> int:
        return len({row.get("id", "") for row in rows if row.get("id")})

    by_day = {}
    for day in WEEK + PREV:
        rows = days.get(day, [])
        by_day[day] = {
            "present": day in days,
            "rows": len(rows),
            "by_status": dict(Counter(row["_status"] for row in rows)),
            "by_class": dict(Counter(row["_class"] for row in rows)),
            "by_confidence": dict(Counter(row["_conf"] for row in rows)),
            "ids": sorted({row.get("id", "") for row in rows if row.get("id")}),
        }
    week_names = name_groups(week_rows)
    # Cross-day same ID is a revalidation chain, not a second feature.
    id_days = defaultdict(set)
    for row in week_rows + prev_rows:
        if row.get("id"):
            id_days[row["id"]].add(row["_day"])
    repeated_ids = sorted(iid for iid, seen in id_days.items() if len(seen) > 1)
    cross_name = [
        group
        for group in week_names
        if len(group["ids"]) > 1 and len({i.split("-")[0] for i in group["ids"]}) > 1
    ]
    same_file_name = [
        group
        for group in week_names
        if len(group["ids"]) > 1 and len(group["days"]) == 1
    ]
    public = {
        "date": "2026-11-15",
        "window": WEEK,
        "previous_window": PREV,
        "week": summarize(week_rows),
        "previous": summarize(prev_rows),
        "week_unique_ids": unique_ids(week_rows),
        "previous_unique_ids": unique_ids(prev_rows),
        "by_day": by_day,
        "repeated_ids_across_days": repeated_ids,
        "cross_region_same_name_groups": [
            {"ids": group["ids"], "munis": group["munis"], "days": group["days"]}
            for group in cross_name
        ],
        "same_day_shared_name_groups": [
            {"ids": group["ids"], "munis": group["munis"], "days": group["days"]}
            for group in same_file_name
        ],
        "high_confidence_week": sum(1 for row in week_rows if row["_conf"] == "高"),
        "high_confidence_previous": sum(1 for row in prev_rows if row["_conf"] == "高"),
    }
    blob = json.dumps(public, ensure_ascii=False, indent=2)
    if COORD_RE.search(blob):
        raise SystemExit("weekly public json contains a coordinate-like number")
    for row in week_rows + prev_rows:
        name = (row.get("name") or "").strip()
        if name and name in blob:
            raise SystemExit("weekly public json contains a candidate name")
    PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC.write_text(blob + "\n", encoding="utf-8")
    lines = [
        "# 週次レビュー私有メモ 2026-11-09 から 2026-11-15",
        "",
        "名称はここだけに書く。公開 JSON には出さない。",
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
    lines.extend(["", "## 同名で別ID", ""])
    for group in week_names:
        if len(group["ids"]) < 2:
            continue
        # The private file may name the shared string. Recover it from members.
        lines.append(
            "- "
            + "、".join(group["ids"])
            + " / "
            + "、".join(group["munis"])
            + " / "
            + "、".join(group["days"])
        )
    PRIVATE_MD.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "week_rows": len(week_rows),
                "prev_rows": len(prev_rows),
                "week_high": public["high_confidence_week"],
                "cross_groups": len(cross_name),
                "same_day_groups": len(same_file_name),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
