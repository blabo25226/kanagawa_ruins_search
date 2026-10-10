"""Entirely synthetic registration and terrain evidence; no real DEM/map is claimed."""

from dataclasses import replace
import math
from pathlib import Path
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET

from affine import Affine
import numpy as np
import rasterio
from rasterio.transform import from_origin
from pyproj import Transformer

from kanagawa_ruins.imaging.georef import GCP, fit_affine, georeference
from kanagawa_ruins.imaging.georef.residuals import residuals
from kanagawa_ruins.terrain import DEMReference, dem_to_cog, terrain_products
from kanagawa_ruins.terrain.dem import parse_fgd_xml, NODATA
from kanagawa_ruins.storage.scratch import scratch_job
from kanagawa_ruins.qa.hashing import sha256


KNOWN = Affine(5, 0, -60000, 0, -5, -40000)


def points():
    def point(i, x, y):
        gx, gy = KNOWN @ (x, y)
        return GCP(
            str(i),
            x,
            y,
            gx,
            gy,
            "EPSG:6677",
            "synthetic analytical transform",
            "high",
            "fixed grid",
        )

    return [
        point(i, *xy) for i, xy in enumerate([(0, 0), (32, 0), (0, 32), (32, 32)])
    ], [point("validation", 16, 16)]


def raster(path, values, crs=6677, transform=None, nodata=NODATA):
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=values.shape[1],
        height=values.shape[0],
        count=1,
        dtype=values.dtype,
        crs=crs,
        transform=transform or from_origin(-60000, -40000, 5, 5),
        nodata=nodata,
    ) as ds:
        ds.write(values, 1)


def reference(crs="EPSG:6677", datum="synthetic"):
    return DEMReference(
        crs,
        datum,
        "synthetic metre heights",
        "metre",
        "analytic fixture; not a real DEM datum",
    )


def xml(*, start="0 0", tuples=None, srs="fguuid:jgd2011.bl", high="2 1", order="+x-y"):
    values = (
        tuples
        if tuples is not None
        else "地表面,1 地表面,-2 データなし,-9999. 地表面,4 地表面,5 地表面,6"
    )
    return f'''<Dataset xmlns="http://fgd.gsi.go.jp/spec/2008/FGD_GMLSchema" xmlns:gml="http://www.opengis.net/gml/3.2">
    <DEM><mesh>533921</mesh><coverage><gml:boundedBy><gml:Envelope srsName="{srs}"><gml:lowerCorner>35.5 139.125</gml:lowerCorner><gml:upperCorner>35.58333333333333 139.25</gml:upperCorner></gml:Envelope></gml:boundedBy>
    <gml:gridDomain><gml:Grid dimension="2"><gml:limits><gml:GridEnvelope><gml:low>0 0</gml:low><gml:high>{high}</gml:high></gml:GridEnvelope></gml:limits><gml:axisLabels>x y</gml:axisLabels></gml:Grid></gml:gridDomain>
    <gml:rangeSet><gml:DataBlock><gml:tupleList>{values}</gml:tupleList></gml:DataBlock></gml:rangeSet><gml:coverageFunction><gml:GridFunction><gml:sequenceRule order="{order}">Linear</gml:sequenceRule><gml:startPoint>{start}</gml:startPoint></gml:GridFunction></gml:coverageFunction></coverage></DEM></Dataset>'''.encode()


