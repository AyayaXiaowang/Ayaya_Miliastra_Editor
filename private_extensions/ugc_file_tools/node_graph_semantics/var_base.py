from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from ugc_file_tools.gil_dump_codec.protobuf_like import format_binary_data_hex_text
from ugc_file_tools.var_type_map import map_server_port_type_text_to_var_type_id_or_raise

from .dict_kv_types import parse_typed_dict_alias_text, try_resolve_dict_kv_var_types_from_type_text


_UI_KEY_TO_GUID: Optional[Dict[str, int]] = None
_ALLOW_UNRESOLVED_UI_KEY: bool = False

_COMPONENT_NAME_TO_ID: Optional[Dict[str, int]] = None
_ALLOW_UNRESOLVED_COMPONENT_KEY: bool = False

_ENTITY_NAME_TO_ID: Optional[Dict[str, int]] = None
_ALLOW_UNRESOLVED_ENTITY_KEY: bool = False


def set_ui_key_guid_registry(ui_key_to_guid: Optional[Dict[str, int]], *, allow_unresolved: bool = False) -> None:
    """注入 UIKey→GUID 映射表（用于 GUID 端口常量的占位符解析）。

    约定占位符（GraphModel.input_constants / Graph Code 常量）：
    - "ui_key:<key>"
    - "ui:<key>"

    说明：
    - 该映射表仅用于写回阶段“编译期替换”，不会出现在 `.gil` 最终产物中。
    - 若未注入映射表，则遇到 ui_key 占位符会直接报错（fail-fast）。
    - allow_unresolved=True 时：未注入映射表 / key 缺失将回退为 0（用于“允许缺映射仍导出”的场景）。
    """
    global _UI_KEY_TO_GUID, _ALLOW_UNRESOLVED_UI_KEY
    _ALLOW_UNRESOLVED_UI_KEY = bool(allow_unresolved)
    if ui_key_to_guid is None:
        _UI_KEY_TO_GUID = None
        return
    cleaned: Dict[str, int] = {}
    for k, v in ui_key_to_guid.items():
        key = str(k or "").strip()
        if key == "":
            continue
        if not isinstance(v, int) or int(v) <= 0:
            continue
        cleaned[key] = int(v)
    _UI_KEY_TO_GUID = cleaned


def set_component_id_registry(component_name_to_id: Optional[Dict[str, int]], *, allow_unresolved: bool = False) -> None:
    """注入“元件名→元件ID”映射表（用于 元件ID 端口常量的占位符解析）。

    约定占位符：
    - "component_key:<元件名>"
    - "component:<元件名>"

    说明：
    - 映射表仅用于写回阶段“编译期替换”，不会出现在 `.gil` 最终产物中。
    - 若未注入映射表，则遇到 component_key 占位符会直接报错（fail-fast）。
    - allow_unresolved=True 时：未注入映射表 / key 缺失将回退为 0（用于“允许缺映射仍导出”的场景）。
    """
    global _COMPONENT_NAME_TO_ID, _ALLOW_UNRESOLVED_COMPONENT_KEY
    _ALLOW_UNRESOLVED_COMPONENT_KEY = bool(allow_unresolved)
    if component_name_to_id is None:
        _COMPONENT_NAME_TO_ID = None
        return
    cleaned: Dict[str, int] = {}
    for k, v in component_name_to_id.items():
        key = str(k or "").strip()
        if key == "":
            continue
        if not isinstance(v, int) or int(v) <= 0:
            continue
        cleaned[key] = int(v)
    _COMPONENT_NAME_TO_ID = cleaned


def set_entity_id_registry(entity_name_to_id: Optional[Dict[str, int]], *, allow_unresolved: bool = False) -> None:
    """注入“实体名→实体GUID/ID”映射表（用于 实体/GUID 端口常量的占位符解析）。

    约定占位符：
    - "entity_key:<实体名>"
    - "entity:<实体名>"

    说明：
    - 映射表仅用于导出/写回阶段“编译期替换”，不会出现在 `.gia/.gil` 最终产物中。
    - 若未注入映射表，则遇到 entity_key 占位符会直接报错（fail-fast）。
    - allow_unresolved=True 时：未注入映射表 / key 缺失将回退为 0（用于“允许缺映射仍导出”的场景）。
    """
    global _ENTITY_NAME_TO_ID, _ALLOW_UNRESOLVED_ENTITY_KEY
    _ALLOW_UNRESOLVED_ENTITY_KEY = bool(allow_unresolved)
    if entity_name_to_id is None:
        _ENTITY_NAME_TO_ID = None
        return
    cleaned: Dict[str, int] = {}
    for k, v in entity_name_to_id.items():
        key = str(k or "").strip()
        if key == "":
            continue
        if not isinstance(v, int) or int(v) <= 0:
            continue
        cleaned[key] = int(v)
    _ENTITY_NAME_TO_ID = cleaned


def _resolve_ui_key_guid_or_raise(text: str) -> int:
    raw = str(text or "").strip()
    lowered = raw.lower()
    if lowered.startswith("ui_key:"):
        key = raw[len("ui_key:") :].strip()
    elif lowered.startswith("ui:"):
        key = raw[len("ui:") :].strip()
    else:
        raise ValueError(f"不是 UIKey GUID 占位符：{text!r}")

    if key == "":
        raise ValueError(f"UIKey 占位符缺少 key：{text!r}")
    mapping = _UI_KEY_TO_GUID
    if mapping is None:
        if bool(_ALLOW_UNRESOLVED_UI_KEY):
            return 0
        raise RuntimeError(f"未注入 UIKey→GUID 映射表，无法解析：{text!r}")
    guid = mapping.get(key)
    if guid is None:
        if bool(_ALLOW_UNRESOLVED_UI_KEY):
            return 0
        raise KeyError(f"UIKey 未在注册表中找到：{key!r}")
    return int(guid)


