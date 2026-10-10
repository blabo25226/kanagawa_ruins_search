#!/usr/bin/env python3
"""Unit tests for Phase 0.4.1 fixes:

1. Bibliography integrity & canonical references.json consistency
2. Google Drive databank file audit & provenance consistency
3. Aerial photo metadata normalization (sentinel handling, decade derivation, degenerate extents)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import pytest

from scripts.storage_utils import get_verified_data_root


@pytest.fixture(scope="session")
def data_root() -> Path:
    return get_verified_data_root()


# ==============================================================================
# 1. Bibliography Tests
# ==============================================================================

def test_references_json_exists_and_valid(data_root: Path):
    json_path = data_root / "literature/bibliography/references.json"
    assert json_path.is_file(), f"{json_path} must exist"
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) == 12, "Should contain exactly 12 literature entries (P01..P12)"


def test_references_unique_ids(data_root: Path):
    json_path = data_root / "literature/bibliography/references.json"
    data = json.loads(json_path.read_text(encoding="utf-8"))
    ids = [r["id"] for r in data]
    assert len(ids) == len(set(ids)), "All reference IDs must be unique"
    expected_ids = [f"P{i:02d}" for i in range(1, 13)]
    assert sorted(ids) == sorted(expected_ids)


def test_p01_tabayashi_attributes(data_root: Path):
    json_path = data_root / "literature/bibliography/references.json"
    data = json.loads(json_path.read_text(encoding="utf-8"))
    p01 = next(r for r in data if r["id"] == "P01")
    assert "田林" in p01["authors"]
    assert p01["year"] == 2021
    assert "畳み込みニューラルネットワーク" in p01["title"]
    assert "自然・人間・社会" in p01["journal"]
    assert p01.get("doi") is None


def test_p06_doi_and_authors(data_root: Path):
    json_path = data_root / "literature/bibliography/references.json"
    data = json.loads(json_path.read_text(encoding="utf-8"))
    p06 = next(r for r in data if r["id"] == "P06")
    assert p06["doi"] == "10.3390/ijgi12030128", "P06 DOI must be 10.3390/ijgi12030128"
    assert "Huang" in p06["authors"]
    assert p06["year"] == 2023
    assert p06["open_access"] is True


def test_p07_title_and_journal(data_root: Path):
    json_path = data_root / "literature/bibliography/references.json"
    data = json.loads(json_path.read_text(encoding="utf-8"))
    p07 = next(r for r in data if r["id"] == "P07")
    assert p07["title"] == "旧版地形図における地図記号の自動認識"
    assert "日本写真測量学会" in p07["journal"]
    assert p07["year"] == 2016


def test_p09_unified_year_and_doi(data_root: Path):
    json_path = data_root / "literature/bibliography/references.json"
    data = json.loads(json_path.read_text(encoding="utf-8"))
    p09 = next(r for r in data if r["id"] == "P09")
    assert p09["year"] == 2017, "P09 year must be unified to 2017 (J-STAGE publication date)"
    assert p09["doi"] == "10.5638/thagis.25.1"

    bib_path = data_root / "literature/bibliography/references.bib"
    assert bib_path.is_file()
    assert "Tani2017" in bib_path.read_text(encoding="utf-8"), "BibTeX citation key must be Tani2017"


def test_p12_excluded(data_root: Path):
    json_path = data_root / "literature/bibliography/references.json"
    data = json.loads(json_path.read_text(encoding="utf-8"))
    p12 = next(r for r in data if r["id"] == "P12")
    assert "除外" in p12["pdf_status"] or "保留" in p12["pdf_status"]
    assert p12["open_access"] is False


def test_acquired_papers_exist_and_valid_pdf(data_root: Path):
    import re

    json_path = data_root / "literature/bibliography/references.json"
    data = json.loads(json_path.read_text(encoding="utf-8"))
    acquired = [r for r in data if "取得済" in r.get("pdf_status", "")]
    assert len(acquired) >= 7, "At least 7 papers must be acquired"

    for r in acquired:
        status = r.get("pdf_status", "")
        m = re.search(r"\((literature/papers/[^)]+\.pdf)\)", status)
        assert m, f"Acquired paper {r['id']} must specify pdf path in pdf_status: {status}"
        pdf_rel = m.group(1)
        pdf_path = data_root / pdf_rel
        assert pdf_path.is_file(), f"File {pdf_path} must exist on disk"
        with open(pdf_path, "rb") as f:
            header = f.read(5)
            assert header.startswith(b"%PDF-"), f"{pdf_rel} must have valid PDF header"


# ==============================================================================
# 2. Provenance & Databank Integrity Tests
# ==============================================================================

def test_provenance_jsonl_integrity(data_root: Path):
    prov_path = data_root / "provenance.jsonl"
    assert prov_path.is_file()

    records = []
    with open(prov_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    assert len(records) == 53, "provenance.jsonl must contain exactly 53 registered download records"

    rel_paths = [r["relative_path"] for r in records]
    assert len(rel_paths) == len(set(rel_paths)), "All relative paths must be unique in provenance.jsonl"

    for r in records:
        assert "relative_path" in r
        assert "size_bytes" in r or "bytes" in r
        assert "sha256" in r
        assert "source_id" in r
        # Verify file exists on disk
        target = data_root / r["relative_path"]
        assert target.is_file(), f"Registered file missing on disk: {target}"
        recorded_size = r.get("size_bytes") or r.get("bytes")
        assert target.stat().st_size == recorded_size, f"Size mismatch for {r['relative_path']}"


def test_databank_actual_files_classification(data_root: Path):
    all_files = [
        p.relative_to(data_root).as_posix()
        for p in data_root.rglob("*")
        if p.is_file() and not any(part == "backups" for part in p.parts)
    ]

    assert len(all_files) == 65, f"Expected 65 actual files on Google Drive, found {len(all_files)}"

    prov_path = data_root / "provenance.jsonl"
    prov_records = [
        json.loads(line)["relative_path"]
        for line in prov_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert len(prov_records) == 53

    remaining = set(all_files) - set(prov_records)
    # Remaining must be exactly 12 files (4 duplicates + 7 metadata + 1 provenance.jsonl)
    assert len(remaining) == 12
    assert "provenance.jsonl" in remaining


# ==============================================================================
# 3. Aerial Photo Metadata Normalization Tests
# ==============================================================================

def test_aerial_catalog_normalization(data_root: Path):
    cat_path = data_root / "raw/aerial_photos/metadata/tsukui_aerial_photos_catalog.json"
    assert cat_path.is_file()
    catalog = json.loads(cat_path.read_text(encoding="utf-8"))

    photos = catalog if isinstance(catalog, list) else catalog.get("photos", [])
    assert len(photos) == 42, f"Catalog must contain 42 photo records, found {len(photos)}"

    # 1. No 1111-11-11 sentinel values
    sentinels = [p for p in photos if p.get("date") == "1111-11-11"]
    assert len(sentinels) == 0, "No records should have raw 1111-11-11 sentinel date"

    # Exactly 6 unknown date records
    unknown_dates = [p for p in photos if p.get("date") is None]
    assert len(unknown_dates) == 6, f"Expected 6 unknown date records, found {len(unknown_dates)}"
    for p in unknown_dates:
        assert p.get("date_status") == "unknown"
        assert p.get("decade") == "unknown"

    # 2. Decade classification strictly matches flight year
    for p in photos:
        decade = p.get("decade")
        assert decade in {"1940s", "1950s", "1960s", "1970s", "unknown"}
        date_str = p.get("date")
        if date_str:
            year = int(date_str.split("-")[0])
            expected_decade = f"{year // 10 * 10}s"
            assert decade == expected_decade, f"Decade {decade} does not match flight year {year}"

    # 3. Degenerate point footprints detected
    point_only = [p for p in photos if p.get("is_point_only") is True]
    assert len(point_only) == 8, f"Expected 8 point-only degenerate photos, found {len(point_only)}"
    for p in point_only:
        assert p.get("footprint_status") == "unknown"

    valid_rectangles = [p for p in photos if p.get("footprint_status") == "valid"]
    assert len(valid_rectangles) == 34, f"Expected 34 valid bounding boxes, found {len(valid_rectangles)}"
    for p in valid_rectangles:
        assert p.get("is_point_only") is False
