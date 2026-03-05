from __future__ import annotations

import struct
from typing import Any, Mapping

from ugc_file_tools.gil_dump_codec.protobuf_like import format_binary_data_hex_text

__all__ = [
    "build_custom_variable_type_descriptor",
    "infer_dict_value_type_int",
    "build_custom_variable_value_message",
    "build_dict_custom_variable_item",
]


def _pack_vector3_to_bytes(value: Any) -> bytes:
    if value is None:
        return b""
    if isinstance(value, dict):
        # 兼容：{x:...,y:...,z:...} 或 {1:x,2:y,3:z}
        x = value.get("x", value.get("1", 0.0))
        y = value.get("y", value.get("2", 0.0))
        z = value.get("z", value.get("3", 0.0))
        xf, yf, zf = float(x or 0.0), float(y or 0.0), float(z or 0.0)
    elif isinstance(value, (list, tuple)) and len(value) == 3:
        xf, yf, zf = float(value[0]), float(value[1]), float(value[2])
    elif isinstance(value, str):
        # 兼容："(1,2,3)" / "1,2,3"
        text = value.strip().strip("()")
        parts = [p.strip() for p in text.split(",") if p.strip() != ""]
        if len(parts) != 3:
            raise ValueError(f"无法解析三维向量默认值：{value!r}")
        xf, yf, zf = float(parts[0]), float(parts[1]), float(parts[2])
    else:
        raise TypeError(f"无法将默认值转为三维向量：{value!r}")

    if xf == 0.0 and yf == 0.0 and zf == 0.0:
        # 与真源样本对齐：零向量常用 empty bytes 表达（减少写回差异）
        return b""
    # 经验：向量常以 3x float32 little-endian 表达
    return struct.pack("<fff", float(xf), float(yf), float(zf))


def _value_field_key_for_custom_variable(*, var_type_int: int) -> str:
    return str(int(var_type_int) + 10)


def build_custom_variable_type_descriptor(
    *,
    var_type_int: int,
    dict_value_type_int: int | None = None,
    dict_key_type_int: int | None = None,
) -> dict[str, Any]:
    """
    构造自定义变量条目中的 `item['6']`（type descriptor）。

    注意：
    - 该结构用于实体/元件模板的“自定义变量”（不是 NodeGraph 的 VarBase）。
    - dict 的 key_type 在样本中通常不单独落在 descriptor 内（主要在 value message 内表达），这里仍保留入参以便调用侧保持一致签名。
    """
    empty = format_binary_data_hex_text(b"")
    vt = int(var_type_int)
    if vt != 27:
        return {"1": int(vt), "2": empty}
    val_vt = int(dict_value_type_int) if dict_value_type_int is not None else 6
    _ = dict_key_type_int
    return {"1": 27, "2": {"503": int(val_vt)}}


def _coerce_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"列表默认值必须为 list/tuple 或 None，实际：{value!r}")


def _coerce_int_list(value: Any) -> list[int]:
    raw_list = _coerce_list(value)
    out: list[int] = []
    for x in raw_list:
        if x is None:
            out.append(0)
            continue
        if isinstance(x, bool):
            out.append(int(1 if x else 0))
            continue
        if isinstance(x, int):
            out.append(int(x))
            continue
        if isinstance(x, float):
            if not (x == x):
                raise ValueError("整数列表默认值包含 NaN（不支持）")
            out.append(int(x))
            continue
        text = str(x).strip()
        out.append(int(float(text))) if text else out.append(0)
    return out


def _coerce_float_list(value: Any) -> list[float]:
    raw_list = _coerce_list(value)
    out: list[float] = []
    for x in raw_list:
        if x is None:
            out.append(0.0)
            continue
        if isinstance(x, bool):
            out.append(1.0 if x else 0.0)
            continue
        if isinstance(x, (int, float)):
            fv = float(x)
            if not (fv == fv):
                raise ValueError("浮点列表默认值包含 NaN（不支持）")
            out.append(float(fv))
            continue
        text = str(x).strip()
        fv2 = float(text) if text else 0.0
        if not (fv2 == fv2):
            raise ValueError("浮点列表默认值包含 NaN（不支持）")
        out.append(float(fv2))
    return out


