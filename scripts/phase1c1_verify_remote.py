#!/usr/bin/env python3
"""Read-only, bounded remote verification of the original nine C1 output pairs."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from kanagawa_ruins.raster.io import local_output


def remote_read(relative, root_id, max_bytes, *, retain=False):
    if relative.startswith('/') or '..' in Path(relative).parts:
        raise ValueError('Unsafe relative remote path')
    cmd = ['timeout', '--kill-after=5s', '45s', 'rclone', 'cat',
           'gdrive:' + relative, '--drive-root-folder-id', root_id,
           '--tpslimit', '0.5', '--tpslimit-burst', '1', '--retries', '1',
           '--low-level-retries', '1', '--contimeout', '5s', '--timeout', '10s']
    digest, count, content = hashlib.sha256(), 0, bytearray()
    with tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=stderr)
        try:
            while block := process.stdout.read(1024 * 1024):
                count += len(block)
                if count > max_bytes:
                    raise ValueError('Remote content exceeds expected size/admission ceiling')
                digest.update(block)
                if retain:
                    content.extend(block)
            rc = process.wait()
            stderr.seek(0)
            error = stderr.read(8192).decode(errors='replace')
            if rc:
                raise OSError(f'Remote read exit {rc} for {relative}: {error}')
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
            process.stdout.close()
    return {'sha256': digest.hexdigest(), 'bytes': count}, bytes(content)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--root-id', required=True)
    parser.add_argument('--ingest-report', default='reports/phase1c1_ingest_r2.json')
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    target = local_output(args.report)
    previous = Path(args.ingest_report).read_bytes()
    report = dict(started_at_utc=datetime.now(timezone.utc).isoformat(),
                  status='RUNNING', remote_upload_verified=False,
                  input_report_sha256=hashlib.sha256(previous).hexdigest(),
                  results=[], errors=[], retries=0)
    with target.open('x') as output:
        output.write(json.dumps(report, indent=2) + '\n')
    layers = [layer for result in json.loads(previous)['results'] for layer in result['layers']]
    try:
        if len(layers) != 9 or len({x['layer_id'] for x in layers}) != 9:
            raise ValueError('Expected exactly nine distinct previously published layers')
        for layer in layers:
            vector, _ = remote_read(layer['processed_path'], args.root_id, layer['bytes'])
            if vector != {'sha256': layer['output_sha256'], 'bytes': layer['bytes']}:
                raise ValueError(f"Remote vector SHA/size mismatch: {layer['layer_id']}")
            manifest_path = 'processed/phase1c/codex/manifests/' + layer['layer_id'] + '.json'
            meta, content = remote_read(manifest_path, args.root_id, 1_000_000, retain=True)
            manifest = json.loads(content)
            for key in ['layer_id', 'source_id', 'source_sha256', 'processing_version',
                        'parameters', 'output_sha256', 'bytes', 'original_crs',
                        'processed_crs', 'processed_path', 'analysis_ready']:
                if manifest.get(key) != layer.get(key):
                    raise ValueError(f"Remote manifest mismatch: {layer['layer_id']}:{key}")
            report['results'].append(dict(layer_id=layer['layer_id'], vector=vector,
                                          manifest=meta, verified=True))
            target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
            print('verified', layer['layer_id'], flush=True)
        report.update(status='PASS', remote_upload_verified=True)
    except Exception as error:
        report['status'] = 'STOPPED_ON_ERROR'
        report['errors'].append(repr(error))
        print('STOP', error, flush=True)
    report['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return 0 if report['remote_upload_verified'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
