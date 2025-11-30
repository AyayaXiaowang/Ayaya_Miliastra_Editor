"""图算法与事件流分组工具

提供与节点图结构相关的通用算法，避免在解析器/生成器/UI 等处重复实现。

当前包含：
- group_nodes_by_event(GraphModel, include_data_dependencies): 将图按事件分组
- collect_event_flow_nodes(...): 事件流内递归收集函数（内部使用）
"""

from __future__ import annotations

from collections import deque
from typing import Dict, List, Set, Any, Iterable, Sequence, Tuple, Deque

from engine.graph.models import GraphModel, NodeModel
from .graph_utils import is_flow_port_name


def _topological_order_from_edges(
    node_sequence: Sequence[str],
    directed_edges: Iterable[Tuple[str, str]],
    append_unordered_tail: bool,
    prioritized_node: str | None = None,
) -> List[str]:
    """对节点序列与边集合执行一次 Kahn 拓扑排序。"""
    unique_node_ids: List[str] = []
    seen_ids: Set[str] = set()
    for node_id in node_sequence:
        if node_id not in seen_ids:
            unique_node_ids.append(node_id)
            seen_ids.add(node_id)

    in_degree: Dict[str, int] = {node_id: 0 for node_id in unique_node_ids}
    adjacency: Dict[str, List[str]] = {node_id: [] for node_id in unique_node_ids}

    for src_node, dst_node in directed_edges:
        if src_node in adjacency and dst_node in in_degree:
            adjacency[src_node].append(dst_node)
            in_degree[dst_node] += 1

    zero_indegree_nodes: List[str] = [
        node_id for node_id in unique_node_ids if in_degree[node_id] == 0
    ]
    if prioritized_node and prioritized_node in zero_indegree_nodes:
        zero_indegree_nodes.remove(prioritized_node)
        zero_indegree_nodes.insert(0, prioritized_node)

    queue: Deque[str] = deque(zero_indegree_nodes)
    ordered: List[str] = []

    while queue:
        current_node = queue.popleft()
        ordered.append(current_node)
        for neighbor in adjacency[current_node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if append_unordered_tail:
        unordered_tail = [node_id for node_id in unique_node_ids if node_id not in ordered]
        ordered.extend(unordered_tail)

    return ordered


def group_nodes_by_event(
    graph_model: GraphModel,
    include_data_dependencies: bool = False,
) -> Dict[str, List[str]]:
    """将节点按事件流分组。

    Args:
        graph_model: 节点图模型
        include_data_dependencies: 是否将数据依赖节点也纳入事件流集合

    Returns:
        {event_node_id: [node_id, ...]}（每个列表不保证拓扑顺序，仅表示成员关系）
    """
    event_flows: Dict[str, List[str]] = {}

    # 找到所有事件节点
    event_nodes = [n for n in graph_model.nodes.values() if n.category == "事件节点"]

    for event_node in event_nodes:
        member_ids: Set[str] = collect_event_flow_nodes(
            graph_model, event_node.id
        )

        if include_data_dependencies and member_ids:
            # 闭包式加入所有上游数据依赖节点
            changed = True
            while changed:
                changed = False
                for edge in list(graph_model.edges.values()):
                    if edge.dst_node in member_ids:
                        # 目标是成员，若是数据边，则将源也加入
                        dst_node = graph_model.nodes.get(edge.dst_node)
                        if not dst_node:
                            continue
                        dst_port = next((p for p in dst_node.inputs if p.name == edge.dst_port), None)
                        if (dst_port is not None) and (not is_flow_port_name(dst_port.name)):
                            if edge.src_node not in member_ids:
                                member_ids.add(edge.src_node)
                                changed = True

        event_flows[event_node.id] = list(member_ids)

    return event_flows


def collect_event_flow_nodes(graph_model: GraphModel, start_node_id: str) -> Set[str]:
    """从事件节点出发，沿流程边递归收集事件流中的节点集合。

    仅沿“流程边”（源端为流程端口）向下游遍历；不包含数据依赖。
    """
    visited: Set[str] = set()

    def dfs(node_id: str) -> None:
        if node_id in visited:
            return
        visited.add(node_id)

        # 查找所有流程出边（源端口为流程端口）
        for edge in list(graph_model.edges.values()):
            if edge.src_node != node_id:
                continue
            src_node = graph_model.nodes.get(edge.src_node)
            if not src_node:
                continue
            src_port = next((p for p in src_node.outputs if p.name == edge.src_port), None)
            if (src_port is not None) and is_flow_port_name(src_port.name):
                dfs(edge.dst_node)

    dfs(start_node_id)
    return visited


def topological_sort_graph_model(graph_model: GraphModel) -> List[NodeModel]:
    """对 GraphModel 的所有节点进行拓扑排序（按依赖顺序）。

    说明：
    - 同时考虑“流程边”和“数据边”作为依赖关系；
    - 若存在环（例如流程中的循环），将返回可排序的有向无环部分；
    - 不对“剩余未入结果的节点”做额外追加，以保持与既有生成器语义一致。
    """
    node_order_hint: List[str] = [node.id for node in graph_model.nodes.values()]
    directed_edges: List[Tuple[str, str]] = [
        (edge.src_node, edge.dst_node) for edge in graph_model.edges.values()
    ]
    ordered_ids = _topological_order_from_edges(
        node_order_hint,
        directed_edges,
        append_unordered_tail=False,
    )
    return [graph_model.nodes[node_id] for node_id in ordered_ids if node_id in graph_model.nodes]


def topological_sort_nodes_edges(nodes: List[dict], edges: List[dict]) -> List[str]:
    """对通用 nodes/edges 列表进行拓扑排序，返回节点ID列表。

    语义对齐 UI 侧的使用习惯：
    - 使用所有边作为依赖；
    - 若存在环或孤立节点，则在 Kahn 结果末尾追加“未入结果”的剩余节点。
    """
    node_ids: List[str] = [str(node.get("id")) for node in nodes]
    directed_edges: List[Tuple[str, str]] = [
        (str(edge.get("src_node")), str(edge.get("dst_node"))) for edge in edges
    ]
    return _topological_order_from_edges(
        node_ids,
        directed_edges,
        append_unordered_tail=True,
    )


def group_nodes_by_event_with_topo_order(
    graph_model: GraphModel,
    include_data_dependencies: bool = False,
) -> Dict[str, List[str]]:
    """
    在 group_nodes_by_event 的基础上，为每个事件成员列表追加拓扑排序（基于子图边关系）。
    - 排序同时考虑“流程边”和“数据边”；
    - 若存在环路，将输出可排序前缀，剩余成员按原成员顺序附加在末尾；
    - 若事件节点在成员集中且入度为0，则优先置于结果序列前部。
    """
    grouped = group_nodes_by_event(graph_model, include_data_dependencies=include_data_dependencies)
    ordered: Dict[str, List[str]] = {}

    for event_id, members in grouped.items():
        member_set: Set[str] = set(members)
        edges_within_members: List[Tuple[str, str]] = [
            (edge.src_node, edge.dst_node)
            for edge in graph_model.edges.values()
            if (edge.src_node in member_set) and (edge.dst_node in member_set)
        ]
        ordered[event_id] = _topological_order_from_edges(
            members,
            edges_within_members,
            append_unordered_tail=True,
            prioritized_node=event_id,
        )

    return ordered


