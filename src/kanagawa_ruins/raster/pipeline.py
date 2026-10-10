"""Existing-source jobs: stage locally, validate, publish immutable derivatives."""

import json
from pathlib import Path
import re
from ..catalog.sources import read_sources
from ..storage.scratch import scratch_job
from ..imaging.tiles import XYZ, tile_to_cog, EXPECTED_TSUKUI_REGION
from ..imaging.catalog import normalize_catalog, write_catalog
from .storage import publish_artifact


def imagery_sources(settings, mode="tiles"):
    sources = read_sources(settings.data_root)
    if mode == "catalog":
        return [
            s
            for s in sources
            if Path(s.relative_path).name == "tsukui_aerial_photos_catalog.json"
        ]
    return [
        s
        for s in sources
        if s.relative_path.startswith("raw/aerial_photos/")
        and Path(s.relative_path).suffix.lower() in {".jpg", ".jpeg"}
        and re.search(r"_z\d+_\d+_\d+$", Path(s.relative_path).stem)
    ]


def ingest_tile(source, settings, *, expected_bbox=EXPECTED_TSUKUI_REGION):
    settings.check_mount()
    path = source.verify(settings.data_root)
    tile = XYZ.from_filename(path)
    url_match = re.search(
        r"/xyz/gazo1/(\d+)/(\d+)/(\d+)\.jpg$", source.source_url or ""
    )
    if not url_match or XYZ(*map(int, url_match.groups())) != tile:
        raise ValueError("Filename XYZ does not match the registered gazo1 source URL")
    aid = f"aerial__gazo1__z{tile.z}_x{tile.x}_y{tile.y}_v1"
    with scratch_job(settings.scratch_limit) as job:
        output = job.path / (aid + ".tif")
        info = tile_to_cog(path, output, job=job, expected_bbox=expected_bbox)
        return publish_artifact(
            settings,
            output,
            asset_id=aid,
            relative_output=f"aerial/georeferenced/{aid}.tif",
            source=source,
            parameters=dict(
                method="xyz_affine",
                compression="DEFLATE",
                overview_resampling="NEAREST",
                expected_bbox_wgs84=list(expected_bbox),
            ),
            metadata=dict(
                kind="xyz_tile",
                original_crs=None,
                processed_crs="EPSG:3857",
                capture_date=None,
                geometric_accuracy="unverified",
                source_period_evidence="registered gazo1 source; 1974-1978 interval, not an exact capture date",
                **info,
            ),
        )


def catalog_records(source, settings):
    path = source.verify(settings.data_root)
    # Only the four XYZ samples exist now. Future unidentified single photos keep unknown status.
    images = [
        p
        for p in (settings.data_root / "raw/aerial_photos").rglob("*")
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
    ]
    only_tiles = all(re.search(r"_z\d+_\d+_\d+$", p.stem) for p in images)
    return normalize_catalog(
        json.loads(path.read_text(encoding="utf-8")),
        acquisition_inventory_complete=only_tiles,
    )


def ingest_catalog(source, settings):
    settings.check_mount()
    records = catalog_records(source, settings)
    aid = "aerial__photo_catalog__tsukui_v1"
    with scratch_job(settings.scratch_limit) as job:
        output = write_catalog(records, job.path / (aid + ".json"))
        job.check()
        return publish_artifact(
            settings,
            output,
            asset_id=aid,
            relative_output=f"aerial/catalog/{aid}.json",
            source=source,
            parameters=dict(
                method="preserve_actual_keys_normalize_dates_and_geometry_status",
                schema_version=1,
            ),
            metadata=dict(
                kind="photo_catalog",
                original_crs=None,
                processed_crs=None,
                feature_count=len(records),
                coordinate_accuracy="unverified",
                spatial_search_mode="native_coordinate_bbox_only_until_crs_verified",
            ),
        )