def _coerce_bool_list_as_ints(value: Any) -> list[int]:
    raw_list = _coerce_list(value)
    out: list[int] = []
    for x in raw_list:
        if isinstance(x, bool):
            out.append(int(1 if x else 0))
            continue
        if isinstance(x, int):
            out.append(int(1 if int(x) != 0 else 0))
            continue
        if isinstance(x, str):
            s = x.strip().lower()
            if s in ("true", "1", "yes", "y", "是"):
                out.append(1)
                continue
            if s in ("false", "0", "no", "n", "否", ""):
                out.append(0)
                continue
        if x is None:
            out.append(0)
            continue
        raise TypeError(f"布尔值列表元素不支持：{x!r}")
    return out


def _coerce_string_list(value: Any) -> list[str]:
    raw_list = _coerce_list(value)
    return [str(x if x is not None else "") for x in raw_list]


def infer_dict_value_type_int(default_value_by_key: Mapping[Any, Any]) -> int:
    """
    推断字典变量 value_type（仅支持：整数/浮点/字符串）。
    - 空字典：fallback 为字符串（最安全）
    - bool：按整数 0/1 处理
    - 混合类型：直接抛错（fail-fast）
    """
    kinds: set[int] = set()
    for v in (default_value_by_key or {}).values():
        if v is None:
            continue
        if isinstance(v, bool):
            kinds.add(3)
            continue
        if isinstance(v, int):
            kinds.add(3)
            continue
        if isinstance(v, float):
            if not (v == v):
                raise ValueError("字典默认值包含 NaN（不支持）")
            kinds.add(5)
            continue
        if isinstance(v, str):
            kinds.add(6)
            continue
        raise TypeError(f"字典默认值仅支持 int/float/str/bool/None，实际：{type(v).__name__}")
    if not kinds:
        return 6
    if len(kinds) != 1:
        raise ValueError(f"字典默认值类型混杂，无法写回单一 value_type：{sorted(kinds)}")
    return int(list(kinds)[0])


def build_custom_variable_value_message(*, var_type_int: int, default_value: Any) -> dict[str, Any]:
    """
    构造自定义变量条目中的 `item['4']`（值 message）。

    注意：
    - 该结构不是 NodeGraph 的 VarBase，而是 `.gil`/实体模板/实例使用的自定义变量值结构。
    - dict 的 value message 需要在 `build_dict_custom_variable_item` 中整体构造（避免遗漏 keys/values/meta）。
    """
    vt = int(var_type_int)
    empty = format_binary_data_hex_text(b"")
    value_key = _value_field_key_for_custom_variable(var_type_int=vt)

    # Dict（value_key=37）
    if vt == 27:
        raise RuntimeError("internal error: dict value message must be built by build_dict_custom_variable_item")

    msg: dict[str, Any] = {
        "1": vt,
        "2": {"1": vt, "2": empty},
    }

    # Vector3（value_key=22）：按 bytes 写入
    if vt == 12:
        packed = _pack_vector3_to_bytes(default_value)
        msg[value_key] = {"1": format_binary_data_hex_text(packed)}
        return msg

    # Int / GUID / Entity / Enum / Faction / ComponentId：按“整数 varint”写入
    if vt in (1, 2, 3, 14, 17, 21):
        if default_value is None:
            iv = 0
        elif isinstance(default_value, bool):
            iv = int(1 if default_value else 0)
        elif isinstance(default_value, int):
            iv = int(default_value)
        elif isinstance(default_value, float):
            if not (default_value == default_value):
                raise ValueError("整数默认值为 NaN（不支持）")
            iv = int(default_value)
        else:
            text = str(default_value).strip()
            iv = int(float(text)) if text else 0
        msg[value_key] = {} if iv == 0 else {"1": int(iv)}
        return msg

    # Bool（Enum-like：0/1）
    if vt == 4:
        bv = bool(default_value)
        msg[value_key] = {} if not bv else {"1": 1}
        return msg

    # Float
    if vt == 5:
        if default_value is None:
            fv = 0.0
        elif isinstance(default_value, bool):
            fv = float(1.0 if default_value else 0.0)
        elif isinstance(default_value, (int, float)):
            fv = float(default_value)
        else:
            text = str(default_value).strip()
            fv = float(text) if text else 0.0
        if not (float(fv) == float(fv)):
            raise ValueError("浮点默认值为 NaN（不支持）")
        msg[value_key] = {} if float(fv) == 0.0 else {"1": float(fv)}
        return msg

    # String
    if vt == 6:
        msg[value_key] = {"1": str(default_value or "")}
        return msg

    # ConfigId（与 UI 写回口径一致；value_key=30）
    if vt == 20:
        v = int(default_value or 0)
        value_30: Any = empty if v == 0 else {"1": 1, "2": int(v)}
        msg[value_key] = {"1": value_30}
        return msg

    # StringList
    if vt == 11:
        values = _coerce_string_list(default_value)
        msg[value_key] = {} if not values else {"1": values}
        return msg

    # IntList / GuidList / EntityList / ConfigIdList / ComponentIdList / CampList（按 repeated varint 写入）
    if vt in (7, 8, 13, 22, 23, 24):
        out = _coerce_int_list(default_value)
        msg[value_key] = {} if not out else {"1": out}
        return msg

    # FloatList
    if vt == 10:
        out_f = _coerce_float_list(default_value)
        msg[value_key] = {} if not out_f else {"1": out_f}
        return msg

    # BoolList（按 repeated varint 0/1 写入）
    if vt == 9:
        out_b = _coerce_bool_list_as_ints(default_value)
        msg[value_key] = {} if not out_b else {"1": out_b}
        return msg

    # Vector3List（value_key=25）：repeated message，每个元素与 Vector3 同结构（field_1 bytes）
    if vt == 15:
        values = _coerce_list(default_value)
        if not values:
            msg[value_key] = {}
            return msg
        nodes = [{"1": format_binary_data_hex_text(_pack_vector3_to_bytes(v))} for v in values]
        msg[value_key] = {"1": nodes}
        return msg

    raise ValueError(f"暂不支持该自定义变量类型写入：var_type_int={vt}")


