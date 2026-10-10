"""Read-only verification of registered Phase1b output, source identity and raster quality."""

import json
import numpy as np
from ..config import contained_path
from ..catalog.sources import read_sources
from ..imaging.tiles import XYZ, check_tile_location
from ..raster.cog import validate_cog, pixels_equal
from ..raster.pipeline import catalog_records
from ..raster.storage import list_artifacts
from .hashing import sha256
from .derived import registered_derived_files


def verify_artifact(manifest, settings, sources=None):
    sources = sources or {s.source_id: s for s in read_sources(settings.data_root)}
    m = manifest
    source = sources[m["source_id"]]
    if (
        source.relative_path != m["original_path"]
        or source.sha256 != m["source_sha256"]
    ):
        raise ValueError("Manifest source differs from acquisition ledger")
    original = source.verify(settings.data_root)
    output = contained_path(settings.data_root, m["processed_path"])
    if sha256(output) != m["output_sha256"] or output.stat().st_size != m["bytes"]:
        raise ValueError("Artifact SHA-256/size mismatch")
    if (
        not m["processing_version"]
        or len(m["implementation_sha256"]) != 64
        or not m["versions"]
    ):
        raise ValueError("Missing reproducibility metadata")
    checks = dict(source_hash=True, output_hash=True, source_ledger_match=True)
    info = {}
    if m["kind"] == "photo_catalog":
        rows = json.loads(output.read_text(encoding="utf-8"))
        expected = catalog_records(source, settings)
        if rows != expected or len(rows) != m["feature_count"]:
            raise ValueError("Normalized photo catalog differs from source")
        info = dict(
            feature_count=len(rows),
            date_unknown=sum(r["capture_date"] is None for r in rows),
            coordinate_crs=m["processed_crs"],
        )
        checks.update(original_attributes_retained=True, catalog_reproduced=True)
    else:
        info = validate_cog(output)
        for key in [
            "crs",
            "width",
            "height",
            "bands",
            "dtypes",
            "bbox",
            "transform",
            "nodata",
            "overviews",
        ]:
            if info[key] != m[key]:
                raise ValueError(f"Raster metadata mismatch: {key}")
        checks["cog_full_check"] = True
        if m["kind"] == "xyz_tile":
            tile = XYZ.from_filename(original)
            if (
                tile.__dict__ != m["xyz"]
                or not np.allclose(info["bbox"], tile.bounds(), rtol=0, atol=1e-8)
                or info["crs"] != "EPSG:3857"
                or info["width"] != 256
                or info["height"] != 256
                or info["transform"][4] >= 0
            ):
                raise ValueError("XYZ raster position/direction mismatch")
            check_tile_location(tile, m["parameters"]["expected_bbox_wgs84"])
            if not pixels_equal(original, output):
                raise ValueError("XYZ source pixels changed")
            checks.update(xyz_bbox=True, north_up=True, source_pixels_identical=True)
        elif m["kind"] == "gcp_affine":
            from ..imaging.georef import GCP, fit_affine
            from ..imaging.georef.residuals import residuals

            training = [GCP(**p) for p in m["training"]]
            validation = [GCP(**p) for p in m["validation"]]
            transform = fit_affine(training)
            if (
                residuals(transform, validation) != m["validation_errors"]
                or residuals(transform, training) != m["training_errors"]
            ):
                raise ValueError("GCP residual metadata mismatch")
            checks["independent_errors_reproduced"] = True
        elif m["kind"] in {"dem", "slope", "hillshade"}:
            from ..terrain import DEMReference

            DEMReference(**m["reference"])
            checks["explicit_height_reference"] = True
        else:
            raise ValueError("Unrecognized artifact kind")
    return dict(
        asset_id=m["asset_id"],
        status="PASS",
        processed_path=m["processed_path"],
        bytes=m["bytes"],
        source_sha256=m["source_sha256"],
        output_sha256=m["output_sha256"],
        checks=checks,
        **info,
    )


def verify_all(settings):
    settings.check_mount()
    sources = {s.source_id: s for s in read_sources(settings.data_root)}
    results = []
    try:
        artifacts = list_artifacts(settings)
    except (ValueError, KeyError, OSError, TypeError) as e:
        return dict(status="FAIL", error=str(e))
    for m in artifacts:
        try:
            results.append(verify_artifact(m, settings, sources))
        except Exception as e:
            results.append(
                dict(
                    asset_id=m.get("asset_id"),
                    status="FAIL",
                    error=f"{type(e).__name__}: {e}",
                )
            )
    files = {
        str(p.relative_to(settings.data_root)): p
        for p in settings.output_root.rglob("*")
        if p.is_file()
    }
    registered = registered_derived_files(settings.data_root, files)
    unregistered = sorted(set(files) - registered)
    return dict(
        status="PASS"
        if results and all(r["status"] == "PASS" for r in results) and not unregistered
        else "FAIL",
        asset_count=len(results),
        results=results,
        unregistered_files=unregistered,
        source_and_phase1a_integrity="See separate baseline integrity comparison; verifier never writes source/Phase1A",
    )
