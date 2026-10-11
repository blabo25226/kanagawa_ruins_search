"""Correspondence and parser failure modes, not synthetic accuracy claims."""
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import geopandas as gpd
from shapely.geometry import box, LineString
from shapely.affinity import translate
from kanagawa_ruins.ingest.fgd import records, inner_archive, FGD, GML
from kanagawa_ruins.geo.temporal import building_matches, road_agreement
from kanagawa_ruins.storage.scratch import Scratch


def frame(geoms):
    return gpd.GeoDataFrame({"orgGILvl": ["2500"] * len(geoms)}, geometry=geoms, crs=6677)


class TemporalTests(unittest.TestCase):
    def test_shift_sensitivity(self):
        a = frame([box(0, 0, 2, 2)])
        b = frame([box(5, 0, 7, 2)])
        small, _, _ = building_matches(a, b, 1, coverage_confirmed=True)
        large, _, _ = building_matches(a, b, 5, coverage_confirmed=True)
        self.assertEqual(small.status[0], "missing_in_newer_dataset")
        self.assertEqual(large.status[0], "large_shape_or_position_change")

    def test_split_merge(self):
        a, b = frame([box(0, 0, 10, 10)]), frame([box(0, 0, 5, 10), box(5, 0, 10, 10)])
        self.assertEqual(building_matches(a, b, 1)[0].status[0], "possible_split")
        self.assertTrue((building_matches(b, a, 1)[0].status == "possible_merge").all())

    def test_missing_coverage_scale_and_crs(self):
        a, b = frame([box(0, 0, 3, 3)]), frame([box(50, 0, 53, 3)])
        self.assertEqual(building_matches(a, b, 1)[0].status[0], "indeterminate_coverage")
        b = a.copy(); b["orgGILvl"] = "25000"
        self.assertEqual(building_matches(a, b, 1)[0].status[0], "ambiguous_survey_scale")
        with self.assertRaises(ValueError): building_matches(a.to_crs(4326), b, 1)

    def test_road_segmentation_and_empty_target(self):
        a = frame([LineString([(0, 0), (10, 0)])])
        b = frame([LineString([(0, 0), (5, 0)]), LineString([(5, 0), (10, 0)])])
        self.assertAlmostEqual(road_agreement(a, b, 1)[0], 1.)
        self.assertEqual(road_agreement(a, frame([]), 1)[0], 0.)


