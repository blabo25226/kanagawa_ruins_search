"""Synthetic regression tests for Phase 1-C2 land-use change analysis (no Drive access)."""

from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd
import shapely
import shapely.affinity

from kanagawa_ruins.landuse_change import mesh, transition, stats, aggregate, codes, proximity, publish
from kanagawa_ruins.landuse_change.analysis import focus_summary, landscape_type, building_loss_clusters, buffer_composition


def grid_frame(g14, g21, area=10_000.0, y0=42400, x0=31200):
    """Cells on a rectangular mesh grid with group labels for 2014/2021."""
    g14 = np.asarray(g14)
    g21 = np.asarray(g21)
    rows, cols = np.indices(g14.shape)
    iy = (y0 + rows).ravel()
    ix = (x0 + cols).ravel()
    code = mesh.encode_100m(iy, ix)
    _, third, half = mesh.parent_codes(code)
    return pd.DataFrame(
        dict(code=code, iy=iy, ix=ix, mesh1km=third, mesh500m=half, grp2014=g14.ravel(), grp2021=g21.ravel(), area_m2=area,
             cen_x=ix * 100.0, cen_y=iy * 100.0)
    )


class MeshCodeTests(unittest.TestCase):
    def test_known_code_decodes_to_sw_corner(self):
        iy, ix = mesh.decode_100m(["5339000000"])
        s, w, n, e = mesh.cell_bounds_deg(iy, ix)
        self.assertAlmostEqual(s[0], 53 / 1.5)
        self.assertAlmostEqual(w[0], 139.0)
        self.assertAlmostEqual(n[0] - s[0], 3 / 3600)
        self.assertAlmostEqual(e[0] - w[0], 4.5 / 3600)

    def test_row_digit_is_latitude(self):
        a = mesh.decode_100m(["5339000010"])
        b = mesh.decode_100m(["5339000001"])
        self.assertEqual((a[0][0], a[1][0]), (42400 + 1, 31200))
        self.assertEqual((b[0][0], b[1][0]), (42400, 31200 + 1))

    def test_roundtrip_and_parents(self):
        rng = np.random.default_rng(0)
        iy = rng.integers(42400, 43200, 500)
        ix = rng.integers(30400, 32000, 500)
        code = mesh.encode_100m(iy, ix)
        y2, x2 = mesh.decode_100m(code)
        np.testing.assert_array_equal(iy, y2)
        np.testing.assert_array_equal(ix, x2)
        second, third, half = mesh.parent_codes(["5339451299", "5339451200", "5339451250", "5339451205"])
        self.assertEqual(list(second), ["533945"] * 4)
        self.assertEqual(list(third), ["53394512"] * 4)
        self.assertEqual(list(half), ["533945124", "533945121", "533945123", "533945122"])

    def test_invalid_codes_rejected(self):
        with self.assertRaises(ValueError):
            mesh.decode_100m(["5339800000"])  # 2nd mesh row 8 does not exist
        with self.assertRaises(ValueError):
            mesh.decode_100m(["533900000"])
        with self.assertRaises(ValueError):
            mesh.decode_100m(["53390000AB"])


class CodeTableTests(unittest.TestCase):
    def test_2014_2021_tables_identical_and_1976_differs(self):
        self.assertTrue(codes.tables_identical(2014, 2021))
        self.assertFalse(codes.tables_identical(1976, 2014))

    def test_groups_cover_official_tables(self):
        t = codes.official_tables()
        self.assertEqual(set(t["2014"]), set(codes.GROUPS_09))
        self.assertEqual(set(t["1976"]), set(codes.GROUPS_1976))

    def test_unknown_code_reported(self):
        r = codes.validate_codes("2021", {"0100": 5, "9999": 1})
        self.assertFalse(r["consistent"])
        self.assertEqual(r["unknown_codes"], {"9999": 1})
        self.assertIn("0500", r["official_codes_not_observed"])


