#!/usr/bin/env python3
"""Phase 0 compatibility entry point for the shared storage implementation."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kanagawa_ruins.storage.drive import (
    StorageError,
    get_mount_entries,
    is_rclone_mounted,
    safe_probe_write,
)
from kanagawa_ruins.storage import drive


def load_env_var(name, root=None):
    return drive.load_env_var(name, root=root or ROOT)


def get_verified_data_root(root=None, mounts_path=None):
    return drive.get_verified_data_root(root=root or ROOT, mounts_path=mounts_path)
