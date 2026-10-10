"""CRS validation. GeoDataFrame geometry is always x/y, including latitude-first EPSG axes."""

import numpy as np
from pyproj import CRS, Transformer
from pyproj.transformer import TransformerGroup
import shapely
from ..config import ANALYSIS_CRS


def describe_crs(crs):
    c = CRS.from_user_input(crs)
    return dict(
        authority=c.to_string(),
        datum=c.datum.name,
        geographic=c.is_geographic,
        axes=[a.direction for a in c.axis_info],
        wkt=c.to_wkt(),
    )


def validate_crs(gdf):
    if gdf.crs is None:
        raise ValueError("Undefined CRS: source metadata is required")
    c = CRS.from_user_input(gdf.crs)
    if not (c.is_geographic or c.is_projected):
        raise ValueError("Only geographic/projected CRS supported")
    if len(c.axis_info) != 2 or shapely.has_z(gdf.geometry.array).any():
        raise ValueError(
            "Only 2D horizontal CRS/geometries are supported; vertical datum needs review"
        )
    coords = shapely.get_coordinates(gdf.geometry.array)
    if not np.isfinite(coords).all():
        raise ValueError("Nonfinite coordinates")
    if c.is_geographic and len(coords):
        if (np.abs(coords[:, 0]) > 180).any() or (np.abs(coords[:, 1]) > 90).any():
            raise ValueError(
                "Longitude/latitude out of range; possible swapped x/y axes"
            )
    # Validate projected coordinates by inverse projection without inferring a datum.
    if c.is_projected and len(coords):
        x, y = Transformer.from_crs(c, c.geodetic_crs, always_xy=True).transform(
            coords[:, 0], coords[:, 1], errcheck=True
        )
        if not np.isfinite([x, y]).all():
            raise ValueError("Invalid projected coordinates")
    return describe_crs(c)


def to_analysis_crs(gdf):
    validate_crs(gdf)
    c = CRS.from_user_input(gdf.crs)
    # EPSG renamed the unchanged JGD2011 horizontal datum to JGD2024.
    # GSI: https://www.gsi.go.jp/sokuchikijun/datum-main.html
    # Only the 2D horizontal definition is used; heights are explicitly rejected.
    group = TransformerGroup(c, ANALYSIS_CRS, always_xy=True, allow_ballpark=False)
    if not group.best_available or not group.transformers:
        raise ValueError("Required non-ballpark datum transformation is unavailable")
    out = gdf.copy()
    geom = shapely.transform(
        gdf.geometry.array, group.transformers[0].transform, interleaved=False
    )
    out = out.set_geometry(geom).set_crs(ANALYSIS_CRS, allow_override=True)
    validate_crs(out)
    return out
