from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from ..py_ugc_converter.ugc_converter import UgcConverter

from .dtype_resource_extractor import (
    _build_resource_file_name,
    _extract_resource_entries,
    _find_graph_like_objects,
    _pick_resource_output_subdir,
)
from .file_io import _ensure_directory, _sanitize_filename, _write_json_file
from .models import DataBlobRecord
from .pyugc_decode import _decode_bytes_with_dtype_root


def _export_decoded_dtype_type3_from_data_blobs(
    *,
    output_package_root: Path,
    dtype_path: Path,
    data_blob_index: List[DataBlobRecord],
    data_blob_min_bytes_for_decode: int,
) -> None:
    dtype_converter = UgcConverter()
    dtype_converter.load_dtype(str(dtype_path))
    dtype_root_type3 = dtype_converter.dtype_model.search_id(dtype_converter.dtype_model.root_node, 3)

    decoded_type3_directory = output_package_root / "原始解析" / "数据块" / "decoded_dtype_type3"
    node_graph_raw_directory = output_package_root / "节点图" / "原始解析"
    resource_entry_directory = output_package_root / "原始解析" / "资源条目"
    _ensure_directory(decoded_type3_directory)
    _ensure_directory(node_graph_raw_directory)
    _ensure_directory(resource_entry_directory)

    decoded_type3_index: List[Dict[str, Any]] = []
    extracted_graph_index: List[Dict[str, Any]] = []
    extracted_resource_index: List[Dict[str, Any]] = []

    if dtype_root_type3 is not None:
        for record in data_blob_index:
            blob_path = output_package_root / "原始解析" / "数据块" / f"{record.file_stem}.bin"
            blob_bytes = blob_path.read_bytes()
            if len(blob_bytes) < data_blob_min_bytes_for_decode:
                continue

            decoded_object, decoded_stats = _decode_bytes_with_dtype_root(
                dtype_converter,
                dtype_root_type3,
                blob_bytes,
            )

            decoded_type3_index.append(
                {
                    "file_stem": record.file_stem,
                    "byte_size": record.byte_size,
                    **decoded_stats,
                }
            )

            is_good_parse = (
                (not decoded_stats["reader_error"])
                and decoded_stats["consumed_ratio"] >= 0.90
                and isinstance(decoded_object, dict)
                and len(decoded_object) > 0
            )
            if not is_good_parse:
                continue

            decoded_output_path = decoded_type3_directory / f"{record.file_stem}.json"
            _write_json_file(decoded_output_path, decoded_object)

            graph_objects = _find_graph_like_objects(decoded_object)
            for graph_object in graph_objects:
                graph_name = graph_object.get("2 name@string") or graph_object.get("3 name@string") or "unnamed"
                graph_name_text = str(graph_name)
                graph_file_name = _sanitize_filename(graph_name_text, max_length=120) + ".json"
                graph_output_path = node_graph_raw_directory / graph_file_name
                _write_json_file(graph_output_path, graph_object)
                extracted_graph_index.append(
                    {
                        "name": graph_name_text,
                        "source_blob": record.file_stem,
                        "output": str(graph_output_path.relative_to(output_package_root)).replace("\\", "/"),
                    }
                )

            resource_entries = _extract_resource_entries(decoded_object)
            for resource_entry in resource_entries:
                output_subdir = _pick_resource_output_subdir(resource_entry)
                file_name = _build_resource_file_name(resource_entry)
                output_path = output_package_root / output_subdir / file_name
                _write_json_file(output_path, resource_entry)
                extracted_resource_index.append(
                    {
                        "name": resource_entry.get("3 name@string") or resource_entry.get("2 name@string"),
                        "output": str(output_path.relative_to(output_package_root)).replace("\\", "/"),
                        "source_blob": record.file_stem,
                    }
                )

    _write_json_file(decoded_type3_directory / "index.json", decoded_type3_index)
    _write_json_file(node_graph_raw_directory / "graphs_index.json", extracted_graph_index)
    _write_json_file(resource_entry_directory / "resource_index.json", extracted_resource_index)


