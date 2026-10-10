"""Streaming XML/PBF ingestion. Relations are counted and explicitly unsupported."""

from collections import defaultdict
import hashlib
import json
import sqlite3
import geopandas as gpd
import osmium
from shapely.geometry import Point, LineString, Polygon, box

DOMAINS = ("roads", "waterways", "worship", "historic", "landuse")
TAGS = (
    "name",
    "amenity",
    "religion",
    "denomination",
    "historic",
    "highway",
    "waterway",
    "landuse",
    "area",
)


def domains(tags):
    out = []
    for tag, domain in [
        ("highway", "roads"),
        ("waterway", "waterways"),
        ("historic", "historic"),
        ("landuse", "landuse"),
    ]:
        if tag in tags:
            out.append(domain)
    if tags.get("amenity") == "place_of_worship":
        out.append("worship")
    return out


def osm_chunks(path, job, stats, bbox=None, batch_size=5000):
    buffers = defaultdict(list)
    clip = box(*bbox) if bbox else None
    seen = sqlite3.connect(job.path / "osm-seen.sqlite")
    seen.execute(
        "CREATE TABLE seen (type TEXT, id BIGINT, digest TEXT, PRIMARY KEY(type,id))"
    )
    fp = osmium.FileProcessor(str(path)).with_locations(
        "sparse_file_array," + str(job.path / "node-locations.idx")
    )
    fp = fp.with_filter(
        osmium.filter.KeyFilter("highway", "waterway", "historic", "landuse", "amenity")
    )
    stats.update(
        dict(
            count_scope="Objects passing native key prefilter; complete-file object totals are not measured",
            key_filtered_nodes=0,
            key_filtered_ways=0,
            key_filtered_relations=0,
            selected_objects=0,
            unsupported_relations=0,
            missing_way_refs=0,
            outside_bbox=0,
            duplicates_removed=0,
            emitted_objects=0,
            emitted_domain_counts={},
        )
    )
    try:
        for obj in fp:
            kind = "node" if obj.is_node() else "way" if obj.is_way() else "relation"
            stats[
                "key_filtered_"
                + {"node": "nodes", "way": "ways", "relation": "relations"}[kind]
            ] += 1
            if (
                sum(
                    stats[k]
                    for k in (
                        "key_filtered_nodes",
                        "key_filtered_ways",
                        "key_filtered_relations",
                    )
                )
                % 100000
                == 0
            ):
                job.check()
            tags = dict(obj.tags)
            selected = domains(tags)
            if not selected:
                continue
            stats["selected_objects"] += 1
            if kind == "relation":
                stats["unsupported_relations"] += 1
                continue
            if kind == "node":
                if not obj.location.valid():
                    raise ValueError(f"Invalid OSM node location: {obj.id}")
                geom = Point(obj.location.lon, obj.location.lat)
            else:
                if len(obj.nodes) < 2 or any(not n.location.valid() for n in obj.nodes):
                    stats["missing_way_refs"] += 1
                    continue
                xy = [(n.location.lon, n.location.lat) for n in obj.nodes]
                # Closed highways stay lines; only explicit area semantics become polygons.
                polygon = tags.get("area") == "yes" or (
                    "landuse" in tags and tags.get("area") != "no"
                )
                geom = (
                    Polygon(xy)
                    if polygon and len(xy) >= 4 and xy[0] == xy[-1]
                    else LineString(xy)
                )
            if clip is not None and not geom.intersects(clip):
                stats["outside_bbox"] += 1
                continue
            row = dict(
                osm_type=kind,
                osm_id=obj.id,
                osm_version=obj.version,
                tags_json=json.dumps(tags, ensure_ascii=False, sort_keys=True),
                geometry=geom,
                **{t: tags.get(t) for t in TAGS},
            )
            digest = hashlib.sha256(
                (row["tags_json"] + geom.wkb_hex).encode()
            ).hexdigest()
            prior = seen.execute(
                "SELECT digest FROM seen WHERE type=? AND id=?", (kind, obj.id)
            ).fetchone()
            if prior:
                if prior[0] != digest:
                    raise ValueError(
                        f"Conflicting repeated OSM object: {kind}/{obj.id}"
                    )
                stats["duplicates_removed"] += 1
                continue
            seen.execute("INSERT INTO seen VALUES (?,?,?)", (kind, obj.id, digest))
            stats["emitted_objects"] += 1
            for domain in selected:
                counts = stats["emitted_domain_counts"]
                counts[domain] = counts.get(domain, 0) + 1
                buffers[domain].append(row)
                if len(buffers[domain]) >= batch_size:
                    yield (
                        domain,
                        gpd.GeoDataFrame(
                            buffers.pop(domain), geometry="geometry", crs="EPSG:4326"
                        ),
                    )
        for domain in sorted(buffers):
            yield (
                domain,
                gpd.GeoDataFrame(buffers[domain], geometry="geometry", crs="EPSG:4326"),
            )
        job.check()
        if stats["selected_objects"] != sum(
            stats[k]
            for k in [
                "unsupported_relations",
                "missing_way_refs",
                "outside_bbox",
                "duplicates_removed",
                "emitted_objects",
            ]
        ):
            raise ValueError("OSM selection accounting mismatch")
    finally:
        seen.close()
