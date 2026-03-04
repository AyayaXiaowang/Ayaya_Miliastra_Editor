from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from ugc_file_tools.gia.container import unwrap_gia_container, validate_gia_container_file
from ugc_file_tools.gia.varbase_semantics import (
    as_list,
    get_message_field,
    get_message_node,
    get_utf8_field,
)
from ugc_file_tools.gil_dump_codec.protobuf_like import decode_message_to_field_map
from ugc_file_tools.node_data_index import (
    load_node_entry_by_id_map,
    load_type_entry_by_id_map,
    resolve_default_node_data_index_path,
)
from ugc_file_tools.graph.node_graph.ir_parser import parse_node_graph


def read_graph_irs_from_gia_file(
    gia_file_path: Path,
    *,
    node_data_index_path: Path | None = None,
    check_header: bool = False,
    decode_max_depth: int = 16,
) -> List[Dict[str, Any]]:
    """
    从 `.gia` 文件读取并解析其中包含的 NodeGraph GraphUnits，返回 Graph IR 列表（不落盘）。

    说明：
    - 解析逻辑对齐 `commands/parse/parse_gia_to_graph_ir.py` 的结构定位方式（GraphUnit.field_13 wrapper）。
    - Graph IR 的 schema_version=2，包含 nodes/pins/edges/graph_variables 等信息。
    """
    gia_file_path = Path(gia_file_path).resolve()
    if not gia_file_path.is_file():
        raise FileNotFoundError(f"input gia file not found: {str(gia_file_path)!r}")

    if check_header:
        validate_gia_container_file(gia_file_path)

    node_data_index_path = (
        Path(node_data_index_path).resolve()
        if node_data_index_path is not None
        else Path(resolve_default_node_data_index_path()).resolve()
    )
    node_entry_by_id = load_node_entry_by_id_map(node_data_index_path)
    type_entry_by_id = load_type_entry_by_id_map(node_data_index_path)

    proto_bytes = unwrap_gia_container(gia_file_path, check_header=False)
    root_fields, consumed = decode_message_to_field_map(
        data_bytes=proto_bytes,
        start_offset=0,
        end_offset=len(proto_bytes),
        remaining_depth=int(decode_max_depth),
    )
    if consumed != len(proto_bytes):
        raise ValueError(
            "protobuf 解析未消费完整字节流："
            f"consumed={consumed} total={len(proto_bytes)} file={str(gia_file_path)!r}"
        )

    root_file_path = get_utf8_field(root_fields, 3) or ""
    root_game_version = get_utf8_field(root_fields, 5) or ""

    graph_units = list(as_list(root_fields.get("field_1"))) + list(as_list(root_fields.get("field_2")))
    graph_irs: List[Dict[str, Any]] = []

    for unit_index, graph_unit in enumerate(graph_units):
        unit_msg = get_message_node(graph_unit)
        if unit_msg is None:
            continue

        wrapper = get_message_field(unit_msg, 13)
        if wrapper is None:
            continue
        inner = get_message_field(wrapper, 1)
        if inner is None:
            continue
        node_graph = get_message_field(inner, 1)
        if node_graph is None:
            continue

        graph_ir = parse_node_graph(
            graph_unit_message=unit_msg,
            node_graph_message=node_graph,
            node_entry_by_id=node_entry_by_id,
            type_entry_by_id=type_entry_by_id,
        )
        graph_irs.append(
            {
                **graph_ir,
                "source_gia_file": str(gia_file_path),
                "decode_max_depth": int(decode_max_depth),
                "root_file_path": str(root_file_path),
                "root_game_version": str(root_game_version),
                "node_data_index_path": str(node_data_index_path),
                "unit_index": int(unit_index),
            }
        )

    return graph_irs


__all__ = [
    "read_graph_irs_from_gia_file",
]

