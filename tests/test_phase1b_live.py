"""Read-only opt-in real JPEG/catalog verification; no real map/DEM dependency."""

import os
import json
import pytest
from kanagawa_ruins.raster.config import RasterSettings
from kanagawa_ruins.raster.storage import list_artifacts
from kanagawa_ruins.qa.raster_verify import verify_all
from kanagawa_ruins.imaging.catalog import search_catalog

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("RUINS_RUN_LIVE") != "1",
        reason="set RUINS_RUN_LIVE=1 for Drive integration",
    ),
]


def test_four_real_jpegs_and_catalog_sources_hashes_pixels_cog():
    result = verify_all(RasterSettings.from_env())
    assert result["status"] == "PASS", result
    assert len([r for r in result["results"] if r["checks"].get("xyz_bbox")]) == 4
    assert not result["unregistered_files"]


def test_catalog_native_search_preserves_uncertainty_and_missing_dates():
    settings = RasterSettings.from_env()
    manifest = next(m for m in list_artifacts(settings) if m["kind"] == "photo_catalog")
    rows = json.loads((settings.data_root / manifest["processed_path"]).read_text())
    assert len(rows) == 42
    assert sum(r["capture_date"] is None for r in rows) == 6
    assert sum(r["footprint_state"] == "center_only" for r in rows) == 8
    assert all(r["coordinate_crs"] is None for r in rows)
    selected = search_catalog(
        rows, bbox_native=[139.0, 35.4, 139.4, 35.8], footprints_only=True
    )
    assert selected
    assert all(r["footprint_state"] == "footprint_approximate" for r in selected)
    assert len(search_catalog(rows, unacquired_only=True)) == 42
