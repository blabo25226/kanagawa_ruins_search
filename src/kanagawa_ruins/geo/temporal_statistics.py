"""Descriptive statistics with explicit land-area and land-use support."""
from collections import defaultdict
import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import shapely
from shapely.geometry import box
from ..catalog.layers import get_layer
from ..qa.hashing import sha256


def grid_support(admin, stats):
    """Projected 1km grid, including unoccupied prefectural land cells."""
    land=admin.geometry.union_all()
    xmin,ymin,xmax,ymax=land.bounds
    rows=[]
    for x in range(int(np.floor(xmin/1000)), int(np.floor(xmax/1000))+1):
        for y in range(int(np.floor(ymin/1000)),int(np.floor(ymax/1000))+1):
            cell=box(x*1000,y*1000,(x+1)*1000,(y+1)*1000)
            area=cell.intersection(land).area
            if area>0: rows.append(dict(grid_x=x,grid_y=y,land_area_m2=area,geometry=cell))
    grid=gpd.GeoDataFrame(rows,crs=6677)
    values=stats[(stats.domain=="building")&(stats.tolerance_m==5)].groupby(["grid_x","grid_y","era"]).record_count.sum().unstack(fill_value=0)
    for era in ["2014","2025"]:
        if era not in values:values[era]=0
    values=values.rename(columns={"2014":"count_2014","2025":"count_2025"})
    grid=grid.merge(values,left_on=["grid_x","grid_y"],right_index=True,how="left")
    for era in ["2014","2025"]:
        grid[f"count_{era}"]=grid[f"count_{era}"].fillna(0).astype(int)
        grid[f"density_{era}_per_km2"]=grid[f"count_{era}"]/grid.land_area_m2*1e6
    grid["record_count_change"]=grid.count_2025-grid.count_2014
    grid["change_rate"]=np.where(grid.count_2014>0,grid.record_count_change/grid.count_2014,np.nan)
    return grid


def landuse_proxy(grid):
    """2021 KSJ cells, centroid area allocation; no inferred elevation class.

    Existing Phase1A support covers 5338/5339 only. Southern uncovered cells
    remain unknown. This is a forest/built-land comparison, not DEM mountains.
    """
    sums=defaultdict(lambda: defaultdict(float)); inputs=[]
    for code in ["5338","5339"]:
        metadata,path=get_layer(f"landuse__l03b__2021_{code}")
        if sha256(path)!=metadata["output_sha256"]: raise ValueError("Land-use SHA mismatch")
        if metadata["processed_crs"]!="EPSG:6677":raise ValueError("Unexpected land-use CRS")
        inputs.append(dict(layer_id=metadata["layer_id"],sha256=metadata["output_sha256"]))
        for batch in pq.ParquetFile(path).iter_batches(batch_size=20000,columns=["landuse_code","geometry"]):
            geoms=shapely.from_wkb(batch.column("geometry").to_pylist())
            centroids=shapely.centroid(geoms)
            x=np.floor(shapely.get_x(centroids)/1000).astype(int)
            y=np.floor(shapely.get_y(centroids)/1000).astype(int)
            area=shapely.area(geoms)
            labels=batch.column("landuse_code").to_pylist()
            for xx,yy,a,label in zip(x,y,area,labels):
                key=(int(xx),int(yy));sums[key]["known_landuse_m2"]+=float(a)
                if str(label)=="0500":sums[key]["forest_m2"]+=float(a)
                if str(label)=="0700":sums[key]["built_land_m2"]+=float(a)
    result=grid.copy()
    for label in ["known_landuse_m2","forest_m2","built_land_m2"]:
        result[label]=[sums[(x,y)][label] for x,y in zip(result.grid_x,result.grid_y)]
    denominator=result.known_landuse_m2.replace(0,np.nan)
    result["forest_fraction"]=result.forest_m2/denominator
    result["built_land_fraction"]=result.built_land_m2/denominator
    result["stratum"]="other_landuse_proxy"
    result.loc[result.forest_fraction>=.5,"stratum"]="forest_dominant_proxy"
    result.loc[result.built_land_fraction>=.5,"stratum"]="built_land_dominant_proxy"
    result.loc[result.known_landuse_m2<500000,"stratum"]="insufficient_landuse_support"
    summary=[]
    for label,f in result.groupby("stratum"):
        old=int(f.count_2014.sum());new=int(f.count_2025.sum())
        summary.append(dict(stratum=label,cells=len(f),old_polygon_records=old,new_polygon_records=new,
                            change_rate=(new-old)/old if old else None,
                            median_occupied_baseline_change_rate=float(f.change_rate.median()) if f.change_rate.notna().any() else None,
                            baseline_zero_cells=int((f.count_2014==0).sum())))
    return result,summary,inputs
