"""Independent DuckDB Spatial re-computation of key results.

DuckDB re-reads the Phase 1-A GeoParquet files, joins years on the mesh code, assigns
cells to N03 municipalities with its own point-in-polygon join and computes areas with
ST_Area. Results are compared with the GeoPandas/pandas pipeline.
"""

import numpy as np
import pandas as pd

from ..geo.spatial import spatial_connection
from .codes import GROUPS_09
from .data import LAYERS


def _q(path):
    return "'" + str(path).replace("'", "''") + "'"


def duckdb_crosscheck(reg, k, group_matrix, agg_muni, rail, tol_km2=1e-6, n_rail_sample=500, seed=7):
    out = {}
    with spatial_connection() as con:
        con.execute("SET threads=4")
        p14 = [_q(reg.path(l)) for l in LAYERS["lu2014"]]
        p21 = [_q(reg.path(l)) for l in LAYERS["lu2021"]]
        pad = _q(reg.path(LAYERS["admin"]))
        groups = ",".join(f"('{c}','{g}')" for c, g in GROUPS_09.items())
        con.execute(f"CREATE TEMP TABLE grp(code VARCHAR, grp VARCHAR); INSERT INTO grp VALUES {groups}")
        con.execute(f'CREATE TEMP TABLE a AS SELECT "メッシュ"::VARCHAR AS code, landuse_code AS lu, ST_Area(geometry) AS area, ST_Centroid(geometry) AS c FROM read_parquet([{",".join(p14)}])')
        con.execute(f"CREATE TEMP TABLE b AS SELECT L03b_001::VARCHAR AS code, landuse_code AS lu FROM read_parquet([{','.join(p21)}])")
        con.execute(f"CREATE TEMP TABLE adm AS SELECT muni_code, geometry FROM read_parquet({pad})")
        con.execute(
            """CREATE TEMP TABLE j AS
               SELECT a.code, g1.grp AS g14, g2.grp AS g21, a.area, adm.muni_code
               FROM a JOIN b USING (code)
               JOIN grp g1 ON g1.code = a.lu JOIN grp g2 ON g2.code = b.lu
               JOIN adm ON ST_Within(a.c, adm.geometry)"""
        )
        dup = con.sql("SELECT count(*) - count(DISTINCT code) FROM j").fetchone()[0]
        mat = con.sql(
            "SELECT g14, g21, sum(area)/1e6 AS km2 FROM j WHERE NOT (g14='sea' AND g21='sea') GROUP BY ALL"
        ).fetchdf()
        muni = con.sql(
            "SELECT muni_code, sum(area)/1e6 AS land_km2, count(*) AS n FROM j WHERE NOT (g14='sea' AND g21='sea') GROUP BY ALL"
        ).fetchdf()
        dm = mat.pivot_table(index="g14", columns="g21", values="km2", aggfunc="sum", fill_value=0.0)
        dm = dm.reindex(index=group_matrix.index, columns=group_matrix.columns, fill_value=0.0)
        diff = np.abs(dm.to_numpy() - group_matrix.to_numpy())
        out["transition_matrix_max_abs_diff_km2"] = float(diff.max())
        out["duplicate_cell_assignments"] = int(dup)
        pm = agg_muni.set_index("muni_code")
        mm = muni.set_index("muni_code").reindex(pm.index)
        out["municipality_land_km2_max_abs_diff"] = float(np.nanmax(np.abs(mm.land_km2.to_numpy() - pm.land_km2.to_numpy())))
        out["municipality_cell_count_max_abs_diff"] = int(np.nanmax(np.abs(mm.n.to_numpy() - pm.n_cells.to_numpy())))
        # Rail distance for a random sample of cells.
        rng = np.random.default_rng(seed)
        idx = rng.choice(len(k), size=min(n_rail_sample, len(k)), replace=False)
        pts = pd.DataFrame(dict(i=idx, x=k.cen_x.values[idx], y=k.cen_y.values[idx]))
        con.register("pts_df", pts)
        con.register("rail_df", pd.DataFrame(dict(wkb=[g.wkb for g in rail.geometry.values])))
        con.execute("CREATE TEMP TABLE rl AS SELECT ST_GeomFromWKB(wkb) AS g FROM rail_df")
        d = con.sql(
            "SELECT i, min(ST_Distance(ST_Point(x, y), g)) AS d FROM pts_df, rl GROUP BY i ORDER BY i"
        ).fetchdf()
        ref = pd.Series(k.dist_rail_m.values[idx] if "dist_rail_m" in k else np.full(len(idx), np.nan), index=idx)
        out["rail_distance_sample_n"] = int(len(d))
        out["rail_distance_max_abs_diff_m"] = float(np.nanmax(np.abs(d.set_index("i").d.reindex(idx).to_numpy() - ref.to_numpy())))
    out["passed"] = bool(
        out["transition_matrix_max_abs_diff_km2"] < tol_km2
        and out["duplicate_cell_assignments"] == 0
        and out["municipality_land_km2_max_abs_diff"] < tol_km2
        and out["municipality_cell_count_max_abs_diff"] == 0
        and out["rail_distance_max_abs_diff_m"] < 1e-6
    )
    return out
