"""Recognize complete derived pairs for Phase 0 file accounting, without reclassifying raw."""

import json
from ..config import contained_path
from ..catalog.layers import validate_layer_id
from .hashing import sha256


def registered_derived_files(data_root, actual_files):
    result = set()
    prefix = "processed/phase1a/manifests/"
    for rel in actual_files:
        if not rel.startswith(prefix) or not rel.endswith(".json"):
            continue
        try:
            m = json.loads(actual_files[rel].read_text(encoding="utf-8"))
            lid = validate_layer_id(m["layer_id"])
            expected = f"processed/phase1a/vectors/{lid}.parquet"
            if (
                rel != prefix + lid + ".json"
                or m["processed_path"] != expected
                or expected not in actual_files
                or m["event"] != "derived"
                or not m["source_sha256"]
                or not m["output_sha256"]
            ):
                continue
            contained_path(data_root, expected)
            result.update((rel, expected))
        except (ValueError, KeyError, OSError, TypeError):
            continue
    prefix = "processed/phase1b/manifests/"
    from ..catalog.sources import read_sources

    try:
        sources = (
            {s.relative_path: s for s in read_sources(data_root)}
            if any(r.startswith(prefix) for r in actual_files)
            else {}
        )
    except (ValueError, KeyError, OSError, TypeError):
        sources = {}
    claimed = set()
    for rel in actual_files:
        if not rel.startswith(prefix) or not rel.endswith(".json"):
            continue
        try:
            m = json.loads(actual_files[rel].read_text(encoding="utf-8"))
            aid = validate_layer_id(m["asset_id"])
            expected = m["processed_path"]
            output = contained_path(data_root, expected)
            source = contained_path(data_root, m["original_path"])
            acquired = sources.get(m["original_path"])
            if (
                rel != prefix + aid + ".json"
                or m.get("event") != "derived"
                or m.get("phase") != "phase1b"
                or not expected.startswith("processed/phase1b/")
                or expected.startswith(prefix)
                or output.stem != aid
                or output.suffix not in {".tif", ".json"}
                or expected not in actual_files
                or expected in claimed
                or not m["original_path"].startswith("raw/")
                or not source.is_file()
                or not source.is_relative_to((data_root / "raw").resolve())
                or acquired is None
                or acquired.source_id != m["source_id"]
                or acquired.sha256 != m["source_sha256"]
                or not m["processing_version"]
                or sha256(output) != m["output_sha256"]
                or sha256(source) != m["source_sha256"]
                or output.stat().st_size != m["bytes"]
            ):
                continue
            claimed.add(expected)
            result.update((rel, expected))
        except (ValueError, KeyError, OSError, TypeError):
            continue
    return result