class GCPTests(unittest.TestCase):
    def test_affine_recovery_and_independent_error(self):
        train, valid = points()
        affine = fit_affine(train)
        np.testing.assert_allclose(list(affine), list(KNOWN), atol=1e-10)
        self.assertLess(residuals(affine, train)["rmse_m"], 1e-9)
        offset = [
            replace(
                valid[0], ground_x=valid[0].ground_x + 3, ground_y=valid[0].ground_y + 4
            )
        ]
        self.assertAlmostEqual(residuals(affine, offset)["rmse_m"], 5)
        self.assertLess(residuals(affine, train)["rmse_m"], 1e-9)

    def test_missing_degenerate_mixed_and_undefined_gcps_rejected(self):
        train, valid = points()
        with self.assertRaises(ValueError):
            fit_affine(train[:2])
        with self.assertRaises(ValueError):
            fit_affine([replace(p, pixel_y=p.pixel_x) for p in train[:3]])
        with self.assertRaises(ValueError):
            replace(train[0], ground_crs=None)
        with self.assertRaises(ValueError):
            replace(train[0], ground_crs="EPSG:4326")
        with self.assertRaises(ValueError):
            fit_affine(train[:2] + [replace(train[2], ground_crs="EPSG:3857")])

    def test_actual_gdal_warp_known_extent_pixels_and_reproducibility(self):
        train, valid = points()
        with scratch_job(1_000_000_000) as job:
            source = job.path / "synthetic.tif"
            data = np.arange(32 * 32, dtype="uint16").reshape(32, 32)
            # Deliberately wrong existing georeference must not supersede explicit GCPs.
            raster(source, data, nodata=None, transform=from_origin(0, 1000, 20, 20))
            output = job.path / "registered.tif"
            info = georeference(
                source, output, training=train, validation=valid, job=job
            )
            np.testing.assert_allclose(
                info["bbox"], [-60000, -40160, -59840, -40000], atol=1e-7
            )
            self.assertLess(info["validation_errors"]["rmse_m"], 1e-9)
            self.assertTrue(info["cog_full_check"])
            with rasterio.open(output) as ds:
                np.testing.assert_array_equal(ds.read(1), data)
            with self.assertRaisesRegex(ValueError, "independent"):
                georeference(
                    source,
                    job.path / "invalid.tif",
                    training=train,
                    validation=train[:1],
                    job=job,
                )
            with scratch_job(1_000_000_000) as second:
                out = second.path / "registered.tif"
                georeference(source, out, training=train, validation=valid, job=second)
                self.assertEqual(sha256(out), sha256(output))


class FGDTests(unittest.TestCase):
    def test_axis_order_elevations_nodata_and_northwest_start(self):
        values, affine, info = parse_fgd_xml(xml(), reference("EPSG:6668", "JGD2011"))
        np.testing.assert_array_equal(values, [[1, -2, NODATA], [4, 5, 6]])
        self.assertEqual(affine @ (0, 0), (139.125, 35.58333333333333))
        self.assertLess(affine.e, 0)
        self.assertEqual(info["mesh"], "533921")

    def test_omitted_head_and_tail_follow_fgd_cell_indices(self):
        values, _, info = parse_fgd_xml(
            xml(start="1 1", tuples="地表面,12"), reference("EPSG:6668", "JGD2011")
        )
        np.testing.assert_array_equal(
            values, [[NODATA, NODATA, NODATA], [NODATA, 12, NODATA]]
        )
        self.assertEqual(info["omitted_leading_cells"], 4)
        self.assertEqual(info["omitted_trailing_cells"], 1)

    def test_unknown_datum_malformed_missing_unsafe_and_excess_tuples_rejected(self):
        ref = reference("EPSG:6668", "JGD2011")
        for data in [
            b"broken",
            b"<!DOCTYPE x>" + xml(),
            xml(srs="unknown"),
            xml(order="-y+x"),
            xml(start="3 1"),
            xml(tuples="地表面,nan"),
            xml(tuples="データなし,0"),
            xml(tuples="地表面,1 " * 7),
            xml().replace(b"<gml:startPoint>0 0</gml:startPoint>", b""),
        ]:
            with self.subTest(data=data[:40]):
                with self.assertRaises((ValueError, ET.ParseError)):
                    parse_fgd_xml(data, ref)
        with self.assertRaises(ValueError):
            parse_fgd_xml(xml(srs="fguuid:jgd2024.bl"), ref)
        with self.assertRaises(ValueError):
            DEMReference("EPSG:6677", "JGD2011", "unknown", "metre", "test")

    def test_zip_to_cog_native_and_horizontal_projection(self):
        with scratch_job(1_000_000_000) as job:
            source = job.path / "fixture.zip"
            with zipfile.ZipFile(source, "w") as z:
                z.writestr("fixture.xml", xml())
            native = dem_to_cog(
                source,
                job.path / "native",
                reference=reference("EPSG:6668", "JGD2011"),
                job=job,
            )[0]
            with rasterio.open(native["path"]) as ds:
                np.testing.assert_array_equal(ds.read(1), [[1, -2, NODATA], [4, 5, 6]])
                self.assertEqual(ds.nodata, NODATA)
            projected = dem_to_cog(
                source,
                job.path / "projected",
                reference=reference("EPSG:6668", "JGD2011"),
                job=job,
                target_crs="EPSG:6677",
            )[0]
            self.assertEqual(projected["crs"], "EPSG:6677")
            self.assertEqual(projected["vertical_transformation"], "none")
            x, y = Transformer.from_crs(6668, 6677, always_xy=True).transform(
                139.125, 35.58333333333333
            )
            self.assertLess(abs(projected["bbox"][0] - x), 1000)
            self.assertLess(abs(projected["bbox"][3] - y), 1000)
            with zipfile.ZipFile(job.path / "bad.zip", "w") as z:
                z.writestr("../fixture.xml", xml())
            with self.assertRaises(ValueError):
                dem_to_cog(
                    job.path / "bad.zip",
                    job.path / "bad",
                    reference=reference("EPSG:6668", "JGD2011"),
                    job=job,
                )

    def test_jgd2024_preserved_without_unverified_projection(self):
        with scratch_job(1_000_000_000) as job:
            source = job.path / "jgd2024.xml"
            source.write_bytes(xml(srs="fguuid:jgd2024.bl"))
            native = dem_to_cog(
                source,
                job.path / "native",
                reference=reference("EPSG:6668", "JGD2024"),
                job=job,
            )[0]
            self.assertEqual(native["declared_horizontal_datum"], "JGD2024")
            with self.assertRaisesRegex(ValueError, "Unverified datum"):
                dem_to_cog(
                    source,
                    job.path / "projected",
                    reference=reference("EPSG:6668", "JGD2024"),
                    job=job,
                    target_crs="EPSG:6677",
                )


