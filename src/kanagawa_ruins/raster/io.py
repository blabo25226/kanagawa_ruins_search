"""Windowed raster reads; low-level writers may only stage outside the data bank."""

from contextlib import contextmanager
from pathlib import Path
import rasterio
from rasterio.windows import Window
from ..storage.drive import is_rclone_mounted, load_env_var


def local_output(path):
    path = Path(path).resolve()
    configured = load_env_var("RUINS_DATA_ROOT")
    if configured and path.is_relative_to(Path(configured).expanduser().resolve()):
        raise ValueError("Data bank writes require the phase1b publisher")
    if is_rclone_mounted(path)[0]:
        raise ValueError("Raster writers require local staging")
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def open_image(path):
    if Path(path).suffix.lower() not in {".tif", ".tiff", ".jpg", ".jpeg", ".png"}:
        raise ValueError("Supported imagery: TIFF, GeoTIFF, JPEG, PNG")
    with rasterio.Env(GDAL_PAM_ENABLED="NO"):
        with rasterio.open(path, "r") as ds:
            yield ds


def windows(width, height, size=512):
    if not isinstance(size, int) or not 1 <= size <= 4096:
        raise ValueError("Window size must be 1..4096 pixels")
    for row in range(0, height, size):
        for col in range(0, width, size):
            yield Window(col, row, min(size, width - col), min(size, height - row))


def read_windows(path, size=512):
    with open_image(path) as ds:
        for window in windows(ds.width, ds.height, size):
            yield window, ds.read(window=window)
