from __future__ import annotations

from typing import Any, Dict, List

from ..file_io import _sanitize_filename, _write_json_file
from .context import Section15ExportContext


def export_growth_curve_entry(
    *,
    section15_entry: Dict[str, Any],
    entry_id_int: int,
    type_code_int: int,
    entry_name: str,
    source_path_text: str,
    context: Section15ExportContext,
    result: Dict[str, Any],
) -> None:
    growth_curve_id = f"growth_curve_{entry_id_int}__{context.package_namespace}"
    raw_file_name = f"ugc_growth_curve_{entry_id_int}.pyugc.json"
    raw_file_path = context.growth_curve_raw_directory / raw_file_name
    _write_json_file(raw_file_path, section15_entry)

    points: List[Dict[str, Any]] = []
    meta_list = section15_entry.get("4")
    if isinstance(meta_list, list):
        for meta_item in meta_list:
            if not isinstance(meta_item, dict):
                continue
            if meta_item.get("1 id@int") != 12:
                continue
            container = meta_item.get("20")
            if not isinstance(container, dict):
                continue
            records = container.get("1")
            if not isinstance(records, list):
                continue
            for record in records:
                if not isinstance(record, dict):
                    continue
                level_value = record.get("1@int")
                if not isinstance(level_value, int):
                    continue
                point: Dict[str, Any] = {"level": int(level_value)}
                if isinstance(record.get("2@float"), float):
                    point["health_multiplier"] = float(record.get("2@float"))
                if isinstance(record.get("3@float"), float):
                    point["attack_multiplier"] = float(record.get("3@float"))
                if isinstance(record.get("4@float"), float):
                    point["defense_multiplier"] = float(record.get("4@float"))
                points.append(point)

    growth_curve_object: Dict[str, Any] = {
        "curve_id": growth_curve_id,
        "curve_name": entry_name,
        "name": entry_name,
        "points": points,
        "metadata": {
            "ugc": {
                "source_entry_id_int": entry_id_int,
                "source_type_code": type_code_int,
                "source_pyugc_path": source_path_text,
                "raw_pyugc_entry": str(raw_file_path.relative_to(context.output_package_root)).replace("\\", "/"),
            }
        },
        "updated_at": "",
    }
    output_file_name = _sanitize_filename(f"{entry_name}_{entry_id_int}") + ".json"
    output_path = context.growth_curve_directory / output_file_name
    _write_json_file(output_path, growth_curve_object)
    result["growth_curves"].append(
        {
            "curve_id": growth_curve_id,
            "curve_name": entry_name,
            "output": str(output_path.relative_to(context.output_package_root)).replace("\\", "/"),
        }
    )


