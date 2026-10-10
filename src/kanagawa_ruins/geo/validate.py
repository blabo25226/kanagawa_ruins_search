"""Fail closed on invalid geometry; repairs are never implicit."""

import numpy as np
from .crs import validate_crs


def validate_frame(gdf):
    validate_crs(gdf)
    if gdf.geometry.isna().any() or gdf.geometry.is_empty.any():
        raise ValueError("Null/empty geometry requires explicit review")
    invalid = int((~gdf.geometry.is_valid).sum())
    if invalid:
        raise ValueError(f"Invalid geometries: {invalid}; no automatic repair")
    for col in gdf.columns.drop(gdf.geometry.name):
        if gdf[col].dtype.kind in "OUS":
            strings = gdf[col].dropna().astype(str)
            for marker in ("\ufffd", "逾槫･亥ｷ晉恁", "譚ｱ莠ｬ"):
                if strings.str.contains(marker, regex=False).any():
                    raise ValueError(f"Encoding corruption marker in {col}")
    bbox = gdf.total_bounds.tolist() if len(gdf) else None
    if bbox is not None and not np.isfinite(bbox).all():
        raise ValueError("Invalid bbox")
    return dict(
        feature_count=len(gdf),
        bbox=bbox,
        geometry_type=sorted(gdf.geom_type.unique().tolist()),
        columns=gdf.columns.tolist(),
        invalid_geometry_count=invalid,
    )
