"""CLI orchestration only: no downloads, no candidate inference."""

import argparse
import json
from pathlib import Path
from .config import Settings
from .pipeline import plan, classify, ingest_source
from .qa.verify import verify_all


def ingest_main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    a = p.add_mutually_exclusive_group()
    a.add_argument("--list", action="store_true")
    a.add_argument("--dry-run", action="store_true")
    a.add_argument("--execute", action="store_true")
    p.add_argument("--area", choices=["tsukui", "all"], default="tsukui")
    p.add_argument("--layers", default="admin,osm,railways,rivers,cultural,landuse")
    p.add_argument(
        "--include-pbf",
        action="store_true",
        help="Stream existing regional PBFs, after XML validation",
    )
    p.add_argument(
        "--source-id", action="append", help="Restrict to exact acquisition source IDs"
    )
    p.add_argument("--report", type=Path)
    args = p.parse_args(argv)
    try:
        settings = Settings.from_env()
        selected = plan(settings, args.layers.split(","), args.area, args.include_pbf)
        if args.source_id:
            unknown = set(args.source_id) - {s.source_id for s in selected}
            if unknown:
                raise ValueError(f"Unknown/unselected source IDs: {unknown}")
            selected = [s for s in selected if s.source_id in args.source_id]
        if not args.execute:
            for s in selected:
                print(
                    json.dumps(
                        dict(
                            source_id=s.source_id,
                            path=s.relative_path,
                            group=classify(s),
                            action="list" if args.list else "dry-run",
                        ),
                        ensure_ascii=False,
                    )
                )
            return 0
        results = []
        errors = []
        for s in selected:
            print("INGEST " + s.source_id, flush=True)
            try:
                layers = ingest_source(s, settings=settings, area=args.area)
                results.extend(layers)
                print(
                    json.dumps(
                        dict(
                            source_id=s.source_id,
                            layers=[
                                dict(
                                    layer_id=m["layer_id"],
                                    count=m["feature_count"],
                                    status=m["status"],
                                )
                                for m in layers
                            ],
                        ),
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
            except Exception as e:
                errors.append(
                    dict(source_id=s.source_id, error=f"{type(e).__name__}: {e}")
                )
                print(json.dumps(errors[-1], ensure_ascii=False), flush=True)
                # Losing a genuine mount is a global stop, never proceed to another write.
                settings.check_mount()
        report = dict(
            status="PASS" if not errors and results else "FAIL",
            layers=results,
            errors=errors,
        )
        if args.report:
            if args.report.resolve().is_relative_to(settings.data_root.resolve()):
                raise ValueError("CLI report must be local, outside the data bank")
            args.report.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        return 1 if report["status"] == "FAIL" else 0
    except Exception as e:
        p.exit(1, f"{type(e).__name__}: {e}\n")


def verify_main(argv=None):
    p = argparse.ArgumentParser(
        description="Verify all Phase 1-A catalogued derivatives"
    )
    p.add_argument("--report", type=Path)
    args = p.parse_args(argv)
    try:
        settings = Settings.from_env()
        if args.report and args.report.resolve().is_relative_to(
            settings.data_root.resolve()
        ):
            raise ValueError("CLI report must be local, outside the data bank")
        result = verify_all(settings=settings)
        text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.report:
            args.report.write_text(text, encoding="utf-8")
        print(text)
        return 0 if result["status"] == "PASS" else 1
    except Exception as e:
        p.exit(1, f"{type(e).__name__}: {e}\n")
