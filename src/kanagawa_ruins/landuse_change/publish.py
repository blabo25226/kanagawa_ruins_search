"""Publish Phase 1-C2 outputs under $RUINS_DATA_ROOT/processed/phase1c/claude/<version>/ only.

Raw data and Phase 1-A/1-B derivatives are read-only inputs. Every output is copied
to a unique partial file, verified by SHA-256 readback, renamed, and re-verified.
Existing outputs are never overwritten: identical bytes are reported as reproduced,
differing bytes stop the run (use a new analysis version).
"""

from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import uuid

from ..qa.hashing import sha256
from ..storage.drive import is_rclone_mounted, StorageError
from . import ANALYSIS_VERSION

SUBTREE = ("processed", "phase1c", "claude")


def output_root(data_root, version=ANALYSIS_VERSION):
    return Path(data_root).resolve().joinpath(*SUBTREE, version)


def _authorized(data_root, path, *, require_mount=True):
    root = Path(data_root).resolve().joinpath(*SUBTREE)
    p = Path(path).resolve()
    if not p.is_relative_to(root):
        raise ValueError(f"Write target escapes processed/phase1c/claude: {p}")
    for protected in ("raw", "processed/phase1a", "processed/phase1b"):
        if p.is_relative_to(Path(data_root).resolve() / protected):
            raise ValueError(f"Protected input subtree: {protected}")
    if require_mount:
        ok, info = is_rclone_mounted(p)
        if not ok:
            raise StorageError(info)


def publish_file(data_root, local, relative, *, version=ANALYSIS_VERSION, require_mount=True):
    """Copy a local file to the run directory; returns an output record."""
    local = Path(local)
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("Relative output path required")
    out = output_root(data_root, version) / relative
    _authorized(data_root, out, require_mount=require_mount)
    digest = sha256(local)
    record = dict(path=str(out.relative_to(Path(data_root).resolve())), sha256=digest, bytes=local.stat().st_size)
    if out.exists():
        if sha256(out) == digest:
            return dict(record, status="already_present_reproduced")
        raise FileExistsError(f"Different output already exists; bump the analysis version: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    partial = out.with_name(out.name + "." + uuid.uuid4().hex + ".partial")
    _authorized(data_root, partial, require_mount=require_mount)
    try:
        with local.open("rb") as src, partial.open("xb") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
        if sha256(partial) != digest:
            raise OSError("Staged SHA-256 mismatch")
        partial.rename(out)
        if sha256(out) != digest:
            raise OSError("Published SHA-256 mismatch")
    finally:
        if partial.exists():
            partial.unlink()
    return dict(record, status="created")


def git_state(repo):
    def run(*args):
        return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=30).stdout.strip()

    return dict(commit=run("rev-parse", "HEAD"), branch=run("rev-parse", "--abbrev-ref", "HEAD"), dirty=bool(run("status", "--porcelain")))


def versions():
    pk = ["kanagawa-ruins", "geopandas", "shapely", "pyproj", "pyarrow", "duckdb", "numpy", "pandas", "scipy", "matplotlib"]
    out = {}
    for p in pk:
        try:
            out[p] = importlib.metadata.version(p)
        except importlib.metadata.PackageNotFoundError:
            out[p] = None
    return out


def write_run_manifest(data_root, local_dir, *, inputs, outputs, parameters, repo, version=ANALYSIS_VERSION, require_mount=True):
    manifest = dict(
        event="derived",
        phase="phase1c2",
        executor="claude",
        analysis_version=version,
        created_at=datetime.now(timezone.utc).isoformat(),
        git=git_state(repo),
        versions=versions(),
        parameters=parameters,
        inputs=inputs,
        outputs=outputs,
        policy=(
            "Descriptive land-use change analysis. No candidate extraction, ranking, existence or "
            "abandonment judgement. Raw, Phase 1-A and Phase 1-B derivatives are unchanged."
        ),
    )
    path = Path(local_dir) / "run_manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    rec = publish_file(data_root, path, "run_manifest.json", version=version, require_mount=require_mount)
    return manifest, rec
