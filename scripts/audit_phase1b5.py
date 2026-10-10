#!/usr/bin/env python3
"""Phase 1-B.5: Comprehensive read-only audit of newly acquired GSI FGD datasets.
Strictly read-only: does not modify or extract raw ZIP files on disk.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sys
import zipfile
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.storage_utils import get_verified_data_root

# Kanagawa 2nd mesh codes intersecting prefecture polygon (calculated via KSJ N03)
KANAGAWA_INTERSECTING_2ND_MESHES = sorted([
    "523867", "523877", "523950", "523951", "523954", "523955", "523960", "523961",
    "523964", "523965", "523970", "523971", "523972", "523973", "523974", "523975",
    "533807", "533817", "533900", "533901", "533902", "533903", "533904", "533905",
    "533910", "533911", "533912", "533913", "533914", "533915", "533916", "533920",
    "533921", "533922", "533923", "533924", "533925", "533926", "533930", "533931",
    "533932", "533933", "533934", "533935", "533941"
])


def calculate_sha256(path: Path, chunk_size: int = 4194304) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def extract_xml_sample_meta(raw_bytes: bytes, filename: str) -> Dict[str, Any]:
    # Detect encoding
    encoding = "utf-8"
    if raw_bytes.startswith(b"<?xml") and b"Shift_JIS" in raw_bytes[:100]:
        encoding = "shift_jis"
    
    try:
        text = raw_bytes.decode(encoding, errors="replace")
    except Exception:
        text = raw_bytes.decode("latin-1", errors="replace")
        encoding = "latin-1"

    # Schema
    schema_match = re.search(r'xsi:schemaLocation="([^"]+)"', text)
    schema = schema_match.group(1) if schema_match else None

    # SRS
    srs_match = re.search(r'srsName="([^"]+)"', text)
    srs = srs_match.group(1) if srs_match else None

    # Envelope
    lower_match = re.search(r'<gml:lowerCorner>([^<]+)</gml:lowerCorner>', text)
    upper_match = re.search(r'<gml:upperCorner>([^<]+)</gml:upperCorner>', text)
    envelope = None
    if lower_match and upper_match:
        envelope = {
            "lower": lower_match.group(1).strip(),
            "upper": upper_match.group(1).strip()
        }

    # Mesh code in XML
    mesh_match = re.search(r'<mesh>([^<]+)</mesh>', text)
    xml_mesh = mesh_match.group(1).strip() if mesh_match else None

    # Dates
    dev_dates = re.findall(r'<devDate[^>]*>\s*<gml:timePosition>([^<]+)</gml:timePosition>', text)
    if not dev_dates:
        dev_dates = re.findall(r'<devDate>([^<]+)</devDate>', text)

    vis_dates = re.findall(r'<visDate[^>]*>\s*<gml:timePosition>([^<]+)</gml:timePosition>', text)
    if not vis_dates:
        vis_dates = re.findall(r'<visDate>([^<]+)</visDate>', text)

    lfspan_dates = re.findall(r'<lfSpanFr[^>]*>\s*<gml:timePosition>([^<]+)</gml:timePosition>', text)

    # orgGILvl (information level)
    gilvl_match = re.search(r'<orgGILvl>([^<]+)</orgGILvl>', text)
    org_gi_lvl = gilvl_match.group(1).strip() if gilvl_match else None

    # orgMDId
    mdid_match = re.search(r'<orgMDId>([^<]+)</orgMDId>', text)
    org_md_id = mdid_match.group(1).strip() if mdid_match else None

    # Feature type detection (e.g. DEM, AdmArea, RdEdg, BldA, etc.)
    features_found = set()
    for feat in ["DEM", "AdmArea", "AdmBdry", "AdmPt", "RdEdg", "BldA", "SBldA", "WA", "WL", "CP", "ElevPt", "CommBdry", "CommPt"]:
        if f"<{feat}" in text:
            features_found.add(feat)

    return {
        "xml_filename": filename,
        "encoding": encoding,
        "schema": schema,
        "srs_name": srs,
        "envelope": envelope,
        "xml_mesh": xml_mesh,
        "dev_dates": dev_dates[:3],
        "vis_dates": vis_dates[:3],
        "lfspan_dates": lfspan_dates[:3],
        "org_gi_lvl": org_gi_lvl,
        "org_md_id": org_md_id,
        "features": sorted(features_found)
    }


def parse_inner_zip_meta(inner_name: str, zf: zipfile.ZipFile, s_info: zipfile.ZipInfo) -> Dict[str, Any]:
    mesh_code = None
    muni_code = None
    item_kind = None
    dataset_date = None

    # Match inner filename patterns:
    # 1. Mesh Basic: FG-GML-523867-ALL-20140701.zip or FG-GML-523867-ALL-20250701.zip
    m1 = re.match(r"^FG-GML-(\d{6})-ALL-(\d{8})\.zip$", inner_name)
    # 2. Muni Basic: FG-GML-14101-ALL-20080331-Z101.zip
    m2 = re.match(r"^FG-GML-(\d{5})-ALL-(\d{8})(-Z\d+)?\.zip$", inner_name)
    # 3. DEM5A: FG-GML-523867-DEM5A-(\d{8})\.zip
    m3 = re.match(r"^FG-GML-(\d{6})-DEM5A-(\d{8})\.zip$", inner_name)
    # 4. DEM10B: FG-GML-523867-DEM10B-(\d{8})\.zip
    m4 = re.match(r"^FG-GML-(\d{6})-DEM10B-(\d{8})\.zip$", inner_name)

    if m1:
        mesh_code = m1.group(1)
        item_kind = "basic_mesh"
        dataset_date = m1.group(2)
    elif m2:
        muni_code = m2.group(1)
        item_kind = "basic_muni"
        dataset_date = m2.group(2)
    elif m3:
        mesh_code = m3.group(1)
        item_kind = "dem5a"
        dataset_date = m3.group(2)
    elif m4:
        mesh_code = m4.group(1)
        item_kind = "dem10b"
        dataset_date = m4.group(2)
    else:
        # Fallback regex
        mesh_cand = re.search(r"(\d{6})", inner_name)
        if mesh_cand:
            mesh_code = mesh_cand.group(1)
        date_cand = re.search(r"(\d{8})", inner_name)
        if date_cand:
            dataset_date = date_cand.group(1)
        if "DEM5A" in inner_name:
            item_kind = "dem5a"
        elif "DEM10B" in inner_name:
            item_kind = "dem10b"
        elif "ALL" in inner_name:
            item_kind = "basic_mesh" if mesh_code else "basic_muni"

    # Read inner zip header and sample XML
    xml_count = 0
    sample_xml_meta = None
    all_xml_names = []

    with zf.open(s_info) as sf:
        inner_zip_bytes = io.BytesIO(sf.read())
        with zipfile.ZipFile(inner_zip_bytes, "r") as inner_zf:
            all_xml_names = [f for f in inner_zf.namelist() if f.endswith(".xml")]
            xml_count = len(all_xml_names)
            if all_xml_names:
                sample_name = all_xml_names[0]
                with inner_zf.open(sample_name) as xf:
                    # Read sample bytes (up to 32KB to capture headers and first feature)
                    raw_bytes = xf.read(32768)
                    sample_xml_meta = extract_xml_sample_meta(raw_bytes, sample_name)

    return {
        "inner_filename": inner_name,
        "compressed_bytes": s_info.compress_size,
        "uncompressed_bytes": s_info.file_size,
        "mesh_code": mesh_code,
        "muni_code": muni_code,
        "item_kind": item_kind,
        "dataset_date": dataset_date,
        "xml_count": xml_count,
        "sample_xml_meta": sample_xml_meta,
        "xml_names_sample": all_xml_names[:5]
    }


def audit_all_fgd() -> Tuple[Dict[str, Any], Dict[str, Any]]:
    root = get_verified_data_root()
    fgd_dir = root / "raw/fgd"

    zip_paths = sorted(fgd_dir.glob("*.zip"))
    print(f"Discovered {len(zip_paths)} ZIP files in {fgd_dir}")

    packages = []
    seen_hashes: Dict[str, str] = {}
    mesh_coverage_by_category: Dict[str, Set[str]] = defaultdict(set)
    muni_coverage_by_category: Dict[str, Set[str]] = defaultdict(set)

    for zp in zip_paths:
        print(f"\n--- Auditing {zp.name} ---")
        size = zp.stat().st_size
        sha256 = calculate_sha256(zp)
        print(f"  Size: {size:,} bytes")
        print(f"  SHA-256: {sha256}")

        is_dup = False
        dup_of = None
        if sha256 in seen_hashes:
            is_dup = True
            dup_of = seen_hashes[sha256]
            print(f"  DUPLICATE DETECTED: identical to {dup_of}")
        else:
            seen_hashes[sha256] = zp.name

        with zipfile.ZipFile(zp, "r") as zf:
            inner_infos = [f for f in zf.infolist() if f.filename.endswith(".zip")]
            total_uncompressed = sum(f.file_size for f in inner_infos)
            print(f"  Inner packages: {len(inner_infos)} (total uncompressed: {total_uncompressed:,} bytes)")

            inner_details = []
            pkg_mesh_codes = set()
            pkg_muni_codes = set()
            pkg_item_kinds = set()
            pkg_dataset_dates = set()
            pkg_srs_names = set()
            pkg_schemas = set()
            total_xml_count = 0

            for idx, s_info in enumerate(inner_infos):
                in_meta = parse_inner_zip_meta(s_info.filename, zf, s_info)
                inner_details.append(in_meta)
                total_xml_count += in_meta["xml_count"]
                if in_meta["mesh_code"]:
                    pkg_mesh_codes.add(in_meta["mesh_code"])
                if in_meta["muni_code"]:
                    pkg_muni_codes.add(in_meta["muni_code"])
                if in_meta["item_kind"]:
                    pkg_item_kinds.add(in_meta["item_kind"])
                if in_meta["dataset_date"]:
                    pkg_dataset_dates.add(in_meta["dataset_date"])
                if in_meta["sample_xml_meta"]:
                    srs = in_meta["sample_xml_meta"].get("srs_name")
                    if srs:
                        pkg_srs_names.add(srs)
                    sch = in_meta["sample_xml_meta"].get("schema")
                    if sch:
                        pkg_schemas.add(sch)

            # Classify package category & subtype
            category = "unknown"
            subtype = "unknown"
            primary_era = None

            if "dem5a" in pkg_item_kinds:
                category = "dem"
                primary_year = sorted(pkg_dataset_dates)[0][:4] if pkg_dataset_dates else "unknown"
                subtype = f"dem5a_{primary_year}"
                primary_era = primary_year
            elif "dem10b" in pkg_item_kinds:
                category = "dem"
                primary_year = sorted(pkg_dataset_dates)[0][:4] if pkg_dataset_dates else "unknown"
                subtype = f"dem10b_{primary_year}"
                primary_era = primary_year
            elif "basic_muni" in pkg_item_kinds:
                category = "basic"
                primary_year = sorted(pkg_dataset_dates)[0][:4] if pkg_dataset_dates else "unknown"
                subtype = f"basic_muni_{primary_year}"
                primary_era = primary_year
            elif "basic_mesh" in pkg_item_kinds:
                category = "basic"
                primary_year = sorted(pkg_dataset_dates)[0][:4] if pkg_dataset_dates else "unknown"
                # Check mesh prefix
                prefixes = {m[:4] for m in pkg_mesh_codes}
                p_str = "-".join(sorted(prefixes))
                subtype = f"basic_mesh_{primary_year}_{p_str}"
                primary_era = primary_year

            # Record coverage
            cat_key = f"{category}_{subtype}"
            for m in pkg_mesh_codes:
                mesh_coverage_by_category[cat_key].add(m)
            for m in pkg_muni_codes:
                muni_coverage_by_category[cat_key].add(m)

            pkg_entry = {
                "filename": zp.name,
                "relative_path": f"raw/fgd/{zp.name}",
                "size_bytes": size,
                "sha256": sha256,
                "is_duplicate": is_dup,
                "duplicate_of": dup_of,
                "category": category,
                "subtype": subtype,
                "primary_era_year": primary_era,
                "inner_zip_count": len(inner_infos),
                "total_xml_count": total_xml_count,
                "total_uncompressed_bytes": total_uncompressed,
                "dataset_dates": sorted(pkg_dataset_dates),
                "coordinate_systems": sorted(pkg_srs_names),
                "schemas": sorted(pkg_schemas),
                "mesh_codes": sorted(pkg_mesh_codes),
                "muni_codes": sorted(pkg_muni_codes),
                "inner_files": inner_details
            }
            packages.append(pkg_entry)

    # Coverage summary
    all_known_meshes = set()
    for cat, meshes in mesh_coverage_by_category.items():
        all_known_meshes.update(meshes)

    coverage_summary = {
        "kanagawa_intersecting_2nd_meshes_count": len(KANAGAWA_INTERSECTING_2ND_MESHES),
        "kanagawa_intersecting_2nd_meshes": KANAGAWA_INTERSECTING_2ND_MESHES,
        "coverage_by_subtype": {
            k: {
                "mesh_count": len(v),
                "meshes": sorted(v),
                "kanagawa_meshes_covered": sorted(set(v) & set(KANAGAWA_INTERSECTING_2ND_MESHES)),
                "kanagawa_coverage_rate": f"{(len(set(v) & set(KANAGAWA_INTERSECTING_2ND_MESHES)) / len(KANAGAWA_INTERSECTING_2ND_MESHES) * 100):.1f}%",
                "kanagawa_missing_meshes": sorted(set(KANAGAWA_INTERSECTING_2ND_MESHES) - set(v)),
                "extra_meshes_outside_kanagawa": sorted(set(v) - set(KANAGAWA_INTERSECTING_2ND_MESHES))
            }
            for k, v in mesh_coverage_by_category.items()
        },
        "muni_coverage_by_subtype": {
            k: {
                "muni_count": len(v),
                "munis": sorted(v)
            }
            for k, v in muni_coverage_by_category.items()
        }
    }

    full_inventory = {
        "metadata": {
            "audit_phase": "Phase 1-B.5",
            "audit_date": "2026-10-11",
            "target_directory": "raw/fgd",
            "total_packages_count": len(packages),
            "unique_packages_count": len(seen_hashes),
            "total_raw_bytes": sum(p["size_bytes"] for p in packages),
            "unique_raw_bytes": sum(p["size_bytes"] for p in packages if not p["is_duplicate"]),
            "total_inner_zips": sum(p["inner_zip_count"] for p in packages),
            "total_xml_count": sum(p["total_xml_count"] for p in packages)
        },
        "packages": packages,
        "spatial_coverage": coverage_summary
    }

    return full_inventory, coverage_summary


def main():
    inventory, coverage = audit_all_fgd()

    # Write inventory JSON to reports/phase1b5_inventory.json
    out_path = ROOT / "reports/phase1b5_inventory.json"
    out_path.write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote full inventory to {out_path}")

    # Also output summary to console
    print("\n================ SUMMARY ================")
    print(f"Total packages: {inventory['metadata']['total_packages_count']}")
    print(f"Unique packages: {inventory['metadata']['unique_packages_count']}")
    print(f"Total bytes: {inventory['metadata']['total_raw_bytes']:,} bytes ({inventory['metadata']['total_raw_bytes']/(1024**3):.2f} GB)")
    print(f"Total XML/GML tiles: {inventory['metadata']['total_xml_count']:,}")
    print("\nCoverage by subtype:")
    for sub, cov in coverage["coverage_by_subtype"].items():
        print(f"  {sub}: {cov['mesh_count']} meshes total, Kanagawa coverage: {cov['kanagawa_coverage_rate']} ({len(cov['kanagawa_meshes_covered'])}/{coverage['kanagawa_intersecting_2nd_meshes_count']})")


if __name__ == "__main__":
    main()
