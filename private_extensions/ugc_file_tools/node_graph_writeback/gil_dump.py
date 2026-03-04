from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Mapping, Sequence, Tuple

from ugc_file_tools.gil_dump_codec.protobuf_like import (
    decode_message_to_field_map,
    encode_message,
    format_binary_data_hex_text,
)
from ugc_file_tools.gil_package_exporter.gil_reader import read_gil_header


def _dump_gil_to_raw_json_object(input_gil_file_path: Path) -> Dict[str, Any]:
    """
    读取 `.gil` 的 payload bytes 并转换为 dump-json 风格的“数值键 dict”。

    注意：
    - 节点图写回链路只需要 payload(root4) 的结构（raw_dump_object['4']），无需依赖 DLL。
    - 这里采用 protobuf-like 的纯 Python 解码（decode_message_to_field_map）并做表示层互转，
      用于规避 DLL 在部分样本上抛出 C++ 异常导致进程不稳定的问题。
    """
    input_path = Path(input_gil_file_path).resolve()
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    file_bytes = input_path.read_bytes()
    header = read_gil_header(file_bytes)
    body_size = int(header.body_size)
    if body_size <= 0:
        raise ValueError(f"invalid gil body_size={body_size}: {str(input_path)!r}")

    payload_bytes = file_bytes[20 : 20 + body_size]
    if len(payload_bytes) != body_size:
        raise ValueError(
            f"payload size mismatch: expected={body_size} got={len(payload_bytes)} path={str(input_path)!r}"
        )

    decoded_field_map, consumed_offset = decode_message_to_field_map(
        data_bytes=payload_bytes,
        start_offset=0,
        end_offset=len(payload_bytes),
        remaining_depth=16,
    )
    if consumed_offset != len(payload_bytes):
        raise ValueError(
            f"payload did not decode to a single complete message: consumed={consumed_offset}, total={len(payload_bytes)} path={str(input_path)!r}"
        )

    payload_root = _decoded_field_map_to_dump_json_message(decoded_field_map)
    _normalize_node_graph_binary_fields_inplace(payload_root)
    return {"4": payload_root}


def dump_gil_to_raw_json_object(input_gil_file_path: Path) -> Dict[str, Any]:
    """Public API: decode `.gil` payload to dump-json style raw object."""
    return _dump_gil_to_raw_json_object(input_gil_file_path)


def _normalize_node_graph_binary_fields_inplace(payload_root: Dict[str, Any]) -> None:
    """
    对齐写回侧的“dump-json 口径”：
    - Node['2']（NodeProperty）应为 `<binary_data>` 字符串
    - Node['4']（records）内的每条 record 也应为 `<binary_data>` 字符串

    说明：
    - protobuf-like decoder 会将“可完整解析的 length-delimited bytes”优先解码为嵌套 message dict；
      但写回侧大量逻辑（模板库提取 / link record 判定等）要求这些字段保持为 bytes 文本形式。
    - 这里在不依赖 DLL 的前提下，对节点图段做一次定向归一化：将 dict 形态重新编码回 bytes，
      再用 `<binary_data>` 文本表示（byte-level 等价）。
    """
    if not isinstance(payload_root, dict):
        return
    section10 = payload_root.get("10")
    if not isinstance(section10, dict):
        return
    for group in _iter_graph_groups(section10):
        for entry in _iter_graph_entries_for_group(group):
            nodes_value = entry.get("3")
            nodes: List[Dict[str, Any]] = []
            if isinstance(nodes_value, list):
                nodes = [n for n in nodes_value if isinstance(n, dict)]
            elif isinstance(nodes_value, dict):
                nodes = [nodes_value]
            for node in nodes:
                node_prop = node.get("2")
                if isinstance(node_prop, dict):
                    node["2"] = format_binary_data_hex_text(encode_message(dict(node_prop)))
                elif isinstance(node_prop, list) and len(node_prop) == 1 and isinstance(node_prop[0], dict):
                    node["2"] = format_binary_data_hex_text(encode_message(dict(node_prop[0])))

                records_value = node.get("4")
                if isinstance(records_value, list):
                    new_records: List[Any] = []
                    for record in records_value:
                        if isinstance(record, dict):
                            new_records.append(format_binary_data_hex_text(encode_message(dict(record))))
                            continue
                        new_records.append(record)
                    node["4"] = new_records
                elif isinstance(records_value, dict):
                    node["4"] = [format_binary_data_hex_text(encode_message(dict(records_value)))]


def _decoded_field_map_to_dump_json_message(decoded_fields: Mapping[str, Any]) -> Dict[str, Any]:
    message: Dict[str, Any] = {}
    for key, value in decoded_fields.items():
        if not isinstance(key, str) or not key.startswith("field_"):
            continue
        suffix = key.replace("field_", "")
        if not suffix.isdigit():
            continue
        message[str(int(suffix))] = _decoded_value_to_dump_json_value(value)
    return message


