"""Small machine-generated summaries; counts and sizes come only from verified manifests."""

from collections import defaultdict
from ..catalog import list_layers


def summarize_layers(*, settings=None):
    layers = list_layers(settings=settings)
    groups = defaultdict(lambda: dict(layers=0, feature_count=0, bytes=0))
    for m in layers:
        group = m["layer_id"].split("__")[0]
        groups[group]["layers"] += 1
        groups[group]["feature_count"] += m["feature_count"]
        groups[group]["bytes"] += m["bytes"]
    fields = [
        "layer_id",
        "source_id",
        "original_path",
        "processed_path",
        "temporal_coverage",
        "original_crs",
        "processed_crs",
        "analysis_ready",
        "geometry_type",
        "feature_count",
        "bytes",
        "source_sha256",
        "output_sha256",
        "notes",
        "ingest_statistics",
        "input_metadata",
    ]
    return dict(
        layer_count=len(layers),
        source_count=len({m["source_id"] for m in layers}),
        feature_count=sum(m["feature_count"] for m in layers),
        bytes=sum(m["bytes"] for m in layers),
        groups=dict(groups),
        layers=[{k: m.get(k) for k in fields} for m in layers],
    )


def layer_table(summary):
    lines = ["| layer_id | 件数 | bytes | 元CRS | 保存CRS |", "|---|---:|---:|---|---|"]
    for m in summary["layers"]:
        lines.append(
            f"| `{m['layer_id']}` | {m['feature_count']} | {m['bytes']} | {m['original_crs']} | {m['processed_crs']} |"
        )
    return "\n".join(lines) + "\n"