def _resolve_component_id_or_raise(text: str) -> int:
    raw = str(text or "").strip()
    lowered = raw.lower()
    if lowered.startswith("component_key:"):
        key = raw[len("component_key:") :].strip()
    elif lowered.startswith("component:"):
        key = raw[len("component:") :].strip()
    else:
        raise ValueError(f"不是 component_key 元件ID 占位符：{text!r}")

    if key == "":
        raise ValueError(f"component_key 占位符缺少 key：{text!r}")
    mapping = _COMPONENT_NAME_TO_ID
    if mapping is None:
        if bool(_ALLOW_UNRESOLVED_COMPONENT_KEY):
            return 0
        raise RuntimeError(f"未注入 元件名→元件ID 映射表，无法解析：{text!r}")
    cid = mapping.get(key)
    if cid is None:
        if bool(_ALLOW_UNRESOLVED_COMPONENT_KEY):
            return 0
        raise KeyError(f"元件名未在注册表中找到：{key!r}")
    return int(cid)


def _resolve_entity_id_or_raise(text: str) -> int:
    raw = str(text or "").strip()
    lowered = raw.lower()
    if lowered.startswith("entity_key:"):
        key = raw[len("entity_key:") :].strip()
    elif lowered.startswith("entity:"):
        key = raw[len("entity:") :].strip()
    else:
        raise ValueError(f"不是 entity_key 实体ID 占位符：{text!r}")

    if key == "":
        raise ValueError(f"entity_key 占位符缺少 key：{text!r}")
    mapping = _ENTITY_NAME_TO_ID
    if mapping is None:
        if bool(_ALLOW_UNRESOLVED_ENTITY_KEY):
            return 0
        raise RuntimeError(f"未注入 实体名→实体ID 映射表，无法解析：{text!r}")
    eid = mapping.get(key)
    if eid is None:
        if bool(_ALLOW_UNRESOLVED_ENTITY_KEY):
            return 0
        raise KeyError(f"实体名未在注册表中找到：{key!r}")
    return int(eid)


def _map_server_port_type_to_var_type_id(port_type: str) -> int:
    """将 Graph_Generater 的中文端口类型映射为 gia.proto 的 VarType 数字。"""
    return map_server_port_type_text_to_var_type_id_or_raise(str(port_type))


def _try_parse_typed_dict_alias_text(type_text: str) -> Optional[Tuple[str, str]]:
    return parse_typed_dict_alias_text(str(type_text or ""))


def _try_map_server_dict_type_text_to_kv_var_types(type_text: str) -> Optional[Tuple[int, int]]:
    """将“别名字典”类型文本映射为 (dict_key_var_type_int, dict_value_var_type_int)。"""
    return try_resolve_dict_kv_var_types_from_type_text(
        str(type_text or ""),
        map_port_type_text_to_var_type_id=_map_server_port_type_to_var_type_id,
        reject_generic=True,
    )


def _build_var_base_message_server_empty_for_dict_kv(
    *,
    dict_key_var_type_int: int,
    dict_value_var_type_int: int,
) -> Dict[str, Any]:
    """构造“空字典”的 MapBase VarBase，但显式携带 key/value 类型信息。"""
    empty = format_binary_data_hex_text(b"")
    return {
        "1": 10003,  # MapBase
        "4": _build_var_base_item_type_server_for_dict(
            dict_key_var_type_int=int(dict_key_var_type_int),
            dict_value_var_type_int=int(dict_value_var_type_int),
        ),
        "112": empty,  # empty MapBaseValue
    }


