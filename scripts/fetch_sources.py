#!/usr/bin/env python3
"""Phase 0 only: fetch small HTTPS-allowlisted official files into verified Google Drive data storage, record provenance; no analysis."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tomllib
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, HTTPRedirectHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from storage_utils import get_verified_data_root, StorageError  # noqa: E402

CATALOG = ROOT / 'config/sources.toml'
DOWNLOADABLE_MODES = {'direct', 'ckan_resource'}
AGENT = 'KanagawaRuinsResearch/0.1 (approved public files, no bulk map tiles)'


class DownloadError(Exception):
    pass


def get_data_root(mounts_path: Path | None = None) -> Path:
    """Resolve RUINS_DATA_ROOT and strictly verify rclone Google Drive mount."""
    try:
        return get_verified_data_root(root=ROOT, mounts_path=mounts_path)
    except StorageError as e:
        raise DownloadError(f"Storage mount security verification failed: {e}") from e


def approved_url(url: str, domains: list[str]) -> bool:
    try:
        p = urlparse(url)
        return (p.scheme == 'https' and p.hostname in domains
                and p.username is None and p.password is None and p.port in (None, 443))
    except (ValueError, TypeError):
        return False


class RedirectGuard(HTTPRedirectHandler):
    def __init__(self, allowed):
        super().__init__()
        self.allowed = allowed

    def redirect_request(self, req, fp, code, msg, headers, url):
        if not approved_url(url, self.allowed):
            raise DownloadError('Blocked off-domain redirect: ' + url)
        return super().redirect_request(req, fp, code, msg, headers, url)


def opener(domains):
    return build_opener(RedirectGuard(domains))


def resolve_download_url(src):
    if src['mode'] == 'direct':
        url = src['url']
    elif src['mode'] == 'ckan_resource':
        api = src['api_url']
        if not approved_url(api, src['allowed_domains']):
            raise DownloadError('CKAN API not allowed')
        request = Request(api, headers={'User-Agent': AGENT, 'Accept': 'application/json'})
        with opener(src['allowed_domains']).open(request, timeout=25) as response:
            body = response.read(256001)
        if len(body) > 256000:
            raise DownloadError('Metadata API returned oversized document')
        metadata = json.loads(body)
        if not metadata.get('success') or not isinstance(metadata.get('result'), dict):
            raise DownloadError('Invalid CKAN API response')
        obj = metadata['result']
        if str(obj.get('format', '')).lower() != 'csv':
            raise DownloadError('CKAN format changed; expected CSV')
        url = obj.get('url', '')
    else:
        raise DownloadError('Source is manual or view-only')
    if not approved_url(url, src['allowed_domains']):
        raise DownloadError('URL not in HTTPS source allowlist: ' + str(url))
    return url


def looks_like_format(header: bytes, fmt: str) -> bool:
    if fmt == 'zip':
        return header.startswith((b'PK\x03\x04', b'PK\x05\x06'))
    if fmt == 'csv':
        data = header.lstrip(b'\xef\xbb\xbf\r\n \t').lower()
        return bool(data) and not data.startswith((b'<html', b'<!doctype', b'{"error"'))
    return False


def download(src, url, data_root: Path | None = None):
    limit = int(src['max_bytes'])
    if not 0 < limit <= 20000000:
        raise DownloadError('Unsafe size limit')

    target_root = data_root or get_data_root()
    target = target_root / 'raw' / src['id'] / src['filename']
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + '.partial')
    if target.exists() or partial.exists():
        raise DownloadError('Already downloaded/partial exists; never overwrite Google Drive data: ' + str(target))

    req = Request(url, headers={'User-Agent': AGENT, 'Accept': 'application/octet-stream,*/*'})
    digest = hashlib.sha256()
    header = b''
    size = 0
    final_url = url
    try:
        with opener(src['allowed_domains']).open(req, timeout=40) as response:
            final_url = response.geturl()
            if not approved_url(final_url, src['allowed_domains']):
                raise DownloadError('Final URL not allowlisted')
            if int(response.headers.get('Content-Length') or '0') > limit:
                raise DownloadError('Content-Length exceeds configured limit')
            with partial.open('xb') as out:
                while True:
                    chunk = response.read(min(65536, limit - size + 1))
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > limit:
                        raise DownloadError('File too large')
                    header += chunk[:max(0, 2048-len(header))]
                    digest.update(chunk)
                    out.write(chunk)
        if not size or not looks_like_format(header, src['expected_format']):
            raise DownloadError('Response is not a valid expected format header')
        partial.rename(target)
    finally:
        if partial.exists():
            partial.unlink()

    rel_path = str(target.relative_to(target_root))
    record = {'source_id': src['id'], 'source_page': src['source_page'],
              'download_url': final_url, 'license_url': src['license_url'],
              'license_note': src['license_note'], 'phase': 0,
              'downloaded_at_utc': datetime.now(timezone.utc).isoformat(),
              'relative_path': rel_path,
              'bytes': size, 'sha256': digest.hexdigest(), 'format': src['expected_format']}

    # Record provenance to Google Drive storage root
    prov_gdrive = target_root / 'provenance.jsonl'
    with prov_gdrive.open('a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')

    # Also record to local project (gitignored) for convenient local inspection
    prov_local = ROOT / 'data/provenance.jsonl'
    prov_local.parent.mkdir(parents=True, exist_ok=True)
    with prov_local.open('a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')

    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--list', action='store_true')
    action.add_argument('--dry-run', action='store_true')
    action.add_argument('--execute', action='store_true')
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument('--all-approved', action='store_true')
    selection.add_argument('--id', action='append')
    a = parser.parse_args()
    with CATALOG.open('rb') as f:
        entries = tomllib.load(f)['source']
    by_id = {s['id']: s for s in entries}
    if len(by_id) != len(entries):
        parser.error('Duplicate source ids')
    if a.list:
        for s in entries:
            print(f"{s['id']:<32} {s['mode']:<16} {s['title']}")
        return 0
    if not a.all_approved and not a.id:
        parser.error('Choose --all-approved or --id')
    ids = a.id if a.id else [s['id'] for s in entries if s['mode'] in DOWNLOADABLE_MODES]
    for sid in ids:
        if sid not in by_id:
            parser.error('Unknown source id: ' + sid)
        if by_id[sid]['mode'] not in DOWNLOADABLE_MODES:
            parser.error('This source is not automatable: ' + sid)

    try:
        data_root = get_data_root()
    except DownloadError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    errors = 0
    for sid in dict.fromkeys(ids):
        src = by_id[sid]
        target_path = data_root / 'raw' / src['id'] / src['filename']
        if a.dry_run:
            print(f"DRY RUN: {sid} -> {target_path} (max={src['max_bytes']} bytes)")
            continue
        try:
            record = download(src, resolve_download_url(src), data_root=data_root)
            print(f"DOWNLOADED {sid}: bytes={record['bytes']} sha256={record['sha256']} -> {record['relative_path']}")
        except (DownloadError, HTTPError, URLError, OSError, ValueError, TimeoutError, json.JSONDecodeError) as e:
            errors += 1
            print(f"FAILED {sid}: {type(e).__name__}: {e}", file=sys.stderr)
    if a.dry_run:
        print('No network access or file downloads in dry-run mode.')
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
