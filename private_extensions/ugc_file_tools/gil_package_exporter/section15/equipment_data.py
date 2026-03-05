from __future__ import annotations

from typing import Any, Dict, Optional

from ..file_io import _sanitize_filename, _write_json_file
from ..section15_decoders import _try_decode_section15_meta_data
from .context import Section15ExportContext
from .decoded_values import (
    _try_extract_int,
    _try_extract_message,
    _try_extract_utf8,
    _try_trim_to_first_chinese,
)


def _extract_equipment_semantics_from_decoded(decoded_wrapper: Dict[str, Any]) -> Dict[str, Any]:
    """从 type_code=16（装备数据）解码结果中抽取可稳定语义化的信息。"""
    result: Dict[str, Any] = {}
    decoded_root = decoded_wrapper.get("decoded")
    if not isinstance(decoded_root, dict):
        return result

    # 兼容 decode_gil “文本优先”策略：某些样本会将整段 payload 直接当作 utf8 返回
    field_1_text_node = decoded_root.get("field_1")
    if isinstance(field_1_text_node, dict):
        text_value = _try_extract_utf8(field_1_text_node)
        if isinstance(text_value, str) and text_value.strip() != "":
            result["description"] = _try_trim_to_first_chinese(text_value)

    root_message = _try_extract_message(decoded_root.get("field_1"))
    if root_message is None:
        return result

    # attribute_type_id：常见为 root.field_1.message.field_1.message.field_51.message.field_1.int
    field_1_msg = _try_extract_message(root_message.get("field_1"))
    if field_1_msg is not None:
        field_51_msg = _try_extract_message(field_1_msg.get("field_51"))
        if field_51_msg is not None:
            attr_id_int = _try_extract_int(field_51_msg.get("field_1"))
            if isinstance(attr_id_int, int):
                result["attribute_type_id_int"] = int(attr_id_int)

    # description 模板：部分样本把可读文本放在 field_501.message.field_501.utf8
    field_501_msg = _try_extract_message(root_message.get("field_501"))
    if field_501_msg is not None:
        text_msg = _try_extract_message(field_501_msg.get("field_501"))
        if text_msg is not None:
            description_text = _try_extract_utf8(text_msg)
            if isinstance(description_text, str) and description_text.strip() != "":
                result["description"] = description_text

    return result


def export_equipment_data_entry(
    *,
    section15_entry: Dict[str, Any],
    entry_id_int: int,
    type_code_int: int,
    entry_name: str,
    source_path_text: str,
    context: Section15ExportContext,
    result: Dict[str, Any],
) -> None:
    equipment_id = str(entry_id_int)
    raw_file_name = f"ugc_equipment_{entry_id_int}.pyugc.json"
    raw_file_path = context.equipment_data_raw_directory / raw_file_name
    _write_json_file(raw_file_path, section15_entry)

    decoded_equipment = _try_decode_section15_meta_data(section15_entry, 43, "51@data")
    decoded_equipment_rel_path: Optional[str] = None
    equipment_semantics: Dict[str, Any] = {}
    if decoded_equipment is not None:
        decoded_file_path = context.equipment_data_raw_directory / f"ugc_equipment_{entry_id_int}.decoded.json"
        _write_json_file(decoded_file_path, decoded_equipment)
        decoded_equipment_rel_path = str(decoded_file_path.relative_to(context.output_package_root)).replace("\\", "/")
        equipment_semantics = _extract_equipment_semantics_from_decoded(decoded_equipment)

    equipment_description = equipment_semantics.get("description") if isinstance(equipment_semantics.get("description"), str) else ""
    equipment_attribute_type_id_int = (
        equipment_semantics.get("attribute_type_id_int") if isinstance(equipment_semantics.get("attribute_type_id_int"), int) else None
    )

    equipment_object: Dict[str, Any] = {
        "equipment_id": equipment_id,
        "equipment_name": entry_name,
        "equipment_slot": "",
        "base_attributes": {},
        "special_effects": [],
        "rarity": "common",
        "level_requirement": 1,
        "icon": "",
        "model": "",
        "description": equipment_description,
        "metadata": {
            "ugc": {
                "source_entry_id_int": entry_id_int,
                "source_type_code": type_code_int,
                "source_pyugc_path": source_path_text,
                "raw_pyugc_entry": str(raw_file_path.relative_to(context.output_package_root)).replace("\\", "/"),
                "decoded": decoded_equipment_rel_path,
                "attribute_type_id_int": equipment_attribute_type_id_int,
            }
        },
        "updated_at": "",
        "name": entry_name,
    }
    output_file_name = _sanitize_filename(entry_name) + ".json"
    output_path = context.equipment_data_directory / output_file_name
    _write_json_file(output_path, equipment_object)
    result["equipment_data"].append(
        {
            "equipment_id": equipment_id,
            "equipment_name": entry_name,
            "output": str(output_path.relative_to(context.output_package_root)).replace("\\", "/"),
        }
    )


