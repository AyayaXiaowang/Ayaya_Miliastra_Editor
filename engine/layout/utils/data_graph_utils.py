from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Set

from engine.graph.models import GraphModel
from engine.utils.graph.graph_utils import is_flow_port_name


@dataclass(frozen=True)
class DataComponentLayers:
    """纯数据图组件及其拓扑分层结果"""

    nodes: List[str]
    layers: List[List[str]]


def compute_data_components_layers(model: GraphModel) -> List[DataComponentLayers]:
    """
    基于数据边构建连通分量，并为每个分量做拓扑分层。

    Returns:
        List[DataComponentLayers]: 每个分量的节点列表与层序。
    """
    if not model or not model.nodes:
        return []

    node_ids = list(model.nodes.keys())
    directed_adj: Dict[str, List[str]] = {node_id: [] for node_id in node_ids}
    undirected_adj: Dict[str, Set[str]] = {node_id: set() for node_id in node_ids}

    for edge in model.edges.values():
        dst_node = model.nodes.get(edge.dst_node)
        if not dst_node:
            continue
        dst_port = dst_node.get_input_port(edge.dst_port)
        if dst_port and not is_flow_port_name(dst_port.name):
            if edge.src_node in directed_adj and edge.dst_node in directed_adj:
                directed_adj[edge.src_node].append(edge.dst_node)
                undirected_adj[edge.src_node].add(edge.dst_node)
                undirected_adj[edge.dst_node].add(edge.src_node)

    components: List[DataComponentLayers] = []
    remaining: Set[str] = set(node_ids)

    while remaining:
        start = next(iter(remaining))
        queue = deque([start])
        visited_order: List[str] = []
        visited_set: Set[str] = set()

        while queue:
            current = queue.popleft()
            if current in visited_set:
                continue
            visited_set.add(current)
            visited_order.append(current)
            for neighbor in undirected_adj.get(current, set()):
                if neighbor not in visited_set:
                    queue.append(neighbor)

        remaining -= visited_set
        layers = _topological_layers_for_component(visited_order, directed_adj)
        components.append(DataComponentLayers(nodes=list(visited_order), layers=layers))

    return components


def _topological_layers_for_component(
    component_nodes: List[str],
    directed_adj: Dict[str, List[str]],
) -> List[List[str]]:
    """对分量内节点做拓扑分层（仅考虑数据边）"""
    if not component_nodes:
        return []

    in_degree = {node_id: 0 for node_id in component_nodes}
    for node_id in component_nodes:
        for dst in directed_adj.get(node_id, []):
            if dst in in_degree:
                in_degree[dst] += 1

    layers: List[List[str]] = []
    processed: Set[str] = set()
    max_iterations = len(component_nodes) + 1

    for _ in range(max_iterations):
        layer_nodes = [
            node_id for node_id in component_nodes if node_id not in processed and in_degree[node_id] == 0
        ]
        if not layer_nodes:
            break
        layers.append(layer_nodes)
        processed.update(layer_nodes)
        for node_id in layer_nodes:
            for dst in directed_adj.get(node_id, []):
                if dst in in_degree:
                    in_degree[dst] -= 1

    leftover = [node_id for node_id in component_nodes if node_id not in processed]
    if leftover:
        layers.append(leftover)

    return layers


