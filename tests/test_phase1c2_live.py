"""Opt-in read-only Drive integration tests for Phase 1-C2 (they never write).

RUINS_RUN_LIVE=1 python -m pytest tests/test_phase1c2_live.py -v
"""

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from kanagawa_ruins.landuse_change import ANALYSIS_VERSION
from kanagawa_ruins.landuse_change.data import LAYERS, InputRegistry, build_cells
from kanagawa_ruins.landuse_change.publish import output_root
from kanagawa_ruins.qa.hashing import sha256
from kanagawa_ruins.storage.drive import get_verified_data_root

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.environ.get("RUINS_RUN_LIVE") != "1", reason="set RUINS_RUN_LIVE=1 for Drive integration"),
]


@pytest.fixture(scope="module")
def root():
    return get_verified_data_root()


@pytest.fixture(scope="module")
def run_dir(root):
    d = output_root(root, ANALYSIS_VERSION)
    if not (d / "run_manifest.json").is_file():
        pytest.skip("Phase 1-C2 outputs not published yet")
    return d


def test_landuse_inputs_match_phase1a_manifests_and_align(root):
    reg = InputRegistry(root, verify_sha=True)
    cells, qa = build_cells(reg)
    assert qa["same_code_set"] and qa["n2014"] == qa["n2021"] == 1_270_000
    assert qa["centroid_shift_max_m"] < 0.01
    assert qa["decoded_centre_vs_geometry_max_m"] < 0.5
    assert qa["area_relative_difference_max"] < 1e-3
    assert set(cells.lu2014) <= {"0100", "0200", "0500", "0600", "0700", "0901", "0902", "1000", "1100", "1400", "1500", "1600"}
    for lid in LAYERS["lu2014"] + LAYERS["lu2021"]:
        assert reg.records[lid]["verified_sha256"] == reg.records[lid]["manifest_sha256"]


def test_1976_remains_tokyo_datum_and_not_analysis_ready(root):
    for lid in LAYERS["lu1976"]:
        m = json.loads((root / "processed" / "phase1a" / "manifests" / f"{lid}.json").read_text())
        assert m["processed_crs"] == "EPSG:4301"
        assert m["analysis_ready"] is False


def test_published_outputs_hashes_and_inputs_unchanged(root, run_dir):
    m = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert m["phase"] == "phase1c2" and m["analysis_version"] == ANALYSIS_VERSION
    for o in m["outputs"]:
        p = root / o["path"]
        assert p.resolve().is_relative_to(root / "processed" / "phase1c" / "claude")
        assert sha256(p) == o["sha256"]
    for i in m["inputs"]:
        assert sha256(root / i["path"]) == i["manifest_sha256"]
    assert not list(run_dir.rglob("*.partial"))


def test_published_tables_are_internally_consistent(run_dir):
    mat = pd.read_csv(run_dir / "csv" / "transition_group_area_km2.csv", index_col=0)
    tot = pd.read_csv(run_dir / "csv" / "agg_kanagawa_covered.csv", index_col=0)
    reg = pd.read_csv(run_dir / "csv" / "agg_region.csv", index_col=0)
    muni = pd.read_csv(run_dir / "csv" / "agg_municipality.csv")
    land = tot.land_km2.iloc[0]
    assert np.isclose(mat.to_numpy().sum(), land)
    assert np.isclose(reg.land_km2.sum(), land)
    assert np.isclose(muni.land_km2.sum(), land)
    cc = json.loads((run_dir / "qa" / "crosscheck.json").read_text())
    assert cc["duckdb"]["passed"] is True
