"""Safe Phase1b CLI: default planning, explicit execute, no acquisition functions."""

import argparse
import json
from pathlib import Path
from .config import RasterSettings
from .pipeline import imagery_sources, ingest_tile, ingest_catalog, catalog_records
from ..imaging.assets import inventory
from ..imaging.catalog import search_catalog
from ..imaging.tiles import EXPECTED_TSUKUI_REGION


def main(command, argv=None):
    parser = argparse.ArgumentParser(
        description=f"Phase 1-B {command}; existing data only, default dry-run"
    )
    group = parser.add_mutually_exclusive_group()
    for flag in ["--list", "--dry-run", "--execute"]:
        group.add_argument(flag, action="store_true")
    parser.add_argument(
        "--report", type=Path, help="New local JSON report, outside the data bank"
    )
    parser.add_argument(
        "--source-id", action="append", help="Exact registered acquisition ID"
    )
    parser.add_argument(
        "--scratch-limit",
        type=int,
        default=1_000_000_000,
        help="Local scratch bytes, default 1GB, ceiling 25GB",
    )
    if command == "imaging":
        parser.add_argument("--mode", choices=["tiles", "catalog"], default="tiles")
        parser.add_argument(
            "--expected-bbox",
            type=float,
            nargs=4,
            default=EXPECTED_TSUKUI_REGION,
            help="WGS84 sanity envelope for XYZ tiles; not an oaza boundary",
        )
        parser.add_argument(
            "--bbox-native",
            type=float,
            nargs=4,
            help="Search catalog's stored lon/lat values, CRS remains unverified",
        )
        parser.add_argument("--decade")
        parser.add_argument("--footprints-only", action="store_true")
        parser.add_argument("--unacquired-only", action="store_true")
    elif command == "georef":
        parser.add_argument(
            "--gcps", type=Path, help="JSON training/validation control points"
        )
        parser.add_argument("--asset-id")
    elif command == "dem":
        parser.add_argument(
            "--reference", type=Path, help="Reviewed horizontal/vertical datum JSON"
        )
        parser.add_argument(
            "--target-crs",
            help="Optional horizontal reprojection, never a height-datum conversion",
        )
        parser.add_argument("--terrain", action="store_true")
        parser.add_argument("--asset-id")
    args = parser.parse_args(argv)
    try:
        if not 0 < args.scratch_limit <= 25_000_000_000:
            raise ValueError("Scratch ceiling is 25GB")
        configured = RasterSettings.from_env()
        settings = RasterSettings(configured.data_root, args.scratch_limit)
        settings.check_mount()
        if args.report:
            from .io import local_output

            args.report = local_output(args.report)
        if command == "inventory":
            result = inventory(settings)
            result["action"] = "read_only_inventory"
        elif command == "imaging":
            sources = imagery_sources(settings, args.mode)
            if args.source_id:
                missing = set(args.source_id) - {s.source_id for s in sources}
                if missing:
                    raise ValueError(f"Unknown/unselected source IDs: {missing}")
                sources = [s for s in sources if s.source_id in args.source_id]
            if args.mode != "catalog" and any(
                [
                    args.bbox_native,
                    args.decade,
                    args.footprints_only,
                    args.unacquired_only,
                ]
            ):
                raise ValueError("Catalog filters require --mode catalog")
            if args.execute and not sources:
                raise ValueError("No registered inputs selected")
            if args.execute and any(
                [
                    args.bbox_native,
                    args.decade,
                    args.footprints_only,
                    args.unacquired_only,
                ]
            ):
                raise ValueError("Catalog filters are read-only; omit --execute")
            results = []
            for source in sources:
                if args.execute:
                    results.append(
                        ingest_tile(source, settings, expected_bbox=args.expected_bbox)
                        if args.mode == "tiles"
                        else ingest_catalog(source, settings)
                    )
                else:
                    row = dict(
                        source_id=source.source_id,
                        relative_path=source.relative_path,
                        action="list" if args.list else "dry-run",
                    )
                    if args.mode == "catalog":
                        rows = search_catalog(
                            catalog_records(source, settings),
                            bbox_native=args.bbox_native,
                            decade=args.decade,
                            footprints_only=args.footprints_only,
                            unacquired_only=args.unacquired_only,
                        )
                        row.update(count=len(rows), photos=rows, coordinate_crs=None)
                    results.append(row)
            result = dict(status="PASS" if args.execute else "PLANNED", results=results)
        elif command == "verify":
            from ..qa.raster_verify import verify_all
            from .storage import list_artifacts

            result = (
                verify_all(settings)
                if args.execute
                else dict(
                    status="PLANNED",
                    action="list" if args.list else "dry-run",
                    assets=list_artifacts(settings),
                )
            )
        elif command in {"georef", "dem"}:
            from .jobs import planned_job, execute_job

            result = (
                execute_job(command, args, settings)
                if args.execute
                else planned_job(command, args, settings)
            )
        else:
            raise ValueError("Unknown Phase1b command")
        text = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            with args.report.open("x", encoding="utf-8") as f:
                f.write(text)
        print(text)
        return 1 if result.get("status") == "FAIL" else 0
    except Exception as e:
        parser.exit(1, f"{type(e).__name__}: {e}\n")
