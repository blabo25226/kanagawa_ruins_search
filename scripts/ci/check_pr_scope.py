#!/usr/bin/env python3
"""GitHub-only PR change guard: no Drive access and no optional GIS dependencies."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import PurePosixPath

BANNED_EXTENSIONS = {".zip", ".7z", ".tar", ".parquet", ".geoparquet", ".gpkg", ".tif", ".tiff", ".pbf", ".duckdb", ".mbtiles", ".shp"}
ROOT_DATA_PREFIXES = ("data/raw/", "data/processed/")


def is_c1(path: str) -> bool:
    return (
        path.startswith(("reports/phase1c1_", "scripts/phase1c1_"))
        or path in ("src/kanagawa_ruins/ingest/fgd.py", "src/kanagawa_ruins/temporal_pipeline.py")
        or path.startswith("src/kanagawa_ruins/geo/temporal")
        or path == "tests/test_phase1c1.py"
    )


def is_c2(path: str) -> bool:
    return (
        path.startswith(("reports/phase1c2_", "reports/figures/phase1c2/", "scripts/phase1c2_", "src/kanagawa_ruins/landuse_change/"))
        or path == "config/phase1c2_regions.toml"
        or path.startswith("tests/test_phase1c2_")
        or path == "docs/phase1c2_terrain_extension.md"
    )


def check_paths(paths: list[str]) -> list[str]:
    problems: list[str] = []
    c1 = sorted(p for p in paths if is_c1(p))
    c2 = sorted(p for p in paths if is_c2(p))
    if c1 and c2:
        problems.append(
            "Cross-agent scope collision: the same PR changes both C1-only and C2-only files. "
            "Split the changes into separate PRs, or document and explicitly review an exception.\n"
            + "  C1: " + ", ".join(c1[:12]) + "\n"
            + "  C2: " + ", ".join(c2[:12])
        )
    for path in paths:
        if any(path.startswith(prefix) for prefix in ROOT_DATA_PREFIXES) and not path.endswith("/.gitkeep"):
            problems.append(f"Data bank content must not be committed: {path}")
        if PurePosixPath(path).suffix.lower() in BANNED_EXTENSIONS:
            problems.append(f"GIS/raw/binary artifact prohibited in Git: {path}")
    return problems


def changed_paths(base: str) -> list[str]:
    if not base.startswith("origin/") or base.count("/") != 1:
        raise ValueError("Expected a simple origin/<basebranch> ref")
    result = subprocess.run(
        ["git", "diff", "--name-only", "-z", f"{base}...HEAD"],
        check=True,
        capture_output=True,
    )
    return sorted(set(p for p in result.stdout.decode("utf-8").split("\0") if p))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="origin/<basebranch>")
    args = parser.parse_args(argv)
    files = changed_paths(args.base)
    problems = check_paths(files)
    print(f"Checked {len(files)} changed paths against {args.base}...")
    if problems:
        for msg in problems:
            print("::error::" + msg.replace("\n", "%0A"))
        return 1
    print("Scope/data guard PASS (does not verify GIS data or Drive state)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
