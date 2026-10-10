"""Bounded FGD GML grid reader based on GSI DLFileSpec 5.3 and the FGD FAQ.

One DEM per XML, Linear +x -y sequence, explicit startPoint and lat/lon envelope.
Unsupported encodings are rejected; no vertical-datum conversion is inferred.
"""

from dataclasses import dataclass, asdict
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from pyproj import CRS
from pyproj.transformer import TransformerGroup
from ..ingest.kokudo import checked_members
from ..raster.io import local_output, open_image
from ..raster.cog import to_cog, validate_cog
from ..imaging.georef.transform import run_gdal, check_warp_budget

NODATA = -9999.0
MAX_XML = 128_000_000
MAX_CELLS = 4_000_000
GML = "http://www.opengis.net/gml/3.2"
FGD = "http://fgd.gsi.go.jp/spec/2008/FGD_GMLSchema"
DECLARED_CRS = {
    "fguuid:jgd2000.bl": (4612, "JGD2000"),
    "fguuid:jgd2011.bl": (6668, "JGD2011"),
    "fguuid:jgd2024.bl": (6668, "JGD2024"),
}


@dataclass(frozen=True)
class DEMReference:
    crs: str
    horizontal_datum: str
    vertical_datum: str
    unit: str
    evidence: str

    def __post_init__(self):
        if any(
            not v or str(v).lower() in {"unknown", "null"}
            for v in asdict(self).values()
        ):
            raise ValueError(
                "DEM horizontal/vertical reference and evidence are required"
            )
        if self.unit != "metre":
            raise ValueError("DEM height unit must be explicitly metre")
        crs = CRS.from_user_input(self.crs)
        if len(crs.axis_info) != 2 or not (crs.is_projected or crs.is_geographic):
            raise ValueError("DEM requires an explicit two-dimensional horizontal CRS")


def _one(parent, tag, namespace=GML):
    nodes = parent.findall(f".//{{{namespace}}}{tag}")
    if len(nodes) != 1:
        raise ValueError(f"Expected exactly one {tag}")
    return nodes[0]


def _numbers(node, length, kind=float):
    values = [kind(v) for v in (node.text or "").split()]
    if len(values) != length or not all(np.isfinite(v) for v in values):
        raise ValueError("Invalid grid coordinates")
    return values


def parse_fgd_xml(data, reference):
    if (
        len(data) > MAX_XML
        or b"<!DOCTYPE" in data.upper()
        or b"<!ENTITY" in data.upper()
    ):
        raise ValueError("Oversized/unsafe DEM XML")
    text = data.decode("utf-8-sig")
    if "\x00" in text or "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise ValueError("Only safe UTF-8 FGD XML is supported")
    declaration = re.search(
        r"encoding\s*=\s*[\"\x27]([^\"\x27]+)", text[:200], re.IGNORECASE
    )
    if declaration and declaration.group(1).lower() not in {"utf-8", "utf8"}:
        raise ValueError("Only UTF-8 FGD XML is supported")
    root = ET.fromstring(text)
    dems = root.findall(f".//{{{FGD}}}DEM")
    if root.tag == f"{{{FGD}}}DEM":
        dems = [root]
    if len(dems) != 1:
        raise ValueError("Only one FGD DEM grid per XML is supported")
    dem = dems[0]
    envelope = _one(dem, "Envelope")
    srs = envelope.get("srsName")
    if srs not in DECLARED_CRS:
        raise ValueError("Unknown FGD CRS declaration; review required")
    epsg, declared_datum = DECLARED_CRS[srs]
    if reference.horizontal_datum != declared_datum or CRS.from_user_input(
        reference.crs
    ) != CRS.from_epsg(epsg):
        raise ValueError("Declared DEM datum differs from reviewed reference")
    south, west = _numbers(_one(envelope, "lowerCorner"), 2)
    north, east = _numbers(_one(envelope, "upperCorner"), 2)
    if not (-90 <= south < north <= 90 and -180 <= west < east <= 180):
        raise ValueError("FGD envelope axis/range error (expected latitude longitude)")
    lowx, lowy = _numbers(_one(dem, "low"), 2, int)
    highx, highy = _numbers(_one(dem, "high"), 2, int)
    width, height = highx - lowx + 1, highy - lowy + 1
    if (
        (lowx, lowy) != (0, 0)
        or width <= 0
        or height <= 0
        or width * height > MAX_CELLS
    ):
        raise ValueError("Invalid/oversized DEM grid")
    grid = _one(dem, "Grid")
    if grid.get("dimension") != "2":
        raise ValueError("Only 2D DEM grids are supported")
    rule = _one(dem, "sequenceRule")
    if (rule.text or "").strip() != "Linear" or rule.get("order") != "+x-y":
        raise ValueError("Unsupported FGD grid scan order")
    startx, starty = _numbers(_one(dem, "startPoint"), 2, int)
    if not (lowx <= startx <= highx and lowy <= starty <= highy):
        raise ValueError("Invalid DEM startPoint")
    # FGD cell indices start at NW (0,0), despite the geographic -y scan direction.
    offset = (starty - lowy) * width + startx - lowx
    tuples = _one(dem, "tupleList")
    if (
        tuples.get("cs", ",") != ","
        or tuples.get("decimal", ".") != "."
        or tuples.get("ts", " ") not in {" ", "\n"}
    ):
        raise ValueError("Unsupported tuple separators")
    # Rows are whitespace-separated class,height pairs. Bounds keep memory predictable.
    entries = (tuples.text or "").split()
    if len(entries) > width * height - offset:
        raise ValueError("Too many DEM tuples")
    values = np.full(width * height, NODATA, dtype="float32")
    types = {}
    for i, entry in enumerate(entries, offset):
        parts = entry.split(",")
        if len(parts) != 2 or not parts[0]:
            raise ValueError("Malformed DEM tuple")
        classification, text = parts
        value = float(text)
        if not np.isfinite(value) or abs(value) > np.finfo("float32").max:
            raise ValueError("Invalid DEM elevation")
        if (classification == "データなし") != (value == NODATA):
            raise ValueError("Inconsistent DEM NoData type/value")
        values[i] = value
        types[classification] = types.get(classification, 0) + 1
    mesh = _one(dem, "mesh", FGD).text
    if not mesh or not re.fullmatch(r"\d{6}(?:\d{2})?", mesh.strip()):
        raise ValueError("Invalid/missing DEM mesh code")
    return (
        values.reshape(height, width),
        from_bounds(west, south, east, north, width, height),
        dict(
            mesh=mesh.strip(),
            declared_srs=srs,
            declared_horizontal_datum=declared_datum,
            scan_order="northwest_east_then_south",
            omitted_leading_cells=offset,
            omitted_trailing_cells=width * height - offset - len(entries),
            tuple_types=types,
        ),
    )