def _coerce_constant_value_for_port_type(*, port_type: str, raw_value: Any) -> Any:
    """将 GraphModel.input_constants 的值按端口类型做强制转换（尽量容忍字符串数字）。"""
    t = str(port_type or "").strip()

    # 列表类型（GraphModel 中经常以字符串形式序列化，例如 "[]" / "[1,2,3]"）
    # 说明：实际元素的 VarBase 仍由 _build_var_base_message_server 的 list 分支负责逐项构造；
    # 这里仅负责把字符串字面量转为 python list。
    if t.endswith("列表"):
        if raw_value is None:
            return []
        if isinstance(raw_value, (list, tuple)):
            return list(raw_value)
        if isinstance(raw_value, str):
            s = raw_value.strip()
            if s in ("[]", "()"):
                return []
            if (s.startswith("[") and s.endswith("]")) or (s.startswith("(") and s.endswith(")")):
                inner = s[1:-1].strip()
                if inner == "":
                    return []
                parts = [p.strip() for p in inner.split(",") if p.strip() != ""]

                # 元素类型按列表类型推断（不使用 try/except；失败直接抛错）
                if t in ("整数列表", "GUID列表", "配置ID列表", "元件ID列表", "阵营列表"):
                    out: List[int] = []
                    for p in parts:
                        token = p.strip()
                        if (token.startswith("'") and token.endswith("'")) or (token.startswith('"') and token.endswith('"')):
                            token = token[1:-1].strip()
                        lowered = token.strip().lower()
                        if t == "元件ID列表" and (lowered.startswith("component_key:") or lowered.startswith("component:")):
                            out.append(int(_resolve_component_id_or_raise(token)))
                            continue
                        if not re.fullmatch(r"[+-]?\d+", token):
                            raise ValueError(f"无法将列表元素转为整数：{p!r}（port_type={t!r} raw={raw_value!r}）")
                        out.append(int(token))
                    return out

                if t in ("浮点数列表",):
                    out_f: List[float] = []
                    for p in parts:
                        token = p.strip()
                        if not re.fullmatch(r"[+-]?(?:\d+\.\d*|\d*\.\d+|\d+)(?:[eE][+-]?\d+)?", token):
                            raise ValueError(f"无法将列表元素转为浮点数：{p!r}（port_type={t!r} raw={raw_value!r}）")
                        out_f.append(float(token))
                    return out_f

                if t in ("布尔值列表",):
                    out_b: List[bool] = []
                    for p in parts:
                        token = p.strip().lower()
                        if token in ("true", "1", "yes", "y", "是"):
                            out_b.append(True)
                            continue
                        if token in ("false", "0", "no", "n", "否"):
                            out_b.append(False)
                            continue
                        raise ValueError(f"无法将列表元素转为布尔值：{p!r}（port_type={t!r} raw={raw_value!r}）")
                    return out_b

                if t in ("字符串列表",):
                    out_s: List[str] = []
                    for p in parts:
                        token = p.strip()
                        if (token.startswith("'") and token.endswith("'")) or (token.startswith('"') and token.endswith('"')):
                            token = token[1:-1]
                        out_s.append(str(token))
                    return out_s

                # 其他列表类型（实体/三维向量/结构体等）先保守要求上游提供 list/tuple；
                # 若只有字符串字面量，除空列表外直接报错，避免误解析。
                raise ValueError(f"暂不支持将该列表常量字符串解析为具体列表：port_type={t!r} raw_value={raw_value!r}")

        raise ValueError(f"列表常量期望 None/list/tuple 或 '[]' 形式字符串，实际：{raw_value!r}（port_type={t!r}）")

    if t == "字符串":
        return str(raw_value)

    if t in ("GUID",):
        if isinstance(raw_value, bool):
            return int(raw_value)
        if isinstance(raw_value, int):
            return int(raw_value)
        if isinstance(raw_value, float):
            return int(raw_value)
        if isinstance(raw_value, str):
            s = raw_value.strip()
            if s == "" or s == "校准_值":
                return 0
            lowered = s.lower()
            if lowered.startswith("ui_key:") or lowered.startswith("ui:"):
                return int(_resolve_ui_key_guid_or_raise(s))
            if lowered.startswith("entity_key:") or lowered.startswith("entity:"):
                return int(_resolve_entity_id_or_raise(s))
            # 兼容 "0.0" 这类写法
            if not re.fullmatch(r"[+-]?(?:\d+\.\d*|\d*\.\d+|\d+)(?:[eE][+-]?\d+)?", s):
                raise ValueError(f"无法将常量转为 GUID：{raw_value!r}")
            return int(float(s))
        raise ValueError(f"无法将常量转为 GUID：{raw_value!r}")

    if t in ("浮点数",):
        if isinstance(raw_value, (int, float)):
            return float(raw_value)
        if isinstance(raw_value, str):
            s = raw_value.strip()
            # 校准图/占位常量：允许用一个统一占位符表示“任意数值”，写回时落到 0.0
            if s == "校准_值" or s == "":
                return 0.0
            if not re.fullmatch(r"[+-]?(?:\d+\.\d*|\d*\.\d+|\d+)(?:[eE][+-]?\d+)?", s):
                raise ValueError(f"无法将常量转为浮点数：{raw_value!r}")
            return float(s)
        raise ValueError(f"无法将常量转为浮点数：{raw_value!r}")

    if t in ("整数", "配置ID", "元件ID"):
        if isinstance(raw_value, bool):
            return int(raw_value)
        if isinstance(raw_value, int):
            return int(raw_value)
        if isinstance(raw_value, float):
            return int(raw_value)
        if isinstance(raw_value, str):
            s = raw_value.strip()
            if s == "校准_值" or s == "":
                return 0
            lowered = s.lower()
            if t == "整数" and (lowered.startswith("ui_key:") or lowered.startswith("ui:")):
                # 工程化：UI 控件索引（整数）允许使用 ui_key 占位符，写回阶段解析为真实整数 ID。
                return int(_resolve_ui_key_guid_or_raise(s))
            if t == "整数" and (lowered.startswith("entity_key:") or lowered.startswith("entity:")):
                return int(_resolve_entity_id_or_raise(s))
            if t == "元件ID" and (lowered.startswith("component_key:") or lowered.startswith("component:")):
                return int(_resolve_component_id_or_raise(s))
            # 兼容 "0.0" 这类写法
            if not re.fullmatch(r"[+-]?(?:\d+\.\d*|\d*\.\d+|\d+)(?:[eE][+-]?\d+)?", s):
                raise ValueError(f"无法将常量转为整数：{raw_value!r}")
            return int(float(s))
        raise ValueError(f"无法将常量转为整数：{raw_value!r}")

    if t in ("布尔值",):
        if isinstance(raw_value, bool):
            return bool(raw_value)
        if isinstance(raw_value, int):
            return bool(int(raw_value))
        if isinstance(raw_value, str):
            s = raw_value.strip().lower()
            if s == "" or s == "校准_值":
                return False
            if s in ("true", "1", "yes", "y", "是"):
                return True
            if s in ("false", "0", "no", "n", "否"):
                return False
        raise ValueError(f"无法将常量转为布尔值：{raw_value!r}")

    if t == "三维向量":
        # 工程化：GraphModel/GraphVariables 的向量默认值允许为 None，表示“未设置该端口常量”。
        # 写回阶段用 [None, None, None] 触发 VectorBaseValue(empty bytes) 的编码分支，从而保持未设置语义与 roundtrip。
        if raw_value is None:
            return [None, None, None]
        if isinstance(raw_value, (list, tuple)) and len(raw_value) == 3:
            def _f(x: Any) -> float:
                # 工程化：GraphModel/GraphVariables 的向量默认值可能包含 None（表示该分量未设置）。
                # 写回阶段会将 None 保留为“缺省字段”（不写入对应坐标），以支持 roundtrip。
                if x is None:
                    return None  # type: ignore[return-value]
                if isinstance(x, str):
                    s = x.strip()
                    if s == "" or s == "校准_值":
                        return 0.0
                    return float(s)
                return float(x)

            return [_f(raw_value[0]), _f(raw_value[1]), _f(raw_value[2])]
        if isinstance(raw_value, str):
            s = raw_value.strip()
            if s == "" or s == "校准_值":
                return [0.0, 0.0, 0.0]
            if (s.startswith("(") and s.endswith(")")) or (s.startswith("[") and s.endswith("]")):
                inner = s[1:-1].strip()
                parts = [p.strip() for p in inner.split(",")]
                if len(parts) == 3:
                    return [float(parts[0]), float(parts[1]), float(parts[2])]
        raise ValueError(f"无法将常量转为三维向量：{raw_value!r}")

    # 其他复杂类型（列表/字典/结构体等）先原样返回；如遇到可再扩展
    return raw_value