class ParserTests(unittest.TestCase):
    def xml(self, kind="BldL", crs="fguuid:jgd2011.bl", encoding="utf-8"):
        s = f'''<?xml version="1.0" encoding="{encoding}"?><Dataset xmlns="{FGD}" xmlns:gml="{GML}">
        <{kind}><fid>1</fid><type>普通建物</type><devDate><gml:timePosition>2014-01-01</gml:timePosition></devDate>
        <loc><gml:Curve srsName="{crs}"><gml:segments><gml:LineStringSegment>
        <gml:posList>35 139 35.001 139.001</gml:posList></gml:LineStringSegment></gml:segments></gml:Curve></loc></{kind}></Dataset>'''
        return s.encode(encoding)

    def test_encoding_axes_and_dates(self):
        for encoding in ["utf-8", "Shift_JIS"]:
            audit = {}
            row = list(records(io.BufferedReader(io.BytesIO(self.xml(encoding=encoding))), audit=audit))[0]
            self.assertEqual(row["geometry"].coords[0], (139, 35))
            self.assertEqual(row["devDate"], "2014-01-01")
            self.assertEqual(row["feature_type"], "普通建物")
            self.assertIsNone(row["orgMDId"])

    def test_unknown_crs_stops(self):
        with self.assertRaises(ValueError):
            list(records(io.BufferedReader(io.BytesIO(self.xml(crs="unknown")))))

    def test_disconnected_curve_preserved(self):
        data=self.xml().decode().replace("</gml:segments>","<gml:LineStringSegment><gml:posList>35.002 139.002 35.003 139.003</gml:posList></gml:LineStringSegment></gml:segments>")
        row=list(records(io.BufferedReader(io.BytesIO(data.encode()))))[0]
        self.assertEqual(row["geometry"].geom_type,"MultiLineString")
        self.assertEqual(len(row["geometry"].geoms),2)

    def test_polygon_hole_and_open_ring(self):
        def xml(shell):
            return f'''<Dataset xmlns="{FGD}" xmlns:gml="{GML}"><BldA><fid>1</fid><area><gml:Surface srsName="fguuid:jgd2024.bl"><gml:patches><gml:PolygonPatch><gml:exterior><gml:Ring><gml:curveMember><gml:Curve><gml:segments><gml:LineStringSegment><gml:posList>{shell}</gml:posList></gml:LineStringSegment></gml:segments></gml:Curve></gml:curveMember></gml:Ring></gml:exterior><gml:interior><gml:Ring><gml:curveMember><gml:Curve><gml:segments><gml:LineStringSegment><gml:posList>35.2 139.2 35.2 139.4 35.4 139.4 35.4 139.2 35.2 139.2</gml:posList></gml:LineStringSegment></gml:segments></gml:Curve></gml:curveMember></gml:Ring></gml:interior></gml:PolygonPatch></gml:patches></gml:Surface></area></BldA></Dataset>'''.encode()
        shell="35 139 35 140 36 140 36 139 35 139"
        row=list(records(io.BufferedReader(io.BytesIO(xml(shell)))))[0]
        self.assertAlmostEqual(row["geometry"].area,.96)
        self.assertEqual(row["source_epsg"],"EPSG:6668")
        with self.assertRaises(ValueError):
            list(records(io.BufferedReader(io.BytesIO(xml("35 139 35 140 36 140 36 139")))))

    def test_inner_zip_budget_and_cleanup(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            outer = root / "outer.zip"
            with zipfile.ZipFile(outer, "w") as z: z.writestr("inner.zip", b"a" * 100)
            with zipfile.ZipFile(outer) as z:
                with self.assertRaises(OSError):
                    with inner_archive(z, "inner.zip", Scratch(root / "scratch", 10)): pass
                self.assertFalse((root / "scratch/inner.zip").exists())

    def test_2008_keeps_source_crs_and_disables_comparison(self):
        from kanagawa_ruins.temporal_pipeline import TemporalSettings,ingest_item
        from kanagawa_ruins.catalog.sources import Source
        from kanagawa_ruins.qa.hashing import sha256
        xml=f'''<Dataset xmlns="{FGD}" xmlns:gml="{GML}"><BldA><fid>1</fid><orgGILvl>2500</orgGILvl><area><gml:Surface srsName="fguuid:jgd2000.bl"><gml:patches><gml:PolygonPatch><gml:exterior><gml:Ring><gml:curveMember><gml:Curve><gml:segments><gml:LineStringSegment><gml:posList>35 139 35 139.001 35.001 139.001 35.001 139 35 139</gml:posList></gml:LineStringSegment></gml:segments></gml:Curve></gml:curveMember></gml:Ring></gml:exterior></gml:PolygonPatch></gml:patches></gml:Surface></area></BldA></Dataset>'''.encode()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/"raw/fgd").mkdir(parents=True)
            buf=io.BytesIO()
            with zipfile.ZipFile(buf,"w") as z:z.writestr("FG-GML-14101-BldA-20080331-0001.xml",xml)
            path=root/"raw/fgd/source.zip"
            with zipfile.ZipFile(path,"w") as z:z.writestr("FG-GML-14101-ALL-20080331.zip",buf.getvalue())
            source=Source("fixture","raw/fgd/source.zip",sha256(path),"2008",None,None,None,None)
            item=dict(era="2008",code="14101",member="FG-GML-14101-ALL-20080331.zip",file_date="20080331",acquisition_registered=False)
            captured=[]
            def inspect(path,lid,metadata,job):
                captured.append((gpd.read_parquet(path).crs.to_epsg(),metadata["analysis_ready"]))
            with patch("kanagawa_ruins.temporal_pipeline.to_analysis_crs",side_effect=AssertionError("Unsafe projection attempted")):
                result=ingest_item(TemporalSettings(root),item,source,publish_output=False,kinds={"BldA"},spatial_mask=box(0,0,1,1),on_layer=inspect)
            self.assertEqual(captured,[(4612,False)])
            self.assertFalse(result["temporal_comparison_ready"])


if __name__ == "__main__": unittest.main()
