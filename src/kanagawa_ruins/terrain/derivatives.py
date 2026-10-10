"""Windowed central differences and Lambertian hillshade, with NoData propagation."""

import math
from pathlib import Path
import numpy as np
import rasterio
from rasterio.windows import Window
from ..imaging.georef.gcp import metre_crs
from ..raster.io import local_output, open_image, windows
from ..raster.cog import to_cog, validate_cog
from .dem import NODATA


def terrain_products(
    source, output_dir, *, reference, job, azimuth=315.0, altitude=45.0
):
    output_dir = Path(output_dir)
    if not (
        math.isfinite(azimuth)
        and 0 <= azimuth < 360
        and math.isfinite(altitude)
        and 0 < altitude <= 90
    ):
        raise ValueError("Invalid hillshade illumination")
    with open_image(source) as ds:
        metre_crs(ds.crs)
        if ds.count != 1 or ds.width < 3 or ds.height < 3:
            raise ValueError("Terrain requires a single-band DEM of at least 3x3")
        a = ds.transform
        input_crs = ds.crs.to_string()
        if a.b != 0 or a.d != 0 or a.a <= 0 or a.e >= 0:
            raise ValueError(
                "Terrain requires a north-up, unrotated positive-resolution DEM"
            )
        # Reference is explicit and never supplies a vertical conversion.
        if (
            reference.unit != "metre"
            or not reference.vertical_datum
            or not reference.evidence
        ):
            raise ValueError("Reviewed metre heights are required")
        job.check(ds.width * ds.height * 4 * 5)
        slope = local_output(output_dir / "staging" / "terrain_slope_work.tif")
        shade = local_output(output_dir / "staging" / "terrain_hillshade_work.tif")
        profile = ds.profile.copy()
        profile.update(driver="GTiff", dtype="float32", count=1, nodata=NODATA)
        az, alt = np.radians([azimuth, altitude])
        sun = np.array(
            [np.sin(az) * np.cos(alt), np.cos(az) * np.cos(alt), np.sin(alt)]
        )
        with (
            rasterio.open(slope, "w", **profile) as slopes,
            rasterio.open(shade, "w", **profile) as shades,
        ):
            for win in windows(ds.width, ds.height):
                halo = Window(
                    win.col_off - 1, win.row_off - 1, win.width + 2, win.height + 2
                )
                z = ds.read(1, window=halo, boundless=True, masked=True)
                raw = (
                    z.filled(np.nan).astype("float64")
                    if np.issubdtype(z.dtype, np.floating)
                    else z.astype("float64").filled(np.nan)
                )
                center, east, west, north, south = (
                    raw[1:-1, 1:-1],
                    raw[1:-1, 2:],
                    raw[1:-1, :-2],
                    raw[:-2, 1:-1],
                    raw[2:, 1:-1],
                )
                valid = (
                    np.isfinite(center)
                    & np.isfinite(east)
                    & np.isfinite(west)
                    & np.isfinite(north)
                    & np.isfinite(south)
                )
                gx = (east - west) / (2 * a.a)
                gy = (north - south) / (2 * (-a.e))
                magnitude = np.sqrt(1 + gx * gx + gy * gy)
                sl = np.degrees(np.arctan(np.hypot(gx, gy)))
                hs = 255 * np.maximum(
                    0, (-gx * sun[0] - gy * sun[1] + sun[2]) / magnitude
                )
                slopes.write(
                    np.where(valid, sl, NODATA).astype("float32"), 1, window=win
                )
                shades.write(
                    np.where(valid, hs, NODATA).astype("float32"), 1, window=win
                )
        job.check()
    results = []
    for kind, work in [("slope", slope), ("hillshade", shade)]:
        out = output_dir / f"{kind}.tif"
        to_cog(work, out, job=job)
        results.append(
            dict(
                path=out,
                **validate_cog(out),
                kind=kind,
                original_crs=reference.crs,
                raster_input_crs=input_crs,
                processed_crs=input_crs,
                reference=reference.__dict__,
                method="central_difference_cross_5_cells",
                unit="degree" if kind == "slope" else "intensity_0_255",
                azimuth=azimuth if kind == "hillshade" else None,
                altitude=altitude if kind == "hillshade" else None,
                border_policy="one_pixel_nodata",
                nodata_policy="center_and_four_neighbors_required",
            )
        )
    return results
