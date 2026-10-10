"""Dataset correspondence hypotheses, not demolition/construction labels."""

import numpy as np
import pandas as pd
import shapely
from shapely import STRtree


def building_matches(old, new, tolerance, *, coverage_confirmed=False):
    """Spatial candidate graph with overlap or distance/area/buffer evidence.

    Inputs are valid, deduplicated EPSG:6677 area geometries. Split/merge labels
    refer to graph components, not counts of pairwise nearest neighbours.
    Missing counterparts require externally confirmed comparable coverage.
    """
    if tolerance <= 0:
        raise ValueError("Positive metre tolerance required")
    for f in [old, new]:
        if f.crs is None or f.crs.to_epsg() != 6677:
            raise ValueError("EPSG:6677 required")
        if not f.geometry.is_valid.all() or not f.geom_type.isin(["Polygon", "MultiPolygon"]).all():
            raise ValueError("Valid area geometries required")
    a, b = old.geometry.to_numpy(), new.geometry.to_numpy()
    tree = STRtree(b)
    parent = list(range(len(a) + len(b)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    edges = []
    best_a, best_b = np.zeros(len(a)), np.zeros(len(b))
    for start in range(0, len(a), 2000):
        i, j = tree.query(a[start:start + 2000], predicate="dwithin", distance=tolerance)
        i = i + start
        aa, bb = a[i], b[j]
        ia = shapely.area(shapely.intersection(aa, bb))
        ar, br = shapely.area(aa), shapely.area(bb)
        iou = ia / (ar + br - ia)
        ratio = np.minimum(ar, br) / np.maximum(ar, br)
        cd = shapely.distance(shapely.centroid(aa), shapely.centroid(bb))
        overlap = ia / np.minimum(ar, br)
        # Require shape evidence for nearby alternatives. Translation tolerance
        # alone would match neighbouring houses in dense urban blocks.
        near = (cd <= tolerance) & (ratio >= .5)
        buffered = np.zeros(len(i))
        if near.any():
            x = shapely.buffer(aa[near], tolerance)
            y = shapely.buffer(bb[near], tolerance)
            q = shapely.area(shapely.intersection(x, y))
            buffered[near] = q / (shapely.area(x) + shapely.area(y) - q)
        keep = (iou >= .2) | (overlap >= .5) | (near & (buffered >= .3))
        for u, v, score in zip(i[keep], j[keep], iou[keep]):
            u, v = int(u), int(v)
            edges.append((u, v, float(score)))
            best_a[u], best_b[v] = max(best_a[u], score), max(best_b[v], score)
            parent[find(u)] = find(len(a) + v)
    groups = {}
    for u, v, _ in edges:
        key = find(u)
        aa, bb = groups.setdefault(key, (set(), set()))
        aa.add(u); bb.add(v)
    labels_a = np.full(len(a), "missing_in_newer_dataset" if coverage_confirmed else "indeterminate_coverage", dtype=object)
    labels_b = np.full(len(b), "only_in_newer_dataset" if coverage_confirmed else "indeterminate_coverage", dtype=object)
    for aa, bb in groups.values():
        if len(aa) > 1 and len(bb) > 1:
            label = "ambiguous_many_to_many"
        elif len(aa) > 1:
            label = "possible_merge"
        elif len(bb) > 1:
            label = "possible_split"
        else:
            u, v = next(iter(aa)), next(iter(bb))
            if "orgGILvl" in old and "orgGILvl" in new and old.iloc[u].orgGILvl != new.iloc[v].orgGILvl:
                label = "ambiguous_survey_scale"
            else:
                label = "matched" if best_a[u] >= .5 else "large_shape_or_position_change"
        for u in aa: labels_a[u] = label
        for v in bb: labels_b[v] = label
    return (pd.DataFrame({"status": labels_a, "best_iou": best_a}),
            pd.DataFrame({"status": labels_b, "best_iou": best_b}), edges)


def road_agreement(source, target, tolerance):
    """Directional length fraction within target road-edge buffers.

    Works for segmented curves; segmentation changes do not inflate agreement.
    Does not turn edges into a navigable centreline network.
    """
    if tolerance <= 0:
        raise ValueError("Positive metre tolerance required")
    for f in [source, target]:
        if f.crs is None or f.crs.to_epsg() != 6677:
            raise ValueError("EPSG:6677 required")
        if not f.geometry.is_valid.all() or not f.geom_type.isin(["LineString", "MultiLineString"]).all():
            raise ValueError("Valid line geometries required")
    b = target.geometry.to_numpy()
    tree = STRtree(b)
    buffered = shapely.buffer(b, tolerance)
    ratios = []
    for line in source.geometry:
        idx = tree.query(line, predicate="dwithin", distance=tolerance)
        if line.length == 0:
            ratios.append(np.nan)
        elif len(idx):
            buffer = shapely.union_all(buffered[idx])
            ratios.append(min(1., line.intersection(buffer).length / line.length))
        else:
            ratios.append(0.)
    return np.array(ratios)
