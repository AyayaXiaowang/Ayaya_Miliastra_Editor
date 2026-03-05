from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from ugc_file_tools.decode_gil import decode_bytes_to_python

from .file_io import _ensure_directory, _sanitize_filename, _write_json_file
from .generic_decode import _decode_base64_to_max_int


def _try_decode_base64_to_bytes(base64_text: str) -> bytes:
    if base64_text == "":
        return b""
    return base64.b64decode(base64_text)


def _decode_base64_to_utf8_text(base64_text: str) -> str:
    raw_bytes = _try_decode_base64_to_bytes(base64_text)
    if raw_bytes == b"":
        return ""
    return raw_bytes.decode("utf-8", errors="replace")


def _try_decode_struct_id_from_type_data(base64_text: str) -> Optional[int]:
    """
    结构体自定义变量的 type data 常见形态（base64 解码后）：
    - field_1.int == 1
    - field_2.int == <struct_id_int>
    """
    raw_bytes = _try_decode_base64_to_bytes(base64_text)
    if raw_bytes == b"":
        return None
    decoded_object = decode_bytes_to_python(raw_bytes)
    if not isinstance(decoded_object, Mapping):
        return None
    field_2 = decoded_object.get("field_2")
    if not isinstance(field_2, Mapping):
        return None
    struct_id_int = field_2.get("int")
    if not isinstance(struct_id_int, int):
        return None
    return int(struct_id_int)


def _read_varint_at_offset(data_bytes: bytes, start_offset: int) -> Tuple[int, int, bool]:
    value = 0
    shift_bits = 0
    current_offset = start_offset
    end_offset = len(data_bytes)
    while current_offset < end_offset and shift_bits < 64:
        current_byte = data_bytes[current_offset]
        current_offset += 1
        value |= (current_byte & 0x7F) << shift_bits
        if (current_byte & 0x80) == 0:
            return value, current_offset, True
        shift_bits += 7
    return 0, current_offset, False


def _scan_varints_in_range(data_bytes: bytes, min_value: int, max_value: int) -> List[int]:
    """
    在原始 bytes 中做“滑窗 varint 扫描”，用于从难以稳定结构化解析的 blob 中提取引用 id。
    """
    hits: List[int] = []
    seen: set[int] = set()
    for start_offset in range(len(data_bytes)):
        value, _next_offset, ok = _read_varint_at_offset(data_bytes, start_offset)
        if not ok:
            continue
        if value < min_value or value > max_value:
            continue
        if value in seen:
            continue
        seen.add(int(value))
        hits.append(int(value))
    return sorted(hits)


def _try_extract_struct_ref_id_from_value_blob_base64(value_blob_base64: str) -> Optional[int]:
    """
    结构体引用值常见形态（base64 解码后 decode_gil）：
    - field_501.int == <struct_id_int>
    - field_502.message.field_4.int == <ugc_ref_id_int>
    """
    raw_bytes = _try_decode_base64_to_bytes(value_blob_base64)
    if raw_bytes == b"":
        return None
    decoded_object = decode_bytes_to_python(raw_bytes)
    if isinstance(decoded_object, Mapping):
        field_502 = decoded_object.get("field_502")
        if isinstance(field_502, Mapping):
            nested_message = field_502.get("message")
            if isinstance(nested_message, Mapping):
                field_4 = nested_message.get("field_4")
                if isinstance(field_4, Mapping) and isinstance(field_4.get("int"), int):
                    return int(field_4["int"])

    # 兜底：部分 blob 会被 decode_gil 的“文本优先”策略折叠为 raw_hex/utf8，无法可靠取到结构化字段；
    # 这里直接扫描 varint，提取 2^30 范围的引用 id。
    hits = _scan_varints_in_range(raw_bytes, 1 << 30, (1 << 31) - 1)
    if len(hits) == 1:
        return hits[0]
    return None


def _extract_struct_ref_id_list_from_value_blob_base64(value_blob_base64: str) -> List[int]:
    raw_bytes = _try_decode_base64_to_bytes(value_blob_base64)
    if raw_bytes == b"":
        return []
    return _scan_varints_in_range(raw_bytes, 1 << 30, (1 << 31) - 1)


