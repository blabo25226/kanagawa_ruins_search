#!/usr/bin/env python3
"""Standardize provenance.jsonl schema while strictly preserving audit history.

Unified Schema:
- source_id: string
- relative_path: string
- source_url: string
- source_page: string | null
- acquired_at: string (exact original timestamp)
- size_bytes: int
- sha256: string
- license: string
- data_type: string
- coverage: string
- temporal_coverage: string

Backward Compatibility Aliases:
- bytes = size_bytes
- download_url = source_url
- downloaded_at_utc = acquired_at
- format = data_type
"""

from __future__ import annotations

import json
import shutil
import tempfile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


METADATA_EXTRAS = {
    "gsi_jusho_midori": ("相模原市緑区", "2014"),
    "sagamihara_cultural_assets": ("相模原市", "2024"),
    "mlit_n03_2026_kanagawa": ("神奈川県全域", "2026"),
    "mlit_n03_2014_kanagawa": ("神奈川県全域", "2014"),
    "codh_tsukui_1955": ("旧津久井町", "1955-10-01"),
    "codh_tsukui_2005": ("旧津久井町", "2005-01-01"),
    "osm_tsukui_core": ("旧津久井地域コア", "2026-10"),
    "mlit_landuse_2021_5339": ("5339メッシュ（相模原・津久井）", "2014"),
    "mlit_railways_2023": ("全国", "2023"),
    "mlit_rivers_kanagawa": ("神奈川県", "2008"),
    "kanagawa_cultural_properties_catalog": ("神奈川県全域", "2025"),
    "kanagawa_archives_tsukui_catalog": ("旧津久井郡全域", "近世・近代"),
    "kanagawa_archives_wakayanagi_list": ("相模原市若柳村", "近世"),
    "paper_wood2024_mapreader": ("英国等（歴史地図）", "2024"),
    "codh_sagamiko_2005": ("旧相模湖町", "2005-01-01"),
    "codh_shiroyama_2005": ("旧城山町", "2005-01-01"),
    "codh_fujino_2005": ("旧藤野町", "2005-01-01"),
    "osm_tsukui_toya": ("旧津久井鳥屋地区", "2026-10"),
    "osm_tsukui_aonohara": ("旧津久井青野原地区", "2026-10"),
    "ndl_shinpen_sagami_vol5": ("津久井郡・三浦郡", "江戸後期（天保期）"),
    "paper_kanaki2003_abandoned": ("日本全国（消滅集落）", "1945-2000"),
    "paper_tani2017_konjaku": ("日本主要都市圏（古地図）", "2017"),
    "paper_fujita2007_shrine_gis": ("東京都23区部（社寺立地）", "2007"),
    "paper_oda2015_shrine_merger": ("三重県飯南・飯高地区（神社合祀）", "明治期・2015"),
    "osm_tsukui_suarashi": ("旧津久井寸沢嵐地区", "2026-10"),
    "osm_tsukui_aoyama": ("旧津久井青山地区", "2026-10"),
    "paper_berganzo2023_mounds": ("インド・パキスタン（歴史地図考古遺構）", "2023"),
    "mlit_n03_2026_tokyo": ("東京都全域", "2026"),
    "mlit_n03_2026_yamanashi": ("山梨県全域", "2026"),
    "mlit_n03_2026_shizuoka": ("静岡県全域", "2026"),
    "mlit_rivers_tokyo": ("東京都", "2008"),
    "mlit_rivers_yamanashi": ("山梨県", "2008"),
    "mlit_rivers_shizuoka": ("静岡県", "2008"),
    "mlit_cultural_properties_nationwide": ("全国44道府県", "2014"),
    "geofabrik_kanto": ("関東地方全域", "2026-10"),
    "geofabrik_chubu": ("中部地方全域", "2026-10"),
    "mlit_cultural_properties_kanagawa": ("神奈川県", "2014"),
    "mlit_cultural_properties_yamanashi": ("山梨県", "2014"),
    "mlit_cultural_properties_shizuoka": ("静岡県", "2014"),
    "tokyo_cultural_properties": ("東京都", "2024"),
    "paper_luft2021": ("ドイツ（メスチッシュブラット）", "2021"),
    "paper_tabayashi2026": ("千葉県いすみ市（迅速測図）", "2026"),
    "mlit_l03_b_1976_5338": ("5338メッシュ（大月・相模原西）", "1976"),
    "mlit_l03_b_1976_5339": ("5339メッシュ（相模原・津久井）", "1976"),
    "mlit_l03_b_2014_5338": ("5338メッシュ（大月・相模原西）", "2014"),
    "mlit_l03_b_2021_5338": ("5338メッシュ（大月・相模原西）", "2021"),
    "mlit_l03_b_2021_5339": ("5339メッシュ（相模原・津久井）", "2021"),
    "gsi_aerial_photo_catalog_tsukui": ("旧津久井4地区", "1940-1978"),
    "gsi_aerial_tile_1974_aonohara_1974": ("旧津久井青野原地区", "1974-1978"),
    "gsi_aerial_tile_1974_aoyama_1974": ("旧津久井青山地区", "1974-1978"),
    "gsi_aerial_tile_1974_toya_1974": ("旧津久井鳥屋地区", "1974-1978"),
    "gsi_aerial_tile_1974_suarashi_1974": ("旧津久井寸沢嵐地区", "1974-1978"),
    "sagamihara_buried_cultural_properties_2026": ("相模原市全域（旧津久井含む）", "2026-02-12"),
}


