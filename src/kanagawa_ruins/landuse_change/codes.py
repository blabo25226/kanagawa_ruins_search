"""Land-use code validation and analysis groups.

Fine codes keep the official vintage-specific labels (config/landuse_codes.toml).
Groups are an analysis convention of this phase, not an official equivalence.
The 1976 crosswalk is coarser and its definitions differ (see GROUPS_1976 notes).
"""

import tomllib
from importlib.resources import files

# 2014 and 2021 share the official LandUseCd-09 table.
GROUPS_09 = {
    "0100": "agri",
    "0200": "agri",
    "0500": "forest",
    "0600": "wasteland",
    "0700": "building",
    "0901": "transport",
    "0902": "transport",
    "1000": "other",
    "1600": "golf",
    "1100": "water",
    "1400": "beach",
    "1500": "sea",
}

# 1976 (LandUseCd-77). Golf courses are inside "A その他の用地"; buildings are split A/B;
# 9 is 幹線交通用地 (rail, wide roads, interchanges, parking) rather than 道路/鉄道.
GROUPS_1976 = {
    "1": "agri",
    "2": "agri",
    "3": "agri",
    "4": "agri",
    "5": "forest",
    "6": "wasteland",
    "7": "building",
    "8": "building",
    "9": "transport",
    "A": "other_incl_golf",
    "B": "water",
    "C": "water",
    "D": "water",
    "E": "beach",
    "F": "sea",
}

GROUP_LABELS = {
    "agri": "農地（田・その他の農用地）",
    "forest": "森林",
    "wasteland": "荒地",
    "building": "建物用地",
    "transport": "交通用地（道路・鉄道）",
    "other": "その他の用地",
    "golf": "ゴルフ場",
    "other_incl_golf": "その他の用地（ゴルフ場含む）",
    "water": "河川地及び湖沼",
    "beach": "海浜",
    "sea": "海水域",
}

GROUP_ORDER = ["agri", "forest", "wasteland", "building", "transport", "other", "golf", "water", "beach", "sea"]
FINE_ORDER_09 = list(GROUPS_09)


def official_tables():
    data = tomllib.loads(files("kanagawa_ruins").joinpath("landuse_codes.toml").read_text(encoding="utf-8"))
    return {year: dict(v["codes"]) for year, v in data.items()}


def validate_codes(year, observed):
    """Return a report comparing observed code values with the official table of the vintage."""
    table = official_tables()[str(year)]
    observed = {str(k): int(v) for k, v in observed.items()}
    unknown = {k: v for k, v in observed.items() if k not in table}
    unused = sorted(set(table) - set(observed))
    return dict(
        year=str(year),
        official_codes=len(table),
        observed_codes=len(observed),
        unknown_codes=unknown,
        official_codes_not_observed=unused,
        consistent=not unknown,
    )


def tables_identical(year_a, year_b):
    t = official_tables()
    return t[str(year_a)] == t[str(year_b)]
