from __future__ import annotations

from typing import Any, Callable, Optional, Tuple


def parse_typed_dict_alias_text(type_text: str) -> Optional[Tuple[str, str]]:
    """
    解析“别名字典”类型文本，返回 (key_type_text, value_type_text)。

    支持形态（Graph_Generater/编辑器常见）：
    - "键类型-值类型字典"
    - "键类型_值类型字典"
    - "字典(键类型→值类型)" / "字典(键类型->值类型)"

    说明：
    - 只做纯文本拆分，不做 VarType 映射。
    - 不在此处做“泛型/合法性”判定：由上层根据使用场景决定。
    """
    t = str(type_text or "").strip()
    if t == "":
        return None

    # 兼容端口名形态：字典_字符串到整数 / 字典-字符串到整数
    if t.startswith("字典_") or t.startswith("字典-"):
        t = t[len("字典_") :].strip() if t.startswith("字典_") else t[len("字典-") :].strip()
        if t == "":
            return None

    # 兼容形态：字典(字符串→整数) / 字典(字符串->整数)
    if t.startswith("字典(") and t.endswith(")"):
        inner = t[len("字典(") : -1].strip()
        if "→" in inner:
            left, right = inner.split("→", 1)
        elif "->" in inner:
            left, right = inner.split("->", 1)
        else:
            return None
        key_text = str(left).strip()
        val_text = str(right).strip()
        if key_text == "" or val_text == "":
            return None
        return key_text, val_text

    # 兼容形态：字符串到整数 / GUID到实体列表 等（常见于端口名，不带“字典”后缀）
    if "到" in t and (not t.endswith("字典")):
        left, right = t.split("到", 1)
        key_text = str(left).strip()
        val_text = str(right).strip()
        if key_text == "" or val_text == "":
            return None
        return key_text, val_text

    if not t.endswith("字典"):
        return None
    core = t[: -len("字典")].strip()
    if core == "":
        return None

    if "-" in core:
        left, right = core.split("-", 1)
    elif "_" in core:
        left, right = core.split("_", 1)
    else:
        return None
    key_text = str(left).strip()
    val_text = str(right).strip()
    if key_text == "" or val_text == "":
        return None
    return key_text, val_text


def try_resolve_dict_kv_var_types_from_type_text(
    type_text: str,
    *,
    map_port_type_text_to_var_type_id: Callable[[str], int],
    reject_generic: bool = True,
) -> Optional[Tuple[int, int]]:
    """
    将“别名字典”类型文本解析为 (dict_key_var_type_int, dict_value_var_type_int)。

    - 若无法解析出 key/value 文本，返回 None。
    - 若 reject_generic=True 且 key/value 文本包含“泛型”，返回 None。
    - VarType 映射使用调用方传入的严格 mapper；无法映射会直接抛错（fail-fast）。
    """
    parsed = parse_typed_dict_alias_text(str(type_text or ""))
    if parsed is None:
        return None
    key_text, val_text = parsed
    if bool(reject_generic) and (("泛型" in key_text) or ("泛型" in val_text)):
        return None
    key_vt = int(map_port_type_text_to_var_type_id(str(key_text)))
    val_vt = int(map_port_type_text_to_var_type_id(str(val_text)))
    if int(key_vt) <= 0 or int(val_vt) <= 0:
        return None
    return int(key_vt), int(val_vt)


def try_infer_dict_kv_var_types_from_default_value(
    default_value: Any,
    *,
    infer_var_type_int_from_raw_value: Callable[[Any], int],
) -> Optional[Tuple[int, int]]:
    """
    从字典默认值推断 (key_vt, value_vt)。

    仅在 default_value 为非空 dict 时启用；否则返回 None。
    """
    if not isinstance(default_value, dict):
        return None
    if not default_value:
        return None

    key_vts = {int(infer_var_type_int_from_raw_value(k)) for k in default_value.keys()}
    val_vts = {int(infer_var_type_int_from_raw_value(v)) for v in default_value.values()}

    if len(key_vts) != 1 or len(val_vts) != 1:
        raise ValueError(
            "字典默认值的键/值类型不唯一，无法推断："
            f"key_vts={sorted(key_vts)} val_vts={sorted(val_vts)} default_value={default_value!r}"
        )
    key_vt = next(iter(key_vts))
    val_vt = next(iter(val_vts))
    if int(key_vt) <= 0 or int(val_vt) <= 0:
        raise ValueError(f"字典默认值推断得到非法 VarType：key_vt={key_vt} val_vt={val_vt}")
    return int(key_vt), int(val_vt)

