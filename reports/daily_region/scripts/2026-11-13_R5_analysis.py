"""R5（相模原、旧津久井郡を除く）3週目。2026-11-13。

主目的は、外部調査の合祀イベントを相模原市の企画展資料で裏づけること。
土地利用は、2026-11-06 の申し送りが既存集計でまだ言えるかの確認に限る。

公開 JSON には件数、区、候補 ID、3軸、確度、リード ID だけを書く。
名称と緯度経度は、環境変数で渡した非公開 CSV から読み、
/opt/cursor/artifacts/kanagawa_private/2026-11-13_R5/ に出す。
スクリプトには地点の緯度経度も候補名も書かない。

評価は件数を数える前に固定した。

- 過去に存在した根拠、廃止・消失の根拠、物理的遺構が残る可能性は別の欄にする。
- 現行の地図に名称が無いこと、森林化、神社庁の検索に出ないことは、消失の根拠にしない。
- 座標は、既存 CSV か、取得した項目の座標欄にあるものだけを使う。
  字名や住所からは点を作らない。この入力の合祀 CSV に座標欄は無い。
- 総合確度の高は、旧版地形図の記号を見ていない限り付けない。
- 画像 PDF は、pdftotext の文字数が閾値未満なら本文未読とする。
  本文未読のファイルに社名が無いことを、原帳で社名を確認したことにはしない。
- 社名が展示本文にだけあり、読めた PDF に無いとき、存在は中までとする。
  強は、その文字列が読めた PDF にあるときだけ付ける。
- 合祀先、現在の拝殿写真、申請だけで実行されなかった合併、焼失後の再建は廃社にしない。
- 合祀の記録だけでは廃社にしない。旧社地を、座標欄か旧版の記号で見ていない限り、
  状態変化として残す。復祀の記述があるものは、現在の消失を確定しない。
- 意見書が個別の社名を挙げず、合併の見込みが無いと書く村は、村単位の負例 1 件にする。
  社名の数を足さない。
- 明細帳の表題が目録にあっても、その画像を開いていなければ本文を読んだことにしない。
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EVENTS_CSV = Path(os.environ["PRIVATE_EVENTS_CSV"])
PDF_INDEX_CSV = Path(os.environ["PRIVATE_PDF_INDEX_CSV"])
PRIOR_CANDIDATES = Path(os.environ.get("PRIVATE_PRIOR_CANDIDATES", ""))
BUNKAZAI_CSV = Path(os.environ.get("BUNKAZAI_CSV", ""))
CELLS_PARQUET = Path(os.environ.get("R5_CELLS_PARQUET", ""))
OUT_PRIV = Path("/opt/cursor/artifacts/kanagawa_private/2026-11-13_R5")
PUBLIC = ROOT / "reports" / "daily_region" / "data" / "2026-11-13_R5_week3_public.json"
RESULTS = ROOT / "reports" / "phase1c2_results.json"
WORK = Path(os.environ.get("R5_WORK_DIR", "/tmp/r5_20261113"))
SUPPLEMENTAL = Path(
    "/opt/cursor/artifacts/kanagawa_private/supplemental_2026-11-13.tar.gz"
)
RETRIEVED = "2026-11-13"
UA = "kanagawa-ruins-search/2026-11-13"
READABLE_MIN_CHARS = 80
GE5_MAX = 0.20
COMPLEMENT_GAP = 0.10
FOREST_OF_BUILDING_LOSS_MAX = 0.10
MIN_RATE_BASE_KM2 = 0.50
COORD_RE = re.compile(r"(?:3[45]|13[89])\.[0-9]{3,}")
WARDS = ("緑区", "中央区", "南区")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def fetch(url: str, dest: Path, timeout: int = 60) -> bytes | None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            status = getattr(resp, "status", 200)
    except Exception as exc:  # noqa: BLE001 — 失敗は未取得として残す
        dest.with_suffix(dest.suffix + ".err").write_text(
            f"{type(exc).__name__}: {exc}\n", encoding="utf-8"
        )
        return None
    dest.write_bytes(raw)
    dest.with_suffix(dest.suffix + ".http").write_text(str(status), encoding="utf-8")
    return raw


def pdftotext(path: Path) -> str:
    import subprocess

    try:
        out = subprocess.run(
            ["pdftotext", "-layout", str(path), "-"],
            check=False,
            capture_output=True,
        )
    except FileNotFoundError:
        return ""
    if out.returncode != 0:
        return ""
    return out.stdout.decode("utf-8", errors="replace")


def html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<script[\s\S]*?</script>", " ", raw)
    raw = re.sub(r"(?is)<style[\s\S]*?</style>", " ", raw)
    raw = re.sub(r"(?is)<br\s*/?>", "\n", raw)
    raw = re.sub(r"</p>|</div>|</h[1-6]>|</li>|</tr>", "\n", raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = raw.replace("&nbsp;", " ").replace("&amp;", "&")
    raw = re.sub(r"[ \t]+\n", "\n", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return raw


def load_events() -> list[dict]:
    with EVENTS_CSV.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_pdf_index() -> list[dict]:
    with PDF_INDEX_CSV.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def prior_id_count() -> int:
    if not PRIOR_CANDIDATES.is_file():
        return 0
    with PRIOR_CANDIDATES.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return len(rows)


def split_entity(value: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"[・、]", value or "") if part.strip()]
    return parts or [value.strip()]


def area_token(area: str) -> str:
    token = (area or "").strip()
    for suffix in ("村", "町"):
        if token.endswith(suffix) and len(token) > len(suffix):
            token = token[: -len(suffix)]
    return token


def parse_catalog(text: str) -> list[dict]:
    flat = re.sub(r"\s+", " ", text)
    matches = list(re.finditer(r"「([^」]{2,50})」", flat))
    items = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else match.end() + 180
        window = flat[match.end() : min(end, match.end() + 200)]
        village = re.search(r"（([^）]{1,18}役場資料)）", window)
        era = re.search(r"(明治|大正|昭和|令和)\s*[0-9０-９]+\s*年", window)
        title = re.sub(r"\s+", "", match.group(1))
        items.append(
            {
                "title": title,
                "office": village.group(1) if village else "",
                "era": re.sub(r"\s+", "", era.group(0)) if era else "",
            }
        )
    return items


def captions(text: str) -> list[tuple[str, str, str]]:
    found = []
    for match in re.finditer(
        r"([^（）\n]{2,30})（((?:緑|中央|南)区)([^）]{0,24})）", text
    ):
        found.append((match.group(1).strip(), match.group(2), match.group(3).strip()))
    return found


def wards_for(area: str, entity: str, caption_rows: list[tuple[str, str, str]]) -> list[str]:
    """写真説明の区。短い共通名が複数の区に当たるときは、その名前では区を足さない。"""
    token = area_token(area)
    hits: list[str] = []

    def add(ward: str) -> None:
        if ward not in hits:
            hits.append(ward)

    for label, ward, rest in caption_rows:
        blob = f"{label}{rest}"
        if token and len(token) >= 2 and token in blob:
            add(ward)
        elif rest and len(rest) >= 2 and rest in (area or ""):
            add(ward)
    for part in split_entity(entity):
        if len(part) < 3:
            continue
        matched: list[str] = []
        for label, ward, rest in caption_rows:
            blob = f"{label}{rest}"
            if part in blob and ward not in matched:
                matched.append(ward)
        if len(matched) == 1:
            add(matched[0])
    return [ward for ward in WARDS if ward in hits]


def muni_name(wards: list[str]) -> str:
    if not wards:
        return "相模原市"
    if len(wards) == 1:
        return f"相模原市{wards[0]}"
    return "相模原市（" + "・".join(wards) + "）"


def near(text: str, left: str, right: str, window: int = 500) -> bool:
    if not left or not right or left not in text or right not in text:
        return False
    start = 0
    while True:
        index = text.find(left, start)
        if index < 0:
            return False
        chunk = text[max(0, index - window) : index + len(left) + window]
        if right in chunk:
            return True
        start = index + len(left)


def catalog_for_area(items: list[dict], area: str) -> list[dict]:
    token = area_token(area)
    if not token:
        return []
    return [item for item in items if token in item["office"] or token in item["title"]]


def classify_parts(event: dict) -> list[str]:
    note = event.get("validation_note") or ""
    record = event.get("record_type") or ""
    entity = event.get("historical_entity") or ""
    if "行われなかった" in note or "申請" in record or "焼失" in record or "仏堂" in record:
        return [entity]
    parts = split_entity(entity)
    if len(parts) > 1 and all(len(part) >= 2 for part in parts):
        return parts
    return [entity]


def category_of(event: dict, name: str) -> str:
    blob = f"{event.get('record_type','')}{event.get('historical_entity','')}{name}"
    if any(token in blob for token in ("仏堂", "薬師", "廃堂", "寺院")):
        return "寺院"
    return "神社"


def name_in(name: str, text: str) -> bool:
    if not name or not text:
        return False
    if name in text:
        return True
    return any(part in text for part in split_entity(name) if len(part) >= 2)


def build_record(
    event: dict,
    name: str,
    html: str,
    readable: dict[str, str],
    items: list[dict],
    caption_rows: list[tuple[str, str, str]],
) -> dict:
    catalog_text = readable.get("10", "")
    pdf01 = readable.get("01", "")
    pdf09 = readable.get("09", "")
    readable_blob = "\n".join(readable.values())
    area = event.get("historical_area") or ""
    note = event.get("validation_note") or ""
    record_type = event.get("record_type") or ""
    in_html = name_in(name, html)
    in_catalog = name_in(name, catalog_text)
    in_pdf = name_in(name, pdf01) or name_in(name, pdf09) or in_catalog
    area_items = catalog_for_area(items, area)
    titles = " ".join(item["title"] for item in area_items)
    # 「地名では」と復祀が同じ箇所にあるときだけ、その村の復祀の記述とする。
    restoration = near(html, area_token(area) + "では", "復祀", 80)
    # 近傍検索は短い共通名で別の村の文に当たる。実行されなかった、は入力の注記と本文の両方があるときだけ。
    unexecuted = "行われなかった" in note and ("行われず" in html or "行われなかった" in html)
    rebuilt_negative = "負の対照" in note or "焼失" in record_type
    rebuilt_after_abolition = "再建あり" in note or ("再建" in record_type and "廃堂" in record_type)
    photo_current = any(
        name_in(name, item["title"]) and item["era"].startswith("令和") and "故地" not in item["title"]
        for item in items
    )
    token2 = area_token(area)[:2] if len(area_token(area)) >= 2 else ""
    former_titles = [item["title"] for item in items if "故地" in item["title"]]
    area_hall_titles = [
        item["title"] for item in items if token2 and token2 in item["title"] and "薬師" in item["title"]
    ]
    former_site_item = "廃堂" in record_type and any(
        "薬師" in former and "薬師" in other for former in former_titles for other in area_hall_titles
    )

    if in_pdf:
        existed = "強"
        existed_why = "読めたPDFに名称がある"
    elif in_html:
        existed = "中"
        existed_why = "展示本文に名称がある。読めたPDFにはこの名称が無い"
    else:
        existed = "弱"
        existed_why = "開いた本文にこの名称が無い"

    if unexecuted:
        abolished = "なし"
        abolished_why = "展示本文は、許可のあと実際の合併は行われなかったと書く"
    elif rebuilt_negative:
        abolished = "なし"
        abolished_why = "焼失後の再建で、負の対照である"
    elif (
        rebuilt_after_abolition
        and token2
        and token2 in catalog_text
        and "処分済" in catalog_text
        and ("廃止" in catalog_text or "廃堂" in catalog_text)
    ):
        abolished = "強"
        abolished_why = "目録が廃堂と処分済の表題を載せ、同じ頁で後年の再建を書く。現在の消失ではない"
    elif "処分済" in titles and in_html and not in_catalog:
        abolished = "中"
        abolished_why = "村の処分済届は目録の表題と日付にある。社名は展示本文にあり、届の画像は未読"
        if restoration:
            abolished_why += "。復祀の記述があり、現在の消失は確定しない"
    elif "合併済" in titles and in_html and not in_catalog:
        abolished = "中"
        abolished_why = "村の合併済届は目録にある。この社名は展示本文にあり、届の画像は未読"
    elif "合併願" in titles and in_html:
        abolished = "中"
        abolished_why = "目録にあるのは合併願であり、処分済の表題はこの村の項に無い。実行は展示本文による"
    elif in_html and any(token in record_type for token in ("合祀", "合併")):
        abolished = "中"
        abolished_why = "展示本文が合併または合祀と書く。読めた目録の表題にはこの社名が無い"
    else:
        abolished = "未確認"
        abolished_why = "開いた本文だけでは廃止を分けられない"

    stones = ("庚申" in html or "無縫塔" in html) and former_site_item
    if stones:
        remains = "中"
        remains_why = "目録が故地を現在の堂と別項にし、展示本文が跡地の石造物を書く。写真は判読していない"
    elif photo_current and abolished == "なし":
        remains = "未確認"
        remains_why = "目録に現在の建物の写真項がある。廃址の有無は見ていない"
    else:
        remains = "未確認"
        remains_why = "座標欄が無く、旧版の記号も見ていない"

    # 合祀の記録だけでは廃社にしない。
    status = "状態変化"
    if abolished == "なし" and (unexecuted or rebuilt_negative):
        confidence = "記録のみ"
    elif existed == "強" and abolished == "強":
        confidence = "中"
    elif existed == "中":
        confidence = "低"
    else:
        confidence = "低"

    wards = wards_for(area, name, caption_rows)
    eras = sorted({item["era"] for item in area_items if item["era"]})
    return {
        "status": status,
        "region": "R5",
        "muni_name": muni_name(wards),
        "name": name,
        "category": category_of(event, name),
        "axis_existed": existed,
        "axis_abolished": abolished,
        "axis_remains": remains,
        "confidence": confidence,
        "lead_id": event["id"],
        "source": event.get("source_url") or "",
        "retrieved": RETRIEVED,
        "license": "相模原市ホームページ。私的使用と引用を除き無断複製・転用不可",
        "era": event.get("period") or "",
        "catalog_eras": "、".join(eras),
        "verification": " ".join(
            part for part in (existed_why, abolished_why, remains_why) if part
        ),
        "reject_reason": "",
        "name_in_html": in_html,
        "name_in_catalog": in_catalog,
        "name_in_readable_pdf": in_pdf,
        "restoration_mentioned": bool(restoration),
        "catalog_titles": titles,
        "lat": "",
        "lon": "",
    }


def opinion_record(pdf09: str, html: str, items: list[dict], caption_rows, events: list[dict], source_url: str) -> dict | None:
    if "見込" not in pdf09 or "合併" not in pdf09:
        return None
    village = ""
    match = re.search(r"(\S+村)文書", pdf09)
    if match:
        village = match.group(1)
    if not village:
        return None
    if any(village in (event.get("historical_area") or "") for event in events):
        return None
    offices = [item for item in items if village in item["office"] and "意見書" in item["title"]]
    if not offices and "意見書" not in pdf09:
        return None
    wards = wards_for(village, "", caption_rows)
    era = offices[0]["era"] if offices else ""
    return {
        "status": "状態変化",
        "region": "R5",
        "muni_name": muni_name(wards),
        "name": village,
        "category": "神社",
        "axis_existed": "中",
        "axis_abolished": "なし",
        "axis_remains": "未確認",
        "confidence": "記録のみ",
        "lead_id": "PDF09",
        "source": source_url,
        "retrieved": RETRIEVED,
        "license": "相模原市ホームページ。私的使用と引用を除き無断複製・転用不可",
        "era": era,
        "catalog_eras": era,
        "verification": (
            "読めた釈文が、村内の各社について合併の見込みが無いと書く。"
            "個別の社名は釈文に無いので社ごとに分けない。"
            "目録に同じ村の意見書がある。"
            "廃社にはしない。"
        ),
        "reject_reason": "合併見送りの負例。個別の社名が無い",
        "name_in_html": village in html,
        "name_in_catalog": bool(offices),
        "name_in_readable_pdf": True,
        "restoration_mentioned": False,
        "catalog_titles": " ".join(item["title"] for item in offices),
        "lat": "",
        "lon": "",
        "record_kind": "village_opinion",
    }


def load_region_table(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    reg = {
        name: dict(zip(data["aggregates"]["region"]["columns"], row))
        for name, row in zip(
            data["aggregates"]["region"]["index"], data["aggregates"]["region"]["data"]
        )
    }
    mcols = data["aggregates"]["municipality"]["columns"]
    wards = [
        dict(zip(mcols, row))
        for row in data["aggregates"]["municipality"]["data"]
        if row[mcols.index("muni_code")] in ("14151", "14152", "14153")
    ]
    cc = data["transitions"]["component_class_share_by_region"]
    comp = {
        name: dict(zip(cc["columns"], row)) for name, row in zip(cc["index"], cc["data"])
    }
    focus = data["transitions"]["focus_by_region"]
    focus_rows = {}
    for row in focus["data"]:
        rec = dict(zip(focus["columns"], row))
        if rec["region"] in ("R5_sagamihara", "R6_tsukui"):
            focus_rows[(rec["region"], rec["transition"])] = rec
    return {"reg": reg, "wards": wards, "comp": comp, "focus": focus_rows}


def public_landuse(tables: dict) -> dict:
    r5 = tables["reg"]["R5_sagamihara"]
    r6 = tables["reg"]["R6_tsukui"]
    comp = tables["comp"]["R5_sagamihara"]
    s1, s2 = comp["share_1"], comp["share_2"]
    s5 = comp["share_>=5"]
    changed = comp["changed_km2"]
    complement = 1 - s1 - s2
    b_loss = r5["building_loss_km2"]
    b_forest = r5["building_to_forest_km2"] + r5["building_to_wasteland_km2"]
    wards = {row["muni_code"]: row for row in tables["wards"]}
    bases = {
        "R5_agri": r5["agri_2014_share"] * r5["land_km2"],
        "R6_agri": r6["agri_2014_share"] * r6["land_km2"],
        "R5_building": r5["building_2014_share"] * r5["land_km2"],
        "R6_building": r6["building_2014_share"] * r6["land_km2"],
    }
    return {
        "thresholds_unchanged": {
            "ge5_max": GE5_MAX,
            "complement_gap": COMPLEMENT_GAP,
            "forest_share_of_building_loss_max": FOREST_OF_BUILDING_LOSS_MAX,
        },
        "h1_still_supported": (
            r6["agri_to_forest_rate"] > r5["agri_to_forest_rate"]
            and r6["building_to_forest_or_wasteland_rate"]
            > r5["building_to_forest_or_wasteland_rate"]
            and r6["agri_to_forest_km2"] > r5["agri_to_forest_km2"]
            and r6["building_to_forest_km2"] > r5["building_to_forest_km2"]
            and all(value >= MIN_RATE_BASE_KM2 for value in bases.values())
        ),
        "h2_still_supported": (b_forest / b_loss) < FOREST_OF_BUILDING_LOSS_MAX,
        "h3_still_supported": (
            s5 < GE5_MAX
            and (complement - s5) >= COMPLEMENT_GAP
            and tables["focus"][("R5_sagamihara", "building->forest")]["size_>=5_share"] == 0
            and tables["focus"][("R5_sagamihara", "agri->forest")]["size_>=5_share"] == 0
        ),
        "h4_still_supported": (
            r5["building_net_change_km2"] < 0
            and wards["14152"]["building_net_change_km2"] < 0
            and wards["14153"]["building_net_change_km2"] < 0
        ),
        "r5_share_ge5": s5,
        "r5_ge5_km2": s5 * changed,
        "r5_complement_of_1_2": complement,
        "r5_complement_km2": complement * changed,
        "r5_building_loss_residual_km2": b_loss - b_forest,
        "r5_forest_wasteland_share_of_building_loss": b_forest / b_loss,
        "published_ward_building_net_km2": {
            "中央区": wards["14152"]["building_net_change_km2"],
            "南区": wards["14153"]["building_net_change_km2"],
            "緑区_区行はR6を含む": wards["14151"]["building_net_change_km2"],
        },
        "focus_ge5_building_to_forest": tables["focus"][
            ("R5_sagamihara", "building->forest")
        ]["size_>=5_share"],
        "focus_ge5_agri_to_forest": tables["focus"][("R5_sagamihara", "agri->forest")][
            "size_>=5_share"
        ],
        "focus_cells_building_to_forest": tables["focus"][
            ("R5_sagamihara", "building->forest")
        ]["cells"],
        "focus_cells_agri_to_forest": tables["focus"][("R5_sagamihara", "agri->forest")][
            "cells"
        ],
    }


def cell_slices(path: Path) -> dict:
    if not path.is_file():
        return {"opened": False}
    import pyarrow.parquet as pq

    table = pq.read_table(
        path, columns=["region", "muni_name", "muni_code", "grp2014", "grp2021", "area_m2"]
    )
    region = table.column("region").to_pylist()
    muni = table.column("muni_name").to_pylist()
    g14 = table.column("grp2014").to_pylist()
    g21 = table.column("grp2021").to_pylist()
    area = table.column("area_m2").to_pylist()
    counts: dict[str, int] = Counter()
    b14: dict[str, float] = Counter()
    b21: dict[str, float] = Counter()
    n_bf = 0
    n_af = 0
    n_r5 = 0
    for reg, name, a, b, square in zip(region, muni, g14, g21, area):
        if reg != "R5_sagamihara":
            continue
        n_r5 += 1
        counts[name] += 1
        if a == "building":
            b14[name] += square / 1e6
        if b == "building":
            b21[name] += square / 1e6
        if a == "building" and b == "forest":
            n_bf += 1
        if a == "agri" and b == "forest":
            n_af += 1
    slices = {}
    for name in sorted(counts):
        net = b21[name] - b14[name]
        slices[name] = {
            "n_cells": counts[name],
            "building_2014_km2": b14[name],
            "building_net_km2": net,
        }
    return {
        "opened": True,
        "n_r5": n_r5,
        "building_to_forest_cells": n_bf,
        "agri_to_forest_cells": n_af,
        "slices": slices,
        "all_slice_nets_negative": all(row["building_net_km2"] < 0 for row in slices.values()),
    }


def bunkazai_counts(path: Path) -> dict:
    if not path.is_file():
        return {"opened": False}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    lat_n = sum(1 for row in rows if (row.get("緯度") or "").strip())
    lon_n = sum(1 for row in rows if (row.get("経度") or "").strip())
    return {
        "opened": True,
        "rows": len(rows),
        "lat_nonempty": lat_n,
        "lon_nonempty": lon_n,
    }


def try_overpass() -> dict:
    query = (
        '[out:json][timeout:20];'
        'area["name"="相模原市"]["admin_level"="7"]->.a;'
        'nwr["amenity"="place_of_worship"](area.a);'
        "out tags;"
    )
    url = "https://overpass-api.de/api/interpreter"
    data = urllib.parse.urlencode({"data": query}).encode()
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            raw = resp.read()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "named": None}
    payload = json.loads(raw)
    elements = payload.get("elements") or []
    named = 0
    for element in elements:
        tags = element.get("tags") or {}
        if tags.get("name") or tags.get("name:ja"):
            named += 1
    # 名称と座標は公開しない。件数だけ残す。照合は座標欄がイベントに無いので廃社の判定に使わない。
    dest = WORK / "osm_worship_tags.json"
    dest.write_bytes(raw)
    return {"ok": True, "elements": len(elements), "named": named, "used_for_adoption": False}


def try_wikidata() -> dict:
    query = """
    SELECT ?item WHERE {
      ?item wdt:P131 wd:Q694496 .
      ?item wdt:P31 ?type .
      FILTER(?type IN (wd:Q845945, wd:Q160742, wd:Q39715))
    }
    """
    url = "https://query.wikidata.org/sparql?format=json&query=" + urllib.parse.quote(query)
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept": "application/sparql-results+json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            raw = resp.read()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    (WORK / "wikidata_sagamihara.json").write_bytes(raw)
    data = json.loads(raw)
    return {"ok": True, "rows": len(data.get("results", {}).get("bindings", []))}


def gsi_layer_counts() -> dict:
    url = "https://maps.gsi.go.jp/development/ichiran.html"
    raw = fetch(url, WORK / "gsi_ichiran.html", timeout=60)
    if raw is None:
        return {"fetched": False}
    text = raw.decode("utf-8", errors="replace")
    return {
        "fetched": True,
        "chars": len(text),
        "旧版": text.count("旧版"),
        "迅速測図": text.count("迅速測図"),
        "旧版地図": text.count("旧版地図"),
        "tiles_fetched": 0,
        "reason": "合祀CSVに座標欄が無く、一覧に旧版と迅速測図のタイル名が無いためタイルは取っていない",
    }


def assert_public_safe(payload: dict, blocked: list[str]) -> None:
    text = json.dumps(payload, ensure_ascii=False)
    if COORD_RE.search(text):
        raise SystemExit("public json matched a coordinate pattern")
    for name in blocked:
        if name and len(name) >= 2 and name in text:
            raise SystemExit("public json contains a private name")
    if "高" in json.dumps([row.get("confidence") for row in payload["rows"]], ensure_ascii=False):
        raise SystemExit("high confidence was assigned")


def write_private(rows: list[dict], findings_lines: list[str]) -> None:
    OUT_PRIV.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "id",
        "status",
        "region",
        "muni_name",
        "name",
        "category",
        "axis_existed",
        "axis_abolished",
        "axis_remains",
        "confidence",
        "lead_id",
        "source",
        "retrieved",
        "license",
        "era",
        "catalog_eras",
        "verification",
        "reject_reason",
        "name_in_html",
        "name_in_catalog",
        "name_in_readable_pdf",
        "restoration_mentioned",
        "catalog_titles",
        "lat",
        "lon",
    ]
    with (OUT_PRIV / "candidates.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    (OUT_PRIV / "findings.md").write_text("\n".join(findings_lines) + "\n", encoding="utf-8")


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    events = load_events()
    pdf_index = load_pdf_index()
    prior_n = prior_id_count()
    if prior_n != 0:
        raise SystemExit(f"prior R5 candidate rows were {prior_n}, expected 0")

    provenance = []
    pdf_text: dict[str, str] = {}
    pdf_meta = []
    for row in pdf_index:
        url = row["source_url"]
        stem = url.rstrip("/").rsplit("/", 1)[-1]
        dest = WORK / "pdfs" / stem
        raw = fetch(url, dest)
        if raw is None:
            pdf_meta.append({"id": row["id"], "fetched": False, "url": url})
            continue
        digest = sha256_bytes(raw)
        text = pdftotext(dest)
        key = stem.replace(".pdf", "")
        pdf_text[key] = text
        readable = len(text.strip()) >= READABLE_MIN_CHARS
        pdf_meta.append(
            {
                "id": row["id"],
                "fetched": True,
                "bytes": len(raw),
                "sha256": digest,
                "pages_note": "pdftotext",
                "text_chars": len(text.strip()),
                "body_read": readable,
                "url": url,
            }
        )
        provenance.append(
            {
                "path": f"pdfs/{stem}",
                "source_url": url,
                "retrieved": RETRIEVED,
                "license": "相模原市に帰属。私的使用と引用を除き無断複製・転用不可。非公開保管用",
                "era": "企画展の解説は令和4年。個々の原文書の年は目録の項による",
                "sha256": digest,
                "bytes": len(raw),
                "body_read": readable,
                "note": row.get("document_title") or "",
            }
        )

    source_url = events[0]["source_url"]
    html_raw = fetch(source_url, WORK / "html" / "exhibit.html")
    html = html_to_text(html_raw.decode("utf-8", errors="replace")) if html_raw else ""
    if html_raw:
        provenance.append(
            {
                "path": "html/exhibit.html",
                "source_url": source_url,
                "retrieved": RETRIEVED,
                "license": "相模原市に帰属。私的使用と引用を除き無断複製・転用不可",
                "era": "ページの最終更新は本文の表示による",
                "sha256": sha256_bytes(html_raw),
                "bytes": len(html_raw),
                "body_read": True,
            }
        )
    about_url = urllib.parse.urljoin(source_url, "/about/index.html")
    about_raw = fetch(about_url, WORK / "html" / "about.html")
    about_text = html_to_text(about_raw.decode("utf-8", errors="replace")) if about_raw else ""
    license_ok = "無断で複製" in about_text
    if about_raw:
        provenance.append(
            {
                "path": "html/about.html",
                "source_url": about_url,
                "retrieved": RETRIEVED,
                "license": "利用条件の頁そのもの",
                "era": "",
                "sha256": sha256_bytes(about_raw),
                "bytes": len(about_raw),
                "body_read": True,
                "copyright_sentence_found": license_ok,
            }
        )

    readable = {
        key: text
        for key, text in pdf_text.items()
        if len(text.strip()) >= READABLE_MIN_CHARS
    }
    catalog = parse_catalog(readable.get("10", ""))
    caption_rows = captions(readable.get("10", ""))
    image_unread = [
        row["id"] for row in pdf_meta if row.get("fetched") and not row.get("body_read")
    ]
    readable_ids = [
        row["id"] for row in pdf_meta if row.get("fetched") and row.get("body_read")
    ]

    records = []
    for event in events:
        for name in classify_parts(event):
            records.append(
                build_record(event, name, html, readable, catalog, caption_rows)
            )
    extra = opinion_record(
        readable.get("09", ""), html, catalog, caption_rows, events, source_url
    )
    if extra:
        records.append(extra)

    start = 1
    for index, record in enumerate(records, start=start):
        record["id"] = f"R5-{index:03d}"
        if record["confidence"] == "高":
            raise SystemExit("rule broken: high confidence")
        if record["status"] == "新規":
            raise SystemExit("rule broken: merger record became a lost-site adoption")

    blocked_names = []
    for event in events:
        blocked_names.append(event.get("historical_entity") or "")
        blocked_names.append(event.get("related_entity") or "")
        blocked_names.append(event.get("historical_area") or "")
        blocked_names.extend(split_entity(event.get("historical_entity") or ""))
    if extra:
        blocked_names.append(extra["name"])
    blocked_names = [name for name in blocked_names if name and len(name) >= 2]

    # 展示本文側の照合件数。名称は出さない。
    lead_summary = []
    for event in events:
        parts = classify_parts(event)
        lead_summary.append(
            {
                "lead_id": event["id"],
                "parts": len(parts),
                "any_name_in_html": any(name_in(part, html) for part in parts),
                "any_name_in_readable_pdf": any(
                    name_in(part, "\n".join(readable.values())) for part in parts
                ),
                "record_type_class": (
                    "未実行"
                    if "行われなかった" in (event.get("validation_note") or "")
                    else "再建の負例"
                    if "負の対照" in (event.get("validation_note") or "")
                    else "廃堂と再建"
                    if "再建あり" in (event.get("validation_note") or "")
                    else "合祀の記録"
                ),
            }
        )

    photo_items = [
        item
        for item in catalog
        if item["era"].startswith("令和")
        and "図面" not in item["title"]
        and not item["title"].startswith("神社寺院")
    ]
    former_site_photos = [item for item in photo_items if "故地" in item["title"]]
    current_photos = [item for item in photo_items if "故地" not in item["title"] and "碑" not in item["title"]]

    landuse = public_landuse(load_region_table(RESULTS))
    slices = cell_slices(CELLS_PARQUET)
    bunk = bunkazai_counts(BUNKAZAI_CSV)
    gsi = gsi_layer_counts()
    osm = try_overpass()
    wiki = try_wikidata()

    counts = Counter(row["status"] for row in records)
    by_cat = Counter(row["category"] for row in records)
    by_conf = Counter(row["confidence"] for row in records)
    by_ward = Counter(row["muni_name"] for row in records)
    adopted = sum(1 for row in records if row["status"] == "新規")

    public_rows = [
        {
            "id": row["id"],
            "status": row["status"],
            "muni_name": row["muni_name"],
            "category": row["category"],
            "axis_existed": row["axis_existed"],
            "axis_abolished": row["axis_abolished"],
            "axis_remains": row["axis_remains"],
            "confidence": row["confidence"],
            "lead_id": row["lead_id"],
        }
        for row in records
    ]
    public = {
        "date": RETRIEVED,
        "region": "R5",
        "week": 3,
        "elapsed_days": 18,
        "rotation": "18 mod 7 = 4, floor(18/7)+1 = 3",
        "prior_candidate_rows": prior_n,
        "adopted_lost_sites": adopted,
        "rows": public_rows,
        "counts": dict(counts),
        "by_category": dict(by_cat),
        "by_confidence": dict(by_conf),
        "by_muni": dict(by_ward),
        "external_leads": {
            "ev_rows": len(events),
            "recorded_rows": len(records),
            "adopted_as_lost": adopted,
            "lead_checks": lead_summary,
            "opinion_letter_added": extra is not None,
            "instagram_r5_used_as_evidence": False,
            "haikyo_info_fetched": False,
        },
        "documents": {
            "pdfs_fetched": sum(1 for row in pdf_meta if row.get("fetched")),
            "pdfs_body_read": readable_ids,
            "pdfs_image_body_unread": image_unread,
            "license_sentence_found": license_ok,
            "catalog_items_parsed": len(catalog),
            "current_photo_items": len(current_photos),
            "former_site_photo_items": len(former_site_photos),
            "caption_wards": len(caption_rows),
        },
        "bunkazai": bunk,
        "gsi": gsi,
        "osm": {key: value for key, value in osm.items() if key != "named" or True},
        "wikidata": wiki,
        "landuse": landuse,
        "cell_slices": slices,
        "rules": {
            "high_confidence_requires_old_map_symbol": True,
            "merger_record_alone_is_not_a_lost_site": True,
            "image_pdf_below_char_threshold_is_unread": READABLE_MIN_CHARS,
        },
    }
    # OSM の named 件数は名称を含まない。そのまま残す。
    assert_public_safe(public, blocked_names)
    PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC.write_text(json.dumps(public, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    findings = [
        "# R5 非公開メモ 2026-11-13",
        "",
        "公開レポートには名称を書いていない。ここは非公開。",
        "",
        f"- 前回 candidates.csv の行数: {prior_n}",
        f"- 企画展 PDF を取得: {sum(1 for row in pdf_meta if row.get('fetched'))}",
        f"- 本文を読んだ PDF: {', '.join(readable_ids)}",
        f"- 画像のまま本文未読: {', '.join(image_unread)}",
        f"- 利用条件の文を確認: {license_ok}",
        f"- 廃社としての採用: {adopted}",
        "",
        "## 候補",
        "",
    ]
    for row in records:
        findings.extend(
            [
                f"### {row['id']} {row['lead_id']} {row['muni_name']}",
                "",
                f"- 名称: {row['name']}",
                f"- 種別: {row['category']} / 状態: {row['status']} / 確度: {row['confidence']}",
                f"- 存在: {row['axis_existed']}",
                f"- 廃止: {row['axis_abolished']}",
                f"- 遺構: {row['axis_remains']}",
                f"- 年代: {row['era']} / 目録の年: {row['catalog_eras']}",
                f"- 検証: {row['verification']}",
                f"- 目録の表題（この行の村に付いたもの）: {row['catalog_titles']}",
                f"- HTMLに名称: {row['name_in_html']} / 読めたPDFに名称: {row['name_in_readable_pdf']}",
                "",
            ]
        )
    findings.extend(["## 目録から拾った項", ""])
    for item in catalog:
        findings.append(f"- {item['title']} / {item['office']} / {item['era']}")
    findings.extend(["", "## 写真説明の区", ""])
    for label, ward, rest in caption_rows:
        findings.append(f"- {label} / {ward} / {rest}")
    findings.extend(
        [
            "",
            "## 取得していないもの",
            "",
            "- 画像 PDF の手書き本文。pdftotext が閾値未満。分類に使っていない。",
            "- 神社明細帳の画像。目録に表題はある。10本の PDF には帳面の全頁は入っていない。",
            "- 旧版地形図と迅速測図のタイル。一覧に名前が無く、イベントに座標欄が無い。",
            "- 鈴木1982、鈴木1997、森田2019、Geoshape、石仏 CSV。未取得のまま。",
            "- 廃墟検索地図は開いていない。SNS の画像は保存していない。",
            "",
        ]
    )
    write_private(records, findings)

    prov_path = WORK / "provenance_supplemental.jsonl"
    with prov_path.open("w", encoding="utf-8") as handle:
        for item in provenance:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    meta_path = WORK / "pdf_fetch_meta.json"
    meta_path.write_text(json.dumps(pdf_meta, ensure_ascii=False, indent=2), encoding="utf-8")

    import tarfile

    with tarfile.open(SUPPLEMENTAL, "w:gz") as tar:
        for folder in ("pdfs", "html"):
            base = WORK / folder
            if not base.exists():
                continue
            for path in sorted(base.rglob("*")):
                if path.is_file() and path.suffix in {".pdf", ".html"}:
                    tar.add(path, arcname=str(path.relative_to(WORK)))
        tar.add(prov_path, arcname="provenance_supplemental.jsonl")
        tar.add(meta_path, arcname="pdf_fetch_meta.json")

    summary = {
        "records": len(records),
        "adopted": adopted,
        "counts": dict(counts),
        "by_confidence": dict(by_conf),
        "by_category": dict(by_cat),
        "by_muni": dict(by_ward),
        "readable_ids": readable_ids,
        "image_unread": image_unread,
        "license_ok": license_ok,
        "bunkazai": bunk,
        "gsi_old": gsi.get("旧版"),
        "gsi_rapid": gsi.get("迅速測図"),
        "osm_ok": osm.get("ok"),
        "osm_error": osm.get("error"),
        "wiki_ok": wiki.get("ok"),
        "wiki_error": wiki.get("error"),
        "cell_slices_opened": slices.get("opened"),
        "n_r5": slices.get("n_r5"),
        "focus_bf": slices.get("building_to_forest_cells"),
        "focus_af": slices.get("agri_to_forest_cells"),
        "slice_nets_negative": slices.get("all_slice_nets_negative"),
        "landuse_flags": {
            "h1": landuse["h1_still_supported"],
            "h2": landuse["h2_still_supported"],
            "h3": landuse["h3_still_supported"],
            "h4": landuse["h4_still_supported"],
            "ge5": landuse["r5_share_ge5"],
            "residual": landuse["r5_building_loss_residual_km2"],
        },
        "current_photo_items": len(current_photos),
        "former_site_photo_items": len(former_site_photos),
        "supplemental_bytes": SUPPLEMENTAL.stat().st_size,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
