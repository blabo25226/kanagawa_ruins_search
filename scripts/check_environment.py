#!/usr/bin/env python3
"""Phase 0: check GIS packages and CLI using synthetic test data only."""
import argparse
from datetime import datetime, timezone
import importlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

MODULES = {'numpy': True, 'pandas': True, 'geopandas': True, 'shapely': True,
           'pyproj': True, 'rasterio': True, 'osgeo.gdal': True, 'cv2': True,
           'folium': False, 'matplotlib': False}
CLI = {'gdalinfo': True, 'ogrinfo': True, 'gdalwarp': True, 'qgis_process': False}


def test_module(name, required):
    try:
        module = importlib.import_module(name)
        v = module.VersionInfo('RELEASE_NAME') if name == 'osgeo.gdal' else getattr(module, '__version__', 'unknown')
        return dict(name=name, required=required, status='PASS', version=str(v))
    except Exception as e:
        return dict(name=name, required=required, status='FAIL', detail=repr(e))


def test_cli(name, required):
    path = shutil.which(name)
    if not path:
        return dict(name=name, required=required, status='FAIL' if required else 'OPTIONAL_MISSING')
    try:
        env = dict(os.environ)
        if name == 'qgis_process':
            env.setdefault('QT_QPA_PLATFORM', 'offscreen')
        p = subprocess.run([path, '--version'], capture_output=True, text=True, timeout=12, env=env)
        output = (p.stdout or p.stderr).strip().splitlines()
        return dict(name=name, required=required, status='PASS' if p.returncode == 0 else 'FAIL',
                    path=path, exit_code=p.returncode, version=(output[0] if output else '')[:200])
    except Exception as e:
        return dict(name=name, required=required, status='FAIL', detail=repr(e))


def smoke():
    results = []
    try:
        import geopandas as gpd
        from shapely.geometry import Point
        from pyproj import Transformer
        d = gpd.GeoDataFrame({'synthetic': [1]}, geometry=[Point(0, 0)], crs='EPSG:4326')
        transformed = d.to_crs('EPSG:3857')
        x, y = transformed.geometry.iloc[0].coords[0]
        lon, lat = Transformer.from_crs('EPSG:3857', 'EPSG:4326', always_xy=True).transform(x, y)
        assert abs(lon) < 1e-8 and abs(lat) < 1e-8
        results.append(dict(name='synthetic_vector_crs', status='PASS'))
    except Exception as e:
        results.append(dict(name='synthetic_vector_crs', status='FAIL', detail=repr(e)))
    try:
        import numpy as np
        from rasterio.io import MemoryFile
        from rasterio.transform import from_origin
        a = np.arange(16, dtype='uint8').reshape(4, 4)
        with MemoryFile() as mem:
            with mem.open(driver='GTiff', height=4, width=4, count=1, dtype='uint8',
                          crs='EPSG:3857', transform=from_origin(0, 4, 1, 1)) as ds:
                ds.write(a, 1)
            with mem.open() as ds:
                assert np.array_equal(ds.read(1), a)
        results.append(dict(name='synthetic_raster', status='PASS'))
    except Exception as e:
        results.append(dict(name='synthetic_raster', status='FAIL', detail=repr(e)))
    try:
        import numpy as np
        import cv2
        a = np.zeros((8, 8), dtype='uint8')
        assert cv2.GaussianBlur(a, (3, 3), 0).shape == (8, 8)
        results.append(dict(name='synthetic_opencv', status='PASS'))
    except Exception as e:
        results.append(dict(name='synthetic_opencv', status='FAIL', detail=repr(e)))
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', default='reports/environment_check.json')
    args = ap.parse_args()
    report = {'phase': 0, 'timestamp_utc': datetime.now(timezone.utc).isoformat(),
              'host': {'platform': platform.platform(), 'python': sys.version.split()[0],
                       'executable': sys.executable, 'conda_prefix': os.environ.get('CONDA_PREFIX')},
              'modules': [test_module(n, req) for n, req in MODULES.items()],
              'cli': [test_cli(n, req) for n, req in CLI.items()],
              'smoke_tests': smoke()}
    report['required_failures'] = [item['name'] for group in ('modules', 'cli', 'smoke_tests')
                                   for item in report[group]
                                   if item['status'] == 'FAIL' and item.get('required', True)]
    report['overall'] = 'PASS' if not report['required_failures'] else 'FAIL'
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('PHASE 0 GIS DOCTOR:', report['overall'])
    for group in ('modules', 'cli', 'smoke_tests'):
        for item in report[group]:
            print(f"  {item['name']:<22} {item['status']} {item.get('version', '')}")
    print('Report:', path)
    return 1 if report['required_failures'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
