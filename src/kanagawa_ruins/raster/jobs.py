"""Explicit future-input jobs. No acquisition or invented real-data results."""

from dataclasses import asdict
import json
from pathlib import Path
from ..catalog.sources import read_sources
from ..catalog.layers import validate_layer_id
from ..qa.hashing import sha256
from ..storage.scratch import scratch_job
from ..imaging.georef import GCP, georeference
from ..terrain import DEMReference, dem_to_cog, terrain_products
from .storage import publish_artifact


def selected_sources(command, args, settings):
    sources = read_sources(settings.data_root)
    if args.source_id:
        selected = [s for s in sources if s.source_id in args.source_id]
        if {s.source_id for s in selected} != set(args.source_id):
            raise ValueError("Unknown source ID")
        return selected
    parts = (
        {"historical_maps", "maps_historical"}
        if command == "georef"
        else {"fgd", "dem", "dem_fgd"}
    )
    return [
        s
        for s in sources
        if any(p in parts for p in Path(s.relative_path).parts)
        and Path(s.relative_path).suffix.lower()
        in {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".zip", ".xml", ".gml"}
    ]


def planned_job(command, args, settings):
    sources = selected_sources(command, args, settings)
    return dict(
        status="PLANNED",
        action="list" if args.list else "dry-run",
        command=command,
        sources=[
            dict(source_id=s.source_id, relative_path=s.relative_path) for s in sources
        ],
        manual_action_required=not bool(sources),
        required_metadata="training and independent validation GCP JSON"
        if command == "georef"
        else "reviewed CRS, horizontal datum, vertical datum, metre unit and evidence JSON",
        writes=False,
    )


def execute_job(command, args, settings):
    settings.check_mount()
    validate_layer_id(args.asset_id or "")
    sources = selected_sources(command, args, settings)
    if len(sources) != 1 or not args.source_id or not args.asset_id:
        raise ValueError(
            "Execution requires one exact --source-id and a unique --asset-id"
        )
    source = sources[0]
    path = source.verify(settings.data_root)
    supplemental = args.gcps if command == "georef" else args.reference
    if (
        supplemental is None
        or not supplemental.is_file()
        or supplemental.stat().st_size > 1_000_000
    ):
        raise ValueError("A small reviewed GCP/reference JSON file is required")
    metadata = json.loads(supplemental.read_text(encoding="utf-8"))
    parameters = dict(
        supplemental_sha256=sha256(supplemental), reviewed_metadata=metadata
    )
    results = []
    with scratch_job(settings.scratch_limit) as job:
        if command == "georef":
            training = [GCP(**p) for p in metadata["training"]]
            validation = [GCP(**p) for p in metadata["validation"]]
            output = job.path / "registered.tif"
            info = georeference(
                path, output, training=training, validation=validation, job=job
            )
            items = [dict(path=output, **info)]
            parameters.update(
                method="affine_order_1",
                pixel_convention="continuous_upper_left_corner_origin",
            )
        else:
            reference = DEMReference(**metadata)
            parameters.update(
                target_crs=args.target_crs,
                terrain=args.terrain,
                resampling="nearest",
                reference=asdict(reference),
            )
            items = dem_to_cog(
                path,
                job.path / "dem_outputs",
                reference=reference,
                job=job,
                target_crs=args.target_crs,
            )
            if args.terrain:
                # Validate terrain prerequisites before any artifact is published.
                for i, item in enumerate(list(items)):
                    items.extend(
                        terrain_products(
                            item["path"],
                            job.path / f"terrain_{i}",
                            reference=reference,
                            job=job,
                        )
                    )
        # Every generated local file has already passed its quality checks.
        for i, item in enumerate(items):
            if (
                sha256(supplemental) != parameters["supplemental_sha256"]
                or json.loads(supplemental.read_text(encoding="utf-8")) != metadata
            ):
                raise ValueError(
                    "Reviewed GCP/reference file changed during processing"
                )
            local = item["path"]
            info = {k: v for k, v in item.items() if k != "path"}
            aid = (
                args.asset_id
                if len(items) == 1
                else f"{args.asset_id}_{i}_{info['kind']}"
            )
            # Publisher requires canonical filename; rename only job-local files.
            final = job.path / (aid + ".tif")
            local.rename(final)
            folder = (
                "historical_maps/georeferenced"
                if command == "georef"
                else f"terrain/{info['kind']}"
            )
            results.append(
                publish_artifact(
                    settings,
                    final,
                    asset_id=aid,
                    relative_output=f"{folder}/{aid}.tif",
                    source=source,
                    parameters=parameters,
                    metadata=info,
                )
            )
    return dict(status="PASS", results=results)