def _decoded_value_to_dump_json_value(value: Any) -> Any:
    if isinstance(value, list):
        return [_decoded_value_to_dump_json_value(item) for item in value]

    if isinstance(value, Mapping):
        nested = value.get("message")
        if isinstance(nested, Mapping):
            return _decoded_field_map_to_dump_json_message(nested)

        if "int" in value:
            raw_int = value.get("int")
            if not isinstance(raw_int, int):
                raise ValueError("decoded int node missing int")
            return int(raw_int)

        if "fixed32_float" in value:
            float_value = value.get("fixed32_float")
            if not isinstance(float_value, float):
                raise ValueError("decoded fixed32_float node missing fixed32_float")
            return float(float_value)

        if "fixed64_int" in value or "fixed64_double" in value:
            # 使用 fixed64_int 作为精确 bit-level 表达；encoder 会按 wire_type=1 写入 8 bytes。
            raw_u64 = value.get("fixed64_int")
            if isinstance(raw_u64, int):
                return {"fixed64_int": int(raw_u64)}
            raw_f64 = value.get("fixed64_double")
            if isinstance(raw_f64, (float, int)):
                return {"fixed64_double": float(raw_f64)}
            raise ValueError("decoded fixed64 node missing fixed64_int/fixed64_double")

        raw_hex = value.get("raw_hex")
        if isinstance(raw_hex, str):
            raw_bytes = bytes.fromhex(raw_hex) if raw_hex else b""
            utf8_value = value.get("utf8")
            if isinstance(utf8_value, str):
                # decode_message_to_field_map 已确认其为有效 UTF-8 且可打印（不会包含 U+FFFD）。
                # 这里使用 raw bytes 原样解码，不做 strip/清理，确保回写 byte-level 等价。
                return raw_bytes.decode("utf-8", errors="strict")
            return format_binary_data_hex_text(raw_bytes)

        raise ValueError(f"unsupported decoded node: keys={sorted(value.keys())}")

    raise ValueError(f"unsupported decoded value type: {type(value).__name__}")


def _get_payload_root(raw_dump_object: Dict[str, Any]) -> Dict[str, Any]:
    payload_root = raw_dump_object.get("4")
    if not isinstance(payload_root, dict):
        raise ValueError("dump 对象缺少根字段 '4'（期望为 dict）。")
    return payload_root


def get_payload_root(raw_dump_object: Dict[str, Any]) -> Dict[str, Any]:
    """Public API: extract payload root ('4') from a raw dump object."""
    return _get_payload_root(raw_dump_object)


def _first_dict(value: Any) -> Optional[Dict[str, Any]]:
    if isinstance(value, dict):
        return value
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    return None


def _first_str(value: Any) -> str:
    if isinstance(value, str):
        return str(value)
    if isinstance(value, list) and value and isinstance(value[0], str):
        return str(value[0])
    return ""


def _ensure_list(root: Dict[str, Any], key: str) -> List[Any]:
    value = root.get(key)
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        root[key] = [value]
        return root[key]
    if value is None:
        root[key] = []
        return root[key]
    raise ValueError(f"expected list/dict/None at {key!r}, got {type(value).__name__}")


def _iter_graph_groups(node_graph_section: Dict[str, Any]) -> List[Dict[str, Any]]:
    groups_value = node_graph_section.get("1")
    if isinstance(groups_value, list):
        return [item for item in groups_value if isinstance(item, dict)]
    if isinstance(groups_value, dict):
        return [groups_value]
    return []


def _iter_graph_entries_for_group(group: Dict[str, Any]) -> List[Dict[str, Any]]:
    entries_value = group.get("1")
    if isinstance(entries_value, list):
        return [item for item in entries_value if isinstance(item, dict)]
    if isinstance(entries_value, dict):
        return [entries_value]
    return []


def _get_graph_id_from_entry(graph_entry: Dict[str, Any]) -> Optional[int]:
    header = _first_dict(graph_entry.get("1"))
    if isinstance(header, dict) and isinstance(header.get("5"), int):
        return int(header.get("5"))
    return None


def _find_graph_entry(payload_root: Dict[str, Any], graph_id_int: int) -> Dict[str, Any]:
    section = payload_root.get("10")
    if not isinstance(section, dict):
        raise ValueError("payload 缺少节点图段 '10'")
    for group in _iter_graph_groups(section):
        for entry in _iter_graph_entries_for_group(group):
            gid = _get_graph_id_from_entry(entry)
            if isinstance(gid, int) and int(gid) == int(graph_id_int):
                return entry
    raise ValueError(f"未找到 graph_id={int(graph_id_int)} 的 GraphEntry")


def find_graph_entry(payload_root: Dict[str, Any], graph_id_int: int) -> Dict[str, Any]:
    """Public API: locate a GraphEntry by graph_id_int under payload root."""
    return _find_graph_entry(payload_root, graph_id_int)


def _collect_existing_graph_ids(payload_root: Dict[str, Any]) -> List[int]:
    section = payload_root.get("10")
    if not isinstance(section, dict):
        return []
    ids: List[int] = []
    for group in _iter_graph_groups(section):
        for entry in _iter_graph_entries_for_group(group):
            gid = _get_graph_id_from_entry(entry)
            if isinstance(gid, int):
                ids.append(int(gid))
    return ids


def _choose_next_graph_id(*, existing_graph_ids: Sequence[int], scope_mask: int) -> int:
    existing_set = set(int(v) for v in existing_graph_ids if isinstance(v, int))
    candidates = [int(v) for v in existing_graph_ids if (int(v) & 0xFF800000) == int(scope_mask)]
    if not candidates:
        candidate = int(scope_mask) | 1
        while candidate in existing_set:
            candidate += 1
        return int(candidate)
    candidate = max(candidates) + 1
    while candidate in existing_set:
        candidate += 1
    return int(candidate)


