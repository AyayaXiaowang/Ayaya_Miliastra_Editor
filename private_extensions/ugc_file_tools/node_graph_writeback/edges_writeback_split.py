from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ugc_file_tools.node_graph_semantics.graph_generater import (
    is_flow_port_by_node_def as _is_flow_port_by_node_def,
)

from .edges_writeback_common import resolve_node_def_for_graph_node


def split_edges_by_flow_or_data(
    *,
    edges: List[Dict[str, Any]],
    node_title_by_graph_node_id: Dict[str, str],
    graph_node_by_graph_node_id: Dict[str, Dict[str, Any]],
    node_defs_by_name: Dict[str, Any],
) -> Tuple[List[Tuple[str, str, str, str]], List[Tuple[str, str, str, str]]]:
    flow_edges: List[Tuple[str, str, str, str]] = []
    data_edges: List[Tuple[str, str, str, str]] = []
    for edge in list(edges):
        if not isinstance(edge, dict):
            continue
        src_node = str(edge.get("src_node") or "")
        dst_node = str(edge.get("dst_node") or "")
        src_port = str(edge.get("src_port") or "")
        dst_port = str(edge.get("dst_port") or "")
        if src_node == "" or dst_node == "":
            continue

        src_title = node_title_by_graph_node_id.get(src_node, "")
        dst_title = node_title_by_graph_node_id.get(dst_node, "")
        if src_title == "" or dst_title == "":
            raise ValueError(f"edge 引用了未知节点：src={src_node!r} dst={dst_node!r}")

        src_payload = graph_node_by_graph_node_id.get(src_node)
        dst_payload = graph_node_by_graph_node_id.get(dst_node)
        if not isinstance(src_payload, dict) or not isinstance(dst_payload, dict):
            raise ValueError(f"edge 引用了缺失 node payload：src={src_node!r} dst={dst_node!r}")

        src_def = resolve_node_def_for_graph_node(
            node_id=str(src_node),
            node_title=str(src_title),
            node_payload=src_payload,
            node_defs_by_name=node_defs_by_name,
        )
        dst_def = resolve_node_def_for_graph_node(
            node_id=str(dst_node),
            node_title=str(dst_title),
            node_payload=dst_payload,
            node_defs_by_name=node_defs_by_name,
        )
        if src_def is None:
            raise KeyError(f"Graph_Generater 节点库未找到节点定义（server）：{src_title!r}")
        if dst_def is None:
            raise KeyError(f"Graph_Generater 节点库未找到节点定义（server）：{dst_title!r}")

        src_is_flow = _is_flow_port_by_node_def(node_def=src_def, port_name=src_port, is_input=False)
        dst_is_flow = _is_flow_port_by_node_def(node_def=dst_def, port_name=dst_port, is_input=True)
        if src_is_flow != dst_is_flow:
            raise ValueError(f"edge 出现 flow/data 混用端口：{src_port!r} -> {dst_port!r}")
        if src_is_flow and dst_is_flow:
            flow_edges.append((src_node, src_port, dst_node, dst_port))
        else:
            data_edges.append((src_node, src_port, dst_node, dst_port))
    return flow_edges, data_edges

