from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from ugc_file_tools.integrations.graph_generater.type_registry_bridge import (
    is_supported_graph_variable_type_text,
    map_graph_variable_cn_type_to_var_type_int,
    parse_typed_dict_alias,
)

# 自定义变量 value/type message 的单一真源（与 NodeGraph VarBase 区分）。
from .value_message import (  # noqa: PLC2701
    build_custom_variable_type_descriptor as _build_custom_variable_type_descriptor,
    build_custom_variable_value_message as _build_custom_variable_value_message,
    build_dict_custom_variable_item as _build_dict_custom_variable_item,
    infer_dict_value_type_int as _infer_dict_value_type_int,
)

__all__ = [
    "CustomVariableSpec",
    "build_custom_variable_item_from_spec",
    "extract_explicit_type_text_from_variable_name",
    "infer_custom_variable_spec_from_default",
]


@dataclass(frozen=True, slots=True)
class CustomVariableSpec:
    group_name: str  # 关卡 / 玩家自身
    variable_name: str
    var_type_int: int
    default_value: Any
    dict_key_type_int: Optional[int] = None
    dict_value_type_int: Optional[int] = None


# === 强约束：这些变量在节点图侧被“按类型”读取，HTML 默认值往往是 [] 无法直接推断 ===
_SPECIAL_VAR_TYPE_OVERRIDES: Dict[str, int] = {
    # 预览控制图：严格读取 元件ID列表/三维向量列表（否则获取自定义变量会类型不匹配）
    "UI选关_预览配置_关卡号到展示元件ID_1": 23,  # 元件ID列表
    "UI选关_预览配置_关卡号到展示元件ID_2": 23,  # 元件ID列表
    "UI选关_预览配置_关卡号到展示位置偏移": 15,  # 三维向量列表
    "UI选关_预览配置_关卡号到第二元件自带偏移": 15,  # 三维向量列表
    "UI选关_预览配置_关卡号到展示旋转_1": 15,  # 三维向量列表
    "UI选关_预览配置_关卡号到展示旋转_2": 15,  # 三维向量列表
}

# dict 变量的 key/value 类型：默认 key=字符串(6)，但少量变量语义为 int->GUID 等。
_SPECIAL_DICT_KV_OVERRIDES: Dict[str, Tuple[int, int]] = {
    # 语义：玩家序号(int) -> 展示位置GUID(GUID)
    "UI选关_预览配置_玩家号到位置GUID": (3, 2),
}


_EXPLICIT_TYPE_TEXT_RE = re.compile(r"(?:^|_)(?P<type_text>[^_]+?)__", re.UNICODE)


def extract_explicit_type_text_from_variable_name(variable_name: str) -> Optional[str]:
    """
    从变量名中提取“显式类型标注”（不修改变量名本身）：
    - 约定格式：`..._<类型名>__...` 或 `<类型名>__...`
    - 类型名必须是 Graph_Generater.type_registry 支持的类型文本（含 typed dict alias，如“整数-字符串字典”）
    """
    raw = str(variable_name or "").strip()
    if raw == "":
        return None
    for m in _EXPLICIT_TYPE_TEXT_RE.finditer(raw):
        cand = str(m.group("type_text") or "").strip()
        if cand == "":
            continue
        if is_supported_graph_variable_type_text(cand):
            return cand
    return None


def _coerce_bool_default(value: Any, *, key: str) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, (int, float)):
        fv = float(value)
        if not (fv == fv):
            raise ValueError(f"{key} 默认值为 NaN（不支持）")
        return bool(int(fv) != 0)
    text = str(value).strip().lower()
    if text == "":
        raise ValueError(f"{key} 默认值为空字符串，无法解析为布尔值")
    if text in ("1", "true", "yes", "y", "是", "对", "真", "t"):
        return True
    if text in ("0", "false", "no", "n", "否", "错", "假", "f"):
        return False
    raise ValueError(f"{key} 默认值不是可解析的布尔值：{value!r}")


