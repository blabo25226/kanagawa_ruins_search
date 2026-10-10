"""Phase 1-C1 bounded ingestion, immutable publication and independent inventory."""

from collections import Counter
from dataclasses import dataclass
from contextlib import nullcontext
import io
import json
import hashlib
from pathlib import Path
import zipfile
import geopandas as gpd
import shapely
from .catalog.sources import Source, read_sources
from .geo.crs import to_analysis_crs
from .storage.drive import get_verified_data_root, is_rclone_mounted
from .storage.scratch import scratch_job
from .storage.parquet import LayerWriter
from .ingest.fgd import inner_archive, records, KINDS
from .qa.hashing import sha256
from .pipeline import publish, implementation_sha256, versions

VERSION = "phase1c1-0.1.0"


@dataclass(frozen=True)
class TemporalSettings:
    data_root: Path
    scratch_limit: int = 1_000_000_000

    @classmethod
    def from_env(cls):
        return cls(get_verified_data_root())

    @property
    def output_root(self):
        return self.data_root / "processed/phase1c/codex"

    def check_mount(self):
        if self.output_root.resolve() != self.data_root.resolve() / "processed/phase1c/codex":
            raise ValueError("Output escapes Phase1c codex subtree")
        ok, info = is_rclone_mounted(self.output_root)
        if not ok:
            raise OSError(info)


def inventory(settings, plan):
    """Inspect actual ZIP central directories, independently of B.5 claims."""
    registered = {s.relative_path: s for s in read_sources(settings.data_root)}
    items, sources = [], {}
    for r in plan["records"]:
        source = Source(r["source_id"], r["relative_path"], r["sha256"],
                        r["temporal_coverage"], r["acquired_at"], r["license"],
                        r["source_url"], r["source_page"])
        path = source.verify(settings.data_root)
        if path.stat().st_size != r["size_bytes"]:
            raise ValueError("Source size mismatch")
        acquired = registered.get(r["relative_path"])
        if acquired and acquired != source:
            raise ValueError("Ledger identity/metadata differs from the reviewed registration plan")
        sources[source.source_id] = source
        with zipfile.ZipFile(path) as outer:
            for i in outer.infolist():
                if not i.filename.endswith(".zip"):
                    continue
                fields = Path(i.filename).stem.split("-")
                if len(fields) < 5 or fields[3] != "ALL":
                    continue
                if not fields[4].isdigit() or len(fields[4]) != 8 or fields[4][:4] != source.temporal_coverage:
                    raise ValueError("Inner file edition contradicts declared comparison era")
                items.append(dict(source_id=source.source_id, member=i.filename,
                                  code=fields[2], file_date=fields[4],
                                  era=source.temporal_coverage,
                                  inner_bytes=i.file_size, crc=i.CRC,
                                  acquisition_registered=acquired is not None))
    # Same-era/code revisions: choose newest explicit file edition, then stable
    # source ordering. Equal-date duplicates must have identical inner content.
    selected, duplicates = {}, []
    with scratch_job(settings.scratch_limit) as job:
        for item in sorted(items, key=lambda x: (x["file_date"], x["source_id"], x["member"])):
            key = (item["era"], item["code"])
            previous = selected.get(key)
            if previous and previous["file_date"] == item["file_date"]:
                def inner_hash(row):
                    with zipfile.ZipFile(settings.data_root / sources[row["source_id"]].relative_path) as z:
                        with inner_archive(z, row["member"], job):
                            return sha256(job.path / "inner.zip")
                if inner_hash(previous) != inner_hash(item):
                    raise ValueError(f"Conflicting same-date inner archives: {key}")
                duplicates.append(dict(item, disposition="identical_inner_content"))
                continue
            if previous:
                duplicates.append(dict(previous, disposition="older_file_edition_not_selected"))
            selected[key] = item
    return list(selected.values()), duplicates, sources