class TransitionTests(unittest.TestCase):
    def test_matrix_is_area_weighted_not_count(self):
        f = pd.DataFrame(dict(a=["agri", "agri", "forest"], b=["forest", "agri", "forest"], w=[1.0, 3.0, 10.0]))
        m = transition.transition_matrix(f, "a", "b", "w", ["agri", "forest"])
        self.assertEqual(m.loc["agri", "forest"], 1.0)
        self.assertEqual(m.loc["agri", "agri"], 3.0)
        self.assertEqual(m.to_numpy().sum(), 14.0)

    def test_gain_loss_swap(self):
        m = pd.DataFrame([[8.0, 2.0], [1.0, 9.0]], index=["agri", "forest"], columns=["agri", "forest"])
        g = transition.gain_loss_swap(m, unit="m2")
        self.assertEqual(g.loc["agri", "gross_loss_m2"], 2.0)
        self.assertEqual(g.loc["agri", "gross_gain_m2"], 1.0)
        self.assertEqual(g.loc["agri", "net_change_m2"], -1.0)
        self.assertEqual(g.loc["agri", "swap_m2"], 2.0)
        self.assertAlmostEqual(g.loc["agri", "net_change_rate"], -0.1)

    def test_context_patch_isolated_boundary_interior(self):
        g14 = np.full((7, 7), "forest", dtype=object)
        g14[:, 0] = "building"
        g21 = g14.copy()
        g21[2:5, 2:5] = "agri"  # 3x3 patch of forest->agri
        g21[0, 1] = "building"  # forest cell next to existing building -> boundary
        g21[6, 6] = "wasteland"  # lone interior change
        f = grid_frame(g14, g21)
        ctx = transition.change_context(f.iy, f.ix, f.grp2014, f.grp2021)
        c = ctx.context.to_numpy().reshape(7, 7)
        self.assertTrue((c[2:5, 2:5] == "patch").all())
        self.assertEqual(c[0, 1], "isolated_boundary")
        self.assertEqual(c[6, 6], "isolated_interior")
        self.assertEqual((c == "no_change").sum(), 49 - 11)
        self.assertEqual(ctx.same_transition_neighbours.to_numpy().reshape(7, 7)[3, 3], 8)

    def test_cell_edge_lengths_ignore_rotation(self):
        from kanagawa_ruins.landuse_change.analysis import cell_edge_lengths

        sq = shapely.Polygon([(0, 0), (113, 0), (113, 92), (0, 92)])
        rot = shapely.affinity.rotate(sq, 0.5, origin=(0, 0))
        ns, ew = cell_edge_lengths([rot, rot])
        self.assertAlmostEqual(ns, 92.0, places=6)
        self.assertAlmostEqual(ew, 113.0, places=6)

    def test_duplicate_positions_rejected(self):
        with self.assertRaises(ValueError):
            transition.rasterize([1, 1], [2, 2], [1, 2], 0)


