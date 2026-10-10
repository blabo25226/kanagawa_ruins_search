"""Lossless COG conversion and GDAL's structural/full tile validator."""

import numpy as np
import rasterio
from rasterio.shutil import copy as raster_copy
from .io import local_output, open_image, windows


def to_cog(source, destination, *, job=None):
    destination = local_output(destination)
    if job:
        with open_image(source) as src:
            job.check(
                src.width
                * src.height
                * src.count
                * np.dtype(src.dtypes[0]).itemsize
                * 3
            )
    with rasterio.Env(GDAL_PAM_ENABLED="NO", GDAL_NUM_THREADS="1"):
        raster_copy(
            source,
            destination,
            driver="COG",
            COMPRESS="DEFLATE",
            BLOCKSIZE=128,
            OVERVIEWS="AUTO",
            RESAMPLING="NEAREST",
            NUM_THREADS="1",
            BIGTIFF="IF_SAFER",
        )
    if job:
        job.check()
    validate_cog(destination)
    if not pixels_equal(source, destination):
        raise ValueError("COG conversion changed base pixels or validity masks")
    return destination


def validate_cog(path):
    from osgeo import gdal
    from osgeo_utils.samples.validate_cloud_optimized_geotiff import validate

    with gdal.ExceptionMgr(), rasterio.Env(GDAL_PAM_ENABLED="NO"):
        warnings, errors, details = validate(str(path), full_check=True)
    if errors:
        raise ValueError(f"Invalid COG: {errors}")
    with open_image(path) as ds:
        if ds.tags(ns="IMAGE_STRUCTURE").get("LAYOUT") != "COG":
            raise ValueError("Missing GDAL COG layout declaration")
        if not ds.crs or not all(np.isfinite(tuple(ds.transform))):
            raise ValueError("Undefined CRS or invalid transform")
        if ds.transform.determinant == 0 or not all(np.isfinite(ds.bounds)):
            raise ValueError("Degenerate raster georeference")
        return dict(
            crs=ds.crs.to_string(),
            width=ds.width,
            height=ds.height,
            bands=ds.count,
            dtypes=list(ds.dtypes),
            bbox=list(ds.bounds),
            transform=list(ds.transform)[:6],
            nodata=ds.nodata,
            compression=ds.compression.value,
            overviews=ds.overviews(1),
            cog_full_check=True,
            cog_warnings=warnings,
        )


def pixels_equal(first, second):
    with open_image(first) as a, open_image(second) as b:
        if (a.width, a.height, a.count, a.dtypes) != (
            b.width,
            b.height,
            b.count,
            b.dtypes,
        ):
            return False
        return all(
            np.array_equal(a.read(window=w), b.read(window=w), equal_nan=True)
            and np.array_equal(a.read_masks(window=w), b.read_masks(window=w))
            for w in windows(a.width, a.height)
        )
