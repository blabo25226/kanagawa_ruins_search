"""Distances from cell centroids to transport features (EPSG:6677 metres).

Vintages differ and are recorded by the caller: N02 railways 2023, OSM 2026-10,
L03-b 道路 cells 2014. OSM roads are never treated as the 2014 road network.
"""

import json

import numpy as np
import pandas as pd
import shapely
from scipy import ndimage

from .transition import rasterize

MOTOR_HIGHWAYS = {
    "motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential",
    "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link",
    "living_street", "service", "road",
}


def nearest_distance(x, y, geoms):
    """Exact Euclidean distance from points to the nearest geometry (STRtree)."""
    geoms = np.asarray([g for g in geoms if g is not None and not g.is_empty])
    if len(geoms) == 0:
        return np.full(len(x), np.nan)
    tree = shapely.STRtree(geoms)
    pts = shapely.points(np.asarray(x), np.asarray(y))
    idx, dist = tree.query_nearest(pts, return_distance=True, all_matches=False)
    out = np.full(len(pts), np.nan)
    out[idx[0]] = dist
    return out


def grid_distance(iy, ix, target, valid, dy_m, dx_m):
    """Centre-to-centre distance to the nearest target cell on the mesh grid.

    Also returns the distance to the nearest missing (outside-data) cell. Where the
    target distance exceeds the edge distance, a nearer target may exist outside the
    data, so the value is only an upper bound; callers flag such cells as censored.
    """
    tgt, r, c = rasterize(iy, ix, np.asarray(target, dtype=bool), False)
    have, _, _ = rasterize(iy, ix, np.asarray(valid, dtype=bool), False)
    d_target = ndimage.distance_transform_edt(~tgt, sampling=(dy_m, dx_m))
    padded = np.pad(have, 1, constant_values=False)
    d_edge = ndimage.distance_transform_edt(padded, sampling=(dy_m, dx_m))[1:-1, 1:-1]
    if not tgt.any():
        d_target[:] = np.inf
    return d_target[r, c], d_edge[r, c]


def osm_union(frames):
    """Deduplicate OSM features across extracts by (osm_type, osm_id); first source wins."""
    df = pd.concat(frames, ignore_index=True)
    n = len(df)
    df = df.drop_duplicates(["osm_type", "osm_id"], keep="first").reset_index(drop=True)
    return df, n - len(df)


def osm_highway_lines(df, motor_only=False):
    lines = df[df.geometry.geom_type.isin(["LineString", "MultiLineString"])]
    if motor_only:
        lines = lines[lines.highway.isin(MOTOR_HIGHWAYS)]
    return lines


def bin_distance(d, edges):
    labels = [f"{int(edges[i])}-{int(edges[i + 1])}" if np.isfinite(edges[i + 1]) else f">={int(edges[i])}" for i in range(len(edges) - 1)]
    return pd.cut(d, bins=edges, labels=labels, right=False, include_lowest=True)


def tags(df):
    return df.tags_json.map(json.loads)
