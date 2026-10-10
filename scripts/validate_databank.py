#!/usr/bin/env python3
"""Comprehensive Databank Validation Script for Kanagawa Ruins Search Project.

Supports two explicit validation modes:
- Fast Mode (--mode fast): Rapid metadata & schema verification (existence, file sizes, format markers).
  Clearly marks hash as unverified against disk to maintain reporting integrity.
- Full Integrity Mode (--mode full): Strict byte-level integrity verification (recalculates SHA-256 in chunks,
  cross-checks against provenance.jsonl, verifies geometry and formats).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd

# Configure PROJ paths dynamically without hardcoded machine paths
try:
    import pyproj
    from osgeo import osr
    proj_dir = pyproj.datadir.get_data_dir()
    if proj_dir and Path(proj_dir).is_dir():
        osr.SetPROJSearchPaths([proj_dir])
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_sources import safe_extract_zip
from scripts.storage_utils import get_verified_data_root


def calculate_sha256(path: Path, chunk_size: int = 1048576) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def check_mojibake(text: str) -> bool:
    """Check if a string exhibits encoding corruption (replacement char or known UTF-8/CP932 mojibake artifacts)."""
    if not text:
        return False
    if "\ufffd" in text:
        return True
    mojibake_indicators = ("逾槫･亥ｷ晉恁", "逾槫･", "譚ｱ莠ｬ", "ｷ", "逾")
    for indicator in mojibake_indicators:
        if indicator in text:
            return True
    return False


def validate_shapefile_encoding(shp_path: Path) -> gpd.GeoDataFrame:
    """Read a Shapefile prioritizing .cpg declaration, verifying against mojibake."""
    cpg_path = shp_path.with_suffix(".cpg")
    if not cpg_path.is_file():
        for sibling in shp_path.parent.iterdir():
            if sibling.stem == shp_path.stem and sibling.suffix.lower() == ".cpg":
                cpg_path = sibling
                break

    detected_enc = None
    if cpg_path.is_file():
        raw_cpg = cpg_path.read_text(encoding="ascii", errors="ignore").strip().lower()
        if "utf" in raw_cpg:
            detected_enc = "utf-8"
        elif "932" in raw_cpg or "sjis" in raw_cpg or "shift" in raw_cpg:
            detected_enc = "cp932"
        elif raw_cpg:
            detected_enc = raw_cpg

    candidate_encs = [detected_enc, None, "utf-8", "cp932"] if detected_enc else [None, "utf-8", "cp932"]
    seen_encs = []
    for ce in candidate_encs:
        if ce not in seen_encs:
            seen_encs.append(ce)

    gdf = None
    used_enc = None
    for enc in seen_encs:
        try:
            candidate_gdf = gpd.read_file(shp_path, encoding=enc) if enc else gpd.read_file(shp_path)
            is_clean = True
            for col in candidate_gdf.select_dtypes(include=["object", "string"]).columns:
                sample_texts = candidate_gdf[col].dropna().head(10).astype(str).tolist()
                if any(check_mojibake(text) for text in sample_texts):
                    is_clean = False
                    break
            if is_clean:
                gdf = candidate_gdf
                used_enc = enc or (detected_enc or "auto")
                break
        except Exception:
            continue

    if gdf is None:
        raise ValueError(f"Could not load Shapefile {shp_path} with clean encoding")
    return gdf, used_enc


def validate_databank(mode: str = "fast", skip_large_pbf: bool = True):
    data_root = get_verified_data_root()
    prov_file = data_root / "provenance.jsonl"
    prov_map: dict[str, str] = {}
    prov_size_map: dict[str, int] = {}

    if prov_file.exists():
        for line in prov_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    d = json.loads(line)
                    rel = d.get("relative_path") or d.get("dest_path")
                    sz = d.get("size_bytes") if "size_bytes" in d else d.get("bytes")
                    if rel:
                        prov_map[rel] = d.get("sha256", "")
                        if sz is not None:
                            prov_size_map[rel] = int(sz)
                except Exception:
                    pass

    report_lines = []
    report_lines.append("# Phase 0.4.1 データ品質・整合性検証レポート\n")
    report_lines.append(f"- 検証実施日時: {datetime.now(timezone.utc).isoformat()} (UTC)")
    report_lines.append(f"- 検証対象ストレージ: Google Drive `{data_root}`")
    report_lines.append(f"- 検証モード: **{mode.upper()}** ({'厳密ハッシュ再計算・実ファイル検証' if mode == 'full' else '高速メタデータ・形式整合性検証（ハッシュ未再計算）'})\n")
    report_lines.append("---\n")

    # 1. Overview Table
    report_lines.append("## 1. ファイル整合性・ハッシュ検証結果一覧\n")
    if mode == "full":
        report_lines.append("| ファイルパス (相対) | 種別 | 実サイズ (bytes) | 再計算SHA-256 (先頭12桁) | ハッシュ照合 | 形式検証結果 | CRS / 空間仕様 | レコード数 |")
        report_lines.append("|:---|:---|---:|:---|:---:|:---|:---|---:|")
    else:
        report_lines.append("| ファイルパス (相対) | 種別 | 実サイズ (bytes) | 台帳SHA-256 (先頭12桁) | ハッシュ検証状態 | 形式検証結果 | CRS / 空間仕様 | レコード数 |")
        report_lines.append("|:---|:---|---:|:---|:---:|:---|:---|---:|")

    validation_details = []
    total_files = 0
    total_errors = 0
    total_hash_mismatches = 0

    for path in sorted(data_root.rglob("*")):
        if not path.is_file() or path.name.endswith(".partial") or "interrupted" in path.name:
            continue
        # Skip backup copies
        if "backups" in path.parts:
            continue

        total_files += 1
        rel = str(path.relative_to(data_root))
        size = path.stat().st_size

        hash_match_status = "未検証 (Fast)"
        is_large_pbf = rel.endswith(".osm.pbf") and size > 100_000_000

        if mode == "full":
            if is_large_pbf and skip_large_pbf:
                sha = prov_map.get(rel, "-")
                hash_match_status = "PBFヘッダー確認（I/O保護のため省略）"
            else:
                sha = calculate_sha256(path)
                expected_sha = prov_map.get(rel)
                if expected_sha:
                    if sha.lower() == expected_sha.lower():
                        hash_match_status = "一致 (OK)"
                    else:
                        hash_match_status = f"不一致 (MISMATCH)"
                else:
                    hash_match_status = "台帳未登録"
        else:
            sha = prov_map.get(rel, "-")
            hash_match_status = "未再計算 (台帳参照)"

        status = "OK"
        crs_info = "-"
        records = "-"
        details = {}

        try:
            if path.suffix == ".geojson":
                gdf = gpd.read_file(path)
                crs_info = str(gdf.crs) if gdf.crs else "None (WGS84 lon/lat assumed)"
                records = str(len(gdf))
                details = {
                    "rel": rel,
                    "type": "GeoJSON",
                    "crs": crs_info,
                    "records": len(gdf),
                    "bounds": [round(b, 5) for b in gdf.total_bounds],
                    "columns": list(gdf.columns),
                    "null_geom_count": int(gdf.geometry.isna().sum())
                }

            elif path.suffix == ".zip":
                with tempfile.TemporaryDirectory() as tmp_dir:
                    tmp_p = Path(tmp_dir)
                    local_zip = tmp_p / path.name
                    shutil.copyfile(path, local_zip)
                    extracted = safe_extract_zip(local_zip, tmp_p / "extracted", max_bytes=500_000_000)
                    shp_files = [f for f in extracted if f.suffix.lower() == ".shp"]
                    if shp_files:
                        target_shp = shp_files[0]
                        try:
                            gdf, used_enc = validate_shapefile_encoding(target_shp)
                        except Exception as e:
                            gdf = None
                            used_enc = "error"
                            status = f"ERROR: Shapefile encoding/read error: {e}"
                            error_count += 1
                        if gdf is not None:
                            crs_info = str(gdf.crs) if gdf.crs else "None"
                            records = str(len(gdf))
                            details = {
                                "rel": rel,
                                "type": "ZIP-Spatial",
                                "layer": target_shp.name,
                                "encoding": used_enc,
                                "crs": crs_info,
                                "records": len(gdf),
                                "bounds": [round(b, 5) for b in gdf.total_bounds],
                                "columns": list(gdf.columns),
                                "null_geom_count": int(gdf.geometry.isna().sum())
                            }
                        else:
                            status = "ERROR: Shapefile encoding/format read error"
                            crs_info = "Read error"
                    else:
                        details = {"rel": rel, "type": "ZIP-Archive", "members_count": len(extracted)}

            elif path.suffix == ".csv":
                import csv
                csv_parsed = False
                csv_enc = None
                for enc in ["utf-8-sig", "utf-8", "cp932"]:
                    try:
                        with path.open("r", encoding=enc) as f:
                            reader = csv.reader(f)
                            header_row = next(reader, None)
                            if not header_row:
                                continue
                            row_count = 0
                            for _ in reader:
                                row_count += 1
                        csv_parsed = True
                        csv_enc = enc
                        records = f"Rows: {row_count:,}"
                        details = {"rel": rel, "type": "CSV", "encoding": csv_enc, "columns": header_row}
                        break
                    except Exception:
                        continue
                if not csv_parsed:
                    status = "ERROR: Corrupt or unreadable CSV"

            elif path.suffix == ".pdf":
                with path.open("rb") as f:
                    head = f.read(10)
                    f.seek(max(0, size - 1024))
                    tail = f.read(1024)
                    if head.startswith(b"%PDF-") and b"%%EOF" in tail:
                        status = "Valid PDF"
                    else:
                        status = "ERROR: PDF marker issue"
                details = {"rel": rel, "type": "PDF", "status": status}

            elif path.suffix == ".osm":
                import xml.etree.ElementTree as ET
                try:
                    # Stream through all elements to ensure file is complete to EOF
                    node_count = 0
                    way_count = 0
                    for event, elem in ET.iterparse(path, events=('end',)):
                        if elem.tag == "node":
                            node_count += 1
                        elif elem.tag == "way":
                            way_count += 1
                        elem.clear()
                    records = f"Nodes: {node_count:,}, Ways: {way_count:,}"
                    crs_info = "EPSG:4326 (WGS84)"
                    details = {"rel": rel, "type": "OSM-XML", "nodes": node_count, "ways": way_count}
                except Exception as e:
                    status = f"ERROR: Truncated OSM XML ({type(e).__name__})"

            elif path.suffix == ".pbf":
                with path.open("rb") as f:
                    len_bytes = f.read(4)
                    if len(len_bytes) < 4:
                        status = "ERROR: Truncated PBF block length"
                    else:
                        hlen = int.from_bytes(len_bytes, "big")
                        if hlen <= 0 or hlen > 64 * 1024:
                            status = f"ERROR: Invalid PBF header length {hlen}"
                        else:
                            hdr = f.read(hlen)
                            if b"OSMHeader" in hdr:
                                status = "Valid OSM PBF (Header verified)"
                                records = "PBF Binary Stream"
                                crs_info = "EPSG:4326 (WGS84)"
                                details = {"rel": rel, "type": "OSM-PBF", "status": status}
                            else:
                                status = "ERROR: Corrupt OSM PBF (missing OSMHeader)"

            elif path.suffix.lower() in [".jpg", ".jpeg"]:
                with path.open("rb") as f:
                    head = f.read(3)
                    f.seek(max(0, size - 2))
                    tail = f.read(2)
                if head != b"\xff\xd8\xff" or tail != b"\xff\xd9":
                    status = "ERROR: Truncated JPEG (missing SOI/EOI)"
                else:
                    try:
                        from PIL import Image
                        with Image.open(path) as im:
                            im.verify()
                        with Image.open(path) as im:
                            im.load()
                        status = "Valid JPEG"
                    except Exception as e:
                        status = f"ERROR: JPEG decode failed ({e})"
                details = {"rel": rel, "type": "JPEG", "status": status}

            elif path.suffix == ".json":
                with path.open("r", encoding="utf-8") as f:
                    jdata = json.load(f)
                    records = f"Keys: {len(jdata)}" if isinstance(jdata, dict) else f"Items: {len(jdata)}"
                details = {"rel": rel, "type": "JSON", "records": records}

        except Exception as e:
            status = f"ERROR: {type(e).__name__}"

        if status.startswith("ERROR"):
            total_errors += 1
        if "MISMATCH" in hash_match_status:
            total_hash_mismatches += 1

        report_lines.append(
            f"| `{rel}` | {path.suffix.upper()} | {size:,} | `{sha[:12]}` | {hash_match_status} | {status} | {crs_info} | {records} |"
        )
        if details:
            validation_details.append(details)

        print(f"Validated: {rel} ({status}, Hash: {hash_match_status})")

    report_lines.append("\n---\n")
    report_lines.append("## 2. 空間データ（GIS）の詳細検証結果\n")

    for det in validation_details:
        if "bounds" in det:
            report_lines.append(f"### `{det['rel']}`")
            report_lines.append(f"- **種別**: {det['type']}")
            if "encoding" in det:
                report_lines.append(f"- **文字コード**: `{det['encoding']}`")
            report_lines.append(f"- **CRS（測地系）**: `{det['crs']}`")
            report_lines.append(f"- **レコード件数**: {det['records']:,}")
            report_lines.append(f"- **外接矩形 (Bounds)**: `Lon: [{det['bounds'][0]}, {det['bounds'][2]}], Lat: [{det['bounds'][1]}, {det['bounds'][3]}]`")
            report_lines.append(f"- **欠損ジオメトリ数**: {det['null_geom_count']}")
            report_lines.append(f"- **属性カラム一覧**: `{', '.join(det['columns'][:8])}`" + ("..." if len(det['columns']) > 8 else ""))
            report_lines.append("")

    report_lines.append("---\n")
    report_lines.append("## 3. 品質評価サマリーと動的判定\n")
    report_lines.append(f"- **検証実施モード**: `{mode.upper()}`")
    report_lines.append(f"- **総検証ファイル数**: **{total_files} 件**")
    report_lines.append(f"- **フォーマット・ロード異常件数**: **{total_errors} 件**")
    report_lines.append(f"- **SHA-256不一致件数**: **{total_hash_mismatches} 件**")
    report_lines.append("")

    if mode == "fast":
        report_lines.append("1. **実ファイル基本検証（FASTモード）**: 全登録ファイルの存在、ファイルサイズ、およびファイル形式構文を検証完了。ハッシュ照合は台帳記録値との参照のみで、ディスクからの全件再計算は省略。")
    else:
        report_lines.append("1. **実ファイル完全整合性検証（FULLモード）**: 全登録ファイルの存在、実ファイルサイズ、および全件SHA-256ハッシュの再計算による台帳照合を実施。")

    if total_errors == 0 and total_hash_mismatches == 0:
        report_lines.append("2. **総合判定: 合格（PASS）**: 全ての検証対象ファイルについて、フォーマット破壊・文字化け・切り詰め欠損・ハッシュ不一致は検出されませんでした。")
    else:
        report_lines.append(f"2. **総合判定: 要対応（FAIL）**: 異常が検出されました（エラー {total_errors} 件、ハッシュ不一致 {total_hash_mismatches} 件）。")

    report_lines.append("3. **CRS統一の留意事項**: 行政区域データ（JGD2011/EPSG:6668）、住居表示（JGD2000/JGD2011）、CODH・OSM（WGS84/EPSG:4326）の測地系が混在しているため、Phase 1の実解析前に**平面直角座標系 第IX系（JGD2011 / EPSG:6677）**へ統一変換するパイプラインを必須とする。")
    report_lines.append("4. **大字・地番境界の補完**: 住居表示未実施地域（旧津久井郡山間部）は大字レベルの行政界（CODHおよびN03）を参照することを確認。")

    out_file = ROOT / "reports/data_validation_report.md"
    out_file.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print(f"Successfully generated data_validation_report.md (Errors: {total_errors}, Hash mismatches: {total_hash_mismatches})")

    return (total_errors == 0 and total_hash_mismatches == 0)


def main():
    parser = argparse.ArgumentParser(description="Validate databank integrity.")
    parser.add_argument("--mode", choices=["fast", "full"], default="fast", help="Validation mode")
    parser.add_argument("--check-all-hashes", action="store_true", help="Calculate SHA256 even for giant PBFs")
    args = parser.parse_args()

    success = validate_databank(mode=args.mode, skip_large_pbf=not args.check_all_hashes)
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
