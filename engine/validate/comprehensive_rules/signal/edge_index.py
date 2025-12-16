from __future__ import annotations

from typing import Any, Dict, List, Tuple


def merge_edges_with_connections(
    edges: List[Dict[str, Any]],
    connections: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """将 edges 与 connections 统一合并为标准边列表。"""
    normalized: List[Dict[str, Any]] = list(edges or [])
    seen_signatures: List[Tuple[str, str, str, str]] = []
    for edge in normalized:
        signature = _extract_edge_signature(edge)
        if signature not in seen_signatures:
            seen_signatures.append(signature)

    for index, connection in enumerate(connections or []):
        src_node, src_port = _extract_edge_endpoint(connection, True)
        dst_node, dst_port = _extract_edge_endpoint(connection, False)
        signature = (src_node, src_port, dst_node, dst_port)
        if not (src_node and src_port and dst_node and dst_port):
            continue
        if signature in seen_signatures:
            continue
        seen_signatures.append(signature)
        normalized.append(
            {
                "id": connection.get("id") or f"connection_{index}",
                "src_node": src_node,
                "src_port": src_port,
                "dst_node": dst_node,
                "dst_port": dst_port,
            }
        )
    return normalized


def build_edge_indices(
    edges: List[Dict[str, Any]],
) -> Tuple[
    Dict[Tuple[str, str], List[Tuple[str, str]]],
    Dict[Tuple[str, str], List[Tuple[str, str]]],
]:
    """构建入边/出边索引：便于按节点+端口快速查询连线。"""
    incoming: Dict[Tuple[str, str], List[Tuple[str, str]]] = {}
    outgoing: Dict[Tuple[str, str], List[Tuple[str, str]]] = {}
    for edge in edges:
        src_node, src_port = _extract_edge_endpoint(edge, True)
        dst_node, dst_port = _extract_edge_endpoint(edge, False)
        if src_node and src_port and dst_node and dst_port:
            dst_key = (dst_node, dst_port)
            src_key = (src_node, src_port)
            if dst_key not in incoming:
                incoming[dst_key] = []
            incoming[dst_key].append(src_key)
            if src_key not in outgoing:
                outgoing[src_key] = []
            outgoing[src_key].append(dst_key)
    return incoming, outgoing


def _extract_edge_endpoint(edge: Dict[str, Any], is_source: bool) -> Tuple[str, str]:
    node_keys = (
        ("src_node", "source", "from_node")
        if is_source
        else ("dst_node", "target", "to_node")
    )
    port_keys = (
        ("src_port", "source_port", "from_output")
        if is_source
        else ("dst_port", "target_port", "to_input")
    )
    node_id = ""
    port_name = ""
    for key in node_keys:
        value = edge.get(key)
        if value:
            node_id = str(value)
            break
    for key in port_keys:
        value = edge.get(key)
        if value:
            port_name = str(value)
            break
    return node_id, port_name


def _extract_edge_signature(edge: Dict[str, Any]) -> Tuple[str, str, str, str]:
    src_node, src_port = _extract_edge_endpoint(edge, True)
    dst_node, dst_port = _extract_edge_endpoint(edge, False)
    return (src_node, src_port, dst_node, dst_port)


__all__ = ["merge_edges_with_connections", "build_edge_indices"]


