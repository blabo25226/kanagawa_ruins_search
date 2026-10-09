#!/usr/bin/env python3
"""Phase 0: check GIS packages, CLI, and Google Drive storage using synthetic test data only."""
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

ROOT = Path(__file__).resolve().parents[1]

MODULES = {'numpy': True, 'pandas': True, 'geopandas': True, 'shapely': True,
           'pyproj': True, 'rasterio': True, 'osgeo.gdal': True, 'cv2': True,
           'folium': False, 'matplotlib': False}
CLI = {'gdalinfo': True, 'ogrinfo': True, 'gdalwarp': True, 'rclone': True, 'qgis_process': False}


def load_env_var(name: str) -> str | None:
    val = os.environ.get(name)
    if val:
        return val
    env_file = ROOT / '.env'
    if env_file.is_file():
        for line in env_file.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                if k.strip() == name:
                    return v.strip().strip('"').strip("'")
    return None


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


def test_storage():
    results = []
    data_root_str = load_env_var('RUINS_DATA_ROOT')
    if not data_root_str:
        return [dict(name='ruins_data_root_configured', required=True, status='FAIL',
                     detail='RUINS_DATA_ROOT not found in environment or .env')]

    data_root = Path(data_root_str).expanduser().resolve()
    results.append(dict(name='ruins_data_root_configured', required=True, status='PASS',
                        configured_path=str(data_root)))

    # Directory existence
    if not data_root.is_dir():
        results.append(dict(name='ruins_data_root_exists', required=True, status='FAIL',
                            detail=f'Path does not exist: {data_root}'))
        return results
    results.append(dict(name='ruins_data_root_exists', required=True, status='PASS'))

    # Check mount status (Google Drive FUSE / rclone)
    is_mounted = False
    mount_entry = ''
    try:
        proc_mounts = Path('/proc/mounts')
        if proc_mounts.is_file():
            mounts_content = proc_mounts.read_text(encoding='utf-8')
            for line in mounts_content.splitlines():
                parts = line.split()
                if len(parts) >= 3:
                    mp = parts[1]
                    fstype = parts[2]
                    if str(data_root).startswith(mp) and mp != '/' and ('rclone' in fstype or 'fuse' in fstype or 'google' in parts[0].lower() or 'gdrive' in parts[0].lower()):
                        is_mounted = True
                        mount_entry = f"{parts[0]} on {mp} ({fstype})"
                        break
    except Exception as e:
        mount_entry = repr(e)

    results.append(dict(name='gdrive_mounted', required=True,
                        status='PASS' if is_mounted else 'FAIL',
                        mount_info=mount_entry))

    # Read/write access test
    test_file = data_root / '.ruins_probe_tmp'
    try:
        test_file.write_text('probe_ok\n', encoding='utf-8')
        content = test_file.read_text(encoding='utf-8').strip()
        assert content == 'probe_ok'
        test_file.unlink()
        results.append(dict(name='storage_read_write', required=True, status='PASS'))
    except Exception as e:
        if test_file.exists():
            try:
                test_file.unlink()
            except Exception:
                pass
        results.append(dict(name='storage_read_write', required=True, status='FAIL', detail=repr(e)))

    # Disk usage
    try:
        local_usage = shutil.disk_usage(ROOT)
        gdrive_usage = shutil.disk_usage(data_root)
        results.append(dict(name='storage_capacity', required=False, status='PASS',
                            local_free_bytes=local_usage.free,
                            gdrive_free_bytes=gdrive_usage.free))
    except Exception:
        pass

    return results


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
    storage_results = test_storage()
    report = {'phase': 0, 'timestamp_utc': datetime.now(timezone.utc).isoformat(),
              'host': {'platform': platform.platform(), 'python': sys.version.split()[0],
                       'executable': sys.executable, 'conda_prefix': os.environ.get('CONDA_PREFIX')},
              'modules': [test_module(n, req) for n, req in MODULES.items()],
              'cli': [test_cli(n, req) for n, req in CLI.items()],
              'storage': storage_results,
              'smoke_tests': smoke()}
    report['required_failures'] = [item['name'] for group in ('modules', 'cli', 'storage', 'smoke_tests')
                                   for item in report[group]
                                   if item['status'] == 'FAIL' and item.get('required', True)]
    report['overall'] = 'PASS' if not report['required_failures'] else 'FAIL'
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('PHASE 0 GIS DOCTOR:', report['overall'])
    for group in ('modules', 'cli', 'storage', 'smoke_tests'):
        print(f"[{group.upper()}]")
        for item in report[group]:
            extra = item.get('version', '') or item.get('mount_info', '') or item.get('configured_path', '')
            print(f"  {item['name']:<28} {item['status']} {extra}")
    print('Report:', path)
    return 1 if report['required_failures'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
