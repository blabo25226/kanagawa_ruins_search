"""Append-only acquisition ledger checks and Phase 0 snapshot accounting.

The Phase 0 snapshot (committed FULL_PASS audit) fixes the first 53 ledger records and
65 data-bank files. Later phases may append ledger records and add files; they must not
modify or remove Phase 0 records, and every later file must be explained by a record.
"""

import json
from pathlib import Path, PurePosixPath
import re

from .hashing import sha256

SHA_RE = re.compile(r"^[0-9a-f]{64}$")
# Operational files that are not data: the cross-host ledger lock used by fetch_sources.py.
OPERATIONAL_FILES = frozenset({".provenance.lock"})


def load_phase0_snapshot(audit_path):
    """Return (audit, ordered ledger records, non-ledger snapshot files) from the audit JSON."""
    audit = json.loads(Path(audit_path).read_text(encoding="utf-8"))
    records = sorted(audit["records"], key=lambda r: r["index"])
    extras = set(audit["duplicate_files"]) | set(audit["metadata_files"]) | {"provenance.jsonl"}
    return audit, records, extras


def read_ledger(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def _size(record):
    return record.get("size_bytes", record.get("bytes"))


def _valid_relative(path):
    p = PurePosixPath(path)
    return (
        isinstance(path, str)
        and path == p.as_posix()
        and not p.is_absolute()
        and ".." not in p.parts
        and len(p.parts) >= 2
        and p.parts[0] == "raw"
    )


def validate_ledger(ledger, phase0_records, *, data_root=None, verify_sha=True, reserved_paths=()):
    """Check an append-only ledger against the Phase 0 snapshot.

    1. The first len(phase0_records) entries are the Phase 0 records, in order, with the
       recorded path, size and SHA-256 (no modification, deletion, insertion or reorder).
    2. Appended entries need source_id, a contained raw/ path, a positive integer size and
       a lowercase SHA-256; paths, source_ids and SHA-256 values are unique across the
       ledger (identical content must not be registered twice); reserved_paths (Phase 0
       non-ledger files) cannot be registered.
    3. With data_root, appended files must exist with the recorded size and, when
       verify_sha, the recorded SHA-256.
    Returns dict(errors=[...], phase0=n, appended=m).
    """
    errors = []
    n0 = len(phase0_records)
    if len(ledger) < n0:
        errors.append(f"ledger has {len(ledger)} records, fewer than the {n0} Phase 0 records")
    for i, ref in enumerate(phase0_records):
        if i >= len(ledger):
            errors.append(f"Phase 0 record deleted: {ref['relative_path']}")
            continue
        r = ledger[i]
        if r.get("relative_path") != ref["relative_path"]:
            errors.append(f"Phase 0 record {i + 1} changed or moved: expected {ref['relative_path']}, found {r.get('relative_path')}")
            continue
        if _size(r) != ref["recorded_size"]:
            errors.append(f"Phase 0 size changed: {ref['relative_path']}")
        if r.get("sha256") != ref["recorded_sha256"]:
            errors.append(f"Phase 0 SHA-256 changed: {ref['relative_path']}")
    seen = {}
    for key in ("relative_path", "source_id", "sha256"):
        values = [r.get(key) for r in ledger]
        dups = sorted({v for v in values if v is not None and values.count(v) > 1})
        if dups:
            errors.append(f"duplicate {key} in ledger: {dups}")
        seen[key] = set(values)
    appended = ledger[n0:]
    for r in appended:
        path = r.get("relative_path")
        if not r.get("source_id"):
            errors.append(f"appended record without source_id: {path}")
        if not _valid_relative(path):
            errors.append(f"appended record path not a contained raw/ path: {path}")
            continue
        if path in reserved_paths:
            errors.append(f"appended record reuses a Phase 0 non-ledger file: {path}")
        size = _size(r)
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            errors.append(f"appended record has invalid size: {path}")
        sha = r.get("sha256")
        if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
            errors.append(f"appended record has invalid SHA-256: {path}")
        if data_root is not None:
            target = Path(data_root) / path
            if not target.is_file():
                errors.append(f"appended record file missing: {path}")
                continue
            if target.stat().st_size != size:
                errors.append(f"appended record size mismatch: {path}")
            elif verify_sha and isinstance(sha, str) and sha256(target) != sha:
                errors.append(f"appended record SHA-256 mismatch: {path}")
    return dict(errors=errors, phase0=min(n0, len(ledger)), appended=len(appended))


def phase1c_manifest_files(data_root, files):
    """Files under processed/phase1c/<executor>/ that are manifests or referenced by one."""
    accounted = set()
    for rel in files:
        if not rel.startswith("processed/phase1c/") or not rel.endswith(".json"):
            continue
        try:
            m = json.loads((Path(data_root) / rel).read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if not isinstance(m, dict):  # e.g. QA result lists; not a manifest
            continue
        refs = []
        if isinstance(m.get("processed_path"), str):
            refs.append(m["processed_path"])
        refs += [o["path"] for o in m.get("outputs", []) if isinstance(o, dict) and isinstance(o.get("path"), str)]
        executor_root = "/".join(rel.split("/")[:3]) + "/"
        refs = [r for r in refs if r.startswith(executor_root) and r in files]
        if refs or rel.endswith("run_manifest.json"):
            accounted.add(rel)
            accounted.update(refs)
    return accounted


def unexplained_files(all_files, snapshot_files, *, ledger_paths=(), derived=(), inventory_paths=(), phase1c=(), operational=OPERATIONAL_FILES):
    """Later files (outside the Phase 0 snapshot) that no phase record explains."""
    later = set(all_files) - set(snapshot_files)
    explained = set(ledger_paths) | set(derived) | set(inventory_paths) | set(phase1c) | set(operational)
    return sorted(later - explained)
