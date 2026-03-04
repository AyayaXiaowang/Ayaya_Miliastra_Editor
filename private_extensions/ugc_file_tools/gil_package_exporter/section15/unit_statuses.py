from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional

from ugc_file_tools.decode_gil import decode_bytes_to_python

from ..file_io import _sanitize_filename, _write_json_file
from ..object_scanners import _collect_data_blobs
from .context import Section15ExportContext


def export_unit_status_entry(
    *,
    section15_entry: Dict[str, Any],
    entry_id_int: int,
    type_code_int: int,
    entry_name: str,
    source_path_text: str,
    context: Section15ExportContext,
    result: Dict[str, Any],
) -> None:
    status_id = f"unit_status_{entry_id_int}__{context.package_namespace}"
    raw_file_name = f"ugc_unit_status_{entry_id_int}.pyugc.json"
    raw_file_path = context.unit_status_raw_directory / raw_file_name
    _write_json_file(raw_file_path, section15_entry)

    decoded_status_rel_path: Optional[str] = None
    decoded_status_blobs: List[Dict[str, Any]] = []
    for json_path, key_name, base64_text in _collect_data_blobs(section15_entry):
        decoded_bytes = base64.b64decode(base64_text)
        decoded_status_blobs.append(
            {
                "json_path": json_path,
                "key": key_name,
                "base64": base64_text,
                "byte_size": len(decoded_bytes),
                "decoded": decode_bytes_to_python(decoded_bytes),
            }
        )
    if decoded_status_blobs:
        decoded_file_path = context.unit_status_raw_directory / f"ugc_unit_status_{entry_id_int}.decoded.json"
        _write_json_file(decoded_file_path, decoded_status_blobs)
        decoded_status_rel_path = str(decoded_file_path.relative_to(context.output_package_root)).replace("\\", "/")

    unit_status_object: Dict[str, Any] = {
        "id": status_id,
        "status_id": status_id,
        "status_name": entry_name,
        "name": entry_name,
        "description": "",
        "duration": 0.0,
        "is_stackable": False,
        "max_stacks": 1,
        "effect_type": "buff",
        "effect_values": {},
        "icon": "",
        "metadata": {
            "ugc": {
                "source_entry_id_int": entry_id_int,
                "source_type_code": type_code_int,
                "source_pyugc_path": source_path_text,
                "raw_pyugc_entry": str(raw_file_path.relative_to(context.output_package_root)).replace("\\", "/"),
                "decoded": decoded_status_rel_path,
            }
        },
        "updated_at": "",
        "last_modified": "",
    }
    output_file_name = _sanitize_filename(f"{entry_name}_{entry_id_int}") + ".json"
    output_path = context.unit_status_directory / output_file_name
    _write_json_file(output_path, unit_status_object)
    result["unit_statuses"].append(
        {
            "status_id": status_id,
            "status_name": entry_name,
            "output": str(output_path.relative_to(context.output_package_root)).replace("\\", "/"),
        }
    )