def _extract_entry_name_from_pyugc_asset_entry(asset_entry: Dict[str, Any]) -> str:
    """
    从 root4['5']['1'] 的单条 entry 中提取“名称”。

    该结构在 test2 中形如：
    entry['5'] = [{'1 id@int': 1, '11': {'1@string': '<name>'}}, ...]
    """
    name_list = asset_entry.get("5")
    if not isinstance(name_list, list):
        return ""
    for item in name_list:
        if not isinstance(item, dict):
            continue
        if item.get("1 id@int") != 1:
            continue
        name_container = item.get("11")
        if not isinstance(name_container, dict):
            continue
        name_value = name_container.get("1@string")
        if isinstance(name_value, str):
            return name_value
    return ""


def _extract_entry_instance_id_from_pyugc_asset_entry(asset_entry: Dict[str, Any]) -> Optional[int]:
    instance_id_list = asset_entry.get("1")
    if not isinstance(instance_id_list, list) or not instance_id_list:
        return None
    first_id = instance_id_list[0]
    if not isinstance(first_id, int):
        return None
    return first_id


def _extract_entry_template_id_from_pyugc_asset_entry(asset_entry: Dict[str, Any]) -> Optional[int]:
    type_list = asset_entry.get("2")
    if isinstance(type_list, list) and type_list:
        first_type = type_list[0]
        if isinstance(first_type, dict):
            candidate_type_id = first_type.get("1@int")
            if isinstance(candidate_type_id, int):
                return candidate_type_id

    template_id_value = asset_entry.get("8@int")
    if isinstance(template_id_value, int):
        return template_id_value
    return None


