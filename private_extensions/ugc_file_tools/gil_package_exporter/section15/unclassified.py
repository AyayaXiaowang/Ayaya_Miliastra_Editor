from __future__ import annotations

from typing import Any, Dict

from ..file_io import _write_json_file
from .context import Section15ExportContext


def export_unclassified_entry(
    *,
    section15_entry: Dict[str, Any],
    entry_id_int: int,
    type_code_int: int,
    entry_name: str,
    source_path_text: str,
    context: Section15ExportContext,
    result: Dict[str, Any],
) -> None:
    raw_file_name = f"ugc_section15_type{type_code_int}_{entry_id_int}.pyugc.json"
    raw_file_path = context.unclassified_directory / raw_file_name
    _write_json_file(raw_file_path, section15_entry)
    result["unclassified"].append(
        {
            "entry_id_int": entry_id_int,
            "type_code": type_code_int,
            "name": entry_name,
            "source_pyugc_path": source_path_text,
            "raw_pyugc_entry": str(raw_file_path.relative_to(context.output_package_root)).replace("\\", "/"),
        }
    )


