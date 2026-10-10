"""Configuration resolved at call time; never assumes a local path is Drive."""

from dataclasses import dataclass
from pathlib import Path
from .storage.drive import get_verified_data_root, is_rclone_mounted, StorageError

ANALYSIS_CRS = "EPSG:6677"
PROCESSING_VERSION = "phase1a-0.1.0"


@dataclass(frozen=True)
class Settings:
    data_root: Path
    scratch_limit: int = 25_000_000_000

    @classmethod
    def from_env(cls):
        return cls(get_verified_data_root())

    @property
    def output_root(self):
        return self.data_root / "processed" / "phase1a"

    def check_mount(self):
        ok, info = is_rclone_mounted(self.data_root)
        if not ok:
            raise StorageError(info)
        output = self.output_root.resolve()
        if output != self.data_root.resolve() / "processed" / "phase1a":
            raise StorageError("Output path escapes authorized directory")
        ok, info = is_rclone_mounted(output)
        if not ok:
            raise StorageError(info)


def contained_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(root.resolve()):
        raise ValueError(f"Path escapes root: {relative}")
    return path
