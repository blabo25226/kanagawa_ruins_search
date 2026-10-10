"""Read immutable acquisitions, stage locally, publish verified new derivatives only."""

from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager
import fcntl
import hashlib
import importlib.metadata
import json
import re
import shutil
import tempfile
import uuid
import pyogrio
from .config import Settings, PROCESSING_VERSION
from .catalog.sources import read_sources
from .catalog.layers import validate_layer_id
from .storage.scratch import scratch_job
from .storage.parquet import LayerWriter
from .ingest.kokudo import vector_files, vector_chunks, layer_suffix
from .ingest.admin import normalize_admin
from .ingest.landuse_mesh import normalize_landuse, evidence
from .ingest.osm import osm_chunks
from .qa.hashing import sha256

TSUKUI_BBOX = (
    139.12,
    35.51,
    139.25,
    35.62,
)  # envelope of Phase 0 four-district extraction rectangles, not oaza


def classify(source):
    p = Path(source.relative_path)
    if p.name.startswith("N03-"):
        return "admin"
    if p.name.startswith("codh_") and p.suffix == ".geojson":
        return "admin"
    if p.suffix in {".osm", ".pbf"}:
        return "osm"
    for prefix, domain in [
        ("N02-", "railways"),
        ("W05-", "rivers"),
        ("P32-", "cultural"),
        ("L03-b-", "landuse"),
    ]:
        if p.name.startswith(prefix):
            return domain
    return None


def plan(
    settings,
    layers=("admin", "osm", "railways", "rivers", "cultural", "landuse"),
    area="tsukui",
    include_pbf=False,
):
    if area not in {"tsukui", "all"}:
        raise ValueError("Unknown area")
    allowed = {"admin", "osm", "railways", "rivers", "cultural", "landuse"}
    if not set(layers) <= allowed:
        raise ValueError(f"Unknown layer groups: {set(layers) - allowed}")
    return [
        s
        for s in read_sources(settings.data_root)
        if classify(s) in layers
        and (include_pbf or not s.relative_path.endswith(".pbf"))
    ]


def vintage_for(source, domain):
    name = Path(source.relative_path).name
    if domain == "landuse":
        match = re.fullmatch(r"L03-b-(76|14|21)_(5338|5339).*\.zip", name)
        if not match:
            raise ValueError("Unsupported/unknown landuse vintage or mesh")
        year = {"76": "1976", "14": "2014", "21": "2021"}[match[1]]
        if source.temporal_coverage and source.temporal_coverage != year:
            raise ValueError(
                "Acquisition ledger temporal coverage contradicts landuse filename"
            )
        return year + "_" + match[2]
    if source.temporal_coverage:
        return re.sub("[^0-9a-z]+", "_", source.temporal_coverage.lower()).strip("_")
    return "unknown"


def base_layer_id(source, domain, vintage):
    sid = source.source_id
    if domain == "admin" and sid.startswith("mlit_n03_"):
        return validate_layer_id("admin__n03__" + sid.removeprefix("mlit_n03_"))
    if domain == "landuse":
        return validate_layer_id("landuse__l03b__" + vintage)
    source_name = re.sub("[^a-z0-9_]+", "_", sid.lower())
    return validate_layer_id(f"{domain}__{source_name}__{vintage}")