def _extract_entry_transform_from_pyugc_asset_entry(asset_entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    transform_list = asset_entry.get("6")
    if not isinstance(transform_list, list):
        return None
    for item in transform_list:
        if not isinstance(item, dict):
            continue
        if item.get("1 id@int") != 1:
            continue
        transform_object = item.get("11")
        if isinstance(transform_object, dict):
            return transform_object
    return None


def _read_float_from_object(mapping_object: Any, key: str, default_value: float) -> float:
    if not isinstance(mapping_object, dict):
        return float(default_value)
    value = mapping_object.get(key)
    if isinstance(value, (int, float)):
        return float(value)
    return float(default_value)


def _parse_vector3(mapping_object: Any, default_value: float) -> List[float]:
    x_coordinate = _read_float_from_object(mapping_object, "1@float", default_value)
    y_coordinate = _read_float_from_object(mapping_object, "2@float", default_value)
    z_coordinate = _read_float_from_object(mapping_object, "3@float", default_value)
    return [x_coordinate, y_coordinate, z_coordinate]


def _try_extract_override_variables_from_pyugc_asset_entry(
    asset_entry: Dict[str, Any],
    instance_id_text: str,
) -> List[Dict[str, Any]]:
    """
    尽力从 entry['7'] 中抽取变量覆盖信息，转换为 Graph_Generater InstanceConfig 的 override_variables 格式。

    注意：该逻辑只做“尽可能解析”，不保证与 Graph_Generater 的变量 DSL 语义一致。
    """
    override_variables: List[Dict[str, Any]] = []

    group_list = asset_entry.get("7")
    if not isinstance(group_list, list):
        return override_variables

    variable_counter = 0
    for group_item in group_list:
        if not isinstance(group_item, dict):
            continue
        container = group_item.get("11 id1")
        if not isinstance(container, dict):
            continue
        variable_items = container.get("1")
        if not isinstance(variable_items, list):
            continue

        for variable_item in variable_items:
            if not isinstance(variable_item, dict):
                continue
            variable_name = variable_item.get("2@string")
            if not isinstance(variable_name, str) or variable_name.strip() == "":
                continue
            type_code_value = variable_item.get("3@int")
            type_code_int = int(type_code_value) if isinstance(type_code_value, int) else None

            value_object = variable_item.get("4")
            extracted_value: Any = None
            extracted_value_source: str = ""
            if isinstance(value_object, dict):
                possible_13 = value_object.get("13")
                if isinstance(possible_13, dict) and isinstance(possible_13.get("1@int"), int):
                    extracted_value = int(possible_13["1@int"])
                    extracted_value_source = "field_13_int"
                else:
                    base64_value = value_object.get("30@data")
                    if isinstance(base64_value, str) and base64_value != "":
                        extracted_value = _decode_base64_to_max_int(base64_value)
                        extracted_value_source = "field_30_data_max_int"

            if type_code_int == 3:
                variable_type = "整数"
            elif type_code_int == 20:
                variable_type = "整数"
            elif type_code_int == 6:
                variable_type = "字符串"
                value_b64: str = ""
                value_slot = variable_item.get("6")
                if isinstance(value_slot, dict) and isinstance(value_slot.get("2@data"), str):
                    value_b64 = str(value_slot.get("2@data") or "")
                    extracted_value_source = "field_6_2@data_utf8"
                elif isinstance(value_object, dict):
                    type_payload = value_object.get("2")
                    if isinstance(type_payload, dict) and isinstance(type_payload.get("2@data"), str):
                        value_b64 = str(type_payload.get("2@data") or "")
                        extracted_value_source = "field_4_2_2@data_utf8"
                extracted_value = _decode_base64_to_utf8_text(value_b64)
            elif type_code_int == 25:
                variable_type = "结构体"
                struct_id_b64: str = ""
                type_slot = variable_item.get("6")
                if isinstance(type_slot, dict) and isinstance(type_slot.get("2@data"), str):
                    struct_id_b64 = str(type_slot.get("2@data") or "")
                elif isinstance(value_object, dict):
                    type_payload = value_object.get("2")
                    if isinstance(type_payload, dict) and isinstance(type_payload.get("2@data"), str):
                        struct_id_b64 = str(type_payload.get("2@data") or "")
                struct_id_int = _try_decode_struct_id_from_type_data(struct_id_b64)

                ref_id_int: Optional[int] = None
                value_blob_b64 = value_object.get("35@data") if isinstance(value_object, dict) else None
                if isinstance(value_blob_b64, str) and value_blob_b64.strip() != "":
                    ref_id_int = _try_extract_struct_ref_id_from_value_blob_base64(value_blob_b64)
                    extracted_value_source = "field_35@data_struct_ref_id"

                extracted_value = {"struct_id_int": struct_id_int, "ugc_ref_id_int": ref_id_int}
            elif type_code_int == 26:
                variable_type = "结构体列表"
                struct_id_b64: str = ""
                type_slot = variable_item.get("6")
                if isinstance(type_slot, dict) and isinstance(type_slot.get("2@data"), str):
                    struct_id_b64 = str(type_slot.get("2@data") or "")
                elif isinstance(value_object, dict):
                    type_payload = value_object.get("2")
                    if isinstance(type_payload, dict) and isinstance(type_payload.get("2@data"), str):
                        struct_id_b64 = str(type_payload.get("2@data") or "")
                struct_id_int = _try_decode_struct_id_from_type_data(struct_id_b64)

                ref_ids: List[int] = []
                value_blob_b64 = value_object.get("36@data") if isinstance(value_object, dict) else None
                if isinstance(value_blob_b64, str) and value_blob_b64.strip() != "":
                    ref_ids = _extract_struct_ref_id_list_from_value_blob_base64(value_blob_b64)
                    if struct_id_int is not None:
                        ref_ids = [ref_id for ref_id in ref_ids if int(ref_id) != int(struct_id_int)]
                    extracted_value_source = "field_36@data_struct_ref_id_list"

                extracted_value = {"struct_id_int": struct_id_int, "ugc_ref_id_ints": ref_ids}
            elif type_code_int is None:
                variable_type = "未知"
            else:
                variable_type = f"未知(type_code={type_code_int})"

            variable_counter += 1
            variable_id = f"ugc_var_{instance_id_text}_{variable_counter:03d}"

            override_variables.append(
                {
                    "variable_id": variable_id,
                    "variable_name": variable_name,
                    "variable_type": variable_type,
                    "value": extracted_value,
                    "metadata": {
                        "ugc_type_code": type_code_int,
                        "ugc_value_source": extracted_value_source,
                    },
                }
            )

    return override_variables


def _export_instances_from_pyugc_dump(
    pyugc_object: Any,
    output_package_root: Path,
) -> List[Dict[str, Any]]:
    """
    从 pyugc dump 中导出“实体摆放”（InstanceConfig）到项目存档目录。

    当前通过启发式定位：
    - root['4']['5']['1'] 作为实例/资源条目列表
    - 每条 entry 的 transform 位于 entry['6'] 里 id=1 的 '11'
    """
    exported_instances: List[Dict[str, Any]] = []

    if not isinstance(pyugc_object, dict):
        return exported_instances
    root4_object = pyugc_object.get("4")
    if not isinstance(root4_object, dict):
        return exported_instances
    section_object = root4_object.get("5")
    if not isinstance(section_object, dict):
        return exported_instances
    entry_list = section_object.get("1")
    if not isinstance(entry_list, list):
        return exported_instances

    entity_placement_directory = output_package_root / "实体摆放"
    _ensure_directory(entity_placement_directory)

    for entry_index, asset_entry in enumerate(entry_list):
        if not isinstance(asset_entry, dict):
            continue

        instance_id_int = _extract_entry_instance_id_from_pyugc_asset_entry(asset_entry)
        if instance_id_int is None:
            continue
        instance_id_text = str(instance_id_int)

        name_text = _extract_entry_name_from_pyugc_asset_entry(asset_entry)
        if name_text.startswith("默认模版"):
            continue
        if name_text == "":
            name_text = f"unnamed_{instance_id_text}"

        template_id_int = _extract_entry_template_id_from_pyugc_asset_entry(asset_entry)
        template_id_text = str(template_id_int) if isinstance(template_id_int, int) else "unknown_template"
        template_type_int = asset_entry.get("8@int") if isinstance(asset_entry.get("8@int"), int) else None

        transform_object = _extract_entry_transform_from_pyugc_asset_entry(asset_entry) or {}
        position_list = _parse_vector3(transform_object.get("1"), 0.0)
        rotation_list = _parse_vector3(transform_object.get("2"), 0.0)
        scale_list = _parse_vector3(transform_object.get("3"), 1.0)
        guid_value = transform_object.get("501@int") if isinstance(transform_object, dict) else None

        is_level_entity = name_text == "关卡实体"
        entity_type = "关卡" if is_level_entity else "物件"

        override_variables = _try_extract_override_variables_from_pyugc_asset_entry(
            asset_entry,
            instance_id_text,
        )

        instance_object: Dict[str, Any] = {
            "instance_id": instance_id_text,
            "name": name_text,
            "template_id": template_id_text,
            "position": position_list,
            "rotation": rotation_list,
            "override_variables": override_variables,
            "additional_graphs": [],
            "additional_components": [],
            "metadata": {
                "entity_type": entity_type,
                "is_level_entity": is_level_entity,
                "ugc_instance_id_int": instance_id_int,
                "ugc_template_id_int": template_id_int,
                "ugc_template_type_int": template_type_int,
                "ugc_scale": scale_list,
                "ugc_guid_int": guid_value,
                "source_pyugc_path": f"4/5/1/[{entry_index}]",
            },
            "graph_variable_overrides": {},
        }

        file_base_name = f"{name_text}_{instance_id_text}"
        file_name = _sanitize_filename(file_base_name, max_length=120) + ".json"
        output_path = entity_placement_directory / file_name
        _write_json_file(output_path, instance_object)

        exported_instances.append(
            {
                "instance_id": instance_id_text,
                "name": name_text,
                "template_id": template_id_text,
                "entity_type": entity_type,
                "is_level_entity": is_level_entity,
                "output": str(output_path.relative_to(output_package_root)).replace("\\", "/"),
            }
        )

    exported_instances_sorted = sorted(
        exported_instances,
        key=lambda item: (
            0 if item.get("is_level_entity") else 1,
            str(item.get("name", "")),
            str(item.get("instance_id", "")),
        ),
    )

    _write_json_file(entity_placement_directory / "instances_index.json", exported_instances_sorted)
    return exported_instances_sorted