class TerrainTests(unittest.TestCase):
    def test_flat_slope_and_hillshade_with_nodata_border(self):
        with scratch_job(1_000_000_000) as job:
            source = job.path / "flat.tif"
            raster(source, np.full((8, 8), 100, dtype="float32"))
            items = terrain_products(
                source, job.path / "out", reference=reference(), job=job
            )
            with rasterio.open(items[0]["path"]) as ds:
                a = ds.read(1, masked=True)
                np.testing.assert_array_equal(a[1:-1, 1:-1], 0)
                self.assertTrue(a.mask[0, :].all())
            with rasterio.open(items[1]["path"]) as ds:
                np.testing.assert_allclose(
                    ds.read(1)[1:-1, 1:-1], 255 / math.sqrt(2), atol=1e-5
                )

    def test_plane_unequal_resolution_and_nodata_propagation(self):
        with scratch_job(1_000_000_000) as job:
            source = job.path / "plane.tif"
            rows, cols = np.indices((520, 520))
            # dz/dx=.2, dz/dy=.1; crosses 512px processing-window seam.
            values = (100 + cols * 2 - rows * 2).astype("float32")
            values[50, 50] = NODATA
            raster(source, values, transform=from_origin(-60000, -40000, 10, 20))
            items = terrain_products(
                source, job.path / "out", reference=reference(), job=job
            )
            with rasterio.open(items[0]["path"]) as ds:
                a = ds.read(1, masked=True)
                expected = np.degrees(np.arctan(np.hypot(0.2, 0.1)))
                self.assertAlmostEqual(float(a[512, 512]), expected, places=5)
                self.assertAlmostEqual(float(a[20, 20]), expected, places=5)
                for y, x in [(50, 50), (49, 50), (51, 50), (50, 49), (50, 51)]:
                    self.assertTrue(a.mask[y, x])
            with rasterio.open(items[1]["path"]) as ds:
                az, alt = np.radians([315, 45])
                expected = 255 * max(
                    0,
                    (
                        -0.2 * np.sin(az) * np.cos(alt)
                        - 0.1 * np.cos(az) * np.cos(alt)
                        + np.sin(alt)
                    )
                    / np.sqrt(1 + 0.2**2 + 0.1**2),
                )
                self.assertAlmostEqual(float(ds.read(1)[512, 512]), expected, places=4)

    def test_geographic_undefined_rotated_and_multiband_rejected(self):
        with scratch_job(1_000_000_000) as job:
            for i, (crs, affine) in enumerate(
                [
                    (4326, from_origin(139, 35, 0.01, 0.01)),
                    (None, KNOWN),
                    (6677, Affine(5, 1, -60000, 1, -5, -40000)),
                ]
            ):
                source = job.path / f"bad_{i}.tif"
                raster(
                    source, np.ones((8, 8), dtype="float32"), crs=crs, transform=affine
                )
                with self.assertRaises(ValueError):
                    terrain_products(
                        source, job.path / f"out_{i}", reference=reference(), job=job
                    )

    def test_dem_and_derivative_bytes_reproducible(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "plane.tif"
            raster(source, np.arange(64, dtype="float32").reshape(8, 8))
            hashes = []
            for _ in range(2):
                with scratch_job(1_000_000_000) as job:
                    dem = dem_to_cog(
                        source, job.path / "dem", reference=reference(), job=job
                    )[0]
                    products = terrain_products(
                        dem["path"],
                        job.path / "products",
                        reference=reference(),
                        job=job,
                    )
                    hashes.append(
                        [sha256(dem["path"]), *[sha256(p["path"]) for p in products]]
                    )
            self.assertEqual(hashes[0], hashes[1])
