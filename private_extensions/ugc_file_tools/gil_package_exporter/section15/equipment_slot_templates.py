from __future__ import annotations

from typing import Any, Dict, Optional

from ..file_io import _sanitize_filename, _write_json_file
from ..section15_decoders import _try_decode_section15_meta_data
from .context import Section15ExportContext


def export_equipment_slot_template_entry(
    *,
    section15_entry: Dict[str, Any],
    entry_id_int: int,
    type_code_int: int,
    entry_name: str,
    source_path_text: str,
    context: Section15ExportContext,
    result: Dict[str, Any],
) -> None:
    template_id = f"equipment_slot_template_{entry_id_int}__{context.package_namespace}"
    raw_file_name = f"ugc_equipment_slot_template_{entry_id_int}.pyugc.json"
    raw_file_path = context.equipment_slot_template_raw_directory / raw_file_name
    _write_json_file(raw_file_path, section15_entry)

    decoded_template = _try_decode_section15_meta_data(section15_entry, 46, "56@data")
    decoded_rel_path: Optional[str] = None
    if decoded_template is not None:
        decoded_file_path = context.equipment_slot_template_raw_directory / f"ugc_equipment_slot_template_{entry_id_int}.decoded.json"
        _write_json_file(decoded_file_path, decoded_template)
        decoded_rel_path = str(decoded_file_path.relative_to(context.output_package_root)).replace("\\", "/")

    slot_template_object: Dict[str, Any] = {
        "template_id": template_id,
        "template_name": entry_name,
        "name": entry_name,
        "slots": [],
        "metadata": {
            "ugc": {
                "source_entry_id_int": entry_id_int,
                "source_type_code": type_code_int,
                "source_pyugc_path": source_path_text,
                "raw_pyugc_entry": str(raw_file_path.relative_to(context.output_package_root)).replace("\\", "/"),
                "decoded": decoded_rel_path,
            }
        },
        "updated_at": "",
    }
    output_file_name = _sanitize_filename(f"{entry_name}_{entry_id_int}") + ".json"
    output_path = context.equipment_slot_template_directory / output_file_name
    _write_json_file(output_path, slot_template_object)
    result["equipment_slot_templates"].append(
        {
            "template_id": template_id,
            "template_name": entry_name,
            "output": str(output_path.relative_to(context.output_package_root)).replace("\\", "/"),
        }
    )


