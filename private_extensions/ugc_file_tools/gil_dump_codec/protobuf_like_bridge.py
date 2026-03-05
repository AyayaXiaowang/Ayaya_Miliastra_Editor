from __future__ import annotations

"""
protobuf_like_bridge.py

目标：集中维护 “decoded_field_map ↔ numeric_message ↔ binary_data_text” 的桥接能力。

说明：
- decoded_field_map：`decode_message_to_field_map(...)` 的输出（key 为 "field_<n>"）。
- numeric_message：`encode_message(...)` 接受的“数值键 dict”（key 为 "1"/"2"/...）。
- binary_data_text：dump-json 侧 bytes 的文本表示（形如 "<binary_data> 0A 01 ..."）。

本模块不实现任何 protobuf-like wire 规则：底层判定与编解码唯一真源仍在 `protobuf_like.py`。
这里仅做表示层互转，避免工具间重复实现导致口径漂移。
"""

from typing import Any, Dict, Mapping, Tuple

from .protobuf_like import (
    decode_message_to_field_map,
    encode_message,
    format_binary_data_hex_text,
    parse_binary_data_hex_text,
)

DecodedFieldMap = Dict[str, Any]
NumericMessage = Dict[str, Any]

DEFAULT_DECODE_DEPTH = 16


def decoded_node_to_numeric_value(node: Any, *, prefer_raw_hex_for_utf8: bool) -> Any:
    """
    将 `decode_message_to_field_map` 的节点值，转换为 `encode_message` 可接受的数值键 message 值。

    约定（与仓库现有工具保持一致）：
    - message -> dict[str, Any]（数值键）
    - int -> int（varint）
    - fixed32_float -> float（fixed32）
    - utf8 -> str（length-delimited 文本）
    - raw_hex -> "<binary_data> .."（length-delimited bytes）
    - repeated -> list[...]
    """
    if node is None:
        return None

    if isinstance(node, list):
        return [decoded_node_to_numeric_value(item, prefer_raw_hex_for_utf8=prefer_raw_hex_for_utf8) for item in node]

    if not isinstance(node, dict):
        raise TypeError(f"decoded node must be dict/list, got {type(node).__name__}")

    nested = node.get("message")
    if isinstance(nested, dict):
        return decoded_field_map_to_numeric_message(nested, prefer_raw_hex_for_utf8=prefer_raw_hex_for_utf8)

    if "int" in node:
        value = node.get("int")
        if not isinstance(value, int):
            raise TypeError(f"decoded int node expects int, got {type(value).__name__}")
        return int(value)

    if "fixed32_float" in node or "fixed32_int" in node:
        value = node.get("fixed32_float")
        if isinstance(value, float):
            return float(value)
        if isinstance(value, int):
            return float(value)
        raise TypeError(f"decoded fixed32_float node expects float/int, got {type(value).__name__}")

    if "fixed64_double" in node or "fixed64_int" in node:
        raw_u64 = node.get("fixed64_int")
        if isinstance(raw_u64, int):
            return {"fixed64_int": int(raw_u64)}
        raw_f64 = node.get("fixed64_double")
        if isinstance(raw_f64, (int, float)):
            return {"fixed64_double": float(raw_f64)}
        raise TypeError(f"decoded fixed64 node expects int/float, got {type(raw_u64).__name__}")

    # 注意：decode_message_to_field_map 的 length-delimited 节点可能同时包含 raw_hex 与 utf8。
    # - dump-json 输出/可读用途：倾向选择 utf8（更可读）
    # - 写回/roundtrip 用途：必须优先选择 raw_hex（保持字节完全一致，避免 sanitize/strip 导致 payload 变化）
    raw_hex = node.get("raw_hex")
    if prefer_raw_hex_for_utf8 and isinstance(raw_hex, str):
        raw_bytes = bytes.fromhex(raw_hex) if raw_hex else b""
        return format_binary_data_hex_text(raw_bytes)

    if "utf8" in node:
        value = node.get("utf8")
        if not isinstance(value, str):
            raise TypeError(f"decoded utf8 node expects str, got {type(value).__name__}")
        return str(value)

    if isinstance(raw_hex, str):
        raw_bytes = bytes.fromhex(raw_hex) if raw_hex else b""
        return format_binary_data_hex_text(raw_bytes)

    raise ValueError(f"unsupported decoded node shape: keys={sorted(node.keys())}")


