from __future__ import annotations

from typing import Any, Dict, List, Mapping

from ugc_file_tools.node_graph_semantics.port_type_inference import (
    infer_dict_kv_var_types_from_default_value as _infer_dict_kv_var_types_from_default_value,
    parse_dict_key_value_var_types_from_port_type_text as _parse_dict_key_value_var_types_from_port_type_text,
)
from ugc_file_tools.node_graph_semantics.var_base import (
    build_var_base_message_server,
    build_var_base_message_server_empty,
    build_var_base_message_server_for_dict,
    coerce_constant_value_for_var_type as _coerce_constant_value_for_var_type,
    map_server_port_type_to_var_type_id as _map_server_port_type_to_var_type_id,
)

_ID_LIKE_VAR_TYPES: tuple[int, ...] = (1, 2, 16, 17, 20, 21)
_ID_LIKE_ZERO_VALUE: int = 0


def build_blackboard_entries(*, graph_model: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    GraphModel.payload.graph_variables → NodeGraph.blackboard（field_6）
    """
    blackboard: List[Dict[str, Any]] = []

    raw_graph_variables = graph_model.get("graph_variables")
    if not isinstance(raw_graph_variables, list):
        return blackboard

    for var in raw_graph_variables:
        if not isinstance(var, dict):
            continue
        name = str(var.get("name") or "").strip()
        if name == "":
            continue
        variable_type_text = str(var.get("variable_type") or "").strip()
        if variable_type_text == "":
            continue

        server_vt = int(_map_server_port_type_to_var_type_id(variable_type_text))
        default_value = var.get("default_value")

        container_key_vt: int = 0
        container_value_vt: int = 0

        typed_value: Dict[str, Any]
        if int(server_vt) == 27:
            kv = _parse_dict_key_value_var_types_from_port_type_text(variable_type_text)
            if kv is None:
                # GraphVariableConfig(variable_type="字典") 的工程化扩展：允许通过 dict_key_type/dict_value_type 提供 KV。
                provided_key = str(var.get("dict_key_type") or "").strip()
                provided_val = str(var.get("dict_value_type") or "").strip()
                if provided_key and provided_val:
                    kv = (
                        int(_map_server_port_type_to_var_type_id(str(provided_key))),
                        int(_map_server_port_type_to_var_type_id(str(provided_val))),
                    )

            if kv is None:
                kv = _infer_dict_kv_var_types_from_default_value(default_value)
            if kv is None:
                raise ValueError(
                    "字典节点图变量缺少键/值类型信息，无法写回默认值："
                    f"name={name!r} variable_type={variable_type_text!r} default_value={default_value!r}\n"
                    "- 解决方案：把 variable_type 写成 '字符串_整数字典' / '字典(字符串→整数)' 这类带键值类型的形式；\n"
                    "- 或在 variable_type='字典' 时提供 dict_key_type/dict_value_type；\n"
                    "- 或提供一个非空的 dict 默认值以便自动推断键/值 VarType。"
                )

            dict_key_vt, dict_value_vt = int(kv[0]), int(kv[1])
            container_key_vt = int(dict_key_vt)
            container_value_vt = int(dict_value_vt)
            typed_value = build_var_base_message_server_for_dict(
                dict_key_var_type_int=int(dict_key_vt),
                dict_value_var_type_int=int(dict_value_vt),
                default_value=default_value,
            )
        elif default_value is None:
            typed_value = build_var_base_message_server_empty(var_type_int=int(server_vt))
            # 真源对齐：blackboard 上的 id-like（GUID/Config/Prefab...）默认值为 0 时，常以 `{field_1=0}` 表达，
            # 而不是 empty bytes（empty bytes 更常用于 pins 的“类型载体/未设置”语义）。
            if int(server_vt) in _ID_LIKE_VAR_TYPES and isinstance(typed_value, dict):
                typed_value = dict(typed_value)
                typed_value["101"] = {"1": int(_ID_LIKE_ZERO_VALUE)}
        else:
            coerced_default = _coerce_constant_value_for_var_type(var_type_int=int(server_vt), raw_value=default_value)
            typed_value = build_var_base_message_server(var_type_int=int(server_vt), value=coerced_default)
            if (
                int(server_vt) in _ID_LIKE_VAR_TYPES
                and isinstance(coerced_default, int)
                and int(coerced_default) == int(_ID_LIKE_ZERO_VALUE)
                and isinstance(typed_value, dict)
            ):
                typed_value = dict(typed_value)
                typed_value["101"] = {"1": int(_ID_LIKE_ZERO_VALUE)}

        entry: Dict[str, Any] = {
            "2": name,
            "3": int(server_vt),
            "4": typed_value,
            "5": bool(var.get("is_exposed", False)),
        }

        if int(container_key_vt) != 0 or int(container_value_vt) != 0:
            entry["7"] = int(container_key_vt)
            entry["8"] = int(container_value_vt)

        struct_id = var.get("struct_id")
        if isinstance(struct_id, int):
            entry["6"] = int(struct_id)

        blackboard.append(entry)

    return blackboard

