#!/usr/bin/env python3
"""Phase 0.3: Geometric adjacency verification of Kanagawa Prefecture and adjacent municipalities.
Uses official Kokudo Suchi Joho N03-2026 administrative boundary datasets.
Does NOT perform any ruin detection or candidate extraction.
"""
from __future__ import annotations
import json
from pathlib import Path
import sys
import os
import tempfile
import zipfile

import geopandas as gpd
from shapely.geometry import MultiLineString, LineString, Point, MultiPoint
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from storage_utils import get_verified_data_root  # noqa: E402
from fetch_sources import safe_extract_zip  # noqa: E402

# Configure PROJ paths dynamically without hardcoded machine paths
try:
    import pyproj
    from osgeo import osr
    proj_dir = pyproj.datadir.get_data_dir()
    if proj_dir and Path(proj_dir).is_dir():
        osr.SetPROJSearchPaths([proj_dir])
        os.environ['PROJ_DATA'] = proj_dir
        os.environ['PROJ_LIB'] = proj_dir
except Exception:
    pass

TARGET_18 = [
    {"pref": "東京都", "name": "八王子市"},
    {"pref": "東京都", "name": "町田市"},
    {"pref": "東京都", "name": "多摩市"},
    {"pref": "東京都", "name": "稲城市"},
    {"pref": "東京都", "name": "調布市"},
    {"pref": "東京都", "name": "狛江市"},
    {"pref": "東京都", "name": "世田谷区"},
    {"pref": "東京都", "name": "大田区"},
    {"pref": "東京都", "name": "檜原村"},
    {"pref": "山梨県", "name": "上野原市"},
    {"pref": "山梨県", "name": "道志村"},
    {"pref": "山梨県", "name": "山中湖村"},
    {"pref": "静岡県", "name": "小山町"},
    {"pref": "静岡県", "name": "御殿場市"},
    {"pref": "静岡県", "name": "裾野市"},
    {"pref": "静岡県", "name": "三島市"},
    {"pref": "静岡県", "name": "函南町"},
    {"pref": "静岡県", "name": "熱海市"},
]


def load_n03_from_zip(zip_path: Path) -> gpd.GeoDataFrame:
    """Safely extract ZIP archive to temporary directory using safe_extract_zip and load Shapefile."""
    if not zip_path.is_file():
        raise FileNotFoundError(f"N03 archive not found: {zip_path}")
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        extracted = safe_extract_zip(zip_path, Path(tmp_dir), max_bytes=300_000_000)
        shp_files = [f for f in extracted if f.suffix.lower() == ".shp"]
        if not shp_files:
            shp_files = list(Path(tmp_dir).glob("*.shp"))
        if not shp_files:
            raise FileNotFoundError(f"No shapefile found in {zip_path}")
        gdf = gpd.read_file(shp_files[0])
    return gdf


def get_municipality_name(row) -> str:
    """Extract clean municipality name (city, ward, town, village) from N03 attributes."""
    # N03 columns typically: N03_001 (Pref), N03_002 (Sub-pref), N03_003 (Gun), N03_004 (City/Ward/Town/Village), N03_007 (Code)
    p = row.get("N03_001") or ""
    c = row.get("N03_004") or ""
    return str(c).strip()


