from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ugc_file_tools.gia.varbase_semantics import (
    FieldMap,
    as_list,
    get_field,
    get_int_field,
    get_message_field,
    get_message_node,
    get_utf8_field,
)
from ugc_file_tools.gil_dump_codec.protobuf_like import decode_message_to_field_map
from ugc_file_tools.gil_dump_codec.gil_container import (
    read_gil_payload_bytes_and_container_meta as _read_gil_payload_bytes_and_container_meta,
)
from ugc_file_tools.node_data_index import (
    load_node_entry_by_id_map,
    load_type_entry_by_id_map,
    resolve_default_node_data_index_path,
)

from .ir_parser import parse_node_graph


@dataclass(frozen=True, slots=True)
class GilPayloadNodeGraphBlob:
    """A NodeGraph blob stored under `.gil` payload section10 groups (10.1.1)."""

    group_index: int
    entry_index: int
    blob_bytes: bytes
    graph_id_int: int
    graph_name: str


@dataclass(frozen=True, slots=True)
class GilPayloadNodeGraphIR:
    """Parsed Graph IR for a NodeGraph blob stored in `.gil` payload."""

    group_index: int
    entry_index: int
    blob_bytes_len: int
    graph_id_int: int
    graph_name: str
    graph_ir: Dict[str, Any]


def read_gil_payload_bytes_and_container_meta(*, gil_file_path: Path) -> Tuple[bytes, Dict[str, Any]]:
    # 容器切片与 meta 提取统一复用 gil_dump_codec（避免重复实现导致口径漂移）。
    return _read_gil_payload_bytes_and_container_meta(gil_file_path=Path(gil_file_path))


def _decode_payload_root_for_node_graph_blob_scan(payload_bytes: bytes) -> FieldMap:
    """
    Shallow decode payload to quickly locate NodeGraph blobs (10.1.1).
    - remaining_depth=3 keeps 10.1.1 as raw_hex (bytes) rather than expanding the whole graph.
    """
    root_fields, consumed = decode_message_to_field_map(
        data_bytes=payload_bytes,
        start_offset=0,
        end_offset=len(payload_bytes),
        remaining_depth=3,
    )
    if consumed != len(payload_bytes):
        raise ValueError(f"gil payload decode did not consume all bytes: consumed={consumed} total={len(payload_bytes)}")
    return root_fields


def _iter_node_graph_entry_blobs_from_payload_root(root_fields: FieldMap) -> Iterable[Tuple[int, int, bytes]]:
    """
    Iterate (group_index, entry_index, entry_bytes) for NodeGraph blobs under section10(field_10).groups(field_1).entries(field_1).
    """
    section10_msg = get_message_field(root_fields, 10)
    if section10_msg is None:
        return

    groups_nodes = get_field(section10_msg, 1)
    group_nodes_list = as_list(groups_nodes)

    for group_index, group_node in enumerate(group_nodes_list):
        group_msg = get_message_node(group_node)
        if group_msg is None and isinstance(group_node, dict) and isinstance(group_node.get("raw_hex"), str):
            group_bytes = bytes.fromhex(str(group_node.get("raw_hex") or ""))
            group_msg, consumed = decode_message_to_field_map(
                data_bytes=group_bytes,
                start_offset=0,
                end_offset=len(group_bytes),
                remaining_depth=1,
            )
            if consumed != len(group_bytes):
                raise ValueError(
                    "gil group decode did not consume all bytes: "
                    f"consumed={consumed} total={len(group_bytes)} group_index={group_index}"
                )
        if group_msg is None:
            continue

        entries_nodes = as_list(get_field(group_msg, 1))
        for entry_index, entry_node in enumerate(entries_nodes):
            if not isinstance(entry_node, dict):
                continue
            raw_hex = entry_node.get("raw_hex")
            if not isinstance(raw_hex, str) or raw_hex.strip() == "":
                continue
            yield int(group_index), int(entry_index), bytes.fromhex(raw_hex)


