"""Load Phase 1-A GeoParquet inputs (read-only) and build the 2014/2021 cell table."""

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyproj
import shapely

from ..qa.hashing import sha256
from .codes import GROUPS_09
from .mesh import cell_bounds_deg, decode_100m, parent_codes

ANALYSIS_CRS = "EPSG:6677"
LANDUSE_MESHES = ("5338", "5339")

LAYERS = dict(
    lu2014=[f"landuse__l03b__2014_{m}" for m in LANDUSE_MESHES],
    lu2021=[f"landuse__l03b__2021_{m}" for m in LANDUSE_MESHES],
    lu1976=[f"landuse__l03b__1976_{m}" for m in LANDUSE_MESHES],
    admin="admin__n03__2026_kanagawa",
    codh_2005=[
        "admin__codh_fujino_2005__2005_01_01",
        "admin__codh_sagamiko_2005__2005_01_01",
        "admin__codh_shiroyama_2005__2005_01_01",
        "admin__codh_tsukui_2005__2005_01_01",
    ],
    codh_1955="admin__codh_tsukui_1955__1955_10_01",
    rail="railways__mlit_railways_2023__2023_n02_23_railroadsection",
    station="railways__mlit_railways_2023__2023_n02_23_station",
    cultural="cultural__mlit_cultural_properties_kanagawa__2014",
    rivers="rivers__mlit_rivers_kanagawa__2008_w05_08_14_g_stream",
)
OSM_DOMAINS = ("roads", "worship", "historic", "waterways")


class InputRegistry:
    """Resolves Phase 1-A layers through their manifests and records verified SHA-256."""

    def __init__(self, data_root, verify_sha=True):
        self.data_root = Path(data_root).resolve()
        self.base = self.data_root / "processed" / "phase1a"
        self.verify_sha = verify_sha
        self.records = {}

    def path(self, layer_id):
        if layer_id in self.records:
            return self.data_root / self.records[layer_id]["path"]
        manifest = json.loads((self.base / "manifests" / f"{layer_id}.json").read_text(encoding="utf-8"))
        if manifest["layer_id"] != layer_id:
            raise ValueError("Manifest id mismatch")
        p = (self.data_root / manifest["processed_path"]).resolve()
        if not p.is_relative_to(self.base / "vectors"):
            raise ValueError("Input outside processed/phase1a/vectors")
        rec = dict(
            layer_id=layer_id,
            path=str(p.relative_to(self.data_root)),
            manifest_sha256=manifest["output_sha256"],
            original_path=manifest.get("original_path"),
            source_sha256=manifest.get("source_sha256"),
            source_id=manifest.get("source_id"),
            original_crs=manifest.get("original_crs"),
            processed_crs=manifest.get("processed_crs"),
            analysis_ready=manifest.get("analysis_ready"),
            license=manifest.get("license"),
            feature_count=manifest.get("feature_count"),
        )
        if self.verify_sha:
            got = sha256(p)
            rec["verified_sha256"] = got
            if got != manifest["output_sha256"]:
                raise ValueError(f"Input SHA-256 mismatch for {layer_id}")
        self.records[layer_id] = rec
        return p

    def read(self, layer_id, columns=None):
        return gpd.read_parquet(self.path(layer_id), columns=columns)

    def read_attributes(self, layer_id, columns):
        """Attribute-only read (no geometry), e.g. for the Tokyo Datum 1976 layers."""
        if "geometry" in columns:
            raise ValueError("Attribute-only read")
        return pd.read_parquet(self.path(layer_id), columns=columns)

    def osm_layers(self, domain):
        return sorted(p.stem for p in (self.base / "manifests").glob(f"osm__{domain}__*.json"))


def _landuse_year(reg, layer_ids, code_col):
    frames = []
    for lid in layer_ids:
        df = reg.read(lid)
        if str(df.crs.to_epsg()) != "6677":
            raise ValueError(f"{lid} is not EPSG:6677; refusing spatial use")
        frames.append(pd.DataFrame(dict(code=df[code_col].astype(str), landuse_code=df["landuse_code"].astype(str), geometry=df.geometry.values)))
    out = pd.concat(frames, ignore_index=True)
    if out.code.duplicated().any():
        raise ValueError("Duplicate mesh codes across landuse files")
    return out


def geodesic_cell_area(iy, ellps):
    """Ellipsoidal area (m2) of 3" x 4.5" cells; depends on the latitude row only."""
    iy = np.asarray(iy)
    rows, inv = np.unique(iy, return_inverse=True)
    s, w, n, e = cell_bounds_deg(rows, np.zeros_like(rows))
    geod = pyproj.Geod(ellps=ellps)
    per_row = np.abs([geod.polygon_area_perimeter([wi, ei, ei, wi], [si, si, ni, ni])[0] for si, wi, ni, ei in zip(s, w, n, e)])
    return per_row[inv]