def decoded_field_map_to_numeric_message(
    field_map: Mapping[str, Any],
    *,
    prefer_raw_hex_for_utf8: bool = False,
) -> NumericMessage:
    """
    将 `decode_message_to_field_map` 的输出 message（field_<n> 键）转换为 `encode_message` 使用的 numeric_message。
    """
    if not isinstance(field_map, Mapping):
        raise TypeError(f"field_map must be Mapping, got {type(field_map).__name__}")

    message: NumericMessage = {}
    for key, value in field_map.items():
        k = str(key)
        if not k.startswith("field_"):
            raise ValueError(f"unexpected field_map key: {k!r}")
        number_text = k[len("field_") :].strip()
        if number_text == "" or not number_text.isdigit():
            raise ValueError(f"unexpected field_map key: {k!r}")
        field_number = int(number_text)
        message[str(field_number)] = decoded_node_to_numeric_value(value, prefer_raw_hex_for_utf8=prefer_raw_hex_for_utf8)
    return message


def numeric_message_to_binary_data_text(message: Mapping[str, Any]) -> str:
    """
    numeric_message -> bytes -> "<binary_data> .."
    """
    if not isinstance(message, Mapping):
        raise TypeError(f"message must be Mapping, got {type(message).__name__}")
    message_dict = dict(message)
    return format_binary_data_hex_text(encode_message(message_dict))


def _decode_single_message_bytes_to_field_map(message_bytes: bytes, *, max_depth: int) -> Tuple[DecodedFieldMap, int]:
    if not isinstance(message_bytes, (bytes, bytearray)):
        raise TypeError(f"message_bytes must be bytes, got {type(message_bytes).__name__}")
    raw = bytes(message_bytes)
    return decode_message_to_field_map(
        data_bytes=raw,
        start_offset=0,
        end_offset=len(raw),
        remaining_depth=int(max_depth),
    )


def binary_data_text_to_decoded_field_map(binary_text: str, *, max_depth: int = DEFAULT_DECODE_DEPTH) -> DecodedFieldMap:
    """
    "<binary_data> .." -> decoded_field_map（field_<n> 键）

    约束：
    - 必须能完整解码为“单个 message”（不允许 trailing bytes）。
    """
    raw_bytes = parse_binary_data_hex_text(binary_text)
    fields_map, consumed_offset = _decode_single_message_bytes_to_field_map(raw_bytes, max_depth=max_depth)
    if consumed_offset != len(raw_bytes):
        raise ValueError(
            f"binary_data_text did not decode to a single complete message: consumed={consumed_offset}, total={len(raw_bytes)}"
        )
    return fields_map


def binary_data_text_to_numeric_message(binary_text: str, *, max_depth: int = DEFAULT_DECODE_DEPTH) -> NumericMessage:
    return decoded_field_map_to_numeric_message(binary_data_text_to_decoded_field_map(binary_text, max_depth=max_depth))


def decoded_field_map_to_binary_data_text(field_map: Mapping[str, Any]) -> str:
    return numeric_message_to_binary_data_text(decoded_field_map_to_numeric_message(field_map))


def numeric_message_to_decoded_field_map(message: Mapping[str, Any], *, max_depth: int = DEFAULT_DECODE_DEPTH) -> DecodedFieldMap:
    """
    numeric_message -> bytes -> decoded_field_map（field_<n>）

    主要用于调试/自检或需要从数值键结构回到 decode_gil 风格中间表示的场景。
    """
    raw_bytes = encode_message(dict(message))
    fields_map, consumed_offset = _decode_single_message_bytes_to_field_map(raw_bytes, max_depth=max_depth)
    if consumed_offset != len(raw_bytes):
        raise ValueError(
            f"numeric_message did not decode to a single complete message: consumed={consumed_offset}, total={len(raw_bytes)}"
        )
    return fields_map