def _infer_var_type_int_from_raw_value(raw_value: Any) -> int:
    """在端口为“泛型”且缺少模板类型提示时，用常量字面值做兜底推断。"""
    if isinstance(raw_value, bool):
        return 4
    if isinstance(raw_value, int):
        return 3
    if isinstance(raw_value, float):
        return 5
    if isinstance(raw_value, (list, tuple)) and len(raw_value) == 3:
        return 12
    if isinstance(raw_value, str):
        s = raw_value.strip().lower()
        # 工程化：ui_key/ui 占位符在语义上表示“整数 GUID/索引”。
        # 目标：即便该常量落在“泛型端口”（例如比较节点的输入）也能推断为整数，
        # 从而在后续 _coerce_constant_value_for_var_type(vt=3) 阶段完成 ui_key→真实整数回填。
        if s.startswith("ui_key:") or s.startswith("ui:"):
            return 3
        if s.startswith("component_key:") or s.startswith("component:"):
            return 3
        if s.startswith("entity_key:") or s.startswith("entity:"):
            return 3
        if s in ("true", "false", "0", "1", "yes", "no", "y", "n", "是", "否"):
            return 4
        # 数字（不使用 try/except）：先判整数，再判浮点/科学计数
        if re.fullmatch(r"[+-]?\d+", s):
            return 3
        if re.fullmatch(r"[+-]?(?:\d+\.\d*|\d*\.\d+)(?:[eE][+-]?\d+)?", s) or re.fullmatch(
            r"[+-]?\d+[eE][+-]?\d+", s
        ):
            return 5
    return 6


def _coerce_constant_value_for_var_type(*, var_type_int: int, raw_value: Any) -> Any:
    """按 VarType 数字（server）将常量强制转换。"""
    vt = int(var_type_int)
    # GraphVariable 默认值写回：允许 ID-like 类型使用 ui_key 占位符（由 registry 在写回阶段解析为真实整数 ID）。
    if vt == 2:
        return _coerce_constant_value_for_port_type(port_type="GUID", raw_value=raw_value)
    if vt == 6:
        return str(raw_value)
    if vt == 5:
        if isinstance(raw_value, (int, float)):
            return float(raw_value)
        if isinstance(raw_value, str):
            return float(raw_value.strip())
        raise ValueError(f"无法将常量转为浮点数：{raw_value!r}")
    if vt == 3:
        if isinstance(raw_value, bool):
            return int(raw_value)
        if isinstance(raw_value, int):
            return int(raw_value)
        if isinstance(raw_value, float):
            return int(raw_value)
        if isinstance(raw_value, str):
            s = raw_value.strip()
            lowered = s.lower()
            # 工程化：允许 GraphVariables/常量中的“整数”使用 ui_key 占位符（编译期替换为真实整数 ID）
            if lowered.startswith("ui_key:") or lowered.startswith("ui:"):
                return int(_resolve_ui_key_guid_or_raise(s))
            # 工程化：允许 GraphVariables/常量中的“整数”使用 component_key 占位符（编译期替换为真实元件ID）
            if lowered.startswith("component_key:") or lowered.startswith("component:"):
                return int(_resolve_component_id_or_raise(s))
            if lowered.startswith("entity_key:") or lowered.startswith("entity:"):
                return int(_resolve_entity_id_or_raise(s))
            return int(float(s))
        raise ValueError(f"无法将常量转为整数：{raw_value!r}")
    if vt == 7:
        if raw_value is None:
            return []
        if isinstance(raw_value, (list, tuple)):
            return [_coerce_constant_value_for_port_type(port_type="GUID", raw_value=item) for item in raw_value]
        if isinstance(raw_value, str):
            s = raw_value.strip()
            if s in ("[]", "()"):
                return []
        raise ValueError(f"无法将常量转为 GUID列表：{raw_value!r}")
    if vt == 8:
        if raw_value is None:
            return []
        if isinstance(raw_value, (list, tuple)):
            return [_coerce_constant_value_for_port_type(port_type="整数", raw_value=item) for item in raw_value]
        if isinstance(raw_value, str):
            s = raw_value.strip()
            if s in ("[]", "()"):
                return []
        raise ValueError(f"无法将常量转为 整数列表：{raw_value!r}")
    if vt == 4:
        return bool(_coerce_constant_value_for_port_type(port_type="布尔值", raw_value=raw_value))
    if vt == 12:
        return _coerce_constant_value_for_port_type(port_type="三维向量", raw_value=raw_value)
    # id-like（Entity/GUID/Config/Prefab...）：允许占位符回填为 int
    if vt in (1, 2, 16, 17, 20, 21):
        if raw_value is None:
            return 0
        if isinstance(raw_value, bool):
            return int(raw_value)
        if isinstance(raw_value, int):
            return int(raw_value)
        if isinstance(raw_value, float):
            return int(raw_value)
        if isinstance(raw_value, str):
            s = raw_value.strip()
            if s == "" or s == "校准_值":
                return 0
            lowered = s.lower()
            if lowered.startswith("ui_key:") or lowered.startswith("ui:"):
                return int(_resolve_ui_key_guid_or_raise(s))
            if lowered.startswith("component_key:") or lowered.startswith("component:"):
                return int(_resolve_component_id_or_raise(s))
            if lowered.startswith("entity_key:") or lowered.startswith("entity:"):
                return int(_resolve_entity_id_or_raise(s))
            if not re.fullmatch(r"[+-]?(?:\d+\.\d*|\d*\.\d+|\d+)(?:[eE][+-]?\d+)?", s):
                raise ValueError(f"无法将常量转为整数ID：{raw_value!r}（var_type={vt}）")
            return int(float(s))
        raise ValueError(f"无法将常量转为整数ID：{raw_value!r}（var_type={vt}）")
    # 其他 id-like
    return raw_value


def _build_var_base_item_type_server(*, var_type_int: int) -> Dict[str, Any]:
    # VarBase.ItemType:
    # - classBase=1(Server)
    # - type_server(field_100): { type(field_1)=VarType, kind(field_2)=0 }
    return {"1": 1, "100": {"1": int(var_type_int)}}


def _build_dict_kv_type_message(*, dict_key_var_type_int: int, dict_value_var_type_int: int) -> Dict[str, Any]:
    """构造字典 key/value 类型描述 message（用于 VarBase.ItemType.type_server.field_101）。"""
    # 真源样本（最简字典节点图）在该 message 内除了 key/value 外，还会带两个恒为 1 的标记字段（field_4/field_5）。
    # 这些字段在旧 schema 文档中未显式命名，但缺失时会导致游戏侧把字典类型判定为“未完整配置”，并在试玩校验中报错。
    return {
        "1": int(dict_key_var_type_int),
        "2": int(dict_value_var_type_int),
        "4": 1,
        "5": 1,
    }


