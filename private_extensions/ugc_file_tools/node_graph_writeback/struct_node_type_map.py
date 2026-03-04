from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple

from ugc_file_tools.decode_gil import decode_bytes_to_python
from ugc_file_tools.gil_dump_codec.protobuf_like import parse_binary_data_hex_text


@dataclass(frozen=True, slots=True)
class StructNodeWritebackMaps:
    """
    写回 struct 节点所需的“真源信息”汇总：
    - title+struct_id -> node_type_id：用于将 GraphModel 中的『拼装/拆分/修改结构体』节点映射到 base gil 内的具体 node_type_id
      （真源表现：每个 struct_id 对应一组独立的 node_type_id）。
    - node_type_id + inparam_index -> record_id(field_7)：用于合成缺失的 InParam record 时补齐 field_7，
      避免丢失端口绑定信息导致编辑器不识别。
    """

    node_type_id_by_title_and_struct_id: Dict[str, Dict[int, int]]
    record_id_by_node_type_id_and_inparam_index: Dict[int, Dict[int, int]]


_STRUCT_NODE_TITLES: Tuple[str, ...] = ("拼装结构体", "拆分结构体", "修改结构体")


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, dict):
        return [value]
    return []


def _extract_int_node(node: Any) -> Optional[int]:
    if not isinstance(node, dict):
        return None
    raw = node.get("int")
    if isinstance(raw, int):
        return int(raw)
    return None


def _extract_nested_int(root: Mapping[str, Any], path: List[str]) -> Optional[int]:
    cur: Any = root
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return _extract_int_node(cur)


def _decode_binary_data_text_to_decoded_field_map(binary_text: str) -> Dict[str, Any]:
    raw = parse_binary_data_hex_text(str(binary_text))
    decoded = decode_bytes_to_python(raw)
    if not isinstance(decoded, dict):
        raise ValueError("binary_data decode 结果不是 dict")
    return decoded


def _extract_node_type_id_from_node_def_inner(inner: Mapping[str, Any]) -> Optional[int]:
    field_4 = inner.get("4")
    if not isinstance(field_4, Mapping):
        return None
    node_a = field_4.get("1")
    node_b = field_4.get("2")
    if not isinstance(node_a, Mapping) or not isinstance(node_b, Mapping):
        return None
    value_a = node_a.get("5")
    value_b = node_b.get("5")
    if not isinstance(value_a, int) or not isinstance(value_b, int):
        return None
    if int(value_a) != int(value_b):
        return None
    return int(value_a)


def _extract_struct_id_from_node_def_inner(inner: Mapping[str, Any]) -> Optional[int]:
    """
    从 node_def 的端口定义（inner['102'][0]）中提取 struct_id。

    已验证样本（真源 / DLL dump）：
    - decoded.field_4.message.field_104.message.field_2.int == struct_id
    """
    port_defs = inner.get("102")
    if not isinstance(port_defs, list) or not port_defs:
        return None
    first = port_defs[0]
    if not isinstance(first, str) or not first.startswith("<binary_data>"):
        return None
    decoded = _decode_binary_data_text_to_decoded_field_map(first)
    struct_id = _extract_nested_int(decoded, ["field_4", "message", "field_104", "message", "field_2"])
    return int(struct_id) if isinstance(struct_id, int) else None


def build_struct_node_writeback_maps_from_payload_root(payload_root: Dict[str, Any]) -> StructNodeWritebackMaps:
    section = payload_root.get("10")
    if not isinstance(section, dict):
        return StructNodeWritebackMaps(node_type_id_by_title_and_struct_id={}, record_id_by_node_type_id_and_inparam_index={})

    node_defs_value = section.get("2")
    node_defs = _as_list(node_defs_value)

    type_id_map: Dict[str, Dict[int, int]] = {}
    record_id_map: Dict[int, Dict[int, int]] = {}

    for entry in node_defs:
        if not isinstance(entry, dict):
            continue
        inner = entry.get("1")
        if not isinstance(inner, dict):
            continue
        title = str(inner.get("200") or "").strip()
        if title not in _STRUCT_NODE_TITLES:
            continue

        node_type_id_int = _extract_node_type_id_from_node_def_inner(inner)
        if not isinstance(node_type_id_int, int):
            continue

        struct_id_int = _extract_struct_id_from_node_def_inner(inner)
        if isinstance(struct_id_int, int):
            type_id_map.setdefault(str(title), {}).setdefault(int(struct_id_int), int(node_type_id_int))

        # 端口表：index -> field_8(int) 映射到 record.field_7（用于写回时补齐）
        port_defs = inner.get("102")
        if isinstance(port_defs, list):
            for inparam_index, port_def in enumerate(list(port_defs)):
                if not isinstance(port_def, str) or not port_def.startswith("<binary_data>"):
                    continue
                decoded_port = _decode_binary_data_text_to_decoded_field_map(port_def)
                record_id = _extract_nested_int(decoded_port, ["field_8"])
                if not isinstance(record_id, int):
                    continue
                record_id_map.setdefault(int(node_type_id_int), {}).setdefault(int(inparam_index), int(record_id))

    return StructNodeWritebackMaps(
        node_type_id_by_title_and_struct_id=type_id_map,
        record_id_by_node_type_id_and_inparam_index=record_id_map,
    )


