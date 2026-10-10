"""XYZ (north-origin, never TMS) tile coordinates, with explicit pixel conventions."""

from dataclasses import dataclass
import math
from pathlib import Path
import re
import numpy as np
import rasterio
from rasterio.transform import Affine
from pyproj import Transformer
from ..raster.io import local_output, open_image, windows
from ..raster.cog import to_cog, pixels_equal, validate_cog

HALF_WORLD = math.pi * 6378137.0
EXPECTED_TSUKUI_REGION = (
    139.0,
    35.4,
    139.4,
    35.8,
)  # plausibility envelope, not an oaza boundary


@dataclass(frozen=True)
class XYZ:
    z: int
    x: int
    y: int

    def __post_init__(self):
        if (
            any(type(v) is not int for v in (self.z, self.x, self.y))
            or not 0 <= self.z <= 30
        ):
            raise ValueError("Invalid XYZ zoom/integer coordinates")
        if not (0 <= self.x < 2**self.z and 0 <= self.y < 2**self.z):
            raise ValueError("XYZ outside zoom range")

    @classmethod
    def from_filename(cls, path):
        m = re.search(r"(?:^|_)z(\d+)_(\d+)_(\d+)$", Path(path).stem)
        if not m:
            raise ValueError("Missing unambiguous z/x/y filename suffix")
        return cls(*map(int, m.groups()))

    def bounds(self):
        span = 2 * HALF_WORLD / 2**self.z
        west, north = -HALF_WORLD + self.x * span, HALF_WORLD - self.y * span
        return west, north - span, west + span, north

    def affine(self, size=256):
        if size != 256:
            raise ValueError("GSI XYZ tiles must be 256x256")
        west, south, east, north = self.bounds()
        return Affine((east - west) / size, 0, west, 0, -(north - south) / size, north)

    def lonlat_bounds(self):
        west, south, east, north = self.bounds()
        t = Transformer.from_crs(3857, 4326, always_xy=True, allow_ballpark=False)
        return (*t.transform(west, south), *t.transform(east, north))


def pixel_to_ground(tile, pixel_x, pixel_y, *, crs="EPSG:3857", center=True):
    offset = 0.5 if center else 0.0
    x, y = tile.affine() @ (pixel_x + offset, pixel_y + offset)
    return Transformer.from_crs(
        3857, crs, always_xy=True, allow_ballpark=False, only_best=True
    ).transform(x, y, errcheck=True)


def ground_to_pixel(tile, x, y, *, crs="EPSG:3857", center=True):
    mx, my = Transformer.from_crs(
        crs, 3857, always_xy=True, allow_ballpark=False, only_best=True
    ).transform(x, y, errcheck=True)
    col, row = (~tile.affine()) @ (mx, my)
    offset = 0.5 if center else 0.0
    return col - offset, row - offset


def check_tile_location(tile, expected_bbox=EXPECTED_TSUKUI_REGION):
    b = tile.lonlat_bounds()
    if len(expected_bbox) != 4 or not all(math.isfinite(v) for v in expected_bbox):
        raise ValueError("Invalid expected-region bbox")
    if not (
        expected_bbox[0] <= b[0] < b[2] <= expected_bbox[2]
        and expected_bbox[1] <= b[1] < b[3] <= expected_bbox[3]
    ):
        raise ValueError("XYZ tile is outside the expected region; stop for review")
    return b


def tile_to_cog(source, destination, *, job, expected_bbox=EXPECTED_TSUKUI_REGION):
    tile = XYZ.from_filename(source)
    geographic_bbox = check_tile_location(tile, expected_bbox)
    stage = local_output(job.path / "tile_georeferenced.tif")
    with open_image(source) as src:
        if (src.width, src.height, src.count) != (256, 256, 3) or set(src.dtypes) != {
            "uint8"
        }:
            raise ValueError("Expected a 256x256 RGB byte tile")
        job.check(256 * 256 * 3 * 4)
        with rasterio.open(
            stage,
            "w",
            driver="GTiff",
            width=256,
            height=256,
            count=3,
            dtype="uint8",
            crs="EPSG:3857",
            transform=tile.affine(),
            compress="deflate",
            tiled=True,
            blockxsize=128,
            blockysize=128,
        ) as dst:
            dst.colorinterp = src.colorinterp
            for w in windows(src.width, src.height):
                dst.write(src.read(window=w), window=w)
    to_cog(stage, destination, job=job)
    info = validate_cog(destination)
    if not np.allclose(
        info["bbox"], tile.bounds(), atol=1e-8, rtol=0
    ) or not pixels_equal(source, destination):
        raise ValueError("Tile bounds/pixels changed unexpectedly")
    return dict(
        info,
        xyz=dict(z=tile.z, x=tile.x, y=tile.y),
        geographic_bbox=list(geographic_bbox),
        pixels_preserved=True,
        resampling="none_base_nearest_overviews",
        tile_scheme="XYZ",
    )
