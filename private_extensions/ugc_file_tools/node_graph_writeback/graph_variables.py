from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from ugc_file_tools.decode_gil import decode_bytes_to_python
from ugc_file_tools.gil_dump_codec.protobuf_like import parse_binary_data_hex_text
from ugc_file_tools.integrations.graph_generater.type_registry_bridge import (
    is_supported_graph_variable_type_text,
    load_graph_generater_type_registry,
    map_graph_variable_cn_type_to_var_type_int,
    parse_typed_dict_alias,
)
from ugc_file_tools.node_graph_semantics.var_base import (
    build_var_base_message_server as _build_var_base_message_server,
    build_var_base_message_server_for_dict as _build_var_base_message_server_for_dict,
    coerce_constant_value_for_var_type as _coerce_constant_value_for_var_type,
    infer_var_type_int_from_raw_value as _infer_var_type_int_from_raw_value,
    map_server_port_type_to_var_type_id as _map_server_port_type_to_var_type_id,
)

from .record_codec import _extract_nested_int
from .writeback_feature_flags import is_writeback_feature_enabled


_HTML_STEM_IN_DESC_RE = re.compile(r"[\(（](?P<stem>[^)）]+)\.html[\)）]")


def apply_ui_registry_auto_fill_to_graph_variables(
    *,
    graph_variables: List[Dict[str, Any]],
    ui_key_to_guid_registry: Optional[Dict[str, int]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    工程化：在写回 `.gil` 前，为“项目配置类 GraphVariables”自动补齐 default_value。

    背景：
    - 节点图 Graph Code 的校验器会要求 `ui_key:` 占位符必须来自 HTML 的 data-ui-key（或其派生规则）。
      因此“布局索引 / 多状态组索引”这类非 HTML data-ui-key 的数值，不能直接在 Graph Code 里写成 `ui_key:...`。
    - Web 导入链路会把这些值写入运行时缓存 `ui_guid_registry.json`（例如 `LAYOUT_INDEX__HTML__1`、`UI_STATE_GROUP__...`）。
    - 这里在“写回阶段”读取 registry 并回填到 GraphVariables(default_value) 上，最终落到 `.gil` 内，无需人工手填。

    约定：
    - 布局索引：从 GraphVariable.description 里解析 `(<stem>.html)`，回填 `LAYOUT_INDEX__HTML__<stem>`。
    - 多状态组索引（揭晓遮罩）：`揭晓遮罩_<state>组` 回填 `UI_STATE_GROUP__battle_settlement_overlay__<state>__group`。
    """
    if not graph_variables:
        return [], {"updated_total": 0, "updates": []}
    if ui_key_to_guid_registry is None:
        return list(graph_variables), {"updated_total": 0, "updates": [], "skipped": True, "reason": "ui_guid_registry_missing"}

    mapping = dict(ui_key_to_guid_registry)
    updates: List[Dict[str, Any]] = []
    out: List[Dict[str, Any]] = []

    for v in graph_variables:
        if not isinstance(v, dict):
            continue
        vv = dict(v)

        name = str(vv.get("name") or "").strip()
        variable_type = str(vv.get("variable_type") or "").strip()
        default_value = vv.get("default_value")
        desc = str(vv.get("description") or "")

        # 只自动填“当前仍是 0（或空）”的项目配置，避免覆盖用户显式配置
        is_unset_int = (default_value is None) or (isinstance(default_value, int) and int(default_value) == 0)

        if variable_type == "整数" and is_unset_int:
            # --- 1) 布局索引：布局索引_XXX + description 中含 (1.html)/(ceshi_rect.html) 等
            if name.startswith("布局索引_"):
                m = _HTML_STEM_IN_DESC_RE.search(desc)
                if m is not None:
                    html_stem = str(m.group("stem") or "").strip()
                    if html_stem != "":
                        key = f"LAYOUT_INDEX__HTML__{html_stem}"
                        val = mapping.get(key)
                        if isinstance(val, int) and int(val) > 0:
                            vv["default_value"] = int(val)
                            updates.append(
                                {
                                    "name": name,
                                    "kind": "layout_index",
                                    "html_stem": html_stem,
                                    "registry_key": key,
                                    "value": int(val),
                                }
                            )
                            out.append(vv)
                            continue

            # --- 2) 揭晓遮罩多状态组索引：揭晓遮罩_hidden组 / waiting组 / ...
            if name.startswith("揭晓遮罩_") and name.endswith("组"):
                state = str(name[len("揭晓遮罩_") : -len("组")]).strip()
                if state != "":
                    # 当前约定：battle_settlement_overlay 为状态组名
                    key = f"UI_STATE_GROUP__battle_settlement_overlay__{state}__group"
                    val = mapping.get(key)
                    if isinstance(val, int) and int(val) > 0:
                        vv["default_value"] = int(val)
                        updates.append(
                            {
                                "name": name,
                                "kind": "ui_state_group",
                                "state_group": "battle_settlement_overlay",
                                "state": state,
                                "registry_key": key,
                                "value": int(val),
                            }
                        )
                        out.append(vv)
                        continue

        out.append(vv)

    return out, {"updated_total": int(len(updates)), "updates": updates[:200]}


def _normalize_graph_variables_from_graph_json(graph_json_object: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    尽可能从输入 JSON 中提取 GraphVariableConfig.serialize() 的列表。

    兼容多种上游输出结构：
    - export_graph_model_json_from_graph_code.py：顶层包含 {metadata, graph_model}
      - graph_model.graph_variables（优先）
      - metadata.graph_variables（兼容旧路径）
    - GraphModel.serialize()：顶层直接包含 graph_variables
    - GraphResultDataBuilder：顶层包含 {data: {...}}，变量可能位于 data.graph_variables
    """
    # 1) export_graph_model_json_from_graph_code.py：graph_model.graph_variables
    gm = graph_json_object.get("graph_model")
    if isinstance(gm, dict):
        variables = gm.get("graph_variables")
        if isinstance(variables, list):
            return [v for v in variables if isinstance(v, dict)]

    # 2) GraphModel.serialize()：top-level graph_variables
    variables = graph_json_object.get("graph_variables")
    if isinstance(variables, list):
        return [v for v in variables if isinstance(v, dict)]

    # 3) GraphResultDataBuilder：data.graph_variables
    data = graph_json_object.get("data")
    if isinstance(data, dict):
        variables = data.get("graph_variables")
        if isinstance(variables, list):
            return [v for v in variables if isinstance(v, dict)]

    # 4) 旧路径：metadata.graph_variables
    metadata = graph_json_object.get("metadata")
    if isinstance(metadata, dict):
        variables = metadata.get("graph_variables")
        if isinstance(variables, list):
            return [v for v in variables if isinstance(v, dict)]

    return []


def _extract_struct_defs_from_payload_root(payload_root: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    从 payload_root(root4) 解码结构体定义表（payload_root['10']['6']）。

    返回结构：
    [
      {
        "struct_id": int,
        "name": str,
        "fields": [
          {"index": int, "name": str, "var_type_int": int},
          ...
        ],
      },
      ...
    ]
    """
    section10 = payload_root.get("10")
    if not isinstance(section10, dict):
        return []
    raw_defs = section10.get("6")
    raw_list: List[str] = []
    if isinstance(raw_defs, list):
        raw_list = [x for x in raw_defs if isinstance(x, str)]
    elif isinstance(raw_defs, str):
        raw_list = [raw_defs]
    else:
        return []

    struct_defs: List[Dict[str, Any]] = []
    for txt in raw_list:
        if not isinstance(txt, str) or not txt.startswith("<binary_data>"):
            continue
        decoded = decode_bytes_to_python(parse_binary_data_hex_text(txt))
        if not isinstance(decoded, dict):
            continue
        m = decoded.get("field_1")
        m_msg = m.get("message") if isinstance(m, dict) else None
        if not isinstance(m_msg, dict):
            continue
        struct_id = _extract_nested_int({"x": m_msg}, ["x", "field_1"])
        if not isinstance(struct_id, int):
            continue
        name_node = m_msg.get("field_501")
        struct_name = str(name_node.get("utf8") or "").strip() if isinstance(name_node, dict) else ""

        fields_list: List[Dict[str, Any]] = []
        raw_fields = m_msg.get("field_3")
        if isinstance(raw_fields, list):
            for wrapper in raw_fields:
                mm = wrapper.get("message") if isinstance(wrapper, dict) else None
                if not isinstance(mm, dict):
                    continue
                field_name_node = mm.get("field_501")
                field_name = str(field_name_node.get("utf8") or "").strip() if isinstance(field_name_node, dict) else ""
                field_index = _extract_nested_int({"x": mm}, ["x", "field_503"])
                field_vt = _extract_nested_int({"x": mm}, ["x", "field_502"])
                if not isinstance(field_index, int) or not isinstance(field_vt, int):
                    continue
                fields_list.append({"index": int(field_index), "name": field_name, "var_type_int": int(field_vt)})

        # 按字段 index 排序，确保后续 values 列表按稳定顺序写入
        fields_list.sort(key=lambda x: int(x.get("index", 0)))
        struct_defs.append({"struct_id": int(struct_id), "name": struct_name, "fields": fields_list})

    return struct_defs


def extract_struct_defs_from_payload_root(payload_root: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Public API: decode struct definitions table from payload root (root4)."""
    return _extract_struct_defs_from_payload_root(payload_root)


def _resolve_struct_def_for_graph_variable(*, variable: Dict[str, Any], struct_defs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """为结构体/结构体列表节点图变量选择一个现有结构体定义（按 struct_id / struct_name / 默认值推断）。"""
    name = str(variable.get("name") or "").strip()
    default_value = variable.get("default_value")

    # 1) 显式 struct_id
    for key in ("struct_id", "struct_def_id"):
        sid = variable.get(key)
        if isinstance(sid, int):
            for sd in struct_defs:
                if int(sd.get("struct_id", -1)) == int(sid):
                    return sd
    if isinstance(default_value, dict):
        sid = default_value.get("struct_id")
        if isinstance(sid, int):
            for sd in struct_defs:
                if int(sd.get("struct_id", -1)) == int(sid):
                    return sd

    # 2) 显式 struct_name
    for key in ("struct_name", "struct_def_name"):
        sname = variable.get(key)
        if isinstance(sname, str) and sname.strip() != "":
            target = sname.strip()
            for sd in struct_defs:
                if str(sd.get("name") or "").strip() == target:
                    return sd
    if isinstance(default_value, dict):
        sname = default_value.get("struct_name")
        if isinstance(sname, str) and sname.strip() != "":
            target = sname.strip()
            for sd in struct_defs:
                if str(sd.get("name") or "").strip() == target:
                    return sd

    # 3) 兜底：仅当默认值为旧 items 格式时，尝试按字段类型序列推断
    if isinstance(default_value, dict) and isinstance(default_value.get("items"), list):
        item_vts: List[int] = []
        for item in list(default_value.get("items") or []):
            if isinstance(item, dict):
                raw_type = item.get("var_type_int")
                if isinstance(raw_type, int):
                    item_vts.append(int(raw_type))
                    continue
                raw_type = (
                    item.get("var_type")
                    if "var_type" in item
                    else item.get("variable_type")
                    if "variable_type" in item
                    else item.get("type")
                )
                if raw_type is not None:
                    item_vts.append(int(_map_server_port_type_to_var_type_id(str(raw_type))))
                    continue
                raw_value = item.get("value") if "value" in item else item.get("default_value")
                item_vts.append(int(_infer_var_type_int_from_raw_value(raw_value)))
                continue
            item_vts.append(int(_infer_var_type_int_from_raw_value(item)))

        matches: List[Dict[str, Any]] = []
        for sd in struct_defs:
            fields = sd.get("fields")
            if not isinstance(fields, list) or not fields:
                continue
            sd_vts = [int(f.get("var_type_int")) for f in fields if isinstance(f, dict) and isinstance(f.get("var_type_int"), int)]
            if sd_vts == item_vts:
                matches.append(sd)
        if len(matches) == 1:
            return matches[0]

    raise ValueError(
        "无法为结构体节点图变量匹配现有结构体定义："
        f"name={name!r}（请提供 variable.struct_id / variable.struct_name，或在 default_value 中提供 struct_id/struct_name）"
    )


def _normalize_struct_default_value_by_struct_def(*, struct_def: Dict[str, Any], default_value: Any) -> Dict[str, Any]:
    """将结构体默认值归一化为 VarBase(struct).field108 所需的 {items:[...]} 形式，且字段类型必须来自 struct_def。"""
    fields = struct_def.get("fields")
    if not isinstance(fields, list) or not fields:
        raise ValueError(
            f"结构体定义缺少字段列表或为空：struct_id={struct_def.get('struct_id')!r} name={struct_def.get('name')!r}"
        )

    # 1) 解析为 values 列表（按 struct_def.fields 顺序）
    values: List[Any]
    if default_value is None:
        raise ValueError(f"结构体节点图变量必须提供默认值（需对齐现有结构体字段）：struct_id={struct_def.get('struct_id')!r}")

    if isinstance(default_value, dict):
        # a) fields 映射
        fields_map = default_value.get("fields")
        if isinstance(fields_map, dict):
            values = []
            for f in fields:
                fname = str(f.get("name") or "")
                if fname == "" or fname not in fields_map:
                    raise ValueError(f"结构体默认值缺少字段：{fname!r}（struct_id={struct_def.get('struct_id')!r}）")
                values.append(fields_map.get(fname))
        else:
            # b) values 列表
            raw_values = default_value.get("values")
            if isinstance(raw_values, list):
                values = list(raw_values)
            else:
                # c) 旧格式 items：只取 value
                raw_items = default_value.get("items")
                if isinstance(raw_items, list):
                    values = []
                    for it in raw_items:
                        if isinstance(it, dict):
                            if "value" in it:
                                values.append(it.get("value"))
                            elif "default_value" in it:
                                values.append(it.get("default_value"))
                            else:
                                values.append(it)
                        else:
                            values.append(it)
                else:
                    # d) 直接把同名键当 fields_map
                    field_name_set = {str(f.get("name") or "") for f in fields}
                    if all(isinstance(k, str) and k in field_name_set for k in default_value.keys()):
                        values = []
                        for f in fields:
                            fname = str(f.get("name") or "")
                            values.append(default_value.get(fname))
                    else:
                        raise ValueError(f"无法解析结构体默认值：{default_value!r}")
    elif isinstance(default_value, (list, tuple)):
        values = list(default_value)
    else:
        raise ValueError(f"无法解析结构体默认值：{default_value!r}")

    if len(values) != len(fields):
        raise ValueError(
            "结构体默认值字段数量与结构体定义不一致："
            f"struct_id={struct_def.get('struct_id')!r} field_count={len(fields)} got={len(values)}"
        )

    # 2) 转为 items（显式携带 var_type_int，避免自由推断/写错类型）
    items: List[Dict[str, Any]] = []
    for f, raw in zip(fields, values):
        vt = f.get("var_type_int")
        if not isinstance(vt, int):
            raise ValueError(f"结构体字段缺少 var_type_int：{f!r}")
        coerced = _coerce_constant_value_for_var_type(var_type_int=int(vt), raw_value=raw)
        items.append({"var_type_int": int(vt), "value": coerced})
    return {"items": items}


def _normalize_struct_list_default_value_by_struct_def(*, struct_def: Dict[str, Any], default_value: Any) -> List[Dict[str, Any]]:
    """将结构体列表默认值归一化为 List[{items:[...]}]，每个元素都必须对齐同一个 struct_def。"""
    if default_value is None:
        return []
    if isinstance(default_value, dict):
        raw_values = default_value.get("values")
        if isinstance(raw_values, list):
            instances = list(raw_values)
        else:
            raise ValueError(f"无法解析结构体列表默认值：{default_value!r}")
    elif isinstance(default_value, list):
        instances = list(default_value)
    else:
        raise ValueError(f"无法解析结构体列表默认值：{default_value!r}")

    normalized: List[Dict[str, Any]] = []
    for inst in instances:
        normalized.append(_normalize_struct_default_value_by_struct_def(struct_def=struct_def, default_value=inst))
    return normalized


def _build_graph_variable_def_item_from_metadata(
    variable: Dict[str, Any], *, struct_defs: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    将 Graph_Generater 的 GraphVariableConfig（导出 JSON）转换为 `.gil` GraphEntry['6'] 的变量定义条目。

    重要：该变量定义表用于编辑器解析【获取/设置节点图变量】的泛型端口具体类型。
    若不写回该表，端口类型会继承模板图的变量定义（常见表现：全部变成字符串/字典或显示不匹配）。
    """
    name = str(variable.get("name") or "").strip()
    if name == "":
        raise ValueError("graph_variable.name 不能为空")

    variable_type_text = str(variable.get("variable_type") or "").strip()
    if variable_type_text == "":
        raise ValueError(f"graph_variable.variable_type 不能为空：name={name!r}")

    # 与 Graph_Generater 同步：节点图变量支持类型以 Graph_Generater/engine/type_registry.py 为唯一事实来源
    tr = load_graph_generater_type_registry()
    if not is_supported_graph_variable_type_text(variable_type_text):
        raise ValueError(
            "节点图变量类型不受 Graph_Generater 支持（请以 engine/type_registry.VARIABLE_TYPES 为准）："
            f"name={name!r} variable_type={variable_type_text!r}"
        )

    is_typed_dict, alias_key_type_text, alias_value_type_text = parse_typed_dict_alias(variable_type_text)
    var_type_int = map_graph_variable_cn_type_to_var_type_int(variable_type_text)
    default_value = variable.get("default_value")

    # keyType/valueType：
    # - after_game 真源：非字典变量通常不写 keyType/valueType（视为缺省/null）
    # - 旧口径：非字典变量写入 6/6（字符串占位）
    # - 字典变量必须写入 key/value 实际类型（用于编辑器与端口类型推断）
    if is_writeback_feature_enabled("graph_variables_non_dict_omit_key_value_type_fields"):
        key_type_int: int | None = None
        value_type_int: int | None = None
    else:
        key_type_int = 6
        value_type_int = 6

    if int(var_type_int) == 27:
        # 字典类型两种来源：
        # - GraphVariableConfig(variable_type="字典", dict_key_type=..., dict_value_type=...)
        # - 别名字典（Graph_Generater 支持）：例如 "字符串-整数字典" / "字符串_整数字典"
        if is_typed_dict:
            key_type_text = alias_key_type_text
            value_type_text = alias_value_type_text

            # 若同时提供 dict_key_type/dict_value_type，则必须一致（避免出现双重来源）
            provided_key = str(variable.get("dict_key_type") or "").strip()
            provided_val = str(variable.get("dict_value_type") or "").strip()
            if provided_key and provided_key != key_type_text:
                raise ValueError(
                    "字典变量类型来源冲突：variable_type 为别名字典，但 dict_key_type 不一致："
                    f"name={name!r} variable_type={variable_type_text!r} dict_key_type={provided_key!r}"
                )
            if provided_val and provided_val != value_type_text:
                raise ValueError(
                    "字典变量类型来源冲突：variable_type 为别名字典，但 dict_value_type 不一致："
                    f"name={name!r} variable_type={variable_type_text!r} dict_value_type={provided_val!r}"
                )
        else:
            key_type_text = str(variable.get("dict_key_type") or "").strip()
            value_type_text = str(variable.get("dict_value_type") or "").strip()

        if key_type_text == "" or value_type_text == "":
            raise ValueError(
                "写回『字典』类型的节点图变量需要 dict_key_type/dict_value_type："
                f"name={name!r} variable_type={variable_type_text!r}"
            )

        # key/value 类型必须为 Graph_Generater 的变量类型（且禁止递归字典，避免出现无法写回/编辑器不支持的形态）
        allowed_kv_types = set(tr.VARIABLE_TYPES) - {tr.TYPE_DICT}
        if key_type_text not in allowed_kv_types:
            raise ValueError(f"字典节点图变量的 key_type 不受支持：{name!r} -> {key_type_text!r}")
        if value_type_text not in allowed_kv_types:
            raise ValueError(f"字典节点图变量的 value_type 不受支持：{name!r} -> {value_type_text!r}")

        dict_key_var_type_int = map_graph_variable_cn_type_to_var_type_int(key_type_text)
        dict_value_var_type_int = map_graph_variable_cn_type_to_var_type_int(value_type_text)
        key_type_int = int(dict_key_var_type_int)
        value_type_int = int(dict_value_var_type_int)
        var_base_message = _build_var_base_message_server_for_dict(
            dict_key_var_type_int=int(dict_key_var_type_int),
            dict_value_var_type_int=int(dict_value_var_type_int),
            default_value=default_value,
        )
    else:
        # 结构体/结构体列表：必须使用存档内已有的结构体定义（否则导入/编辑器可能失败）
        if int(var_type_int) in (25, 26):
            # 与 Graph_Generater 对齐：结构体图变量常见默认值为 None（在运行期通过【拼装结构体】赋值）
            # - default_value=None：允许，无需匹配 struct_def
            # - 需要写入非空默认值时：必须能匹配到存档内的 struct_defs
            if default_value is None:
                var_base_message = _build_var_base_message_server(var_type_int=int(var_type_int), value=None)
            elif int(var_type_int) == 26 and isinstance(default_value, (list, tuple)) and len(default_value) == 0:
                var_base_message = _build_var_base_message_server(var_type_int=26, value=list(default_value))
            else:
                struct_defs_list = list(struct_defs or [])
                if not struct_defs_list:
                    raise ValueError(
                        "写回结构体/结构体列表节点图变量的非空默认值需要 base gil 内存在结构体定义表 payload['10']['6']，但当前未解析到任何结构体定义："
                        f"name={name!r} variable_type={variable_type_text!r}"
                    )
                struct_def = _resolve_struct_def_for_graph_variable(variable=variable, struct_defs=struct_defs_list)
                if int(var_type_int) == 25:
                    normalized_struct_value = _normalize_struct_default_value_by_struct_def(
                        struct_def=struct_def, default_value=default_value
                    )
                    var_base_message = _build_var_base_message_server(var_type_int=25, value=normalized_struct_value)
                else:
                    normalized_struct_list_value = _normalize_struct_list_default_value_by_struct_def(
                        struct_def=struct_def, default_value=default_value
                    )
                    var_base_message = _build_var_base_message_server(var_type_int=26, value=normalized_struct_list_value)
        else:
            coerced_default_value = _coerce_constant_value_for_var_type(var_type_int=int(var_type_int), raw_value=default_value)
            var_base_message = _build_var_base_message_server(var_type_int=int(var_type_int), value=coerced_default_value)

    exposed = bool(variable.get("is_exposed", False))
    out: Dict[str, Any] = {
        "2": name,
        "3": int(var_type_int),
        "4": var_base_message,
    }
    if isinstance(key_type_int, int) and isinstance(value_type_int, int):
        out["7"] = int(key_type_int)
        out["8"] = int(value_type_int)
    if exposed:
        out["5"] = True
    return out


def build_graph_variable_def_item_from_metadata(
    variable: Dict[str, Any],
    *,
    struct_defs: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Public API: convert GraphVariableConfig metadata dict to a GIL GraphEntry['6'] item."""
    return _build_graph_variable_def_item_from_metadata(variable, struct_defs=struct_defs)

