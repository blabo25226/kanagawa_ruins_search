"""Recognize complete derived pairs for Phase 0 file accounting, without reclassifying raw."""

import json
from ..config import contained_path
from ..catalog.layers import validate_layer_id


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
    return result