class AggregateTests(unittest.TestCase):
    def setUp(self):
        g14 = np.array([["agri", "agri", "building", "sea"], ["forest", "forest", "building", "sea"]], dtype=object)
        g21 = np.array([["forest", "agri", "wasteland", "sea"], ["forest", "building", "building", "agri"]], dtype=object)
        f = grid_frame(g14, g21, area=1e6)
        f["context"] = "patch"
        self.f = aggregate.add_indicators(f)

    def test_rates(self):
        r = aggregate.aggregate(self.f.assign(u="x"), "u").iloc[0]
        self.assertEqual(r.n_cells, 8)
        self.assertAlmostEqual(r.land_km2, 7.0)  # sea->sea excluded, sea->agri kept
        self.assertAlmostEqual(r.agri_gross_loss_rate, 0.5)
        self.assertAlmostEqual(r.agri_to_forest_rate, 0.5)
        self.assertAlmostEqual(r.building_gross_loss_rate, 0.5)
        self.assertAlmostEqual(r.building_to_forest_or_wasteland_rate, 0.5)
        self.assertAlmostEqual(r.building_net_change_rate, 0.0)
        # non-forest land 2014: agri x2, building x2, sea(->agri) x1 = 5; to forest: 1
        self.assertAlmostEqual(r.forestation_rate, 1 / 5)
        self.assertAlmostEqual(r.changed_share, 4 / 7)
        self.assertAlmostEqual(r.agri_net_change_rate, 0.0)

    def test_zero_denominator_gives_nan(self):
        r = aggregate.aggregate(self.f[self.f.grp2014 == "forest"].assign(u="x"), "u").iloc[0]
        self.assertTrue(np.isnan(r.agri_gross_loss_rate))
        self.assertTrue(np.isnan(r.building_gross_loss_rate))

    def test_focus_summary_reverse(self):
        fs = focus_summary(self.f).set_index("transition")
        self.assertAlmostEqual(fs.loc["agri->forest", "area_km2"], 1.0)
        self.assertAlmostEqual(fs.loc["building->wasteland", "rate_of_2014_class"], 0.5)
        self.assertAlmostEqual(fs.loc["agri->forest", "reverse_area_km2"], 0.0)

    def test_region_config_partitions_kanagawa_codes(self):
        regs = aggregate.load_regions()
        codes_ = [c for s in regs.values() for c in s.get("muni_codes", [])]
        self.assertEqual(len(codes_), len(set(codes_)))
        self.assertEqual(len(codes_), 58)
        r = aggregate.assign_regions(pd.Series(["14151", "14151", "14101", "99999"]), [True, False, False, False], regs)
        self.assertEqual(list(r.fillna("NA")), ["R6_tsukui", "R5_sagamihara", "R1_yokohama_kawasaki", "NA"])

    def test_landscape_type_and_clusters(self):
        g14 = np.full((10, 10), "forest", dtype=object)
        f = grid_frame(g14, g14.copy())
        f["context"] = "no_change"
        f = aggregate.add_indicators(f)
        t = landscape_type(f)
        self.assertEqual(set(t), {"forest_dominant"})
        g14b = np.full((5, 5), "building", dtype=object)
        g21b = g14b.copy()
        g21b[0, 0:2] = "forest"
        g21b[4, 4] = "wasteland"
        fb = grid_frame(g14b, g21b)
        cl = building_loss_clusters(fb)
        self.assertEqual(cl["n_clusters"], 2)
        self.assertEqual(sorted(cl["size_hist"].index), [1, 2])


class StatsTests(unittest.TestCase):
    def test_moran_matches_bruteforce(self):
        rng = np.random.default_rng(1)
        r, c = np.indices((6, 7))
        r, c = r.ravel(), c.ravel()
        v = rng.normal(size=len(r))
        w, _ = stats.queen_weights(r, c)
        n = len(v)
        W = np.zeros((n, n))
        for i in range(n):
            nb = [j for j in range(n) if max(abs(r[i] - r[j]), abs(c[i] - c[j])) == 1]
            W[i, nb] = 1 / len(nb)
        z = v - v.mean()
        expected = n / W.sum() * (z @ W @ z) / (z @ z)
        self.assertAlmostEqual(stats.morans_i(v, w), expected)

    def test_gradient_positive_random_near_expectation(self):
        r, c = np.indices((15, 15))
        res = stats.morans_i_test((r + c).ravel().astype(float), r.ravel(), c.ravel(), permutations=199)
        self.assertGreater(res["I"], 0.8)
        self.assertLess(res["p_one_sided"], 0.01)
        rng = np.random.default_rng(3)
        res2 = stats.morans_i_test(rng.normal(size=225), r.ravel(), c.ravel(), permutations=199)
        self.assertLess(abs(res2["I"]), 0.15)

    def test_nan_values_dropped(self):
        r, c = np.indices((5, 5))
        v = (r + c).ravel().astype(float)
        v[3] = np.nan
        res = stats.morans_i_test(v, r.ravel(), c.ravel(), permutations=19)
        self.assertEqual(res["n"], 24)

    def test_block_bootstrap(self):
        num = np.array([1.0, 1.0, 0.0, 0.0])
        den = np.ones(4)
        res = stats.block_bootstrap_ratio(num, den, ["a", "a", "b", "b"], n_boot=500)
        self.assertAlmostEqual(res["estimate"], 0.5)
        self.assertEqual(res["blocks"], 2)
        self.assertLessEqual(res["ci_low"], 0.5)
        self.assertGreaterEqual(res["ci_high"], 0.5)


