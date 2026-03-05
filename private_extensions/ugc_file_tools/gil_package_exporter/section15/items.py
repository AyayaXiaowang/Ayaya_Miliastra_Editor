from __future__ import annotations

from typing import Any, Dict, Optional

from ..file_io import _sanitize_filename, _write_json_file
from ..section15_decoders import _try_decode_section15_meta_data
from .context import Section15ExportContext


def export_item_entry(
    *,
    section15_entry: Dict[str, Any],
    entry_id_int: int,
    type_code_int: int,
    entry_name: str,
    source_path_text: str,
    context: Section15ExportContext,
    result: Dict[str, Any],
) -> None:
    item_id = f"item_{entry_id_int}"
    raw_file_name = f"ugc_item_{entry_id_int}.pyugc.json"
    raw_file_path = context.item_raw_directory / raw_file_name
    _write_json_file(raw_file_path, section15_entry)

    decoded_item_data = _try_decode_section15_meta_data(section15_entry, 39, "49@data")
    decoded_item_rel_path: Optional[str] = None
    if decoded_item_data is not None:
        decoded_file_path = context.item_raw_directory / f"ugc_item_{entry_id_int}.decoded.json"
        _write_json_file(decoded_file_path, decoded_item_data)
        decoded_item_rel_path = str(decoded_file_path.relative_to(context.output_package_root)).replace("\\", "/")

    item_type_text = "equipment" if type_code_int == 10 else "consumable"
    max_stack_int = 1 if item_type_text == "equipment" else 99

    item_min_level: Optional[int] = None
    item_internal_config_id_int: Optional[int] = None
    item_class_code_int: Optional[int] = None
    if isinstance(decoded_item_data, dict):
        decoded_root = decoded_item_data.get("decoded")
        if isinstance(decoded_root, dict):
            field_1 = decoded_root.get("field_1")
            if isinstance(field_1, dict):
                message_root = field_1.get("message")
                if isinstance(message_root, dict):
                    field_1_message_container = message_root.get("field_1")
                    if isinstance(field_1_message_container, dict):
                        nested_message = field_1_message_container.get("message")
                        if isinstance(nested_message, dict):
                            class_code_field = nested_message.get("field_5")
                            if isinstance(class_code_field, dict) and isinstance(class_code_field.get("int"), int):
                                item_class_code_int = int(class_code_field.get("int"))
                    field_4 = message_root.get("field_4")
                    if isinstance(field_4, dict) and isinstance(field_4.get("int"), int):
                        item_internal_config_id_int = int(field_4.get("int"))
                    field_11 = message_root.get("field_11")
                    if isinstance(field_11, dict):
                        message_11 = field_11.get("message")
                        if isinstance(message_11, dict):
                            level_field = message_11.get("field_1")
                            if isinstance(level_field, dict) and isinstance(level_field.get("int"), int):
                                item_min_level = int(level_field.get("int"))

    requirements_object: Dict[str, Any] = {}
    if isinstance(item_min_level, int):
        requirements_object["min_level"] = int(item_min_level)

    rarity_text = "common"
    if item_class_code_int == 4303:
        rarity_text = "epic"

    attributes_object: Dict[str, Any] = {}
    if isinstance(item_internal_config_id_int, int):
        attributes_object["ugc_internal_config_id_int"] = int(item_internal_config_id_int)
    if isinstance(item_class_code_int, int):
        attributes_object["ugc_class_code_int"] = int(item_class_code_int)

    item_object: Dict[str, Any] = {
        "id": item_id,
        "item_id": item_id,
        "item_name": entry_name,
        "name": entry_name,
        "description": "",
        "item_type": item_type_text,
        "rarity": rarity_text,
        "max_stack": max_stack_int,
        "icon": "",
        "use_effect": "",
        "cooldown": 0.0,
        "attributes": attributes_object,
        "requirements": requirements_object,
        "config_id": str(entry_id_int),
        "metadata": {
            **({"equipment_id": str(entry_id_int)} if item_type_text == "equipment" else {}),
            "ugc": {
                "source_entry_id_int": entry_id_int,
                "source_type_code": type_code_int,
                "source_pyugc_path": source_path_text,
                "raw_pyugc_entry": str(raw_file_path.relative_to(context.output_package_root)).replace("\\", "/"),
                "decoded": decoded_item_rel_path,
                "decoded_internal_config_id_int": item_internal_config_id_int,
                "decoded_class_code_int": item_class_code_int,
                "decoded_min_level": item_min_level,
            },
        },
        "updated_at": "",
        "last_modified": "",
    }
    output_file_name = _sanitize_filename(entry_name) + ".json"
    output_path = context.item_directory / output_file_name
    _write_json_file(output_path, item_object)
    result["items"].append(
        {
            "item_id": item_id,
            "item_name": entry_name,
            "output": str(output_path.relative_to(context.output_package_root)).replace("\\", "/"),
        }
    )


