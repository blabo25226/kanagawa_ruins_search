#!/usr/bin/env python3
"""Quota-safe fallback: real paired meshes, <=1GB scratch, no permanent local GIS."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from kanagawa_ruins.temporal_pipeline import TemporalSettings,ingest_item,inventory
from kanagawa_ruins.storage.scratch import scratch_job
from kanagawa_ruins.qa.hashing import sha256
import phase1c1_analyze


def main():
    settings=TemporalSettings.from_env()
    gate=json.load(open(ROOT/"reports/phase1c1_pilot_r2.json"))
    if gate["status"]!="PASS":raise ValueError("Pilot gate failed")
    # Reuse independently verified inventory; no repeated remote directory enumeration.
    from kanagawa_ruins.catalog.sources import Source
    plan=json.load(open(ROOT/"reports/phase1c1_registration_plan.json"))
    sources={r["source_id"]:Source(r["source_id"],r["relative_path"],r["sha256"],r["temporal_coverage"],r["acquired_at"],r["license"],r["source_url"],r["source_page"]) for r in plan["records"]}
    selected=[x for x in gate["inventory"] if x["era"] in {"2014","2025"} and x["code"] in {"523867","533935"}]
    report=dict(stage="temporary_real_analysis_fallback",status="RUNNING",results=[],errors=[])
    with scratch_job(1_000_000_000) as job:
        for item in selected:
            source=sources[item["source_id"]];source.verify(settings.data_root)
            layers=[]
            def capture(path,lid,metadata,job):
                destination=job.path/f"{lid}.parquet"
                path.rename(destination)
                layers.append(dict(layer_id=lid,temporary_path=str(destination),output_sha256=sha256(destination),**metadata))
            print("temporary ingest",item["era"],item["code"],flush=True)
            result=ingest_item(settings,item,source,publish_output=False,kinds={"BldA","RdEdg"},job_override=job,on_layer=capture)
            result["layers"]=layers;report["results"].append(result)
            job.check()
        temporary=job.path/"ingest.json";temporary.write_text(json.dumps(report,ensure_ascii=False,indent=2))
        sys.argv=["phase1c1_analyze.py","--ingest-report",str(temporary),"--report",str(ROOT/"reports/phase1c1_pilot_analysis.json"),"--run-id","pilot_20261011","--local-pilot-artifacts",str(ROOT/"reports/phase1c1_figures"),"--skip-landuse"]
        phase1c1_analyze.main(job_override=job)
        # Persist metadata/counts but no temporary paths or geometry bodies.
        for result in report["results"]:
            for layer in result["layers"]:
                layer.pop("temporary_path",None);layer["status"]="temporary_only_cleaned_on_exit"
        report["status"]="TEMPORARY_INPUTS_VERIFIED_ANALYSIS_RUN"
        report["scratch_peak_bytes"]=job.peak_bytes
        path=ROOT/"reports/phase1c1_temporary_ingest.json"
        with path.open("x") as f:json.dump(report,f,ensure_ascii=False,indent=2)


if __name__=="__main__":main()