def run_verification(data_root: Path | None = None) -> dict:
    root = data_root or get_verified_data_root()
    admin_dir = root / "raw/administrative"

    kanagawa_zip = admin_dir / "N03-20260101_14_GML.zip"
    tokyo_zip = admin_dir / "N03-20260101_13_GML.zip"
    yamanashi_zip = admin_dir / "N03-20260101_19_GML.zip"
    shizuoka_zip = admin_dir / "N03-20260101_22_GML.zip"

    print("Loading Kanagawa N03...")
    gdf_kanagawa = load_n03_from_zip(kanagawa_zip)
    gdf_kanagawa = gdf_kanagawa.to_crs(epsg=6677)

    # Individual Kanagawa municipalities for detailed contact reporting
    gdf_kanagawa["muni_name"] = gdf_kanagawa.apply(get_municipality_name, axis=1)
    kanagawa_munis = gdf_kanagawa.dissolve(by="muni_name", as_index=False)
    kanagawa_union = unary_union(gdf_kanagawa.geometry)

    adjacent_zips = [
        ("東京都", tokyo_zip),
        ("山梨県", yamanashi_zip),
        ("静岡県", shizuoka_zip),
    ]

    all_adjacent_results = []
    contacting_all = []

    for pref_name, zip_p in adjacent_zips:
        print(f"Loading {pref_name} N03 from {zip_p.name}...")
        gdf_pref = load_n03_from_zip(zip_p)
        gdf_pref = gdf_pref.to_crs(epsg=6677)
        gdf_pref["muni_name"] = gdf_pref.apply(get_municipality_name, axis=1)
        
        # Dissolve by municipality name
        munis = gdf_pref.dissolve(by="muni_name", as_index=False)

        for _, row in munis.iterrows():
            m_name = row["muni_name"]
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue

            # Quick envelope rejection to optimize processing
            if not kanagawa_union.envelope.intersects(geom):
                continue

            # Exact intersection with Kanagawa
            inter = geom.intersection(kanagawa_union)
            
            line_length = 0.0
            point_count = 0
            contact_type = "None"

            if not inter.is_empty:
                if inter.geom_type in ("LineString", "MultiLineString"):
                    line_length = inter.length
                    contact_type = "Line Contact (Shared Boundary)"
                elif inter.geom_type in ("Point", "MultiPoint"):
                    point_count = len(inter.geoms) if hasattr(inter, "geoms") else 1
                    contact_type = "Point Contact (Single Point)"
                elif inter.geom_type == "GeometryCollection":
                    lines = [g for g in inter.geoms if g.geom_type in ("LineString", "MultiLineString")]
                    points = [g for g in inter.geoms if g.geom_type in ("Point", "MultiPoint")]
                    if lines:
                        line_length = sum(g.length for g in lines)
                        contact_type = "Line Contact (Shared Boundary)"
                    elif points:
                        point_count = sum(len(g.geoms) if hasattr(g, "geoms") else 1 for g in points)
                        contact_type = "Point Contact (Single Point)"
                    else:
                        contact_type = "Other"

            # Tolerance check with 5-meter buffer if exact is empty
            buffer_contact = False
            if inter.is_empty:
                inter_buf = geom.intersection(kanagawa_union.buffer(5.0))
                if not inter_buf.is_empty:
                    buffer_contact = True

            # Identify which Kanagawa municipalities touch this municipality
            touching_kg_munis = []
            if line_length > 0 or point_count > 0 or buffer_contact:
                for _, kg_row in kanagawa_munis.iterrows():
                    kg_m = kg_row["muni_name"]
                    kg_geom = kg_row.geometry
                    if not kg_geom.envelope.intersects(geom):
                        continue
                    kg_inter = geom.intersection(kg_geom)
                    if not kg_inter.is_empty:
                        l = kg_inter.length if kg_inter.geom_type in ("LineString", "MultiLineString", "GeometryCollection") else 0
                        touching_kg_munis.append({"name": kg_m, "shared_length_m": round(l, 1)})

            res = {
                "prefecture": pref_name,
                "municipality": m_name,
                "contact_type": contact_type,
                "shared_length_m": round(line_length, 1),
                "shared_length_km": round(line_length / 1000.0, 3),
                "point_count": point_count,
                "buffer_contact_5m": buffer_contact,
                "touching_kanagawa_municipalities": touching_kg_munis,
            }

            if line_length > 0 or point_count > 0 or buffer_contact:
                contacting_all.append(res)
            
            # Check if in target 18
            for t in TARGET_18:
                if t["pref"] == pref_name and t["name"] == m_name:
                    all_adjacent_results.append(res)
                    break

    # Evaluation against target 18 list
    target_names = {(t["pref"], t["name"]) for t in TARGET_18}
    found_target_names = {(r["prefecture"], r["municipality"]) for r in all_adjacent_results}
    all_contacting_names = {(r["prefecture"], r["municipality"]) for r in contacting_all}

    missing_from_target = all_contacting_names - target_names
    in_target_not_contacting = target_names - all_contacting_names
    point_only = [r for r in all_adjacent_results if r["contact_type"] == "Point Contact (Single Point)"]

    summary = {
        "verified_at_crs": "EPSG:6677 (JGD2011 / Japan Plane Rectangular CS IX)",
        "target_18_results": all_adjacent_results,
        "all_contacting_municipalities_in_gis": contacting_all,
        "in_target_18_but_not_contacting": list(in_target_not_contacting),
        "contacting_in_gis_but_not_in_target_18": list(missing_from_target),
        "point_contact_only_municipalities": point_only,
    }

    return summary


if __name__ == "__main__":
    summary = run_verification()
    out_file = ROOT / "reports" / "phase0_3_adjacency_verification.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Adjacency verification complete. Saved to {out_file}")