def _infer_list_var_type_int(*, name: str, values: list[Any]) -> int:
    # 非空：按元素类型推断
    if values:
        if all(isinstance(x, str) for x in values):
            return 11  # 字符串列表
        if all(isinstance(x, bool) for x in values):
            return 9  # 布尔值列表（0/1）
        if all(isinstance(x, (int, bool)) for x in values):
            return 8  # 整数列表
        if all(isinstance(x, (int, float, bool)) for x in values):
            # 若出现 float，认为是浮点列表；否则仍归为整数列表
            return 10 if any(isinstance(x, float) for x in values) else 8
        # 兜底：按字符串列表写回（更容忍）
        return 11

    # 空列表：按变量名规则推断（尽量贴近节点图/约定）
    n = str(name or "")
    if "元件ID" in n:
        return 23
    if "配置ID" in n:
        return 22
    if "GUID" in n:
        return 7
    if ("旋转" in n) or ("偏移" in n):
        return 15
    # 常见：xxx列表
    if "列表" in n:
        return 11
    return 11


def _infer_scalar_id_like_var_type_int(*, name: str) -> Optional[int]:
    n = str(name or "").strip()
    if n == "":
        return None
    # “实体/GUID/元件ID/配置ID”等是 int-like，但类型不同；先按变量名强约束。
    if n.endswith("实体") or ("_实体" in n):
        return 1
    if n.endswith("GUID") or ("GUID" in n):
        return 2
    if "元件ID" in n:
        return 21
    if "配置ID" in n:
        return 20
    return None


def _infer_dict_kv_types_from_explicit_type(type_text: str) -> Tuple[int, int]:
    is_typed_dict, key_type_text, value_type_text = parse_typed_dict_alias(type_text)
    if not is_typed_dict:
        raise ValueError(f"internal error: not a typed dict alias: {type_text!r}")
    key_vt = map_graph_variable_cn_type_to_var_type_int(key_type_text)
    val_vt = map_graph_variable_cn_type_to_var_type_int(value_type_text)
    return int(key_vt), int(val_vt)


