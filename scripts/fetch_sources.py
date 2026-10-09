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
from urllib.request import Request, HTTPRedirectHandler, build_opener, HTTPCookieProcessor

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
    return build_opener(HTTPCookieProcessor(), RedirectGuard(domains))


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
    fmt_lower = fmt.lower()
    if fmt_lower == 'zip':
        return header.startswith((b'PK\x03\x04', b'PK\x05\x06'))
    if fmt_lower == 'csv':
        data = header.lstrip(b'\xef\xbb\xbf\r\n \t').lower()
        return bool(data) and not data.startswith((b'<html', b'<!doctype', b'{"error"'))
    if fmt_lower in ('json', 'geojson'):
        data = header.lstrip(b'\xef\xbb\xbf\r\n \t')
        return data.startswith((b'{', b'['))
    if fmt_lower in ('xml', 'osm'):
        data = header.lstrip(b'\xef\xbb\xbf\r\n \t')
        return data.startswith((b'<?xml', b'<osm', b'<gml'))
    if fmt_lower == 'pdf':
        return header.startswith(b'%PDF-')
    if fmt_lower == 'pbf':
        return b'OSMHeader' in header or (len(header) >= 4 and header[:2] == b'\x00\x00')
    if fmt_lower in ('jpg', 'jpeg'):
        return header.startswith(b'\xff\xd8\xff')
    return False


def validate_file_integrity(file_path: Path, fmt: str, min_bytes: int = 10) -> tuple[bool, str]:
    """Strictly validate file format and integrity to prevent corruption or incomplete writes."""
    if not file_path.is_file():
        return False, f"File does not exist: {file_path}"
    size = file_path.stat().st_size
    if size < min_bytes:
        return False, f"File size too small ({size} bytes < {min_bytes})"

    fmt_lower = fmt.lower()
    try:
        if fmt_lower == 'zip':
            import zipfile
            if not zipfile.is_zipfile(file_path):
                return False, "Not a valid ZIP file"
            with zipfile.ZipFile(file_path, 'r') as zf:
                bad_file = zf.testzip()
                if bad_file is not None:
                    return False, f"ZIP CRC check failed on {bad_file}"
            return True, "Valid ZIP file with integrity confirmed"

        elif fmt_lower == 'pdf':
            with file_path.open('rb') as f:
                header = f.read(1024)
                if not header.startswith(b'%PDF-'):
                    return False, "Missing %PDF- header"
                f.seek(max(0, size - 2048))
                tail = f.read(2048)
                if b'%%EOF' not in tail:
                    return False, "Missing %%EOF marker in PDF tail"
            return True, "Valid PDF format confirmed"

        elif fmt_lower == 'pbf':
            with file_path.open('rb') as f:
                header = f.read(2048)
                if b'OSMHeader' not in header:
                    return False, "Missing OSMHeader marker in PBF file"
            return True, "Valid OSM PBF format confirmed"

        elif fmt_lower in ('json', 'geojson'):
            with file_path.open('r', encoding='utf-8') as f:
                json.load(f)
            return True, "Valid JSON/GeoJSON syntax confirmed"

        elif fmt_lower in ('xml', 'osm'):
            import xml.etree.ElementTree as ET
            # Parse head/elements
            with file_path.open('rb') as f:
                head = f.read(2048).lstrip()
                if not head.startswith((b'<?xml', b'<osm', b'<gml')):
                    return False, "Invalid XML/OSM header"
            return True, "Valid XML/OSM format confirmed"

        elif fmt_lower == 'csv':
            with file_path.open('rb') as f:
                head = f.read(2048)
                if not looks_like_format(head, 'csv'):
                    return False, "Invalid CSV header"
            return True, "Valid CSV format confirmed"

        elif fmt_lower in ('jpg', 'jpeg'):
            with file_path.open('rb') as f:
                head = f.read(3)
                if head != b'\xff\xd8\xff':
                    return False, "Missing JPEG SOI marker"
            return True, "Valid JPEG format confirmed"

    except Exception as e:
        return False, f"Integrity check failed: {type(e).__name__}: {e}"

    return True, "Format accepted"


