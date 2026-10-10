"""Bounded nested-ZIP and strict, feature-at-a-time FGD GML reader.

BldA is an area; BldL and RdEdg remain curves. No polygon repair or
polygonization is implicit. Dates describe records, never construction events.
"""

from contextlib import contextmanager
import io
import re
import zipfile
import xml.etree.ElementTree as ET
import numpy as np
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString

FGD = "http://fgd.gsi.go.jp/spec/2008/FGD_GMLSchema"
GML = "http://www.opengis.net/gml/3.2"
NS = {"f": FGD, "g": GML}
CRS = {"fguuid:jgd2000.bl": "EPSG:4612",
       "fguuid:jgd2011.bl": "EPSG:6668",
       "fguuid:jgd2024.bl": "EPSG:6668"}
KINDS = {"BldA", "BldL", "RdEdg"}


@contextmanager
def inner_archive(outer, member, job):
    """One seekable inner ZIP on bounded job scratch; never buffer an outer ZIP."""
    info = outer.getinfo(member)
    job.check(info.file_size)
    path = job.path / "inner.zip"
    try:
        with outer.open(info) as src, path.open("xb") as dst:
            count = 0
            while chunk := src.read(1024 * 1024):
                count += len(chunk)
                if count > info.file_size:
                    raise ValueError("ZIP member exceeds declared size")
                dst.write(chunk)
                job.check()
        with zipfile.ZipFile(path) as inner:
            yield inner
    finally:
        path.unlink(missing_ok=True)


def _coordinates(node):
    parts = []
    for pos in node.findall(".//g:posList", NS):
        if pos.get("srsDimension", "2") != "2":
            raise ValueError("Only 2D positions supported")
        tokens = (pos.text or "").split()
        if len(tokens) % 2:
            raise ValueError("Odd coordinate count")
        values = np.array([float(v) for v in tokens]).reshape(-1, 2)
        if not np.isfinite(values).all():
            raise ValueError("Nonfinite coordinates")
        # FGD .bl is latitude, longitude; GeoDataFrame is x, y.
        coords = [(lon, lat) for lat, lon in values]
        if parts and coords and parts[-1] != coords[0]:
            raise ValueError("Disconnected ring/curve segments")
        parts.extend(coords[1:] if parts else coords)
    if not parts:
        raise ValueError("No inline posList; references/other curves unsupported")
    if any(not (-180 <= x <= 180 and -90 <= y <= 90) for x, y in parts):
        raise ValueError("Coordinates out of range")
    return parts


def feature_record(node, kind):
    declarations = {e.get("srsName") for e in node.iter() if e.get("srsName")}
    if len(declarations) != 1 or not declarations <= CRS.keys():
        raise ValueError(f"Unknown/mixed/absent CRS: {declarations}")
    declaration = next(iter(declarations))
    if kind == "BldA":
        polygons = []
        for patch in node.findall(".//g:PolygonPatch", NS):
            exterior = patch.find("g:exterior", NS)
            if exterior is None:
                raise ValueError("Missing exterior")
            shell = _coordinates(exterior)
            holes = [_coordinates(h) for h in patch.findall("g:interior", NS)]
            if any(len(r) < 4 or r[0] != r[-1] for r in [shell, *holes]):
                raise ValueError("Open/short polygon ring")
            polygons.append(Polygon(shell, holes))
        if not polygons:
            raise ValueError("No supported surface patches")
        geom = polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)
    else:
        # Real 2008 BldL can contain non-contiguous LineStringSegments.
        # Preserve each segment rather than drawing a fictitious connecting edge.
        curves = [LineString(_coordinates(c)) for c in node.findall(".//g:LineStringSegment", NS)]
        if not curves:
            raise ValueError("No supported curves")
        geom = curves[0] if len(curves) == 1 else MultiLineString(curves)

    def text(name):
        n = node.find("f:" + name, NS)
        return "".join(n.itertext()).strip() if n is not None else None

    return dict(fid=text("fid"), feature_kind=kind, devDate=text("devDate"),
                lfSpanFr=text("lfSpanFr"), orgMDId=text("orgMDId"),
                orgGILvl=text("orgGILvl"), xml_mesh=text("mesh"),
                feature_type=text("type"), declared_crs=declaration,
                geometry=geom, geometry_valid=geom.is_valid,
                source_epsg=CRS[declaration])


def records(stream, *, kinds=KINDS, audit=None):
    """Strict decode then iterparse; remove completed top-level elements.

    XML member size is guarded by the caller. Invalid topology is retained and
    flagged; unsupported geometry or unknown CRS stops the member, not guessed.
    """
    header = stream.peek(256) if hasattr(stream, "peek") else b""
    match = re.search(br'encoding=[\"\x27]([^\"\x27]+)', header, re.I)
    encoding = match[1].decode("ascii").lower() if match else "utf-8"
    if encoding not in {"utf-8", "shift_jis", "shift-jis"}:
        raise ValueError(f"Unsupported XML encoding: {encoding}")
    if audit is not None:
        audit["encoding"] = encoding
    wrapper = io.TextIOWrapper(stream, encoding=encoding, errors="strict")
    try:
        parser = ET.iterparse(wrapper, events=("start", "end"))
        _, root = next(parser)
        if root.tag != "{" + FGD + "}Dataset":
            raise ValueError("Unexpected FGD dataset namespace/root")
        depth = 0
        for event, node in parser:
            if event == "start":
                depth += 1
                continue
            if depth == 1:
                kind = node.tag.removeprefix("{" + FGD + "}")
                if kind in kinds and node.tag == "{" + FGD + "}" + kind:
                    yield feature_record(node, kind)
                root.remove(node)
                node.clear()
            depth -= 1
    finally:
        wrapper.detach()