def _xml_members(source, job):
    if source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source) as z:
            checked_members(z, job.limit)
            members = [
                m
                for m in z.infolist()
                if Path(m.filename).suffix.lower() in {".xml", ".gml"}
            ]
            if not members:
                raise ValueError("No DEM XML/GML found in ZIP")
            for member in members:
                if member.file_size > MAX_XML:
                    raise ValueError("Oversized DEM XML member")
                job.check(member.file_size * 3)
                yield Path(member.filename).stem, z.read(member)
    elif source.suffix.lower() in {".xml", ".gml"}:
        if source.stat().st_size > MAX_XML:
            raise ValueError("Oversized DEM XML")
        job.check(source.stat().st_size * 3)
        yield source.stem, source.read_bytes()
    else:
        raise ValueError("DEM requires FGD XML/GML/ZIP or a referenced GeoTIFF")


def dem_to_cog(source, output_dir, *, reference, job, target_crs=None):
    source, output_dir = Path(source), Path(output_dir)
    items = []
    if source.suffix.lower() in {".tif", ".tiff"}:
        with open_image(source) as ds:
            if (
                ds.crs is None
                or CRS.from_user_input(ds.crs) != CRS.from_user_input(reference.crs)
                or ds.count != 1
            ):
                raise ValueError(
                    "DEM raster CRS/band count differs from reviewed reference"
                )
            if ds.transform.is_identity or abs(ds.transform.determinant) == 0:
                raise ValueError("DEM raster is not georeferenced")
        items.append(
            (
                source,
                dict(mesh=None, declared_horizontal_datum=reference.horizontal_datum),
            )
        )
    else:
        for i, (name, data) in enumerate(_xml_members(source, job)):
            values, transform, metadata = parse_fgd_xml(data, reference)
            job.check(values.nbytes * 4)
            path = local_output(output_dir / "staging" / f"dem_grid_{i}.tif")
            with rasterio.open(
                path,
                "w",
                driver="GTiff",
                width=values.shape[1],
                height=values.shape[0],
                count=1,
                dtype="float32",
                crs=reference.crs,
                transform=transform,
                nodata=NODATA,
            ) as ds:
                ds.write(values, 1)
            items.append((path, dict(xml_member=name, **metadata)))
    results = []
    for i, (native, metadata) in enumerate(items):
        image = native
        commands = []
        if target_crs and CRS.from_user_input(target_crs) != CRS.from_user_input(
            reference.crs
        ):
            # Current EPSG naming alone can conflate JGD2011/2024 heights. Restrict to a reviewed horizontal operation.
            if reference.horizontal_datum != "JGD2011" or CRS.from_user_input(
                target_crs
            ) != CRS.from_epsg(6677):
                raise ValueError("Unverified datum transformation; native output only")
            group = TransformerGroup(
                reference.crs, target_crs, always_xy=False, allow_ballpark=False
            )
            if not group.best_available or not group.transformers:
                raise ValueError(
                    "Required DEM horizontal transformation grid unavailable"
                )
            pipeline = group.transformers[0].definition
            image = local_output(output_dir / "staging" / f"dem_projected_{i}.tif")
            command = [
                "gdalwarp",
                "-s_srs",
                reference.crs,
                "-t_srs",
                target_crs,
                "-ct",
                pipeline,
                "-r",
                "near",
                "-wm",
                "64",
                "-of",
                "GTiff",
                str(native),
                str(image),
            ]
            check_warp_budget(
                native,
                job,
                ["-s_srs", reference.crs, "-t_srs", target_crs, "-ct", pipeline],
            )
            run_gdal(command)
            job.check()
            commands = [command]
            metadata["horizontal_pipeline"] = pipeline
        output = output_dir / f"dem_{i}.tif"
        to_cog(image, output, job=job)
        results.append(
            dict(
                path=output,
                **validate_cog(output),
                kind="dem",
                reference=asdict(reference),
                original_crs=reference.crs,
                processed_crs=target_crs or reference.crs,
                vertical_transformation="none",
                gdal_commands=commands,
                **metadata,
            )
        )
    return results
