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


# SHA-256 of the published phase1c2-claude-0.2.0 run_manifest.json, as recorded in PR #7 and in
# reports/phase1c2_results.json. The manifest lists every output/input hash, so pinning its own hash
# makes the whole published set tamper-evident. A new analysis version must get its own pin.
PINNED_MANIFEST_SHA256 = {"phase1c2-claude-0.2.0": "e578f2331f7bacf93383dd213fc66d72b4ae35d49508e8cc663bd9f2a02d6a8e"}


def test_published_manifest_hash_is_pinned(run_dir):
    assert sha256(run_dir / "run_manifest.json") == PINNED_MANIFEST_SHA256[ANALYSIS_VERSION]
    results = json.loads((Path(__file__).resolve().parents[1] / "reports" / "phase1c2_results.json").read_text(encoding="utf-8"))
    assert results["published"]["manifest"]["sha256"] == PINNED_MANIFEST_SHA256[ANALYSIS_VERSION]


def test_published_outputs_hashes_and_inputs_unchanged(root, run_dir):
    m = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert m["phase"] == "phase1c2" and m["analysis_version"] == ANALYSIS_VERSION
    for o in m["outputs"]:
        p = root / o["path"]
        assert p.resolve().is_relative_to(root / "processed" / "phase1c" / "claude")
        assert sha256(p) == o["sha256"]
    for i in m["inputs"]:
        assert sha256(root / i["path"]) == i["manifest_sha256"]
        assert i["verified_sha256"] == i["manifest_sha256"]
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
    # Coverage scope: never extrapolated beyond the L03-b meshes.
    cov = pd.read_csv(run_dir / "csv" / "municipality_coverage.csv", dtype={"muni_code": str})
    assert land <= cov.covered_km2.sum() + 1e-6
    assert 0.75 < cov.covered_km2.sum() / cov.area_km2.sum() < 0.76
    assert reg.loc["R2_miura", "scope"] == "excluded"
    assert reg.loc["R7_kensei", "scope"] == "reference_partial"
    assert set(cov.loc[cov.coverage < 0.01, "muni_code"]) >= {"14201", "14206", "14208", "14210", "14301", "14382", "14383", "14384"}
    sizes = pd.read_csv(run_dir / "csv" / "change_component_size_overall.csv", index_col=0)
    assert np.isclose(sizes[["share_1", "share_2", "share_3-4", "share_>=5"]].sum(axis=1).iloc[0], 1.0)


def test_codh_fujino_sagamiko_file_names_and_contents_are_swapped(root):
    """Reproducible evidence for the Phase 0 naming error (originals are not modified).

    The acquisition URLs point to 14423 (相模湖町) for 'fujino' and 14424 (藤野町) for
    'sagamiko'; the downloaded contents match their URLs, so the error is the name<->code
    mapping at acquisition time. Areas confirm the identity (藤野町 is about twice 相模湖町)."""
    from kanagawa_ruins.landuse_change.data import codh_identity_records

    recs = {r["name_token"]: r for r in codh_identity_records(root)}
    assert set(recs) == {"fujino", "sagamiko", "shiroyama", "tsukui"}
    for r in recs.values():
        assert r["raw_sha256"] == r["ledger_sha256"]
        assert r["url_matches_content"]
        assert (r["layer_attr_name"], r["layer_attr_code"]) == (r["attr_name"], r["attr_code"])
    assert not recs["fujino"]["name_matches_content"]
    assert not recs["sagamiko"]["name_matches_content"]
    assert (recs["fujino"]["attr_name"], recs["fujino"]["attr_code"]) == ("相模湖町", "14423")
    assert (recs["sagamiko"]["attr_name"], recs["sagamiko"]["attr_code"]) == ("藤野町", "14424")
    assert recs["shiroyama"]["name_matches_content"] and recs["tsukui"]["name_matches_content"]
    assert 60 < recs["sagamiko"]["layer_area_km2"] < 70 and 28 < recs["fujino"]["layer_area_km2"] < 35