def ingest_item(settings, item, source, *, publish_output=True, kinds=KINDS, spatial_mask=None,
                job_override=None, on_layer=None):
    """Bounded batches; invalid geometry excluded with explicit audit counts."""
    lid_prefix = f"fgd__{item['era']}_{item['code']}"
    audit = dict(**item, members=[], counts={}, excluded_invalid={},
                 duplicates={}, layers=[], source_sha256=source.sha256)
    if spatial_mask is not None: shapely.prepare(spatial_mask)
    with (nullcontext(job_override) if job_override is not None else scratch_job(settings.scratch_limit)) as job:
        writers, batches, seen = {}, {}, {}
        counts, invalid, duplicates, outside = Counter(), Counter(), Counter(), Counter()
        def emit(kind, rows):
            if not rows:
                return
            for crs in sorted({r["source_epsg"] for r in rows}):
                selected = [dict(r) for r in rows if r["source_epsg"] == crs]
                for r in selected: r.pop("source_epsg")
                frame = gpd.GeoDataFrame(selected, crs=crs)
                if spatial_mask is not None and item["era"] != "2008":
                    keep = shapely.intersects(spatial_mask,to_analysis_crs(frame).geometry.to_numpy())
                    outside[kind] += int((~keep).sum())
                    frame = frame.loc[keep]
                if len(frame): writers[kind].write(frame)
        with zipfile.ZipFile(settings.data_root / source.relative_path) as outer:
            with inner_archive(outer, item["member"], job) as inner:
                audit["xml_names"] = [i.filename for i in inner.infolist() if i.filename.endswith(".xml")]
                for info in inner.infolist():
                    kind = next((k for k in kinds if f"-{k}-" in info.filename), None)
                    if kind is None:
                        continue
                    if info.file_size > 512_000_000:
                        raise ValueError("XML member exceeds 512MB admission ceiling")
                    member_audit = dict(name=info.filename, bytes=info.file_size,
                                        crs={}, orgGILvl={}, devDate={}, orgMDId_missing=0,
                                        orgMDId={}, xml_mesh={}, count=0)
                    audit["members"].append(member_audit)
                    if kind not in writers:
                        lid = lid_prefix + "__" + kind.lower() + "_v1"
                        writers[kind] = LayerWriter(job.path / (kind + ".parquet"), source, lid, item["era"], job,
                                                    retain_source_crs=item["era"] == "2008")
                        batches[kind], seen[kind] = [], {}
                    with inner.open(info) as raw:
                        with io.BufferedReader(raw) as stream:
                            for row in records(stream, audit=member_audit):
                                counts[kind] += 1; member_audit["count"] += 1
                                for field, value in [("crs", row["declared_crs"]), ("orgGILvl", row["orgGILvl"]), ("devDate", row["devDate"]), ("orgMDId",row["orgMDId"]), ("xml_mesh",row["xml_mesh"])]:
                                    value = value or "unknown"
                                    member_audit[field][value] = member_audit[field].get(value, 0) + 1
                                if not row["orgMDId"]: member_audit["orgMDId_missing"] += 1
                                if not row["geometry_valid"] or row["geometry"].is_empty:
                                    invalid[kind] += 1
                                    continue
                                # Scope fid to inner source; do not assume global stability across eras.
                                identity = row["fid"]
                                if not identity: raise ValueError("Missing feature ID")
                                attributes={k:v for k,v in row.items() if k != "geometry"}
                                signature = hashlib.sha256(row["geometry"].wkb + json.dumps(attributes,sort_keys=True,ensure_ascii=False).encode()).digest()
                                if identity in seen[kind]:
                                    if seen[kind][identity] != signature:
                                        raise ValueError("Conflicting duplicate fid within selected partition")
                                    duplicates[kind] += 1
                                    continue
                                seen[kind][identity] = signature
                                row.update(source_xml=info.filename, source_inner_zip=item["member"],
                                           source_code=item["code"], file_edition=item["file_date"],
                                           acquisition_registered=item["acquisition_registered"])
                                batches[kind].append(row)
                                if len(batches[kind]) >= 2000:
                                    emit(kind, batches[kind]); batches[kind].clear()
                for kind, writer in writers.items():
                    emit(kind, batches[kind])
                    if not writer.count:
                        continue
                    metadata = writer.close()
                    if on_layer is not None:
                        on_layer(writer.path, writer.layer_id, metadata, job)
                    if publish_output:
                        manifest = dict(layer_id=writer.layer_id, phase="phase1c1",
                                        source_id=source.source_id, source_sha256=source.sha256,
                                        processing_version=VERSION, parameters=dict(item, converted_kinds=sorted(kinds), spatial_mask="N03_2026_Kanagawa_buffer_20m" if spatial_mask is not None and item["era"] != "2008" else None, retain_source_crs=item["era"] == "2008"),
                                        implementation_sha256=implementation_sha256(),
                                        versions=versions(), output_sha256=sha256(writer.path),
                                        source_page=source.source_page, license=source.license,
                                        acquisition_registered=item["acquisition_registered"],
                                        **metadata)
                        result = publish(settings, writer.path, manifest)
                        audit["layers"].append(result)
        audit.update(counts=dict(counts), excluded_invalid=dict(invalid),
                     duplicates=dict(duplicates), excluded_outside_mask=dict(outside),
                     converted_kinds=sorted(kinds), spatial_mask="N03_2026_Kanagawa_buffer_20m" if spatial_mask is not None and item["era"] != "2008" else None,
                     temporal_comparison_ready=item["era"] != "2008",
                     crs_limitation="JGD2000 earthquake correction grid unavailable; retained EPSG:4612" if item["era"] == "2008" else None,
                     scratch_peak_bytes=job.peak_bytes,
                     vfs_bytes=job.vfs_bytes)
    return audit
