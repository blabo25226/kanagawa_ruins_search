"""Deterministic chunked GeoParquet 1.1 writing (WKB, explicit PROJJSON)."""

import json
import pyarrow as pa
import pyarrow.parquet as pq
from pyproj import CRS
from ..geo.validate import validate_frame
from ..geo.crs import to_analysis_crs, describe_crs


class LayerWriter:
    def __init__(
        self, path, source, layer_id, vintage, job, *, retain_source_crs=False
    ):
        self.path, self.source, self.layer_id, self.vintage, self.job = (
            path,
            source,
            layer_id,
            vintage,
            job,
        )
        self.retain_source_crs = retain_source_crs
        self.processed_crs = None
        self.writer = None
        self.count = 0
        self.bbox = None
        self.types = set()
        self.original_crs = None
        self.columns = None
        self.source_crs_info = None

    def write(self, frame):
        validate_frame(frame)
        original = frame.crs.to_string()
        if self.original_crs is not None and original != self.original_crs:
            raise ValueError("Mixed source CRS within a layer")
        self.original_crs = original
        self.source_crs_info = describe_crs(frame.crs)
        frame = frame.copy() if self.retain_source_crs else to_analysis_crs(frame)
        self.processed_crs = frame.crs.to_string()
        for col, val in [
            ("source_id", self.source.source_id),
            ("source_vintage", self.vintage),
            ("original_crs", original),
        ]:
            if col in frame:
                raise ValueError(f"Reserved metadata column already in input: {col}")
            frame[col] = val
        qa = validate_frame(frame)
        b = qa["bbox"]
        if b:
            self.bbox = (
                b
                if self.bbox is None
                else [
                    min(self.bbox[0], b[0]),
                    min(self.bbox[1], b[1]),
                    max(self.bbox[2], b[2]),
                    max(self.bbox[3], b[3]),
                ]
            )
        self.types.update(qa["geometry_type"])
        self.count += len(frame)
        self.columns = frame.columns.tolist()
        arrays = {}
        for col in frame.columns:
            if col == frame.geometry.name:
                arrays[col] = pa.array(frame.geometry.to_wkb(), type=pa.binary())
            elif frame[col].dtype.kind in "OUS":
                arrays[col] = pa.array(
                    frame[col].astype("string"), type=pa.string(), from_pandas=True
                )
            else:
                arrays[col] = pa.array(frame[col], from_pandas=True)
        table = pa.table(arrays).replace_schema_metadata(self.metadata())
        self.job.check(table.nbytes + 1_000_000)
        if self.writer is None:
            self.writer = pq.ParquetWriter(
                self.path, table.schema, compression="zstd", version="2.6"
            )
        self.writer.write_table(table, row_group_size=50000)
        self.job.check()

    def metadata(self):
        geo = dict(
            version="1.1.0",
            primary_column="geometry",
            columns={
                "geometry": dict(
                    encoding="WKB",
                    crs=CRS.from_user_input(self.processed_crs).to_json_dict(),
                    geometry_types=sorted(self.types),
                )
            },
        )
        if self.bbox is not None:
            geo["columns"]["geometry"]["bbox"] = self.bbox
        return {
            b"geo": json.dumps(geo, sort_keys=True).encode(),
            b"ruins": json.dumps(
                dict(
                    source_id=self.source.source_id,
                    source_sha256=self.source.sha256,
                    layer_id=self.layer_id,
                ),
                sort_keys=True,
            ).encode(),
        }

    def close(self):
        if self.writer:
            self.writer.add_key_value_metadata(self.metadata())
            self.writer.close()
            self.writer = None
        if not self.path.exists():
            raise ValueError("Empty layer: no file generated")
        return dict(
            original_crs=self.original_crs,
            processed_crs=self.processed_crs,
            analysis_ready=not self.retain_source_crs,
            source_crs_info=self.source_crs_info,
            feature_count=self.count,
            bbox=self.bbox,
            geometry_type=sorted(self.types),
            columns=self.columns,
            bytes=self.path.stat().st_size,
        )

    def abort(self):
        if self.writer:
            self.writer.close()
            self.writer = None