def _build_var_base_item_type_server_for_dict(*, dict_key_var_type_int: int, dict_value_var_type_int: int) -> Dict[str, Any]:
    """对齐样本：字典变量的 VarBase.ItemType.type_server 需要额外写入 key/value 类型信息。"""
    return {
        "1": 1,
        "100": {
            "1": 27,  # VarType=字典
            "2": 2,  # kind=2（样本一致）
            "101": _build_dict_kv_type_message(
                dict_key_var_type_int=int(dict_key_var_type_int),
                dict_value_var_type_int=int(dict_value_var_type_int),
            ),
        },
    }


def _build_var_base_item_type_server_for_dict_pair(*, dict_key_var_type_int: int, dict_value_var_type_int: int) -> Dict[str, Any]:
    """对齐样本：MapPair(VarBase.cls=10007) 的 ItemType.type_server.field_1 为 25，且携带 key/value 类型。"""
    return {
        "1": 1,
        "100": {
            "1": 25,  # 样本：MapPair 的 type_server.type=25
            "2": 2,  # kind=2（样本一致）
            "101": _build_dict_kv_type_message(
                dict_key_var_type_int=int(dict_key_var_type_int),
                dict_value_var_type_int=int(dict_value_var_type_int),
            ),
        },
    }


def _normalize_dict_default_pairs(default_value: Any) -> List[Tuple[Any, Any]]:
    """
    将字典默认值归一化为 (key,value) 对列表。
    支持：
    - dict：按 items() 顺序
    - list/tuple：元素为 [k,v] / (k,v) 或 {"key":k,"value":v}
    """
    if default_value is None:
        return []

    if isinstance(default_value, dict):
        return list(default_value.items())

    if isinstance(default_value, (list, tuple)):
        pairs: List[Tuple[Any, Any]] = []
        for item in default_value:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                pairs.append((item[0], item[1]))
                continue
            if isinstance(item, dict) and ("key" in item) and ("value" in item):
                pairs.append((item.get("key"), item.get("value")))
                continue
            raise ValueError(f"字典默认值条目格式不支持：{item!r}")
        return pairs

    raise ValueError(f"字典默认值格式不支持：{default_value!r}")


def _build_var_base_message_server_for_dict(
    *,
    dict_key_var_type_int: int,
    dict_value_var_type_int: int,
    default_value: Any,
) -> Dict[str, Any]:
    """
    按样本对齐构造“字典”类型的 VarBase（cls=10003 MapBase）。
    - field_112: MapBase.pairs（message，field_1 为 repeated MapPair VarBase）
    - MapPair: VarBase.cls=10007，field_111 为 key/value 的 VarBase
    """
    key_vt = int(dict_key_var_type_int)
    val_vt = int(dict_value_var_type_int)

    pairs = _normalize_dict_default_pairs(default_value)

    pair_var_bases: List[Dict[str, Any]] = []
    for key, value in pairs:
        coerced_key = _coerce_constant_value_for_var_type(var_type_int=int(key_vt), raw_value=key)
        coerced_val = _coerce_constant_value_for_var_type(var_type_int=int(val_vt), raw_value=value)

        key_var_base = _build_var_base_message_server(var_type_int=int(key_vt), value=coerced_key)
        val_var_base = _build_var_base_message_server(var_type_int=int(val_vt), value=coerced_val)

        pair_var_bases.append(
            {
                "1": 10007,  # MapPair
                "2": 1,
                "4": _build_var_base_item_type_server_for_dict_pair(
                    dict_key_var_type_int=int(key_vt), dict_value_var_type_int=int(val_vt)
                ),
                "111": {
                    "1": key_var_base,
                    "2": val_var_base,
                },
            }
        )

    map_base: Dict[str, Any] = {
        "1": 10003,  # MapBase
        "4": _build_var_base_item_type_server_for_dict(
            dict_key_var_type_int=int(key_vt), dict_value_var_type_int=int(val_vt)
        ),
    }
    if pair_var_bases:
        # 只有“显式填了键值对”才标记 alreadySetVal=1，并写入 MapBaseValue.mapPairs
        map_base["2"] = 1
        map_base["112"] = {"1": pair_var_bases}
    else:
        # 真源（最简字典节点图）在“连线输入的字典 pin”场景会写入空 bytes，而不是省略该字段。
        # 省略会让游戏侧把字典类型视为“未完整配置”，导致试玩校验报错。
        map_base["112"] = format_binary_data_hex_text(b"")
    return map_base


def _build_var_base_message_server_for_concrete_string_list(*, values: List[str]) -> Dict[str, Any]:
    """对齐样本：ConcreteBase(10000) 包裹 ArrayBase(10002, StringList=11) 的字符串列表值。"""
    entries = [_build_var_base_message_server(var_type_int=6, value=str(v)) for v in list(values)]
    array_base: Dict[str, Any] = {
        "1": 10002,  # ArrayBase
        "2": 1,
        "4": _build_var_base_item_type_server(var_type_int=11),  # StringList
    }
    if entries:
        array_base["109"] = {"1": entries}
    return {
        "1": 10000,  # ConcreteBase
        "2": 1,
        "110": {
            "1": 1,  # indexOfConcrete（样本为 1）
            "2": array_base,
        },
    }


def _build_var_base_message_server_empty(*, var_type_int: int) -> Dict[str, Any]:
    """构造“空值/未设置”的 VarBase（用于泛型端口仅写回类型、不写具体值的场景）。

    约定：使用对应 baseValues 字段写入空 bytes（raw_hex=""），并省略 alreadySetVal(field_2)。
    """
    vt = int(var_type_int)
    item_type = _build_var_base_item_type_server(var_type_int=int(vt))
    empty = format_binary_data_hex_text(b"")
    scalar = _try_build_empty_scalar_var_base(vt=vt, item_type=item_type, empty=empty)
    if scalar is not None:
        return scalar
    container = _try_build_empty_container_var_base(vt=vt, item_type=item_type, empty=empty)
    if container is not None:
        return container
    enum_like = _try_build_empty_enum_like_var_base(vt=vt, item_type=item_type)
    if enum_like is not None:
        return enum_like
    raise ValueError(f"暂不支持该 VarType 的空值 VarBase 构造：var_type={vt}")


