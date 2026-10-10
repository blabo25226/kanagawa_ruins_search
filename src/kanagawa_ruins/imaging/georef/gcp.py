"""GDAL continuous pixel coordinates: upper-left corner (0,0), center (.5,.5)."""

from dataclasses import dataclass
import math
from pyproj import CRS


def metre_crs(value):
    if not value:
        raise ValueError("GCP/terrain CRS is undefined")
    crs = CRS.from_user_input(value)
    if (
        not crs.is_projected
        or len(crs.axis_info) != 2
        or any(
            a.unit_conversion_factor != 1
            or a.unit_name.lower() not in {"metre", "meter"}
            for a in crs.axis_info
        )
    ):
        raise ValueError("A two-dimensional projected metre CRS is required")
    return crs


@dataclass(frozen=True)
class GCP:
    point_id: str
    pixel_x: float
    pixel_y: float
    ground_x: float
    ground_y: float
    ground_crs: str
    source: str
    confidence: str
    selection_method: str | None = None

    def __post_init__(self):
        if not self.point_id or not self.source or not self.confidence:
            raise ValueError("GCP identity, source and confidence are required")
        if not all(
            math.isfinite(v)
            for v in [self.pixel_x, self.pixel_y, self.ground_x, self.ground_y]
        ):
            raise ValueError("GCP coordinates must be finite")
        metre_crs(self.ground_crs)


def validate_points(points, *, minimum=1):
    if len(points) < minimum:
        raise ValueError(f"At least {minimum} GCPs are required")
    crs = metre_crs(points[0].ground_crs)
    if any(metre_crs(p.ground_crs) != crs for p in points):
        raise ValueError("Mixed GCP coordinate systems")
    if len({p.point_id for p in points}) != len(points) or len(
        {(p.pixel_x, p.pixel_y) for p in points}
    ) != len(points):
        raise ValueError("Duplicate GCP IDs or pixel positions")
    return crs
