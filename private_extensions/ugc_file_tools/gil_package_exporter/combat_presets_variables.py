from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional

from ugc_file_tools.decode_gil import decode_bytes_to_python

from .generic_decode import _decode_base64_to_max_int


def _extract_player_template_variables_from_template_entry(template_entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    从玩家模板条目中提取“变量定义”列表（用于玩家模板编辑器相关内容）。

    当前主要来源：template_entry['8'] 中 id=1 的 '11 id1' 下的 '1' 列表。
    """
    variables: List[Dict[str, Any]] = []
    section_list = template_entry.get("8")
    if not isinstance(section_list, list):
        return variables

    variable_items: Optional[List[Any]] = None
    for section_item in section_list:
        if not isinstance(section_item, dict):
            continue
        if section_item.get("1 id@int") != 1:
            continue
        container = section_item.get("11 id1")
        if not isinstance(container, dict):
            continue
        candidate_items = container.get("1")
        if isinstance(candidate_items, list):
            variable_items = candidate_items
            break

    if not isinstance(variable_items, list):
        return variables

    for index, variable_item in enumerate(variable_items):
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
            elif isinstance(value_object.get("16 id6"), dict) and isinstance(
                value_object["16 id6"].get("1@string"), str
            ):
                extracted_value = value_object["16 id6"]["1@string"]
                extracted_value_source = "field_16_string"
            elif isinstance(value_object.get("18@data"), str) and value_object.get("18@data") != "":
                base64_value = value_object["18@data"]
                decoded_bytes = base64.b64decode(base64_value)
                extracted_value = decode_bytes_to_python(decoded_bytes)
                extracted_value_source = "field_18_data_generic_decode"
            elif isinstance(value_object.get("30@data"), str) and value_object.get("30@data") != "":
                extracted_value = _decode_base64_to_max_int(value_object["30@data"])
                extracted_value_source = "field_30_data_max_int"

        variables.append(
            {
                "index": index,
                "variable_name": variable_name,
                "ugc_type_code": type_code_int,
                "default_value": extracted_value,
                "default_value_source": extracted_value_source,
            }
        )

    return variables


def _map_player_template_variable_type_code_to_level_variable_type(type_code: Optional[int]) -> str:
    if type_code == 3:
        return "整数"
    if type_code == 6:
        return "字符串"
    if type_code == 8:
        return "整数列表"
    if type_code == 26:
        return "字典"
    return "未知"


def _default_level_variable_value_for_type(variable_type: str) -> Any:
    if variable_type == "整数":
        return 0
    if variable_type == "字符串":
        return ""
    if variable_type == "整数列表":
        return []
    if variable_type == "字典":
        return {}
    return None


def _build_level_variable_file_text(
    variable_file_id: str,
    variable_file_name: str,
    variables: List[Dict[str, Any]],
    package_namespace: str,
    template_id_int: int,
) -> str:
    lines: List[str] = []
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append("from engine.graph.models.package_model import LevelVariableDefinition")
    lines.append("")
    lines.append(f'VARIABLE_FILE_ID = "{variable_file_id}"')
    lines.append(f'VARIABLE_FILE_NAME = "{variable_file_name}"')
    lines.append("")
    lines.append("LEVEL_VARIABLES: list[LevelVariableDefinition] = [")
    for variable_index, variable_record in enumerate(variables, start=1):
        variable_name = variable_record.get("variable_name")
        if not isinstance(variable_name, str) or variable_name.strip() == "":
            continue

        ugc_type_code = variable_record.get("ugc_type_code")
        ugc_type_code_int = int(ugc_type_code) if isinstance(ugc_type_code, int) else None
        variable_type = _map_player_template_variable_type_code_to_level_variable_type(ugc_type_code_int)

        default_value = variable_record.get("default_value")
        if variable_type == "整数" and not isinstance(default_value, int):
            default_value = _default_level_variable_value_for_type(variable_type)
        elif variable_type == "字符串" and not isinstance(default_value, str):
            default_value = _default_level_variable_value_for_type(variable_type)
        elif variable_type == "整数列表":
            default_value = _default_level_variable_value_for_type(variable_type)
        elif variable_type == "字典":
            default_value = _default_level_variable_value_for_type(variable_type)

        variable_id = f"var_{package_namespace}_player_template_{template_id_int}_{variable_index:03d}"

        lines.append("    LevelVariableDefinition(")
        lines.append(f'        variable_id="{variable_id}",')
        lines.append(f'        variable_name="{variable_name}",')
        lines.append(f'        variable_type="{variable_type}",')
        lines.append(f"        default_value={repr(default_value)},")
        lines.append("        is_global=True,")
        lines.append('        description="",')
        lines.append(
            "        metadata={"
            f"\"ugc_type_code\": {repr(ugc_type_code_int)}, "
            f"\"source\": \"player_template_{template_id_int}\", "
            f"\"index\": {repr(variable_record.get('index'))}"
            "},"
        )
        lines.append("    ),")
    lines.append("]")
    lines.append("")
    return "\n".join(lines)