def build_cells(reg):
    """Join 2014 and 2021 on the 10-digit mesh code and verify positional agreement."""
    a = _landuse_year(reg, LAYERS["lu2014"], "メッシュ")
    b = _landuse_year(reg, LAYERS["lu2021"], "L03b_001")
    qa = dict(n2014=len(a), n2021=len(b), same_code_set=set(a.code) == set(b.code))
    if not qa["same_code_set"]:
        raise ValueError("2014/2021 mesh code sets differ")
    m = a.merge(b, on="code", suffixes=("_2014", "_2021"), validate="one_to_one")
    g14 = gpd.GeoSeries(m.geometry_2014, crs=ANALYSIS_CRS)
    g21 = gpd.GeoSeries(m.geometry_2021, crs=ANALYSIS_CRS)
    c14 = g14.centroid
    shift = c14.distance(g21.centroid)
    qa["centroid_shift_max_m"] = float(shift.max())
    qa["symmetric_difference_area_max_m2"] = float(shapely.area(shapely.symmetric_difference(g14.values, g21.values)).max())
    iy, ix = decode_100m(m.code.values)
    s, w, n, e = cell_bounds_deg(iy, ix)
    # Code-geometry consistency: decoded cell centre (JGD2011 lat/lon) projected vs stored centroid.
    tr = pyproj.Transformer.from_crs("EPSG:6668", ANALYSIS_CRS, always_xy=True)
    px, py = tr.transform((w + e) / 2, (s + n) / 2)
    dec = np.hypot(px - c14.x.values, py - c14.y.values)
    qa["decoded_centre_vs_geometry_max_m"] = float(dec.max())
    if qa["centroid_shift_max_m"] > 0.01 or qa["decoded_centre_vs_geometry_max_m"] > 0.5:
        raise ValueError(f"Mesh alignment check failed: {qa}")
    area = g14.area.values
    geodesic = geodesic_cell_area(iy, ellps="GRS80")
    qa["area_projected_total_km2"] = float(area.sum() / 1e6)
    qa["area_geodesic_total_km2"] = float(geodesic.sum() / 1e6)
    qa["area_relative_difference_max"] = float(np.max(np.abs(area / geodesic - 1)))
    second, third, half = parent_codes(m.code.values)
    cells = gpd.GeoDataFrame(
        dict(
            code=m.code.values,
            mesh2=second,
            mesh1km=third,
            mesh500m=half,
            iy=iy,
            ix=ix,
            lu2014=m.landuse_code_2014.values,
            lu2021=m.landuse_code_2021.values,
            area_m2=area,
            area_geodesic_m2=geodesic,
        ),
        geometry=g14.values,
        crs=ANALYSIS_CRS,
    )
    for y in ("2014", "2021"):
        unknown = set(cells[f"lu{y}"]) - set(GROUPS_09)
        if unknown:
            raise ValueError(f"Unknown {y} codes: {unknown}")
        cells[f"grp{y}"] = cells[f"lu{y}"].map(GROUPS_09)
    cells["cen_x"] = c14.x.values
    cells["cen_y"] = c14.y.values
    return cells, qa


def assign_admin(cells, reg):
    """Assign cells to N03 2026 municipalities by centroid; flag the old Tsukui-gun towns."""
    adm = reg.read(LAYERS["admin"])
    muni = adm.dissolve("muni_code", aggfunc="first").reset_index()
    muni["muni_name"] = muni.N03_004.fillna("") + muni.N03_005.fillna("")
    pts = gpd.GeoDataFrame(dict(i=np.arange(len(cells))), geometry=gpd.points_from_xy(cells.cen_x, cells.cen_y), crs=ANALYSIS_CRS)
    j = gpd.sjoin(pts, muni[["muni_code", "muni_name", "geometry"]], predicate="within", how="left")
    if j.i.duplicated().any():
        raise ValueError("Cell centroid falls in multiple municipalities")
    j = j.sort_values("i")
    cells = cells.copy()
    cells["muni_code"] = j.muni_code.values
    cells["muni_name"] = j.muni_name.values
    codh = pd.concat([reg.read(l) for l in LAYERS["codh_2005"]], ignore_index=True)
    codh_union = codh.geometry.union_all()
    inside = shapely.contains_xy(codh_union, cells.cen_x.values, cells.cen_y.values)
    cells["old_tsukui_gun"] = inside & (cells.muni_code == "14151").values
    old = gpd.GeoDataFrame(dict(old_muni=codh.muni.values, old_code=codh.muni_code.values), geometry=codh.geometry.values, crs=ANALYSIS_CRS)
    jo = gpd.sjoin(pts, old, predicate="within", how="left").sort_values("i")
    if jo.i.duplicated().any():
        raise ValueError("Overlapping CODH polygons")
    cells["old_muni_2005"] = np.where(cells.old_tsukui_gun, jo.old_muni.values, None)
    return cells, muni, codh


def coverage_polygon(cells):
    """Union of the 2nd-mesh squares present in the landuse data (EPSG:6677)."""
    present = sorted(set(cells.mesh2))
    tr = pyproj.Transformer.from_crs("EPSG:6668", ANALYSIS_CRS, always_xy=True)
    polys = []
    for code in present:
        lat = int(code[:2]) / 1.5 + int(code[4]) / 12.0
        lon = 100 + int(code[2:4]) + int(code[5]) / 8.0
        ring = shapely.geometry.box(lon, lat, lon + 1 / 8.0, lat + 1 / 12.0)
        ring = shapely.segmentize(ring, 0.001)
        polys.append(shapely.ops.transform(tr.transform, ring))
    return shapely.union_all(polys), present