def _try_build_empty_scalar_var_base(*, vt: int, item_type: Dict[str, Any], empty: str) -> Optional[Dict[str, Any]]:
    if int(vt) == 6:
        return {"1": 5, "4": item_type, "105": empty}  # StringBaseValue(empty)
    if int(vt) == 5:
        return {"1": 4, "4": item_type, "104": empty}  # FloatBaseValue(empty)
    if int(vt) == 3:
        return {"1": 2, "4": item_type, "102": empty}  # IntBaseValue(empty)
    if int(vt) == 12:
        # 真源对齐：VectorBaseValue 需要保留 message 结构（field_107.message.field_1.message）。
        return {"1": 7, "4": item_type, "107": {"1": {}}}  # VectorBaseValue(Vector{})
    if int(vt) in (1, 2, 16, 17, 20, 21):
        return {"1": 1, "4": item_type, "101": empty}  # IdBaseValue(empty)
    return None


def _try_build_empty_container_var_base(*, vt: int, item_type: Dict[str, Any], empty: str) -> Optional[Dict[str, Any]]:
    if int(vt) in (7, 8, 9, 10, 11, 13, 15, 22, 23, 24, 26):
        return {"1": 10002, "4": item_type, "109": empty}  # ArrayBaseValue(empty)
    if int(vt) == 27:
        return {"1": 10003, "4": item_type, "112": empty}  # MapBaseValue(empty)
    if int(vt) == 25:
        return {"1": 10001, "4": item_type, "108": empty}  # RecordBaseValue(empty)
    return None


