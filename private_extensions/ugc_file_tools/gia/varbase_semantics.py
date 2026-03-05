from __future__ import annotations

"""
`.gia` 语义层（VarBase）辅助工具。

注意：这里不是 protobuf-like codec（编解码层/线级规则）；这里只在“decoded_field_map /
numeric_message”这类中间表示之上做语义提取与小工具函数。

历史上本模块曾命名为 `gia_protobuf_like.py`，为了兼容旧 import，该文件现在仅作为薄 wrapper
保留；新代码应优先引用本模块。
"""

import re
from typing import Any, Dict, Iterable, List, Optional

from ugc_file_tools.gil_dump_codec.protobuf_like_bridge import (
    decoded_field_map_to_numeric_message,
    decoded_node_to_numeric_value,
)
from ugc_file_tools.gil_dump_codec.protobuf_like import decode_message_to_field_map

DecodedNode = Dict[str, Any]
FieldMap = Dict[str, Any]

__all__ = [
    "DecodedNode",
    "FieldMap",
    "decoded_field_map_to_numeric_message",
    "decoded_node_to_numeric_value",
    "as_list",
    "field_key",
    "is_empty_length_delimited",
    "get_message_node",
    "iter_message_nodes",
    "get_int_node",
    "get_float32_node",
    "get_utf8_node",
    "get_field",
    "get_int_field",
    "get_float32_field",
    "get_utf8_field",
    "get_message_field",
    "extract_varbase_value",
    "coerce_bool_value",
]


def as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def field_key(field_number: int) -> str:
    return "field_" + str(int(field_number))


def is_empty_length_delimited(node: Any) -> bool:
    return (
        isinstance(node, dict)
        and node.get("raw_hex") == ""
        and "message" not in node
        and "utf8" not in node
    )


_RAW_HEX_RE = re.compile(r"^[0-9a-fA-F]*$")


def _try_decode_length_delimited_raw_hex_to_message(node: Any) -> Optional[FieldMap]:
    """
    尝试把 protobuf-like 解码产物中的 length-delimited 节点（raw_hex）反解成嵌套 message。

    背景：
    - `protobuf_like.decode_message_to_field_map()` 对 length-delimited 的策略是“先判 utf8 文本，再判嵌套 message”；
    - 但 VarBase 的 StringBaseValue 等字段（例如 field_105）本质上是嵌套 message，
      其 wire bytes 形如 `0a <len> <utf8 bytes>`，会被误判为“可读文本”从而不展开为 `{message:{...}}`；
    - 这会导致语义层 `get_message_field()` / `extract_varbase_value()` 取不到 message，进而把字符串/字典默认值解析成空。
    """
    if not isinstance(node, dict):
        return None
    if isinstance(node.get("message"), dict):
        return node["message"]
    if is_empty_length_delimited(node):
        return {}

    raw_hex = node.get("raw_hex")
    if not isinstance(raw_hex, str) or raw_hex == "":
        return None
    # 避免 bytes.fromhex() 抛错（不使用 try/except）
    if len(raw_hex) % 2 != 0:
        return None
    if _RAW_HEX_RE.fullmatch(raw_hex) is None:
        return None

    raw_bytes = bytes.fromhex(raw_hex)
    nested, consumed = decode_message_to_field_map(
        data_bytes=raw_bytes,
        start_offset=0,
        end_offset=len(raw_bytes),
        remaining_depth=8,
    )
    if consumed != len(raw_bytes):
        return None
    if not isinstance(nested, dict) or len(nested) == 0:
        return None
    return nested


def get_message_node(node: Any) -> Optional[FieldMap]:
    if isinstance(node, dict) and isinstance(node.get("message"), dict):
        return node["message"]
    if is_empty_length_delimited(node):
        return {}
    decoded = _try_decode_length_delimited_raw_hex_to_message(node)
    if decoded is not None:
        return decoded
    return None


def iter_message_nodes(nodes: Any) -> Iterable[FieldMap]:
    for element in as_list(nodes):
        msg = get_message_node(element)
        if msg is None:
            continue
        yield msg


def get_int_node(node: Any) -> Optional[int]:
    if not isinstance(node, dict):
        return None
    value = node.get("int")
    if isinstance(value, int):
        return int(value)
    return None


def get_float32_node(node: Any) -> Optional[float]:
    if not isinstance(node, dict):
        return None
    value = node.get("fixed32_float")
    if isinstance(value, float):
        return float(value)
    if isinstance(value, int):
        return float(value)
    return None


def get_utf8_node(node: Any) -> Optional[str]:
    if not isinstance(node, dict):
        return None
    value = node.get("utf8")
    if isinstance(value, str):
        text = value.strip()
        if text != "":
            return text
    return None


