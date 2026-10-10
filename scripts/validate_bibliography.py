#!/usr/bin/env python3
"""Validation tool for Kanagawa Ruins Search literature database.

Verifies:
1. ID uniqueness in references.json (P01..P12)
2. DOI format validation (regex)
3. Publication year and required metadata fields
4. Local PDF existence for items marked as acquired
5. Consistency between references.json and references.bib
6. Cross-reference consistency between Markdown reports and references.json
7. (Optional --online) Real-time DOI resolution against Crossref API
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.storage_utils import get_verified_data_root

DOI_REGEX = re.compile(r"^10\.\d{4,9}/[-._;()/:A-Za-z0-9]+$")


def parse_bib_entries(bib_text: str) -> dict[str, dict[str, str]]:
    """Simple parser for bibtex entries in references.bib."""
    entries: dict[str, dict[str, str]] = {}
    pattern = re.compile(r"@(\w+)\s*\{\s*([^,]+),([\s\S]*?)\n\}", re.MULTILINE)
    field_pattern = re.compile(r"^\s*([a-zA-Z_]+)\s*=\s*\{([\s\S]*?)\},?\s*$", re.MULTILINE)

    for match in pattern.finditer(bib_text):
        entry_type = match.group(1).lower()
        key = match.group(2).strip()
        body = match.group(3)
        fields: dict[str, str] = {"entry_type": entry_type}
        for f_match in field_pattern.finditer(body):
            f_name = f_match.group(1).lower()
            f_val = f_match.group(2).strip()
            fields[f_name] = f_val
        entries[key] = fields
    return entries


def validate_bibliography(
    data_root: Path | None = None,
    online: bool = False,
    reports_dir: Path | None = None
) -> tuple[bool, list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    target_root = data_root or get_verified_data_root()
    json_path = target_root / "literature/bibliography/references.json"
    bib_path = target_root / "literature/bibliography/references.bib"

    if not json_path.is_file():
        return False, [f"Missing canonical bibliography: {json_path}"]

    try:
        refs = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as e:
        return False, [f"Failed to parse references.json: {e}"]

    # 1. ID uniqueness and structure
    seen_ids: set[str] = set()
    ref_map: dict[str, dict] = {}
    for r in refs:
        rid = r.get("id")
        if not rid:
            errors.append(f"Record missing 'id': {r}")
            continue
        if rid in seen_ids:
            errors.append(f"Duplicate literature ID found: {rid}")
        seen_ids.add(rid)
        ref_map[rid] = r

        # Check required fields
        for field in ("authors", "title"):
            if not r.get(field):
                errors.append(f"[{rid}] Missing required field '{field}'")

        # Check year (P12 is retained as excluded audit note so year may be null)
        year = r.get("year")
        if rid != "P12":
            if not isinstance(year, int) or year < 1800 or year > 2030:
                errors.append(f"[{rid}] Invalid publication year: {year}")

        # Check DOI syntax
        doi = r.get("doi")
        if doi:
            if not DOI_REGEX.match(doi):
                errors.append(f"[{rid}] Invalid DOI format: '{doi}'")

        # Check PDF existence when marked as acquired
        pdf_status = str(r.get("pdf_status", ""))
        if "取得済" in pdf_status:
            match = re.search(r"\((literature/papers/[^)]+)\)", pdf_status)
            if match:
                rel_pdf = match.group(1)
                full_pdf = target_root / rel_pdf
                if not full_pdf.is_file():
                    errors.append(f"[{rid}] PDF marked acquired but file missing: {rel_pdf}")
                elif full_pdf.stat().st_size < 1000:
                    errors.append(f"[{rid}] PDF file suspiciously small: {rel_pdf} ({full_pdf.stat().st_size} bytes)")
            else:
                warnings.append(f"[{rid}] '取得済' marked without explicit relative path: {pdf_status}")

    # 2. BibTeX consistency
    if bib_path.is_file():
        bib_text = bib_path.read_text(encoding="utf-8")
        bib_entries = parse_bib_entries(bib_text)

        # Cross-reference note field with Pxx
        bib_by_pid: dict[str, tuple[str, dict]] = {}
        for key, fields in bib_entries.items():
            note = fields.get("note", "")
            match = re.search(r"\b(P\d{2})\b", note)
            if match:
                pid = match.group(1)
                bib_by_pid[pid] = (key, fields)

        for rid, r in ref_map.items():
            if rid == "P12":
                continue  # P12 is excluded from bib
            if rid not in bib_by_pid:
                errors.append(f"BibTeX missing entry for {rid}")
            else:
                b_key, b_fields = bib_by_pid[rid]
                # Compare year
                if r.get("year") and "year" in b_fields:
                    try:
                        b_year = int(b_fields["year"])
                        if b_year != r["year"]:
                            errors.append(
                                f"[{rid}] Year mismatch between references.json ({r['year']}) and references.bib ({b_year})"
                            )
                    except ValueError:
                        errors.append(f"[{rid}] Non-integer year in BibTeX: {b_fields['year']}")
                # Compare DOI
                r_doi = (r.get("doi") or "").lower().strip()
                b_doi = (b_fields.get("doi") or "").lower().strip()
                if r_doi != b_doi:
                    errors.append(f"[{rid}] DOI mismatch between JSON ('{r_doi}') and BibTeX ('{b_doi}')")
    else:
        errors.append(f"Missing references.bib file at {bib_path}")

    # 3. Cross-reference Markdown reports
    rep_dir = reports_dir or (ROOT / "reports")
    if rep_dir.is_dir():
        # Check phase0_4_manual_actions.md
        manual_actions_path = rep_dir / "phase0_4_manual_actions.md"
        if manual_actions_path.is_file():
            text = manual_actions_path.read_text(encoding="utf-8")
            # Must not associate P01 with Buchi
            if re.search(r"P01\s*\([^\)]*Buchi", text, re.IGNORECASE):
                errors.append("phase0_4_manual_actions.md incorrectly associates P01 with Buchi")
            # P06 DOI must be 10.3390/ijgi12030128 and not 10.3390/ijgi12030085
            if re.search(r"-\s*\*\*DOI\*\*:\s*`?10\.3390/ijgi12030085", text):
                errors.append("phase0_4_manual_actions.md specifies deprecated erroneous DOI 10.3390/ijgi12030085 as DOI for P06")
            if "10.3390/ijgi12030128" not in text:
                errors.append("phase0_4_manual_actions.md missing correct P06 DOI 10.3390/ijgi12030128")

    # 4. (Optional) Online DOI verification against Crossref
    if online:
        for rid, r in ref_map.items():
            doi = r.get("doi")
            if not doi or rid == "P12":
                continue
            url = f"https://api.crossref.org/works/{doi}"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "KanagawaRuinsBot/1.0 (mailto:blabo@example.com)"}
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    cr_title = data.get("message", {}).get("title", [""])[0]
                    # Substring check for basic match
                    r_title = r.get("title", "")
                    clean_cr = re.sub(r"[^\w\s]", "", cr_title.lower())
                    clean_r = re.sub(r"[^\w\s]", "", r_title.lower())
                    # Check overlap
                    if not any(w in clean_r for w in clean_cr.split() if len(w) > 4):
                        warnings.append(
                            f"[{rid}] Online title check divergence: JSON='{r_title[:30]}...' vs Crossref='{cr_title[:30]}...'"
                        )
            except Exception as e:
                warnings.append(f"[{rid}] Online DOI check could not resolve '{doi}': {e}")

    all_msgs = errors + [f"WARNING: {w}" for w in warnings]
    return len(errors) == 0, all_msgs


def main():
    parser = argparse.ArgumentParser(description="Validate literature references consistency.")
    parser.add_argument("--data-root", type=Path, default=None, help="Root path of databank data directory")
    parser.add_argument("--online", action="store_true", help="Run online Crossref resolution checks")
    args = parser.parse_args()

    ok, msgs = validate_bibliography(data_root=args.data_root, online=args.online)
    for m in msgs:
        print(m)
    if ok:
        print("SUCCESS: All bibliography consistency checks passed.")
        sys.exit(0)
    else:
        print(f"FAILED: Found {len([m for m in msgs if not m.startswith('WARNING')])} error(s).")
        sys.exit(1)


if __name__ == "__main__":
    main()