def _try_build_empty_enum_like_var_base(*, vt: int, item_type: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Enum-like 空值构造：
    - 内建 Bool(4) / Enum(14)：对齐真源样本，使用 raw_hex="" 的空 bytes 表达空值。
      （此前写入 `{field_106.field_1=1}` 会与真源不一致，且并不能解决“端口显示泛型”的根因）
    """
    if int(vt) in (4, 14):
        empty = format_binary_data_hex_text(b"")
        return {"1": 6, "4": item_type, "106": empty}  # EnumBaseValue(empty bytes)

    # 具体枚举类型（例如 受击等级=28）
    from ugc_file_tools.node_graph_semantics.enum_codec import build_entry_by_id_map, get_known_enum_type_ids, load_node_data_index_doc

    if int(vt) not in get_known_enum_type_ids():
        return None
    doc = load_node_data_index_doc()
    enum_entry_by_id = build_entry_by_id_map(doc.get("Enums"))
    enum_entry = enum_entry_by_id.get(int(vt))
    items = enum_entry.get("Items") if isinstance(enum_entry, dict) else None
    if not (isinstance(items, list) and items and isinstance(items[0], dict) and isinstance(items[0].get("ID"), int)):
        raise ValueError(f"无法为枚举类型构造占位 EnumBaseValue：enum_id={int(vt)} Items 缺失或无效")
    return {"1": 6, "4": item_type, "106": {"1": int(items[0]['ID'])}}


def _build_var_base_message_server_empty_list_value(*, var_type_int: int) -> Dict[str, Any]:
    """
    构造“空数组值”的 VarBase（用于部分节点的列表输入端口：连线时也需要携带一个显式的空 ArrayBase）。

    对齐真源（有错的节点挑出来.gil）：
    - vt=8(整数列表) 的 InParam 在连线时仍携带 ArrayBase(10002) 且 alreadySetVal(field_2)=1，ArrayBaseValue(field_109) 为空 bytes。
    """
    vb = _build_var_base_message_server_empty(var_type_int=int(var_type_int))
    if int(vb.get("1") or 0) != 10002:
        raise ValueError(f"empty_list_value 仅支持 ArrayBase(10002)，实际：var_type={int(var_type_int)} vb_cls={vb.get('1')!r}")
    out = dict(vb)
    # 真源对齐：空数组也标记为“已设置”
    out["2"] = 1
    return out


def _wrap_var_base_as_concrete_base(*, inner: Dict[str, Any], index_of_concrete: Optional[int]) -> Dict[str, Any]:
    """将一个 inner VarBase 包裹为 ConcreteBase（反射/泛型端口常见）。"""
    msg: Dict[str, Any] = {
        "1": 10000,  # ConcreteBase
        "2": 1,  # alreadySetVal
        "110": {"2": dict(inner)},
    }
    if isinstance(index_of_concrete, int) and int(index_of_concrete) != 0:
        msg["110"]["1"] = int(index_of_concrete)

    # 对齐真源：MapBase(字典) 的 ConcreteBaseValue 需要额外写入 field_5 的类型描述，
    # 否则编辑器可能忽略 inner(MapBase) 里 ItemType 的 key/value，回退显示为“实体-实体字典”。
    #
    # 样本结构（decode 视角）：
    # - field_110.message.field_2.message: MapBase VarBase（含 ItemType.type_server.field_101=key/value）
    # - field_110.message.field_5.message.field_100.message.field_1.message:
    #     { field_1=10003(MapBase), field_102={field_1=key_vt, field_2=val_vt} }
    if isinstance(inner, dict) and int(inner.get("1") or 0) == 10003:
        item_type = inner.get("4")
        type_server = item_type.get("100") if isinstance(item_type, dict) else None
        kv = type_server.get("101") if isinstance(type_server, dict) else None
        key_vt = kv.get("1") if isinstance(kv, dict) else None
        val_vt = kv.get("2") if isinstance(kv, dict) else None
        if isinstance(key_vt, int) and isinstance(val_vt, int):
            msg["110"]["5"] = {
                "4": 1,
                "100": {
                    "1": {
                        "1": 10003,  # MapBase
                        "102": {
                            "1": int(key_vt),
                            "2": int(val_vt),
                            # 真源样本：还会带两个恒为 1 的标记字段（避免被游戏侧判为“未配置 map 类型”）。
                            "4": 1,
                            "5": 1,
                        },
                    }
                },
            }
    return msg


def _build_var_base_message_server(*, var_type_int: int, value: Any) -> Dict[str, Any]:
    """按 gia.proto 的 VarBase 结构编码 server 常量值。"""
    vt = int(var_type_int)
    item_type = _build_var_base_item_type_server(var_type_int=int(var_type_int))

    # Struct
    if vt == 25:
        struct_base: Dict[str, Any] = {"1": 10001, "2": 1, "4": item_type}
        if value is None:
            return struct_base

        items_value = None
        if isinstance(value, dict) and "items" in value:
            items_value = value.get("items")
        elif isinstance(value, (list, tuple)):
            items_value = list(value)
        if not isinstance(items_value, list):
            raise ValueError(f"结构体默认值仅支持 None / list / {{items:[...]}}，实际：{value!r}")

        entries: List[Dict[str, Any]] = []
        for item in items_value:
            # 支持显式指定项类型：{"var_type": "整数", "value": 1} / {"variable_type": "...", "default_value": ...}
            if isinstance(item, dict):
                explicit_vt = item.get("var_type_int")
                if isinstance(explicit_vt, int):
                    raw_value = item.get("value") if "value" in item else item.get("default_value")
                    coerced = _coerce_constant_value_for_var_type(var_type_int=int(explicit_vt), raw_value=raw_value)
                    entries.append(_build_var_base_message_server(var_type_int=int(explicit_vt), value=coerced))
                    continue
                raw_type = (
                    item.get("var_type")
                    if "var_type" in item
                    else item.get("variable_type")
                    if "variable_type" in item
                    else item.get("type")
                )
                raw_value = item.get("value") if "value" in item else item.get("default_value")
                if isinstance(raw_type, int):
                    item_vt = int(raw_type)
                    coerced = _coerce_constant_value_for_var_type(var_type_int=int(item_vt), raw_value=raw_value)
                    entries.append(_build_var_base_message_server(var_type_int=int(item_vt), value=coerced))
                    continue
                if raw_type is not None:
                    item_vt = _map_server_port_type_to_var_type_id(str(raw_type))
                    coerced = _coerce_constant_value_for_var_type(var_type_int=int(item_vt), raw_value=raw_value)
                    entries.append(_build_var_base_message_server(var_type_int=int(item_vt), value=coerced))
                    continue
            # 回退：按值字面量推断
            inferred_vt = _infer_var_type_int_from_raw_value(item)
            coerced = _coerce_constant_value_for_var_type(var_type_int=int(inferred_vt), raw_value=item)
            entries.append(_build_var_base_message_server(var_type_int=int(inferred_vt), value=coerced))

        struct_base["108"] = {"1": entries}
        return struct_base

    # List types (ArrayBase)
    list_elem_type_map: Dict[int, int] = {
        7: 2,  # GUID列表 -> GUID
        8: 3,  # 整数列表 -> 整数
        9: 4,  # 布尔值列表 -> 布尔值
        10: 5,  # 浮点数列表 -> 浮点数
        11: 6,  # 字符串列表 -> 字符串
        13: 1,  # 实体列表 -> 实体
        15: 12,  # 三维向量列表 -> 三维向量
        22: 20,  # 配置ID列表 -> 配置ID
        23: 21,  # 元件ID列表 -> 元件ID
        24: 17,  # 阵营列表 -> 阵营
        26: 25,  # 结构体列表 -> 结构体
    }
    elem_vt = list_elem_type_map.get(int(vt))
    if isinstance(elem_vt, int):
        if value is None:
            values_list: List[Any] = []
        elif isinstance(value, (list, tuple)):
            values_list = list(value)
        else:
            raise ValueError(f"列表默认值仅支持 None / list / tuple，实际：{value!r}（var_type={vt}）")

        entries: List[Dict[str, Any]] = []
        for element in values_list:
            coerced = _coerce_constant_value_for_var_type(var_type_int=int(elem_vt), raw_value=element)
            entries.append(_build_var_base_message_server(var_type_int=int(elem_vt), value=coerced))

        array_base: Dict[str, Any] = {"1": 10002, "2": 1, "4": item_type, "109": {"1": entries}}
        return array_base

    # String
    if vt == 6:
        return {"1": 5, "2": 1, "4": item_type, "105": {"1": str(value)}}

    # Float
    if vt == 5:
        # 真源对齐：0.0 常用 alreadySetVal=1 + empty bytes 表达（避免写入显式 0.0 的 fixed32）。
        # 例：拼装列表(浮点数列表) 的元素常量为 0.0 时，FloatBaseValue(field_104) 为空 bytes，但仍标记为已设置。
        fv = float(value)
        if float(fv) == 0.0:
            empty = format_binary_data_hex_text(b"")
            return {"1": 4, "2": 1, "4": item_type, "104": empty}
        return {"1": 4, "2": 1, "4": item_type, "104": {"1": float(fv)}}

    # Int
    if vt == 3:
        # 经验修正：对输入常量而言，“0”必须显式写入 IntBaseValue(field_102.field_1=0)，
        # 否则部分节点（例如 获取列表对应值.序号）在编辑器中会显示为空（raw_hex="" 不会渲染为 0）。
        iv = int(value)
        return {"1": 2, "2": 1, "4": item_type, "102": {"1": int(iv)}}

    # Bool (EnumBaseValue: 0/1)
    if vt == 4:
        # 对齐真源样本：false 常以 “alreadySetVal=1 + empty bytes” 表达（而不是显式写 0）
        if bool(value):
            return {"1": 6, "2": 1, "4": item_type, "106": {"1": 1}}
        empty = format_binary_data_hex_text(b"")
        return {"1": 6, "2": 1, "4": item_type, "106": empty}

    # Enum (EnumBaseValue: enum_item_id)
    if vt == 14:
        return {"1": 6, "2": 1, "4": item_type, "106": {"1": int(value)}}

    # Vector
    if vt == 12:
        if not (isinstance(value, (list, tuple)) and len(value) == 3):
            raise ValueError(f"三维向量常量期望 [x,y,z]，实际：{value!r}")
        x0, y0, z0 = value[0], value[1], value[2]

        # 允许 None：表示该分量未设置（写回时省略该字段，保持与 dump/export 的 roundtrip 一致性）。
        # 若三者均为 None，则写入 VectorBaseValue(empty bytes)，并省略 alreadySetVal（语义为“未设置”）。
        if x0 is None and y0 is None and z0 is None:
            empty = format_binary_data_hex_text(b"")
            return {"1": 7, "4": item_type, "107": empty}

        vec: Dict[str, Any] = {}
        if x0 is not None:
            vec["1"] = float(x0)
        if y0 is not None:
            vec["2"] = float(y0)
        if z0 is not None:
            vec["3"] = float(z0)

        return {"1": 7, "2": 1, "4": item_type, "107": {"1": vec}}

    # Id-like (GUID / Config / Prefab / LocalVariable 等)：用 IdBaseValue 承载 int32
    if vt in (1, 2, 16, 17, 20, 21):
        # 对齐真源样本：0 常以 “alreadySetVal=1 + empty bytes” 表达（而不是显式写 0）。
        # 该口径在 GraphVariables/default_value 等场景更常见；显式 0 可能导致官方侧更严格校验失败。
        iv = int(value)
        if int(iv) == 0:
            empty = format_binary_data_hex_text(b"")
            return {"1": 1, "2": 1, "4": item_type, "101": empty}
        return {"1": 1, "2": 1, "4": item_type, "101": {"1": int(iv)}}

    raise ValueError(f"暂不支持该 VarType 的常量写回：var_type={var_type_int} value={value!r}")


# -------------------- Public helpers (reusable) --------------------


def build_var_base_message_server(*, var_type_int: int, value: Any) -> Dict[str, Any]:
    """
    对外稳定入口：构造 server VarType 的 VarBase message（数值键 dict），可用于 `.gia` 与 `.gil` 场景。
    """
    return _build_var_base_message_server(var_type_int=int(var_type_int), value=value)


def build_var_base_message_server_empty(*, var_type_int: int) -> Dict[str, Any]:
    """
    对外稳定入口：构造“空/未设置”的 server VarType VarBase message（数值键 dict）。
    """
    return _build_var_base_message_server_empty(var_type_int=int(var_type_int))


def build_var_base_message_server_for_dict(
    *,
    dict_key_var_type_int: int,
    dict_value_var_type_int: int,
    default_value: Any,
) -> Dict[str, Any]:
    """
    对外稳定入口：构造“字典”类型的 VarBase(MapBase)（数值键 dict）。
    """
    return _build_var_base_message_server_for_dict(
        dict_key_var_type_int=int(dict_key_var_type_int),
        dict_value_var_type_int=int(dict_value_var_type_int),
        default_value=default_value,
    )


def build_var_base_item_type_server_for_dict(
    *,
    dict_key_var_type_int: int,
    dict_value_var_type_int: int,
) -> Dict[str, Any]:
    """对外稳定入口：构造 MapBase 的 itemType（显式携带 key/value VarType）。"""
    return _build_var_base_item_type_server_for_dict(
        dict_key_var_type_int=int(dict_key_var_type_int),
        dict_value_var_type_int=int(dict_value_var_type_int),
    )


def build_var_base_message_server_empty_for_dict_kv(
    *,
    dict_key_var_type_int: int,
    dict_value_var_type_int: int,
) -> Dict[str, Any]:
    """对外稳定入口：构造“空字典”的 MapBase VarBase，但显式携带 key/value 类型信息。"""
    return _build_var_base_message_server_empty_for_dict_kv(
        dict_key_var_type_int=int(dict_key_var_type_int),
        dict_value_var_type_int=int(dict_value_var_type_int),
    )


def build_var_base_message_server_empty_list_value(*, var_type_int: int) -> Dict[str, Any]:
    """对外稳定入口：构造“空列表”的 ArrayBase VarBase（用于占位 pins 与真源对齐）。"""
    return _build_var_base_message_server_empty_list_value(var_type_int=int(var_type_int))


def build_var_base_message_server_for_concrete_string_list(*, values: List[str]) -> Dict[str, Any]:
    """对外稳定入口：构造 ConcreteBase 需要的字符串列表 inner VarBase（用于多分支节点等）。"""
    return _build_var_base_message_server_for_concrete_string_list(values=[str(v) for v in list(values or [])])


def try_map_server_dict_type_text_to_kv_var_types(type_text: str) -> Optional[Tuple[int, int]]:
    """对外稳定入口：将“别名字典”类型文本映射为 (key_vt, value_vt)，无法解析返回 None。"""
    return _try_map_server_dict_type_text_to_kv_var_types(str(type_text or ""))




def map_server_port_type_to_var_type_id(port_type: str) -> int:
    """对外稳定入口：将 server port_type 文本映射为 VarType int（失败直接抛错）。"""
    return _map_server_port_type_to_var_type_id(str(port_type))


def infer_var_type_int_from_raw_value(raw_value: Any) -> int:
    """对外稳定入口：按值字面量推断 VarType int（用于常量写回）。"""
    return _infer_var_type_int_from_raw_value(raw_value)


def coerce_constant_value_for_port_type(*, port_type: str, raw_value: Any) -> Any:
    """对外稳定入口：按端口类型文本将 GraphModel.input_constants 的 raw_value 规整为可写回的值形态。"""
    return _coerce_constant_value_for_port_type(port_type=str(port_type), raw_value=raw_value)


def coerce_constant_value_for_var_type(*, var_type_int: int, raw_value: Any) -> Any:
    """对外稳定入口：将 raw_value 规整为指定 VarType 的常量值形态。"""
    return _coerce_constant_value_for_var_type(var_type_int=int(var_type_int), raw_value=raw_value)


def wrap_var_base_as_concrete_base(*, inner: Dict[str, Any], index_of_concrete: Optional[int]) -> Dict[str, Any]:
    """对外稳定入口：将 inner VarBase 包裹为 ConcreteBase（反射/泛型端口常见）。"""
    return _wrap_var_base_as_concrete_base(inner=dict(inner), index_of_concrete=index_of_concrete)

