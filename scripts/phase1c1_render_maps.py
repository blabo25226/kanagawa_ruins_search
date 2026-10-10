#!/usr/bin/env python3
"""Render reviewed maps from actual aggregates; shade only analyzed support."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import geopandas as gpd
import pandas as pd
import shapely
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from matplotlib.patches import Patch
from kanagawa_ruins.catalog import load_layer
from kanagawa_ruins.qa.hashing import sha256
from phase1c1_analyze import mesh_bounds


def main():
    root=Path(__file__).resolve().parents[1]
    result=json.loads((root/"reports/phase1c1_analysis.json").read_text())
    directory=root/"reports/phase1c1_figures_r3"
    stats=pd.read_csv(directory/"municipality_statistics.csv",dtype={"era":str,"muni_code":str})
    admin=load_layer("admin__n03__2026_kanagawa").dissolve(by="muni_code",as_index=False)
    support=shapely.union_all([mesh_bounds(c) for c in result["meshes"]])
    artifacts=[]
    for domain,measure,label in [("building","record_count","Building polygon records"),("road_edge","edge_length_m","Road-edge length (m)")]:
        table=stats[(stats.domain==domain)&(stats.tolerance_m==5)].groupby(["muni_code","era"])[measure].sum().unstack()
        table["change"]=table["2025"]-table["2014"]
        layer=admin.merge(table[["change"]],left_on="muni_code",right_index=True,how="left")
        layer["geometry"]=layer.geometry.intersection(support)
        layer=layer.loc[~layer.geometry.is_empty & layer.change.notna()]
        maximum=max(1.,float(table.change.abs().max()))
        fig,ax=plt.subplots(figsize=(8,7))
        admin.plot(ax=ax,color="#dedede",edgecolor="white",linewidth=.25)
        layer.plot(ax=ax,column="change",cmap="RdBu",norm=Normalize(-maximum,maximum),legend=True,
                   legend_kwds={"label":label+" change"})
        ax.set_axis_off()
        ax.set_title("PARTIAL real-data comparison: 2 of 45 archive meshes\n"+label+": 2025 minus 2014",fontsize=12)
        ax.legend(handles=[Patch(facecolor="#dedede",label="Outside analyzed mesh support")],loc="lower left",fontsize=8)
        fig.text(.5,.025,"Municipal aggregates cover the selected mesh intersections only.",ha="center",fontsize=9)
        fig.tight_layout(rect=(0,.04,1,1))
        destination=directory/f"{domain}_regional_map_reviewed.png"
        if destination.exists():raise FileExistsError(destination)
        fig.savefig(destination,dpi=150);plt.close(fig)
        artifacts.append(dict(path=str(destination.relative_to(root)),sha256=sha256(destination),bytes=destination.stat().st_size))
    audit=dict(status="VISUAL_REVIEW_REQUIRED",input_summary_sha256=sha256(directory/"municipality_statistics.csv"),
               support_meshes=result["meshes"],color_scale="symmetric about zero",artifacts=artifacts,
               prefecture_area_m2=float(admin.geometry.union_all().area),
               selected_prefecture_land_area_m2=float(admin.geometry.union_all().intersection(support).area))
    with (root/"reports/phase1c1_plot_review.json").open("x") as f:json.dump(audit,f,indent=2)


if __name__=="__main__":main()