def implementation_sha256():
    root = Path(__file__).parent
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.suffix in {".py", ".toml", ".sql"}:
            h.update(str(p.relative_to(root)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def versions():
    return {
        p: importlib.metadata.version(p)
        for p in [
            "kanagawa-ruins",
            "geopandas",
            "shapely",
            "pyproj",
            "pyogrio",
            "pyarrow",
            "duckdb",
            "osmium",
        ]
    }


@contextmanager
def publication_lock(settings):
    # Same-host writer exclusion without touching the acquisition ledger or its lock.
    lockroot = Path(tempfile.gettempdir()) / ".kanagawa_ruins_locks"
    lockroot.mkdir(exist_ok=True)
    key = hashlib.sha256(str(settings.output_root).encode()).hexdigest()[:16]
    with (lockroot / f"phase1a_{key}.lock").open("a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def authorized(settings, path):
    settings.check_mount()
    if not path.resolve().is_relative_to(settings.output_root.resolve()):
        raise ValueError("Write target escapes authorized phase1a subtree")
    from .storage.drive import is_rclone_mounted, StorageError

    ok, info = is_rclone_mounted(path)
    if not ok:
        raise StorageError(info)


def publish(settings, local, manifest):
    lid = validate_layer_id(manifest["layer_id"])
    out = settings.output_root / "vectors" / f"{lid}.parquet"
    meta = settings.output_root / "manifests" / f"{lid}.json"
    with publication_lock(settings):
        for p in [out, meta]:
            authorized(settings, p)
        if meta.exists():
            old = json.loads(meta.read_text(encoding="utf-8"))
            if any(
                old.get(k) != manifest.get(k)
                for k in [
                    "source_id",
                    "source_sha256",
                    "parameters",
                    "processing_version",
                    "output_sha256",
                ]
            ):
                raise FileExistsError(
                    f"Layer identity/build conflict: {lid}; use a new processing version/layer namespace"
                )
            if not out.is_file() or sha256(out) != old["output_sha256"]:
                raise ValueError("Existing output is missing or corrupt")
            return dict(
                old,
                status="already_present_reproduced",
                reproduced_by_implementation_sha256=manifest["implementation_sha256"],
            )
        if out.exists():
            raise FileExistsError(
                f"Uncatalogued output exists, preserve for review: {out}"
            )
        for p in [out.parent, meta.parent]:
            authorized(settings, p)
            p.mkdir(parents=True, exist_ok=True)
        partial = out.with_name(out.name + "." + uuid.uuid4().hex + ".partial")
        metatmp = meta.with_name(meta.name + "." + uuid.uuid4().hex + ".partial")
        published = False
        try:
            authorized(settings, partial)
            with local.open("rb") as src, partial.open("xb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
            if sha256(partial) != manifest["output_sha256"]:
                raise OSError("Drive staged SHA-256 mismatch")
            authorized(settings, out)
            partial.rename(out)
            published = True
            if sha256(out) != manifest["output_sha256"]:
                raise OSError("Drive published SHA-256 mismatch")
            manifest = dict(
                manifest, processed_path=str(out.relative_to(settings.data_root))
            )
            with metatmp.open("x", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, sort_keys=True, indent=2)
                f.write("\n")
            if json.loads(metatmp.read_text()) != manifest:
                raise OSError("Manifest readback mismatch")
            authorized(settings, meta)
            metatmp.rename(meta)  # manifest is the commit marker
            return dict(manifest, status="created")
        except Exception:
            if published and not meta.exists():
                authorized(settings, out)
                out.unlink()  # rollback only this invocation's new derived output
            raise
        finally:
            for p in [partial, metatmp]:
                if p.exists():
                    authorized(settings, p)
                    p.unlink()


def ingest_source(source, *, settings=None, area="tsukui"):
    settings = settings or Settings.from_env()
    settings.check_mount()
    domain = classify(source)
    if domain is None:
        raise ValueError("Unsupported source")
    path = source.verify(settings.data_root)
    vintage = vintage_for(source, domain)
    stats = {}
    notes = []
    input_metadata = {}
    writers = {}
    with scratch_job(settings.scratch_limit) as job:

        def emit(suffix, frame):
            if domain == "osm":
                region = "tsukui_" if path.suffix == ".pbf" and area == "tsukui" else ""
                lid = validate_layer_id(
                    f"osm__{suffix}__{vintage}_{region}{source.source_id}"
                )
            else:
                lid = base_layer_id(source, domain, vintage) + (
                    ("_" + suffix) if suffix else ""
                )
            validate_layer_id(lid)
            if (
                domain == "landuse"
                and vintage.startswith("1976")
                and frame.crs.to_epsg() != 4301
            ):
                raise ValueError(
                    "1976 retain-source policy requires explicit Tokyo Datum; review different CRS"
                )
            if lid not in writers:
                writers[lid] = LayerWriter(
                    job.path / f"{lid}.parquet",
                    source,
                    lid,
                    vintage,
                    job,
                    retain_source_crs=domain == "landuse"
                    and vintage.startswith("1976"),
                )
            writers[lid].write(frame)

        try:
            if domain == "osm":
                bbox = (
                    TSUKUI_BBOX if area == "tsukui" and path.suffix == ".pbf" else None
                )
                for suffix, frame in osm_chunks(path, job, stats, bbox=bbox):
                    emit(suffix, frame)
                notes.append(
                    "Relations unsupported; no geometry synthesized. Closed ways become areas only for area=yes or landuse without area=no."
                )
            else:
                if source.source_id.startswith("codh_"):
                    obj = json.loads(path.read_text(encoding="utf-8"))
                    input_metadata = obj.get("metadata", {})
                    notes.append(
                        "Municipal boundary, not an oaza boundary; source GeoJSON CRS convention is recorded by GDAL."
                    )
                    if input_metadata.get("cc:license"):
                        notes.append(
                            "Embedded CODH license: "
                            + input_metadata["cc:license"]
                            + "; acquisition ledger license retained separately."
                        )
                with vector_files(path, job) as files:
                    for file in files:
                        if domain == "landuse":
                            input_metadata["vintage_evidence"] = evidence(
                                file, vintage[:4]
                            )
                            if vintage.startswith("1976"):
                                notes.append(
                                    "Tokyo Datum retained: required tky2jgd.gsb is unavailable; EPSG:6677 transformation blocked, analysis_ready=false."
                                )
                            if vintage[:4] not in source.source_id:
                                notes.append(
                                    "Source ID vintage disagrees with ZIP/internal metadata; output uses verified "
                                    + vintage[:4]
                                )
                        for name, frame in vector_chunks(file):
                            suffix = (
                                layer_suffix(name)
                                if len(files) > 1 or len(pyogrio.list_layers(file)) > 1
                                else ""
                            )
                            stats.setdefault("input_feature_counts", {})[
                                file.name + "/" + name
                            ] = frame.attrs.get("input_feature_count")
                            if domain == "admin":
                                frame = normalize_admin(frame)
                            if domain == "landuse":
                                frame = normalize_landuse(frame, vintage[:4])
                            input_metadata.setdefault("crs_evidence", {})[file.name] = (
                                {"prj_wkt": file.with_suffix(".prj").read_text()}
                                if file.with_suffix(".prj").is_file()
                                else frame.attrs.get("crs_evidence")
                            )
                            # Keep whole file coverage for vectors; area selects OSM PBF extraction only.
                            emit(suffix, frame)
            summaries = {lid: w.close() for lid, w in writers.items()}
            if not summaries:
                raise ValueError(
                    "No supported features emitted; consult source/OSM coverage"
                )
            source.verify(settings.data_root)  # source unchanged before any publication
            results = []
            for lid, w in writers.items():
                summary = summaries[lid]
                manifest = dict(
                    schema_version=1,
                    event="derived",
                    layer_id=lid,
                    source_id=source.source_id,
                    original_path=source.relative_path,
                    source_sha256=source.sha256,
                    temporal_coverage=vintage[:4]
                    if domain == "landuse"
                    else source.temporal_coverage,
                    acquired_at=source.acquired_at,
                    created_at=datetime.now(timezone.utc).isoformat(),
                    license=source.license,
                    source_url=source.source_url,
                    source_page=source.source_page,
                    output_sha256=sha256(w.path),
                    processing_version=PROCESSING_VERSION,
                    implementation_sha256=implementation_sha256(),
                    versions=versions(),
                    parameters=dict(
                        area=area,
                        pbf_bbox=list(TSUKUI_BBOX)
                        if domain == "osm"
                        and path.suffix == ".pbf"
                        and area == "tsukui"
                        else None,
                    ),
                    input_metadata=input_metadata,
                    notes=notes,
                    ingest_statistics=stats,
                    record_count_policy="No geometry repair or vector row exclusion; OSM tag/area selection, missing references and dedup counts are explicit.",
                    scratch_peak_bytes=job.peak_bytes,
                    rclone_vfs_bytes_observed=job.vfs_bytes,
                    **summary,
                )
                results.append(publish(settings, w.path, manifest))
            return results
        finally:
            for w in writers.values():
                w.abort()
