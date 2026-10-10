"""Job-local temporary space with admission checks and guaranteed cleanup."""

from contextlib import contextmanager
from pathlib import Path
import shutil
import os
import subprocess
import time
import tempfile


class Scratch:
    def __init__(self, path, limit):
        self.path, self.limit = Path(path), limit
        self.peak_bytes = 0
        self.vfs_bytes = None
        self._vfs_checked_at = 0.0

    def check(self, additional=0):
        size = sum(p.stat().st_size for p in self.path.rglob("*") if p.is_file())
        self.peak_bytes = max(self.peak_bytes, size)
        if time.monotonic() - self._vfs_checked_at > 30:
            self.vfs_bytes = rclone_cache_bytes()
            self._vfs_checked_at = time.monotonic()
        if (
            self.vfs_bytes is not None
            and size + additional + self.vfs_bytes > 25_000_000_000
        ):
            raise OSError("Combined job/VFS scratch ceiling exceeded")
        if size + additional > self.limit:
            raise OSError("Job scratch budget exceeded")
        if shutil.disk_usage(self.path).free < additional + 1_000_000_000:
            raise OSError("Insufficient scratch free space (1GB reserve required)")
        return size


@contextmanager
def scratch_job(limit=25_000_000_000):
    if not 0 < limit <= 25_000_000_000:
        raise ValueError("Scratch ceiling is 25GB")
    with tempfile.TemporaryDirectory(prefix="ruins-phase1a-") as d:
        job = Scratch(d, limit)
        job.check()
        yield job


def rclone_cache_bytes():
    """Best-effort monitoring of the standard cache directory; never changes mount settings."""
    base = (
        Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "rclone"
    )
    if not base.is_dir():
        return None
    try:
        result = subprocess.run(
            ["du", "-s", "-B1", str(base)],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        return int(result.stdout.split()[0])
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
