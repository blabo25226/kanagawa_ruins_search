#!/usr/bin/env python3
"""Storage utilities for Google Drive / rclone verification and safe I/O."""
from __future__ import annotations
import os
from pathlib import Path
import shutil
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]


class StorageError(Exception):
    """Raised when data storage directory or mount is invalid or insecure."""
    pass


def load_env_var(name: str, root: Path | None = None) -> str | None:
    val = os.environ.get(name)
    if val:
        return val
    project_root = root or ROOT
    env_file = project_root / '.env'
    if env_file.is_file():
        for line in env_file.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                if k.strip() == name:
                    return v.strip().strip('"').strip("'")
    return None


def get_mount_entries(mounts_path: Path | None = None) -> list[tuple[str, Path, str]]:
    """Parse mount entries as (device, mount_point_path, fstype)."""
    mpath = mounts_path or Path('/proc/mounts')
    entries = []
    if mpath.is_file():
        lines = mpath.read_text(encoding='utf-8').splitlines()
        for line in lines:
            parts = line.split()
            if len(parts) >= 3:
                dev = parts[0]
                mp = Path(parts[1]).resolve()
                fstype = parts[2]
                entries.append((dev, mp, fstype))
    else:
        # Fallback to mount command if /proc/mounts is unavailable
        mount_bin = shutil.which('mount')
        if mount_bin:
            res = subprocess.run([mount_bin], capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    # Format: device on /path type fstype (opts)
                    parts = line.split()
                    if len(parts) >= 5 and parts[1] == 'on' and parts[3] == 'type':
                        dev = parts[0]
                        mp = Path(parts[2]).resolve()
                        fstype = parts[4]
                        entries.append((dev, mp, fstype))
    return entries


def is_rclone_mounted(path: Path | str, mounts_path: Path | None = None) -> tuple[bool, str]:
    """
    Verify that path resides under a genuine rclone mount point.
    Strictly uses path hierarchy (parent check), avoiding naive string prefix matching.
    """
    try:
        target = Path(path).expanduser().resolve()
    except Exception as e:
        return False, f"Invalid path: {e}"

    entries = get_mount_entries(mounts_path)
    if not entries:
        return False, "Could not read mount table"

    # Find the deepest (longest) mount point containing target
    matching_mount = None
    max_parts = -1

    for dev, mp, fstype in entries:
        # Strict hierarchy check: target must be the mount point or a descendant of it
        if target == mp or mp in target.parents:
            depth = len(mp.parts)
            if depth > max_parts:
                max_parts = depth
                matching_mount = (dev, mp, fstype)

    if not matching_mount:
        return False, f"No mount point found for {target}"

    dev, mp, fstype = matching_mount
    is_rclone = (
        fstype == 'fuse.rclone'
        or ('rclone' in fstype.lower())
        or ('fuse' in fstype.lower() and ('rclone' in dev.lower() or 'gdrive' in dev.lower()))
    )

    info = f"{dev} on {mp} ({fstype})"
    if is_rclone:
        return True, info
    else:
        return False, f"Path is on non-rclone filesystem: {info}"


def get_verified_data_root(root: Path | None = None, mounts_path: Path | None = None) -> Path:
    """Resolve RUINS_DATA_ROOT, verify its existence and rclone mount status."""
    val = load_env_var('RUINS_DATA_ROOT', root=root)
    if not val:
        raise StorageError(
            "RUINS_DATA_ROOT is not set. Please set the environment variable or create .env file."
        )

    data_root = Path(val).expanduser().resolve()
    if not data_root.is_dir():
        raise StorageError(f"RUINS_DATA_ROOT directory does not exist: {data_root}")

    mounted, info = is_rclone_mounted(data_root, mounts_path=mounts_path)
    if not mounted:
        raise StorageError(f"Google Drive rclone mount verification failed for {data_root}: {info}")

    return data_root


def safe_probe_write(directory: Path) -> None:
    """Perform exclusive, non-overwriting probe write with unique filename."""
    probe_id = uuid.uuid4().hex
    test_file = directory / f".ruins_probe_{probe_id}.tmp"

    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(str(test_file), flags, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write("probe_ok\n")

        content = test_file.read_text(encoding='utf-8').strip()
        if content != "probe_ok":
            raise StorageError("Probe read-back content mismatch")
    finally:
        if test_file.exists():
            try:
                test_file.unlink()
            except Exception:
                pass