def build_dict_custom_variable_item(
    *,
    variable_name: str,
    default_value_by_key: Mapping[Any, Any],
    dict_key_type_int: int | None = None,
    dict_value_type_int: int | None = None,
) -> dict[str, Any]:
    """
    构造 dict 自定义变量 item（含 `item['4']` 的 keys/values 列表与 `item['6']` descriptor）。
    """
    name = str(variable_name or "").strip()
    if name == "":
        raise ValueError("variable_name 不能为空")

    key_vt = int(dict_key_type_int) if isinstance(dict_key_type_int, int) else 6
    val_vt = int(dict_value_type_int) if isinstance(dict_value_type_int, int) else infer_dict_value_type_int(default_value_by_key)

    # 仅稳定支持：key=int/string（其余 key 类型需要样本确认）
    if key_vt not in (3, 6):
        raise ValueError(f"暂不支持该字典 key_type：{key_vt}（variable={name!r}）")

    default_map = dict(default_value_by_key or {})

    # sort keys for stable writeback
    keys_sorted: list[Any]
    if key_vt == 3:
        keys_sorted = sorted({int(k) for k in default_map.keys() if str(k).strip() != ""})
    else:
        keys_sorted = sorted({str(k).strip() for k in default_map.keys() if str(k).strip() != ""}, key=lambda s: s.casefold())

    # non-empty default values: only support a safe subset
    if keys_sorted:
        allowed_value_types = {1, 2, 3, 4, 5, 6, 14, 17, 20, 21, 7, 8, 9, 10, 11, 13, 22, 23, 24, 12, 15}
        if val_vt not in allowed_value_types:
            raise ValueError(f"暂不支持该字典 value_type：{val_vt}（variable={name!r}）")

    dict_meta_code = int(60 + int(val_vt))

    keys_nodes = [build_custom_variable_value_message(var_type_int=int(key_vt), default_value=k) for k in keys_sorted]
    vals_nodes = [build_custom_variable_value_message(var_type_int=int(val_vt), default_value=default_map.get(k)) for k in keys_sorted]

    dict_value_node: dict[str, Any] = {
        "501": keys_nodes,
        "502": vals_nodes,
        "503": int(key_vt),
        "504": int(val_vt),
    }

    value_message: dict[str, Any] = {
        "1": 27,
        "2": {
            "1": 27,
            "2": {
                "2": int(dict_meta_code),
                "502": int(key_vt),
                "503": int(val_vt),
            },
        },
        "37": dict_value_node,
    }

    return {
        "2": str(name),
        "3": 27,
        "4": value_message,
        "5": 1,
        "6": build_custom_variable_type_descriptor(var_type_int=27, dict_key_type_int=int(key_vt), dict_value_type_int=int(val_vt)),
    }

