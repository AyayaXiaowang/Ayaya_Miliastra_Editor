from __future__ import annotations

from typing import Any, Dict, Optional

from ..file_io import _sanitize_filename, _write_json_file
from ..section15_decoders import _try_decode_section15_meta_data
from .context import Section15ExportContext


def export_unit_tag_entry(
    *,
    section15_entry: Dict[str, Any],
    entry_id_int: int,
    type_code_int: int,
    entry_name: str,
    source_path_text: str,
    context: Section15ExportContext,
    result: Dict[str, Any],
) -> None:
    tag_id = f"unit_tag_{entry_id_int}__{context.package_namespace}"
    raw_file_name = f"ugc_unit_tag_{entry_id_int}.pyugc.json"
    raw_file_path = context.unit_tag_raw_directory / raw_file_name
    _write_json_file(raw_file_path, section15_entry)

    decoded_tag = _try_decode_section15_meta_data(section15_entry, 45, "53@data")
    decoded_tag_rel_path: Optional[str] = None
    if decoded_tag is not None:
        decoded_file_path = context.unit_tag_raw_directory / f"ugc_unit_tag_{entry_id_int}.decoded.json"
        _write_json_file(decoded_file_path, decoded_tag)
        decoded_tag_rel_path = str(decoded_file_path.relative_to(context.output_package_root)).replace("\\", "/")

    unit_tag_object: Dict[str, Any] = {
        "tag_id": tag_id,
        "tag_name": entry_name,
        "tag_category": "combat",
        "color": "",
        "icon": "",
        "description": "",
        "metadata": {
            "ugc": {
                "source_entry_id_int": entry_id_int,
                "source_type_code": type_code_int,
                "source_pyugc_path": source_path_text,
                "raw_pyugc_entry": str(raw_file_path.relative_to(context.output_package_root)).replace("\\", "/"),
                "decoded": decoded_tag_rel_path,
            }
        },
        "updated_at": "",
        "name": entry_name,
    }
    output_file_name = _sanitize_filename(f"{entry_name}_{entry_id_int}") + ".json"
    output_path = context.unit_tag_directory / output_file_name
    _write_json_file(output_path, unit_tag_object)
    result["unit_tags"].append(
        {
            "tag_id": tag_id,
            "tag_name": entry_name,
            "output": str(output_path.relative_to(context.output_package_root)).replace("\\", "/"),
        }
    )