def safe_extract_zip(zip_path: Path, dest_dir: Path, max_bytes: int = 200_000_000) -> list[Path]:
    """Safely extract a ZIP file guarding against Zip Bomb, directory traversal (Zip Slip), and symlink attacks."""
    import zipfile
    import stat
    if not zip_path.is_file() or not zipfile.is_zipfile(zip_path):
        raise DownloadError(f"Cannot extract non-zip file: {zip_path}")

    dest_resolved = dest_dir.resolve()
    dest_resolved.mkdir(parents=True, exist_ok=True)
    extracted_files: list[Path] = []
    total_uncompressed = 0

    with zipfile.ZipFile(zip_path, 'r') as zf:
        for member in zf.infolist():
            # Check symlink attributes
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise DownloadError(f"Symlink rejected for security: member {member.filename}")

            total_uncompressed += member.file_size
            if total_uncompressed > max_bytes:
                raise DownloadError(f"Zip Bomb protection: uncompressed size exceeds limit ({total_uncompressed} > {max_bytes} bytes)")

            # Check Zip Slip: path must be strictly within dest_resolved
            target_path = (dest_resolved / member.filename).resolve()
            if target_path != dest_resolved and dest_resolved not in target_path.parents:
                raise DownloadError(f"Zip Slip detected: member {member.filename} escapes destination")

        for member in zf.infolist():
            zf.extract(member, dest_resolved)
            extracted_files.append(dest_resolved / member.filename)

    return extracted_files


def download(src, url, data_root: Path | None = None):
    limit = int(src['max_bytes'])
    if not 0 < limit <= 700000000:
        raise DownloadError('Unsafe size limit: must be between 1 and 700,000,000 bytes')

    target_root = data_root or get_data_root()
    dest_dir = src.get('dest_dir', f"raw/{src['id']}")
    target = target_root / dest_dir / src['filename']
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + '.partial')

    if target.exists():
        # Validate existing file before trusting it
        valid, reason = validate_file_integrity(target, src['expected_format'])
        if not valid:
            raise DownloadError(f"Existing file is corrupted ({reason}); never overwrite without explicit confirmation: {target}")

        file_size = target.stat().st_size
        h = hashlib.sha256()
        with target.open('rb') as f:
            while chunk := f.read(65536):
                h.update(chunk)
        calculated_sha = h.hexdigest()

        # If expected SHA is configured, verify match
        if 'expected_sha256' in src and src['expected_sha256'] != calculated_sha:
            raise DownloadError(f"Existing file SHA256 mismatch for {src['id']}: expected {src['expected_sha256']}, got {calculated_sha}")

        rel_path = str(target.relative_to(target_root))
        record = {'source_id': src['id'], 'source_page': src.get('source_page', ''),
                  'download_url': url, 'license_url': src.get('license_url', ''),
                  'license_note': src.get('license_note', ''), 'phase': 0,
                  'downloaded_at_utc': datetime.now(timezone.utc).isoformat(),
                  'relative_path': rel_path,
                  'bytes': file_size, 'sha256': calculated_sha, 'format': src['expected_format'],
                  'status': 'already_present'}
        return record

    if partial.exists():
        # Safely preserve partial download for investigation instead of unconditionally deleting
        interrupted_name = partial.with_name(f"{partial.name}.interrupted_{int(datetime.now(timezone.utc).timestamp())}")
        try:
            partial.rename(interrupted_name)
            print(f"NOTICE: Preserved existing partial download as {interrupted_name.name}", file=sys.stderr)
        except OSError:
            pass

    req = Request(url, headers={'User-Agent': AGENT, 'Accept': 'application/octet-stream,*/*'})
    digest = hashlib.sha256()
    header = b''
    size = 0
    final_url = url
    try:
        with opener(src['allowed_domains']).open(req, timeout=40) as response:
            final_url = response.geturl()
            if not approved_url(final_url, src['allowed_domains']):
                raise DownloadError('Final URL not allowlisted: ' + final_url)
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

        # Full file integrity check on partial file before committing to target
        valid, reason = validate_file_integrity(partial, src['expected_format'])
        if not valid:
            raise DownloadError(f"Downloaded file failed integrity verification: {reason}")

        partial.rename(target)
    finally:
        # If partial still exists (due to error before rename), preserve it safely
        if partial.exists():
            interrupted = partial.with_name(f"{partial.name}.interrupted_{int(datetime.now(timezone.utc).timestamp())}")
            try:
                partial.rename(interrupted)
            except OSError:
                pass

    rel_path = str(target.relative_to(target_root))
    record = {'source_id': src['id'], 'source_page': src.get('source_page', ''),
              'download_url': final_url, 'license_url': src.get('license_url', ''),
              'license_note': src.get('license_note', ''), 'phase': 0,
              'downloaded_at_utc': datetime.now(timezone.utc).isoformat(),
              'relative_path': rel_path,
              'bytes': size, 'sha256': digest.hexdigest(), 'format': src['expected_format'],
              'status': 'downloaded'}

    # Record provenance to Google Drive storage root if not already present
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
        dest_dir = src.get('dest_dir', f"raw/{src['id']}")
        target_path = data_root / dest_dir / src['filename']
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
