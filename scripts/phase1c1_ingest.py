#!/usr/bin/env python3
"""Independent pilot gate followed by resumable, partitioned real ingestion."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from kanagawa_ruins.temporal_pipeline import TemporalSettings, inventory, ingest_item
from kanagawa_ruins.catalog import load_layer
from kanagawa_ruins.qa.hashing import sha256
from kanagawa_ruins.raster.io import local_output


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--stage", choices=["pilot", "all"], default="pilot")
    p.add_argument("--plan", default="reports/phase1c1_registration_plan.json")
    p.add_argument("--report", required=True)
    p.add_argument("--pilot-report", default="reports/phase1c1_pilot_r2.json")
    p.add_argument("--resume-report")
    args = p.parse_args()
    settings = TemporalSettings.from_env(); settings.check_mount()
    target = local_output(args.report)
    items, duplicates, sources = inventory(settings, json.load(open(args.plan)))
    if args.stage == "all":
        gate = json.load(open(args.pilot_report))
        if gate["status"] != "PASS" or gate["errors"]:
            raise ValueError("Real-data pilot gate has not passed")
        selected = items
    else:
        selected = [x for x in items if (x["era"], x["code"]) in
                    {("2008", "14101"), ("2014", "523867"), ("2025", "523867"),
                     ("2014", "533935"), ("2025", "533935")}]
    report = dict(stage=args.stage, status="RUNNING", selected=selected,
                  inventory=items, duplicate_archives=duplicates, results=[], errors=[])
    mask = None
    if args.stage == "all":
        mask = load_layer("admin__n03__2026_kanagawa").geometry.union_all().buffer(20)
    if args.resume_report:
        previous = json.load(open(args.resume_report))
        for result in previous["results"]:
            for layer in result["layers"]:
                if sha256(settings.data_root/layer["processed_path"]) != layer["output_sha256"]:
                    raise ValueError("Cannot resume corrupt output")
            report["results"].append(result)
    done = {(r["era"],r["code"]) for r in report["results"]}
    with target.open("x") as f: json.dump(report, f, ensure_ascii=False, indent=2)
    for item in selected:
        if (item["era"],item["code"]) in done: continue
        print("processing", item["era"], item["code"], flush=True)
        try:
            result = ingest_item(settings, item, sources[item["source_id"]], publish_output=args.stage == "all",
                                 kinds={"BldA","BldL","RdEdg"} if args.stage == "pilot" else {"BldA","RdEdg"}, spatial_mask=mask)
            report["results"].append(result)
            print("counts", result["counts"], "invalid",result["excluded_invalid"], flush=True)
        except Exception as e:
            report["errors"].append(dict(item=item, error=repr(e)))
            print("ERROR", repr(e), flush=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    report["status"] = "PASS" if not report["errors"] else "PARTIAL_FAILURE"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return 1 if report["errors"] else 0


if __name__ == "__main__": raise SystemExit(main())