class ProximityTests(unittest.TestCase):
    def test_nearest_distance_matches_bruteforce(self):
        lines = [shapely.LineString([(0, 0), (100, 0)]), shapely.LineString([(500, 500), (500, 900)])]
        x = np.array([50.0, 520.0, 300.0])
        y = np.array([30.0, 700.0, 0.0])
        d = proximity.nearest_distance(x, y, lines)
        brute = [min(l.distance(shapely.Point(a, b)) for l in lines) for a, b in zip(x, y)]
        np.testing.assert_allclose(d, brute)

    def test_grid_distance_and_censoring(self):
        r, c = np.indices((1, 10))
        target = np.zeros(10, bool)
        target[0] = True
        d, edge = proximity.grid_distance(r.ravel(), c.ravel(), target, np.ones(10, bool), 90.0, 110.0)
        np.testing.assert_allclose(d, np.arange(10) * 110.0)
        self.assertTrue((d > edge)[5])  # far cells may have a nearer road outside the data

    def test_osm_union_dedup(self):
        a = pd.DataFrame(dict(osm_type=["way", "node"], osm_id=[1, 2], v=[1, 2]))
        b = pd.DataFrame(dict(osm_type=["way", "way"], osm_id=[1, 3], v=[9, 3]))
        u, n = proximity.osm_union([a, b])
        self.assertEqual(n, 1)
        self.assertEqual(sorted(u.v), [1, 2, 3])  # first source wins for way/1

    def test_buffer_composition_counts_centroids_within_radius(self):
        g = np.full((5, 5), "forest", dtype=object)
        f = grid_frame(g, g.copy(), area=1.0)
        f["context"] = "no_change"
        f = aggregate.add_indicators(f)
        x0, y0 = f.cen_x.iloc[12], f.cen_y.iloc[12]
        out = buffer_composition(np.array([[x0, y0]]), f, radii=(100, 150))
        self.assertEqual(out[100].land_m2.iloc[0], 5.0)
        self.assertEqual(out[150].land_m2.iloc[0], 9.0)


class PublishTests(unittest.TestCase):
    def test_publish_contained_reproducible_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "data"
            (root / "processed" / "phase1a").mkdir(parents=True)
            src = Path(td) / "x.csv"
            src.write_text("a\n1\n")
            rec = publish.publish_file(root, src, "csv/x.csv", version="t1", require_mount=False)
            self.assertEqual(rec["status"], "created")
            self.assertTrue(rec["path"].startswith("processed/phase1c/claude/t1/"))
            again = publish.publish_file(root, src, "csv/x.csv", version="t1", require_mount=False)
            self.assertEqual(again["status"], "already_present_reproduced")
            src.write_text("a\n2\n")
            with self.assertRaises(FileExistsError):
                publish.publish_file(root, src, "csv/x.csv", version="t1", require_mount=False)
            with self.assertRaises(ValueError):
                publish.publish_file(root, src, "../../phase1a/x.csv", version="t1", require_mount=False)
            self.assertFalse(list((root / "processed" / "phase1c").rglob("*.partial")))

    def test_unmounted_target_refused(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "x.csv"
            src.write_text("a\n")
            with self.assertRaises(Exception):
                publish.publish_file(Path(td), src, "x.csv", version="t1", require_mount=True)


if __name__ == "__main__":
    unittest.main()