def migrate_record(r: dict) -> dict:
    sid = r.get("source_id") or r.get("id")
    rel = r.get("relative_path") or r.get("dest_path")
    url = r.get("download_url") or r.get("url")
    page = r.get("source_page")
    acq = r.get("acquired_at") or r.get("downloaded_at_utc") or r.get("fetched_at")
    size = r.get("size_bytes") if "size_bytes" in r else r.get("bytes")
    sha = r.get("sha256")
    lic = r.get("license") or r.get("license_note") or r.get("license_url") or "-"
    data_type = r.get("data_type") or r.get("format") or Path(rel).suffix.lstrip(".").lower()

    # Look up coverage & temporal coverage
    cov, temp_cov = METADATA_EXTRAS.get(sid, ("相模原市・神奈川県", "近現代"))

    # Special update for catalog record (normalized in Phase 0.4.1)
    if sid == "gsi_aerial_photo_catalog_tsukui":
        size = 59394
        sha = "205325245d13387c31ec29eb47bb3e2240f010dfd0064de276ab872fc6163327"
        prev_sha = "0ffa71e149a2a09770513e843c0d7ff7d174620f4c0a520cae57022d4f5ca66d"
        prev_size = 76317
    else:
        prev_sha = None
        prev_size = None

    unified = {
        "source_id": sid,
        "relative_path": rel,
        "source_url": url,
        "source_page": page,
        "acquired_at": acq,
        "size_bytes": size,
        "sha256": sha,
        "license": lic,
        "data_type": data_type,
        "coverage": cov,
        "temporal_coverage": temp_cov,
        # Backward compatibility aliases
        "bytes": size,
        "download_url": url,
        "downloaded_at_utc": acq,
        "format": data_type,
        "status": r.get("status", "downloaded")
    }

    if prev_sha:
        unified["audit_history"] = {
            "phase0_4_raw_size_bytes": prev_size,
            "phase0_4_raw_sha256": prev_sha,
            "normalization_note": "Phase 0.4.1: 欠損値1111-11-11の正規化および年代・撮影範囲検証メタデータを追加"
        }

    return unified


def main():
    from scripts.storage_utils import get_verified_data_root

    data_root = get_verified_data_root()
    prov_path = data_root / "provenance.jsonl"
    lines = [l for l in prov_path.read_text(encoding="utf-8").splitlines() if l.strip()]

    print(f"Reading {len(lines)} records from {prov_path}...")
    migrated = []
    for line in lines:
        r = json.loads(line)
        migrated.append(migrate_record(r))

    print(f"Successfully migrated {len(migrated)} records.")

    # Write using tempfile to FUSE safely
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_prov = Path(tmp_dir) / "provenance.jsonl"
        with tmp_prov.open("w", encoding="utf-8") as f:
            for rec in migrated:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        shutil.copyfile(tmp_prov, prov_path)
        print("Updated provenance.jsonl on Google Drive successfully.")


if __name__ == "__main__":
    main()
