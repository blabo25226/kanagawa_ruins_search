"""Bounded ZIP extraction and chunked GDAL vector loading; preserve distinct sublayers."""

from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
import codecs
import re
import shutil
import stat
import warnings
import xml.etree.ElementTree as ET
import zipfile
import geopandas as gpd
import pyogrio


def checked_members(z, limit):
    total = 0
    seen = set()
    for m in z.infolist():
        p = Path(m.filename)
        if p.is_absolute() or ".." in p.parts or stat.S_ISLNK(m.external_attr >> 16):
            raise ValueError(f"Unsafe ZIP member: {m.filename}")
        if p.as_posix() in seen:
            raise ValueError(f"Duplicate ZIP member: {m.filename}")
        seen.add(p.as_posix())
        total += m.file_size
        if total > limit:
            raise ValueError("ZIP expanded size exceeds job budget")
    bad = z.testzip()
    if bad:
        raise ValueError(f"ZIP CRC mismatch: {bad}")
    return total


@contextmanager
def vector_files(path, job):
    """Prefer UTF-8 representation; do not load both encoding copies or GML + SHP."""
    if path.suffix.lower() != ".zip":
        if path.suffix.lower() not in {".shp", ".gml", ".geojson", ".json", ".gpkg"}:
            raise ValueError("Unsupported vector input format")
        if path.suffix.lower() == ".gml":
            # GDAL can create .gfs beside a GML during discovery. Keep every such
            # driver side effect in the job, including when input is not zipped.
            companions = (
                [path]
                + [
                    p
                    for p in (path.with_suffix(".xsd"), path.with_suffix(".gfs"))
                    if p.is_file()
                ]
                + sorted(path.parent.glob("KS-META*.xml"))
            )
            job.check(sum(p.stat().st_size for p in companions))
            dest = job.path / "standalone_gml"
            dest.mkdir()
            for p in companions:
                shutil.copyfile(p, dest / p.name)
            job.check()
            yield [dest / path.name]
            return
        yield [path]
        return
    with zipfile.ZipFile(path) as z:
        total = checked_members(z, job.limit)
        job.check(total)
        dest = job.path / "extracted"
        dest.mkdir()
        z.extractall(dest)
        job.check()
        shps = sorted(dest.rglob("*.shp"))
        if shps:
            utf = [p for p in shps if "UTF-8" in p.parts]
            yield utf or shps
        else:
            files = sorted(dest.rglob("*.gml")) or [
                p
                for p in sorted(dest.rglob("*.xml"))
                if not p.name.startswith("KS-META")
            ]
            if not files:
                raise ValueError("ZIP contains no supported vector dataset")
            yield files


@lru_cache(maxsize=256)
def shapefile_encoding(path):
    if path.suffix.lower() != ".shp":
        return None
    cpgs = [
        p
        for p in path.parent.iterdir()
        if p.stem == path.stem and p.suffix.lower() == ".cpg"
    ]
    if cpgs:
        raw = cpgs[0].read_text(encoding="ascii").strip()
        enc = {"65001": "utf-8", "932": "cp932"}.get(raw, raw)
        codecs.lookup(
            enc
        )  # unknown declared encoding is an error, never silently overridden
        return enc
    if "UTF-8" in path.parts:
        return "utf-8"
    if "Shift-JIS" in path.parts:
        return "cp932"
    # DBF files with LDID=0 may contain CP932 field names. Validate every text field
    # strictly, UTF-8 first then CP932, instead of trusting GDAL's Latin-1 fallback.
    for enc in ("utf-8", "cp932"):
        try:
            validate_dbf_text(path.with_suffix(".dbf"), enc)
            return enc
        except UnicodeDecodeError:
            continue
    raise ValueError("DBF is neither strict UTF-8 nor strict CP932")


def vector_chunks(path, batch_size=50000):
    layers = pyogrio.list_layers(path)
    for name, geometry_type in layers:
        if geometry_type is None:
            continue
        info = pyogrio.read_info(
            path,
            layer=name,
            encoding=shapefile_encoding(path),
            force_feature_count=True,
        )
        actual_count = 0
        for offset in range(0, int(info["features"]), batch_size):
            with warnings.catch_warnings():
                warnings.filterwarnings("error", message=".*convert.*")
                frame = gpd.read_file(
                    path,
                    layer=name,
                    engine="pyogrio",
                    encoding=shapefile_encoding(path),
                    skip_features=offset,
                    max_features=batch_size,
                )
            if frame.crs is None:
                crs, declaration = metadata_crs(path)
                frame = frame.set_crs(
                    crs
                )  # Explicit bundled declaration, never coordinate inference.
                frame.attrs["crs_evidence"] = declaration
            actual_count += len(frame)
            frame.attrs["input_feature_count"] = int(info["features"])
            yield name, frame
        if actual_count != int(info["features"]):
            raise ValueError(f"GDAL source record count mismatch: {name}")


def layer_suffix(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def parse_metadata(path):
    data = path.read_bytes()
    declaration = re.search(rb'encoding=["\']([^"\']+)', data[:150], re.I)
    encoding = declaration[1].decode("ascii") if declaration else "utf-8-sig"
    return ET.fromstring(data.decode(encoding))


def metadata_crs(path):
    known = {
        "JGD2000 / (B, L)": "EPSG:4612",
        "JGD2011 / (B, L)": "EPSG:6668",
        "JGD2024 / (B, L)": "EPSG:6668",
        "TD / (B, L)": "EPSG:4301",
    }
    matches = []
    for p in sorted(path.parent.glob("KS-META*.xml")):
        tree = parse_metadata(p)
        for node in tree.iter():
            if node.tag.rsplit("}", 1)[-1] == "referenceSystemInfo":
                for c in node.iter():
                    if c.tag.rsplit("}", 1)[-1] == "code" and c.text:
                        matches.append((c.text.strip(), p.name))
    labels = {m[0] for m in matches}
    if len(labels) != 1 or next(iter(labels)) not in known:
        raise ValueError(f"Undefined/ambiguous CRS: bundled declarations {matches}")
    label = next(iter(labels))
    return known[label], dict(
        declaration=label, metadata_files=sorted({m[1] for m in matches})
    )


def validate_dbf_text(path, encoding):
    with path.open("rb") as f:
        header = f.read(32)
        if len(header) != 32:
            raise ValueError("Truncated DBF header")
        header_size = int.from_bytes(header[8:10], "little")
        row_size = int.from_bytes(header[10:12], "little")
        rows = int.from_bytes(header[4:8], "little")
        if header_size < 33 or row_size < 1:
            raise ValueError("Invalid DBF dimensions")
        descriptors = f.read(header_size - 32)
        fields = []
        offset = 1
        for i in range(0, len(descriptors) - 1, 32):
            field = descriptors[i : i + 32]
            if len(field) != 32:
                raise ValueError("Invalid DBF field descriptor")
            field[:11].split(b"\0")[0].decode(encoding, errors="strict")
            width = field[16]
            if field[11] == ord("C"):
                fields.append((offset, width))
            offset += width
        for _ in range(rows):
            record = f.read(row_size)
            if len(record) != row_size:
                raise ValueError("Truncated DBF record")
            if record[0] == ord("*"):
                continue
            for start, width in fields:
                record[start : start + width].decode(encoding, errors="strict")
