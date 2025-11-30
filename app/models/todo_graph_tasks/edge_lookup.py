from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from engine.graph.models import GraphModel
from engine.utils.graph.graph_utils import is_flow_port_name


@dataclass
class GraphEdgeLookup:
    edges_list: List
    input_edges_map: Dict[Tuple[str, str], List]
    incoming_edges_by_node: Dict[str, List]
    flow_adj: Dict[str, List[Tuple]]
    flow_in_degree_map: Dict[str, int]
    flow_edge_ids: set[str]


def build_edge_lookup(model: GraphModel) -> GraphEdgeLookup:
    edges_list = list(model.edges.values())
    input_edges_map: Dict[Tuple[str, str], List] = {}
    incoming_edges_by_node: Dict[str, List] = {}
    flow_adj: Dict[str, List[Tuple]] = {}
    flow_in_degree_map: Dict[str, int] = {}
    flow_edge_ids: set[str] = set()

    for edge in edges_list:
        incoming_edges_by_node.setdefault(edge.dst_node, []).append(edge)
        input_edges_map.setdefault((edge.dst_node, edge.dst_port), []).append(edge)
        if _edge_is_flow(model, edge):
            flow_edge_ids.add(edge.id)
            flow_adj.setdefault(edge.src_node, []).append((edge, edge.dst_node))
            flow_in_degree_map[edge.dst_node] = flow_in_degree_map.get(edge.dst_node, 0) + 1

    return GraphEdgeLookup(
        edges_list=edges_list,
        input_edges_map=input_edges_map,
        incoming_edges_by_node=incoming_edges_by_node,
        flow_adj=flow_adj,
        flow_in_degree_map=flow_in_degree_map,
        flow_edge_ids=flow_edge_ids,
    )


def _edge_is_flow(model: GraphModel, edge) -> bool:
    src_node = model.nodes.get(edge.src_node)
    if src_node and any(
        port.name == edge.src_port and is_flow_port_name(port.name) for port in src_node.outputs
    ):
        return True
    dst_node = model.nodes.get(edge.dst_node)
    if dst_node and any(
        port.name == edge.dst_port and is_flow_port_name(port.name) for port in dst_node.inputs
    ):
        return True
    return False

