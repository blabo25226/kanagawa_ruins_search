"""Read-only access to the canonical acquisition ledger (not the stale local mirror)."""

from dataclasses import dataclass
import json
from pathlib import Path
from ..config import contained_path
from ..qa.hashing import sha256


@dataclass(frozen=True)
class Source:
    source_id: str
    relative_path: str
    sha256: str
    temporal_coverage: str | None
    acquired_at: str | None
    license: str | None
    source_url: str | None
    source_page: str | None

    def verify(self, data_root):
        p = contained_path(data_root, self.relative_path)
        if not p.is_relative_to((data_root / "raw").resolve()):
            raise ValueError("Input must be under raw/")
        if sha256(p) != self.sha256:
            raise ValueError(f"Source SHA-256 mismatch: {self.relative_path}")
        return p


def read_sources(data_root: Path):
    records = [
        json.loads(l)
        for l in (data_root / "provenance.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if l.strip()
    ]
    sources = []
    paths = set()
    ids = set()
    for r in records:
        p = r.get("relative_path", r.get("dest_path"))
        sid = r.get("source_id", r.get("id"))
        if not p or not p.startswith("raw/"):
            continue
        contained_path(data_root, p)
        if p in paths or sid in ids:
            raise ValueError(f"Duplicate source path/id in acquisition ledger: {sid}")
        paths.add(p)
        ids.add(sid)
        sources.append(
            Source(
                sid,
                p,
                r["sha256"],
                r.get("temporal_coverage") or None,
                r.get("acquired_at"),
                r.get("license") or None,
                r.get("source_url") or None,
                r.get("source_page") or None,
            )
        )
    return sources
