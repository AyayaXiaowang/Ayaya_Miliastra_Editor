from __future__ import annotations

"""
dump_json_tree.py

集中维护“dump-json（数值键 JSON）树”的通用小工具，避免在多个写回域里重复实现同一套逻辑而漂移。

术语：
- numeric_message：`encode_message(...)` 可接受的“数值键 dict”（key 为 "1"/"2"/...）。
- dump-json object：历史 DLL dump-json 的顶层形态 `{"4": <payload_root>}`。
- decoded_field_map：`decode_message_to_field_map(...)` 的输出（key 为 "field_<n>"）。

本模块只提供“树操作 + 统一加载入口”，不包含任何具体业务（信号/结构体/UI）。
"""

from pathlib import Path
from typing import Any, Dict, List, Mapping

from ugc_file_tools.gil_dump_codec.gil_container import read_gil_payload_bytes
from ugc_file_tools.gil_dump_codec.protobuf_like import decode_message_to_field_map
from ugc_file_tools.gil_dump_codec.protobuf_like_bridge import decoded_field_map_to_numeric_message


def ensure_dict(parent: Dict[str, Any], key: str) -> Dict[str, Any]:
    """
    确保 `parent[key]` 为 dict：
    - dict：原样返回
    - None：创建空 dict 并返回
    - 其他：抛错
    """
    value = parent.get(key)
    if isinstance(value, dict):
        return value
    if value is None:
        new_value: Dict[str, Any] = {}
        parent[key] = new_value
        return new_value
    raise ValueError(f"expected dict at key={key!r}, got {type(value).__name__}")


def ensure_list(parent: Dict[str, Any], key: str) -> List[Any]:
    """
    确保 `parent[key]` 为 list，并返回可写的 list 视图：
    - list：原样返回
    - dict：兼容“单元素 repeated 被标量化为 dict”的情况，归一化为 [dict]
    - None：创建空 list 并返回
    - 其他：抛错
    """
    value = parent.get(key)
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        parent[key] = [value]
        return parent[key]
    if value is None:
        new_value: List[Any] = []
        parent[key] = new_value
        return new_value
    raise ValueError(f"expected list at key={key!r}, got {type(value).__name__}")


def ensure_list_allow_scalar(parent: Dict[str, Any], key: str) -> List[Any]:
    """
    确保 `parent[key]` 为 list（用于 repeated bytes/text 等字段可能被标量化的场景）：
    - list：原样返回
    - str：归一化为 [str]
    - dict：归一化为 [dict]（兼容单元素 repeated message 的标量化）
    - None：创建空 list 并返回
    - 其他：抛错
    """
    value = parent.get(key)
    if isinstance(value, list):
        return value
    if value is None:
        new_value: List[Any] = []
        parent[key] = new_value
        return new_value
    if isinstance(value, str):
        new_value = [value]
        parent[key] = new_value
        return new_value
    if isinstance(value, dict):
        parent[key] = [value]
        return parent[key]
    raise ValueError(f"expected list/str/dict/None at key={key!r}, got {type(value).__name__}")


def set_int_node(node: Dict[str, Any], value: int) -> None:
    """
    写入 decode_message_to_field_map 风格的 varint 节点（对齐仓库既有输出口径）。
    """
    node["int"] = int(value)
    lower32 = int(value) & 0xFFFFFFFF
    node["int32_high16"] = lower32 >> 16
    node["int32_low16"] = lower32 & 0xFFFF


def set_text_node_utf8(node: Dict[str, Any], text: str) -> None:
    """
    写入 decode_message_to_field_map 风格的 length-delimited 文本节点：{raw_hex, utf8}。
    """
    raw_bytes = str(text).encode("utf-8")
    node["raw_hex"] = raw_bytes.hex()
    node["utf8"] = str(text)


def deep_replace_int_inplace(obj: Any, *, old: int, new: int) -> None:
    """
    深度替换 numeric_message（dict/list 组合）里的 int 值（就地修改）：
    - 仅替换 **type(value) is int** 的值（避免 bool 被误当作 int 替换）
    """

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            for k, v in list(x.items()):
                if type(v) is int and int(v) == int(old):
                    x[k] = int(new)
                    continue
                walk(v)
            return
        if isinstance(x, list):
            for i, v in enumerate(list(x)):
                if type(v) is int and int(v) == int(old):
                    x[i] = int(new)
                    continue
                walk(v)
            return

    walk(obj)


def load_gil_payload_as_dump_json_object(
    gil_file_path: Path,
    *,
    max_depth: int = 32,
    prefer_raw_hex_for_utf8: bool = False,
) -> Dict[str, Any]:
    """
    统一入口：读取 `.gil` 的 payload，并转换为 dump-json 兼容的“数值键 JSON”对象：
      {"4": <payload_root>}

    - `prefer_raw_hex_for_utf8=False`：更可读（倾向输出 utf8 string）
    - `prefer_raw_hex_for_utf8=True`：更保守（utf8 节点也优先用 raw_hex 转为 `<binary_data>`，便于 lossless roundtrip）
    """
    input_path = Path(gil_file_path).resolve()
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    payload_bytes = read_gil_payload_bytes(input_path)
    decoded_field_map, consumed_offset = decode_message_to_field_map(
        data_bytes=payload_bytes,
        start_offset=0,
        end_offset=len(payload_bytes),
        remaining_depth=int(max_depth),
    )
    if consumed_offset != len(payload_bytes):
        raise ValueError(
            "gil payload 未能完整解码为单个 message（存在 trailing bytes）："
            f"consumed={consumed_offset}, total={len(payload_bytes)} path={str(input_path)!r}"
        )

    payload_root = decoded_field_map_to_numeric_message(
        decoded_field_map,
        prefer_raw_hex_for_utf8=bool(prefer_raw_hex_for_utf8),
    )
    if not isinstance(payload_root, dict):
        raise TypeError("decoded payload_root is not dict")

    return {"4": dict(payload_root)}


def load_gil_payload_as_numeric_message(
    gil_file_path: Path,
    *,
    max_depth: int = 32,
    prefer_raw_hex_for_utf8: bool = False,
) -> Dict[str, Any]:
    """
    统一入口：返回 `.gil` payload_root 的 numeric_message（等价于 `dump_obj['4']`）。
    """
    dump_obj = load_gil_payload_as_dump_json_object(
        gil_file_path,
        max_depth=int(max_depth),
        prefer_raw_hex_for_utf8=bool(prefer_raw_hex_for_utf8),
    )
    payload_root = dump_obj.get("4")
    if not isinstance(payload_root, dict):
        raise TypeError("dump object missing key '4' (payload_root)")
    return dict(payload_root)


__all__ = [
    "ensure_dict",
    "ensure_list",
    "ensure_list_allow_scalar",
    "set_int_node",
    "set_text_node_utf8",
    "deep_replace_int_inplace",
    "load_gil_payload_as_dump_json_object",
    "load_gil_payload_as_numeric_message",
]

