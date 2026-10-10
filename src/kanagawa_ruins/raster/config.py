"""Phase 1-B authorization; Phase 1-A settings remain unchanged."""

from ..config import Settings
from ..storage.drive import is_rclone_mounted, StorageError

VERSION = "phase1b-0.1.0"


class RasterSettings(Settings):
    def __init__(self, data_root, scratch_limit=1_000_000_000):
        super().__init__(data_root, scratch_limit)

    @property
    def output_root(self):
        return self.data_root / "processed" / "phase1b"

    def check_mount(self):
        root = self.data_root.resolve()
        output = self.output_root.resolve()
        if output != root / "processed" / "phase1b":
            raise StorageError("Output escapes authorized phase1b subtree")
        for path in [root, output]:
            ok, info = is_rclone_mounted(path)
            if not ok:
                raise StorageError(info)
