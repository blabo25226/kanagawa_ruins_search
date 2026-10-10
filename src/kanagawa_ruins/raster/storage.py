"""Publish a complete immutable artifact/manifest pair; raw and Phase 1-A stay protected."""

from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import shutil
import uuid
from ..catalog.layers import validate_layer_id
from ..catalog.sources import read_sources
from ..config import contained_path
from ..pipeline import publication_lock, authorized, implementation_sha256
from ..qa.hashing import sha256
from .config import VERSION


def raster_versions():
    import rasterio
    from osgeo import gdal

    return dict(
        **{
            p: importlib.metadata.version(p)
            for p in ["kanagawa-ruins", "rasterio", "numpy", "pyproj"]
        },
        rasterio_gdal=rasterio.__gdal_version__,
        gdal_cli=gdal.VersionInfo("RELEASE_NAME"),
    )


def publish_artifact(
    settings, local, *, asset_id, relative_output, source, parameters, metadata
):
    settings.check_mount()
    acquired = {s.source_id: s for s in read_sources(settings.data_root)}.get(
        source.source_id
    )
    if acquired != source:
        raise ValueError("Input Source must match the immutable acquisition ledger")
    asset_id = validate_layer_id(asset_id)
    if Path(relative_output).suffix not in {".tif", ".json"}:
        raise ValueError("Phase1b artifacts must be COG TIFF or normalized JSON")
    out = contained_path(settings.output_root, relative_output)
    if out.stem != asset_id:
        raise ValueError("Artifact filename must match its unique asset ID")
    meta = settings.output_root / "manifests" / f"{asset_id}.json"
    if out == meta or out.is_relative_to(settings.output_root / "manifests"):
        raise ValueError("Artifact cannot occupy the manifest namespace")
    source_path = source.verify(settings.data_root)
    reserved = {
        "event",
        "phase",
        "asset_id",
        "source_id",
        "original_path",
        "source_sha256",
        "processed_path",
        "output_sha256",
        "bytes",
        "processing_version",
        "implementation_sha256",
        "created_at",
        "versions",
        "source_url",
        "source_page",
        "license",
        "acquired_at",
        "temporal_coverage",
        "parameters",
    }
    if reserved.intersection(metadata):
        raise ValueError("Metadata cannot replace provenance/identity fields")
    manifest = dict(
        event="derived",
        phase="phase1b",
        asset_id=asset_id,
        source_id=source.source_id,
        original_path=source.relative_path,
        source_sha256=source.sha256,
        processed_path=str(out.relative_to(settings.data_root)),
        output_sha256=sha256(Path(local)),
        bytes=Path(local).stat().st_size,
        processing_version=VERSION,
        implementation_sha256=implementation_sha256(),
        created_at=datetime.now(timezone.utc).isoformat(),
        versions=raster_versions(),
        source_url=source.source_url,
        source_page=source.source_page,
        license=source.license,
        acquired_at=source.acquired_at,
        temporal_coverage=source.temporal_coverage,
        parameters=parameters,
        **metadata,
    )
    # Normalize tuple/list and NumPy scalar surprises before comparison and serialization.
    manifest = json.loads(json.dumps(manifest, ensure_ascii=False, allow_nan=False))
    with publication_lock(settings):
        for p in [out, meta]:
            authorized(settings, p)
        if meta.exists():
            old = json.loads(meta.read_text(encoding="utf-8"))
            keys = [
                "phase",
                "event",
                "asset_id",
                "source_id",
                "original_path",
                "source_sha256",
                "processed_path",
                "parameters",
                "processing_version",
                "output_sha256",
            ]
            if any(old.get(k) != manifest.get(k) for k in keys):
                raise FileExistsError(
                    "Artifact/build conflict; use a new asset ID/version"
                )
            if not out.is_file() or sha256(out) != old["output_sha256"]:
                raise ValueError("Existing artifact is missing/corrupt")
            return dict(old, status="already_present_reproduced")
        if out.exists():
            raise FileExistsError("Unregistered output exists; preserve for review")
        for d in [out.parent, meta.parent]:
            authorized(settings, d)
            d.mkdir(parents=True, exist_ok=True)
        partial = out.with_name(out.name + "." + uuid.uuid4().hex + ".partial")
        metatmp = meta.with_name(meta.name + "." + uuid.uuid4().hex + ".partial")
        published = False
        try:
            authorized(settings, partial)
            with Path(local).open("rb") as src, partial.open("xb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
            if sha256(partial) != manifest["output_sha256"]:
                raise OSError("Staged artifact hash mismatch")
            if sha256(source_path) != source.sha256:
                raise ValueError("Input changed during processing")
            authorized(settings, out)
            partial.rename(out)
            published = True
            if sha256(out) != manifest["output_sha256"]:
                raise OSError("Published artifact hash mismatch")
            with metatmp.open("x", encoding="utf-8") as f:
                json.dump(
                    manifest,
                    f,
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                    allow_nan=False,
                )
                f.write("\n")
            if json.loads(metatmp.read_text()) != manifest:
                raise OSError("Manifest readback mismatch")
            authorized(settings, meta)
            metatmp.rename(meta)
            return dict(manifest, status="created")
        except BaseException:
            if published and not meta.exists():
                authorized(settings, out)
                out.unlink()
            raise
        finally:
            for p in [partial, metatmp]:
                if p.exists():
                    authorized(settings, p)
                    p.unlink()


def list_artifacts(settings):
    settings.check_mount()
    result = []
    for path in sorted((settings.output_root / "manifests").glob("*.json")):
        m = json.loads(path.read_text(encoding="utf-8"))
        if (
            path.stem != validate_layer_id(m["asset_id"])
            or m.get("phase") != "phase1b"
            or m.get("event") != "derived"
        ):
            raise ValueError("Invalid Phase1b manifest identity")
        output = contained_path(settings.data_root, m["processed_path"])
        if not output.is_relative_to(
            settings.output_root.resolve()
        ) or output.is_relative_to((settings.output_root / "manifests").resolve()):
            raise ValueError("Manifest output escapes artifact namespace")
        if output.stem != m["asset_id"] or output.suffix not in {".tif", ".json"}:
            raise ValueError("Invalid artifact filename/format")
        result.append(m)
    return result