def infer_custom_variable_spec_from_default(*, group_name: str, variable_name: str, default_value: Any) -> CustomVariableSpec:
    """
    从 (group_name, variable_name, default_value) 推断“实体自定义变量”类型与默认值：
    - 支持显式类型标注（`..._<类型名>__...`），类型名必须为 Graph_Generater.type_registry 支持的类型
    - 兼容 typed dict alias（例如 `整数-字符串字典`）
    - 无显式标注时，按：强约束表 → 值结构(dict/list/scalar) → 变量名启发式(GUID/元件ID/配置ID/实体) → 值类型 推断
    """
    g = str(group_name or "").strip()
    n = str(variable_name or "").strip()
    if g not in ("关卡", "玩家自身"):
        raise ValueError(f"未知变量组名：{g!r}（仅支持：关卡 / 玩家自身）")
    if n == "":
        raise ValueError("variable_name 不能为空")

    # 0) 显式类型标注：最高优先级
    explicit_type_text = extract_explicit_type_text_from_variable_name(n)
    if explicit_type_text is not None:
        vt = map_graph_variable_cn_type_to_var_type_int(explicit_type_text)
        if int(vt) == 27:
            # dict：typed alias 或 plain "字典"
            is_typed_dict, _k_text, _v_text = parse_typed_dict_alias(explicit_type_text)
            if is_typed_dict:
                key_vt, val_vt = _infer_dict_kv_types_from_explicit_type(explicit_type_text)
            else:
                key_vt = 6
                val_vt = int(_infer_dict_value_type_int(default_value)) if isinstance(default_value, dict) else 6
            if default_value is None:
                default_map: dict = {}
            elif isinstance(default_value, dict):
                default_map = dict(default_value)
            else:
                raise TypeError(f"显式声明为字典，但默认值不是 dict：{g}.{n} -> {type(default_value).__name__}")
            return CustomVariableSpec(
                group_name=g,
                variable_name=n,
                var_type_int=27,
                default_value=default_map,
                dict_key_type_int=int(key_vt),
                dict_value_type_int=int(val_vt),
            )

        # list：显式声明为列表类型时要求默认值为 list/tuple/None（便于 fail-fast）
        if str(explicit_type_text).endswith("列表") and default_value is not None and not isinstance(default_value, (list, tuple)):
            raise TypeError(f"显式声明为列表，但默认值不是 list/tuple：{g}.{n} -> {type(default_value).__name__}")

        dv = default_value
        if int(vt) == 4:
            dv = _coerce_bool_default(default_value, key=f"{g}.{n}")
        return CustomVariableSpec(group_name=g, variable_name=n, var_type_int=int(vt), default_value=dv)

    # 1) 强制覆盖（节点图严格依赖类型）
    forced = _SPECIAL_VAR_TYPE_OVERRIDES.get(n)
    if isinstance(forced, int):
        return CustomVariableSpec(group_name=g, variable_name=n, var_type_int=int(forced), default_value=default_value)

    # 2) dict
    if isinstance(default_value, dict):
        override_kv = _SPECIAL_DICT_KV_OVERRIDES.get(n)
        if override_kv is not None:
            key_vt, val_vt = override_kv
        else:
            key_vt, val_vt = 6, _infer_dict_value_type_int(default_value)
        return CustomVariableSpec(
            group_name=g,
            variable_name=n,
            var_type_int=27,
            default_value=dict(default_value),
            dict_key_type_int=int(key_vt),
            dict_value_type_int=int(val_vt),
        )

    # 3) list
    if isinstance(default_value, list):
        vt = _infer_list_var_type_int(name=n, values=list(default_value))
        return CustomVariableSpec(group_name=g, variable_name=n, var_type_int=int(vt), default_value=list(default_value))

    # 4) scalar：先做 ID-like 名称规则约束，再按值类型推断
    id_like = _infer_scalar_id_like_var_type_int(name=n)
    if isinstance(id_like, int):
        return CustomVariableSpec(group_name=g, variable_name=n, var_type_int=int(id_like), default_value=default_value)

    if isinstance(default_value, bool):
        return CustomVariableSpec(group_name=g, variable_name=n, var_type_int=4, default_value=bool(default_value))
    if isinstance(default_value, int):
        return CustomVariableSpec(group_name=g, variable_name=n, var_type_int=3, default_value=int(default_value))
    if isinstance(default_value, float):
        return CustomVariableSpec(group_name=g, variable_name=n, var_type_int=5, default_value=float(default_value))
    return CustomVariableSpec(group_name=g, variable_name=n, var_type_int=6, default_value=str(default_value or ""))


def build_custom_variable_item_from_spec(spec: CustomVariableSpec) -> Dict[str, Any]:
    """
    构造实体自定义变量 item（可直接插入 root4/5/1[*].override_variables(group1) 列表）。
    结构与 `level_custom_variables_importer` 保持一致，保证与主程序类型体系一致。
    """
    vt = int(spec.var_type_int)
    if vt == 27:
        key_vt = int(spec.dict_key_type_int) if spec.dict_key_type_int is not None else 6
        val_vt = int(spec.dict_value_type_int) if spec.dict_value_type_int is not None else 6
        if not isinstance(spec.default_value, dict):
            raise TypeError("dict spec default_value must be dict")
        return _build_dict_custom_variable_item(
            default_value_by_key=dict(spec.default_value),
            variable_name=str(spec.variable_name),
            dict_key_type_int=int(key_vt),
            dict_value_type_int=int(val_vt),
        )

    return {
        "2": str(spec.variable_name),
        "3": int(vt),
        "4": _build_custom_variable_value_message(var_type_int=int(vt), default_value=spec.default_value),
        "5": 1,
        "6": _build_custom_variable_type_descriptor(var_type_int=int(vt)),
    }

