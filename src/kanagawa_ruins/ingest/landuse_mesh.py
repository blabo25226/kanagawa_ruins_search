"""Year-specific codebooks; no speculative correspondence between vintages."""

import re
import tomllib
from pathlib import Path


def load_codes(path=None):
    with (
        Path(path) if path else Path(__file__).parents[1] / "landuse_codes.toml"
    ).open("rb") as f:
        return tomllib.load(f)


def evidence(path, expected_year):
    """Require internal KS-META title agreement, retain publication and coverage dates separately."""
    metas = sorted(path.parent.rglob("KS-META*.xml"))
    if not metas:
        raise ValueError("Landuse year requires internal KS-META metadata")
    records = []
    for p in metas:
        from .kokudo import parse_metadata

        tree = parse_metadata(p)
        titles = [
            n.text or "" for n in tree.iter() if n.tag.rsplit("}", 1)[-1] == "title"
        ]
        dates = [
            n.text
            for n in tree.iter()
            if n.tag.rsplit("}", 1)[-1] in {"date", "beginPosition", "endPosition"}
            and n.text
            and n.text.strip()
        ]
        codes = set(re.findall(r"L03-b-(\d\d)_", " ".join(titles)))
        if codes != {str(expected_year)[-2:]}:
            raise ValueError(f"Landuse internal year mismatch: {titles}")
        records.append(dict(metadata_file=p.name, titles=titles, dates=dates))
    return records


def normalize_landuse(frame, year):
    candidates = [c for c in ("L03b_002", "土地利用種") if c in frame]
    if len(candidates) != 1:
        raise ValueError("L03-b classification field missing or ambiguous")
    field = candidates[0]
    frame = frame.copy()
    # Original field remains unchanged; labels only use this vintage's verified codebook.
    frame["landuse_code"] = frame[field].astype("string")
    codes = load_codes().get(str(year), {}).get("codes", {})
    frame["landuse_label"] = frame["landuse_code"].map(codes).fillna("unknown")
    return frame