def get_field(message: FieldMap, field_number: int) -> Any:
    if not isinstance(message, dict):
        return None
    return message.get(field_key(field_number))


def get_int_field(message: FieldMap, field_number: int) -> Optional[int]:
    return get_int_node(get_field(message, field_number))


def get_float32_field(message: FieldMap, field_number: int) -> Optional[float]:
    return get_float32_node(get_field(message, field_number))


def get_utf8_field(message: FieldMap, field_number: int) -> Optional[str]:
    return get_utf8_node(get_field(message, field_number))


def get_message_field(message: FieldMap, field_number: int) -> Optional[FieldMap]:
    return get_message_node(get_field(message, field_number))


def extract_varbase_value(varbase_message: FieldMap) -> Any:
    """
    将 `.gia` 的 VarBase（按真源 NodeEditorPack `gia.proto` 的字段号口径）提取为 Python 值（尽力而为）。
    """

    cls = get_int_field(varbase_message, 1)
    if not isinstance(cls, int) or cls == 0:
        return None

    # ConcreteBase: unwrap inner value
    if cls == 10000:
        concrete = get_message_field(varbase_message, 110)
        if concrete is None:
            return None
        inner = get_message_field(concrete, 2)
        if inner is None:
            return None
        return extract_varbase_value(inner)

    # IdBase / IntBase / FloatBase / StringBase / EnumBase
    if cls == 1:
        msg = get_message_field(varbase_message, 101) or {}
        return get_int_field(msg, 1) or 0
    if cls == 2:
        msg = get_message_field(varbase_message, 102) or {}
        return get_int_field(msg, 1) or 0
    if cls == 4:
        msg = get_message_field(varbase_message, 104) or {}
        value = get_float32_field(msg, 1)
        return 0.0 if value is None else float(value)
    if cls == 5:
        # StringBaseValue(field_105) 的“空 bytes”在语义上既可能是：
        # - 未设置（alreadySetVal(field_2) 缺失）：作为 type carrier（常见于已连线 pins）
        # - 显式空字符串（alreadySetVal=1 且 field_105 为空/或 text=""）
        #
        # 关键：未设置时应返回 None，避免上层把“连线输入”的字符串误显示为 "" 并造成误解。
        already_set = get_int_field(varbase_message, 2)
        raw_node = get_field(varbase_message, 105)
        if already_set is None and is_empty_length_delimited(raw_node):
            return None
        msg = get_message_node(raw_node) or {}
        return get_utf8_field(msg, 1) or ""
    if cls == 6:
        msg = get_message_field(varbase_message, 106) or {}
        return get_int_field(msg, 1) or 0

    # VectorBase
    if cls == 7:
        msg = get_message_field(varbase_message, 107)
        if msg is None:
            return None
        vec = get_message_field(msg, 1)
        if vec is None:
            return None
        x = get_float32_field(vec, 1)
        y = get_float32_field(vec, 2)
        z = get_float32_field(vec, 3)
        return [x, y, z]

    # StructBase: repeated VarBase items = 1
    if cls == 10001:
        msg = get_message_field(varbase_message, 108)
        if msg is None:
            return None
        items: List[Any] = []
        for item_msg in iter_message_nodes(get_field(msg, 1)):
            items.append(extract_varbase_value(item_msg))
        return items

    # ArrayBase: repeated VarBase entries = 1
    if cls == 10002:
        msg = get_message_field(varbase_message, 109)
        if msg is None:
            return None
        entries: List[Any] = []
        for entry_msg in iter_message_nodes(get_field(msg, 1)):
            entries.append(extract_varbase_value(entry_msg))
        return entries

    # MapBase: repeated VarBase mapPairs = 1 (each should be MapPair)
    if cls == 10003:
        msg = get_message_field(varbase_message, 112)
        if msg is None:
            return None
        pairs: List[Any] = []
        for pair_msg in iter_message_nodes(get_field(msg, 1)):
            pairs.append(extract_varbase_value(pair_msg))
        return pairs

    # MapPair: key/value are VarBase
    if cls == 10007:
        msg = get_message_field(varbase_message, 111)
        if msg is None:
            return None
        key_msg = get_message_field(msg, 1)
        val_msg = get_message_field(msg, 2)
        if key_msg is None or val_msg is None:
            return None
        return [extract_varbase_value(key_msg), extract_varbase_value(val_msg)]

    return None


def coerce_bool_value(value: Any) -> Any:
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, list):
        return [coerce_bool_value(v) for v in value]
    return value


