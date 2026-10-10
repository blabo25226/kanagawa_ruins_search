"""First-order GCP warp via GDAL, with explicit pixel convention and audit trail."""

from dataclasses import asdict
import os
from pathlib import Path
import subprocess
import numpy as np
from affine import Affine
from .gcp import validate_points
from .residuals import residuals
from ...raster.io import local_output, open_image
from ...raster.cog import to_cog, validate_cog


def fit_affine(points):
    validate_points(points, minimum=3)
    xy = np.array([(p.pixel_x, p.pixel_y) for p in points], dtype=float)
    origin = xy.mean(axis=0)
    scale = xy.std(axis=0)
    if np.any(scale == 0):
        raise ValueError("Degenerate GCP arrangement")
    design = np.column_stack(((xy - origin) / scale, np.ones(len(points))))
    if np.linalg.matrix_rank(design) != 3 or np.linalg.cond(design) > 1e8:
        raise ValueError("Degenerate/ill-conditioned GCP arrangement")
    ground = np.array([(p.ground_x, p.ground_y) for p in points])
    coefficients = np.linalg.lstsq(design, ground, rcond=None)[0]
    linear = coefficients[:2] / scale[:, None]
    translation = coefficients[2] - origin @ linear
    transform = Affine(
        linear[0, 0],
        linear[1, 0],
        translation[0],
        linear[0, 1],
        linear[1, 1],
        translation[1],
    )
    if abs(transform.determinant) < 1e-12:
        raise ValueError("Degenerate ground-coordinate transform")
    return transform


def run_gdal(command):
    env = dict(os.environ, GDAL_PAM_ENABLED="NO", PROJ_NETWORK="OFF")
    subprocess.run(command, check=True, capture_output=True, text=True, env=env)


def check_warp_budget(source, job, options):
    """Ask GDAL for virtual output dimensions before allocating a warped raster."""
    from osgeo import gdal

    with gdal.ExceptionMgr():
        vrt = gdal.Warp(
            "", str(source), options=gdal.WarpOptions(options=["-of", "VRT", *options])
        )
        if vrt is None:
            raise ValueError("GDAL cannot determine warp dimensions")
        size = (
            vrt.RasterXSize
            * vrt.RasterYSize
            * sum(
                gdal.GetDataTypeSize(vrt.GetRasterBand(i).DataType) // 8
                for i in range(1, vrt.RasterCount + 1)
            )
        )
        job.check(size * 4)
        vrt = None


def georeference(source, output, *, training, validation, job):
    crs = validate_points(training, minimum=3)
    if validate_points(validation) != crs:
        raise ValueError("Validation CRS differs from training CRS")
    if ({p.point_id for p in training} & {p.point_id for p in validation}) or (
        {(p.pixel_x, p.pixel_y) for p in training}
        & {(p.pixel_x, p.pixel_y) for p in validation}
    ):
        raise ValueError("Validation points must be independent of training points")
    transform = fit_affine(training)
    with open_image(source) as ds:
        original_crs = ds.crs.to_string() if ds.crs else None
        for p in training + validation:
            if not (0 <= p.pixel_x <= ds.width and 0 <= p.pixel_y <= ds.height):
                raise ValueError("GCP lies outside image")
        job.check(ds.width * ds.height * ds.count * np.dtype(ds.dtypes[0]).itemsize * 5)
    output = local_output(output)
    control = local_output(job.path / "gcp_control.tif")
    warped = local_output(job.path / "gcp_warped.tif")
    first = ["gdal_translate", "-of", "GTiff", "-a_srs", crs.to_string()]
    for p in training:
        first.extend(
            [
                "-gcp",
                *[
                    format(v, ".17g")
                    for v in [p.pixel_x, p.pixel_y, p.ground_x, p.ground_y]
                ],
            ]
        )
    first.extend([str(Path(source)), str(control)])
    second = [
        "gdalwarp",
        "-order",
        "1",
        "-r",
        "near",
        "-t_srs",
        crs.to_string(),
        "-wm",
        "64",
        "-of",
        "GTiff",
        str(control),
        str(warped),
    ]
    for command in [first, second]:
        if command is second:
            check_warp_budget(
                control,
                job,
                [
                    "-order",
                    "1",
                    "-t_srs",
                    crs.to_string(),
                ],
            )
        run_gdal(command)
        job.check()
    to_cog(warped, output, job=job)
    return dict(
        **validate_cog(output),
        kind="gcp_affine",
        original_crs=original_crs,
        processed_crs=crs.to_string(),
        method="affine_order_1",
        affine=list(transform)[:6],
        training=[asdict(p) for p in training],
        validation=[asdict(p) for p in validation],
        training_errors=residuals(transform, training),
        validation_errors=residuals(transform, validation),
        gdal_commands=[first, second],
        pixel_convention="continuous_upper_left_corner_origin",
        resampling="nearest",
        geometric_accuracy="synthetic_or_control_point_evaluation_only",
    )