def _extract_graph_id_and_name_from_node_graph_bytes(node_graph_bytes: bytes) -> Tuple[int, str]:
    """
    Shallow decode NodeGraph bytes and extract (graph_id_int, graph_name).
    """
    node_graph_fields, consumed = decode_message_to_field_map(
        data_bytes=node_graph_bytes,
        start_offset=0,
        end_offset=len(node_graph_bytes),
        remaining_depth=2,
    )
    if consumed != len(node_graph_bytes):
        raise ValueError(
            "node graph blob decode did not consume all bytes: "
            f"consumed={consumed} total={len(node_graph_bytes)}"
        )
    graph_id_msg = get_message_field(node_graph_fields, 1) or {}
    graph_id_int = int(get_int_field(graph_id_msg, 5) or 0)
    graph_name = str(get_utf8_field(node_graph_fields, 2) or "")
    return graph_id_int, graph_name


def extract_node_graph_blobs_from_gil_payload(
    *,
    gil_file_path: Path,
    graph_ids: Optional[Sequence[int]] = None,
) -> List[GilPayloadNodeGraphBlob]:
    """
    Extract NodeGraph blobs (bytes) from `.gil` payload (section10 groups).
    Returns a list of blobs with basic header (graph_id/name) parsed for filtering.
    """
    payload_bytes, _container_meta = read_gil_payload_bytes_and_container_meta(gil_file_path=Path(gil_file_path))
    root_fields = _decode_payload_root_for_node_graph_blob_scan(payload_bytes)

    selected: Optional[set[int]] = None
    if graph_ids is not None:
        selected = {int(x) for x in list(graph_ids) if isinstance(x, int)}

    out: List[GilPayloadNodeGraphBlob] = []
    for group_index, entry_index, entry_bytes in _iter_node_graph_entry_blobs_from_payload_root(root_fields):
        graph_id_int, graph_name = _extract_graph_id_and_name_from_node_graph_bytes(entry_bytes)
        if selected is not None and int(graph_id_int) not in selected:
            continue
        out.append(
            GilPayloadNodeGraphBlob(
                group_index=int(group_index),
                entry_index=int(entry_index),
                blob_bytes=entry_bytes,
                graph_id_int=int(graph_id_int),
                graph_name=str(graph_name),
            )
        )
    return out


def parse_gil_payload_node_graphs_to_graph_ir(
    *,
    gil_file_path: Path,
    node_data_index_path: Optional[Path] = None,
    graph_ids: Optional[Sequence[int]] = None,
    max_depth: int = 16,
) -> List[GilPayloadNodeGraphIR]:
    """
    Parse NodeGraph blobs from `.gil` payload directly into Graph IR (in-memory).

    This is the shared implementation for:
    - diagnostics tools (parse/export IR)
    - writeback golden/roundtrip regression tests
    """
    node_data_index_path = (
        Path(node_data_index_path).resolve()
        if node_data_index_path is not None
        else Path(resolve_default_node_data_index_path()).resolve()
    )
    node_entry_by_id = load_node_entry_by_id_map(node_data_index_path)
    type_entry_by_id = load_type_entry_by_id_map(node_data_index_path)

    blobs = extract_node_graph_blobs_from_gil_payload(gil_file_path=Path(gil_file_path), graph_ids=graph_ids)
    out: List[GilPayloadNodeGraphIR] = []
    for blob in blobs:
        node_graph_fields, consumed = decode_message_to_field_map(
            data_bytes=blob.blob_bytes,
            start_offset=0,
            end_offset=len(blob.blob_bytes),
            remaining_depth=int(max_depth),
        )
        if consumed != len(blob.blob_bytes):
            raise ValueError(
                "node graph blob deep decode did not consume all bytes: "
                f"consumed={consumed} total={len(blob.blob_bytes)} graph_id_int={int(blob.graph_id_int)}"
            )

        graph_ir = parse_node_graph(
            graph_unit_message=None,
            node_graph_message=node_graph_fields,
            node_entry_by_id=dict(node_entry_by_id),
            type_entry_by_id=dict(type_entry_by_id),
        )
        out.append(
            GilPayloadNodeGraphIR(
                group_index=int(blob.group_index),
                entry_index=int(blob.entry_index),
                blob_bytes_len=int(len(blob.blob_bytes)),
                graph_id_int=int(blob.graph_id_int),
                graph_name=str(blob.graph_name),
                graph_ir=dict(graph_ir),
            )
        )
    return out

