"""
事件流分析模块（flow 子包）

负责发现事件起点和事件流相关的节点。
"""

from __future__ import annotations
from typing import List, Tuple, Dict, Set, Optional

from engine.graph.models import GraphModel, NodeModel
from engine.utils.graph.graph_utils import is_flow_port_name
from ..utils.graph_query_utils import has_flow_edges, is_flow_output_port, get_node_order_key
from ..core.constants import CATEGORY_EVENT, ORDER_MAX_FALLBACK
from ..core.layout_context import LayoutContext


def find_event_roots(
    model: GraphModel,
    include_virtual_pin_roots: bool = True,
    layout_context: Optional[LayoutContext] = None,
) -> List[NodeModel]:
    """
    统一的事件起点发现
    
    规则：
    1) 真实事件节点（category=='事件节点'）
    2) 在存在事件节点时，可追加：
       - 仅由"虚拟引脚"驱动且没有非引脚流程入的流程根
       - 具有流程入口端口且"流程入度为0"的流程节点（忽略来自虚拟引脚的入边）
    3) 当不存在事件节点时：
       - 若存在流程连线：选择"流程入度为0"的流程节点；若仍空则选择任意一个流程节点
       - 若不存在流程连线：返回空列表（视为纯数据图）
    
    排序：
       - 真实事件：优先使用 GraphModel.event_flow_order（ID）、event_flow_titles（标题）；
         次序键：source_lineno；最后回退 id
       - 额外起点：按（source_lineno, id）稳定排序，且置于真实事件之后
    
    Args:
        model: 图模型
        include_virtual_pin_roots: 是否包含虚拟引脚驱动的根节点
        
    Returns:
        事件起点节点列表
    """
    all_nodes = list(model.nodes.values())
    real_events: List[NodeModel] = [node for node in all_nodes if node.category == CATEGORY_EVENT]
    if layout_context is None:
        layout_context = LayoutContext(model)
    virtual_pin_nodes: Set[str] = set(layout_context.virtualPinNodeIds)

    flow_in_edges_non_pin, flow_in_edges_from_pin = _partition_flow_in_edges(
        layout_context.flowInByNode,
        virtual_pin_nodes,
    )

    # 当没有事件时：按"存在流程连线"的情况做回退
    if not real_events:
        if not has_flow_edges(model):
            return []
        # 搜索"流程入度为0"的流程节点（忽略虚拟引脚入边）
        flow_nodes = [
            node for node in all_nodes if any(is_flow_port_name(port.name) for port in node.inputs + node.outputs)
        ]
        in_degree = _compute_flow_indegree(
            model,
            flow_nodes,
            flow_in_edges_map=flow_in_edges_non_pin,
        )
        start_nodes = [model.nodes[node_id] for node_id, degree in in_degree.items() if degree == 0]
        if start_nodes:
            return sorted(start_nodes, key=get_node_order_key)
        # 有流程连线但存在循环，退化为任意一个流程节点
        return [flow_nodes[0]] if flow_nodes else []

    # 存在真实事件：收集"额外起点"
    result: List[NodeModel] = []
    # 真实事件排序（event_flow_order → event_flow_titles → source_lineno → id）
    order_map: Dict[str, int] = {}
    if getattr(model, "event_flow_order", None):
        for index, node_id in enumerate(model.event_flow_order):
            order_map[node_id] = index
    title_order_map: Dict[str, int] = {}
    if getattr(model, "event_flow_titles", None):
        for index, title in enumerate(model.event_flow_titles):
            title_order_map[title] = index

    def event_sort_key(node: NodeModel) -> Tuple[int, int, int, str]:
        idx = order_map.get(node.id, ORDER_MAX_FALLBACK)
        title_idx = title_order_map.get(getattr(node, "title", ""), ORDER_MAX_FALLBACK)
        line_number = getattr(node, "source_lineno", 0)
        line_number_key = line_number if isinstance(line_number, int) and line_number > 0 else ORDER_MAX_FALLBACK
        return (idx, title_idx, line_number_key, node.id)

    ordered_real_events = sorted(real_events, key=event_sort_key)
    result.extend(ordered_real_events)

    if include_virtual_pin_roots:
        flow_nodes_all = [
            node for node in all_nodes if any(is_flow_port_name(port.name) for port in node.inputs + node.outputs)
        ]

        def has_non_pin_flow_in(node_id: str) -> bool:
            return bool(flow_in_edges_non_pin.get(node_id))

        def has_pin_flow_in(node_id: str) -> bool:
            return bool(flow_in_edges_from_pin.get(node_id))

        existing_ids = {node.id for node in result}
        # 仅由虚拟引脚驱动、且没有非引脚流程入
        additional_pin_roots: List[NodeModel] = []
        for node in flow_nodes_all:
            if node.id in existing_ids:
                continue
            if has_pin_flow_in(node.id) and not has_non_pin_flow_in(node.id):
                additional_pin_roots.append(node)
        # 流程入度为0（忽略虚拟引脚）的流程入口节点
        in_degree_all = _compute_flow_indegree(
            model,
            flow_nodes_all,
            flow_in_edges_map=flow_in_edges_non_pin,
        )
        for node in flow_nodes_all:
            if node.id in existing_ids:
                continue
            has_flow_input = any(is_flow_port_name(port.name) for port in node.inputs)
            if has_flow_input and in_degree_all.get(node.id, 0) == 0:
                additional_pin_roots.append(node)

        # 稳定去重并排序
        uniq_extra_map: Dict[str, NodeModel] = {}
        for node in additional_pin_roots:
            if node.id not in uniq_extra_map:
                uniq_extra_map[node.id] = node
        ordered_extra = sorted(uniq_extra_map.values(), key=get_node_order_key)
        result.extend(ordered_extra)

    return result


def _compute_flow_indegree(
    model: GraphModel,
    candidate_nodes: List[NodeModel],
    ignore_virtual_pin_roots: bool = True,
    flow_in_edges_map: Optional[Dict[str, List]] = None,
) -> Dict[str, int]:
    """
    计算候选流程节点的入度（仅统计流程输入边），可选择忽略来自虚拟引脚的输入。
    """
    candidate_ids = {node.id for node in candidate_nodes}
    indegree: Dict[str, int] = {node_id: 0 for node_id in candidate_ids}
    if not indegree:
        return indegree

    if flow_in_edges_map is not None:
        for node_id in candidate_ids:
            indegree[node_id] = len(flow_in_edges_map.get(node_id, []))
        return indegree

    virtual_pin_nodes: Set[str] = set()
    if ignore_virtual_pin_roots:
        virtual_pin_nodes = {
            node_id for node_id, node in model.nodes.items() if getattr(node, "is_virtual_pin", False)
        }

    for edge in model.edges.values():
        dst_id = edge.dst_node
        if dst_id not in indegree:
            continue
        dst_node = model.nodes.get(dst_id)
        if not dst_node:
            continue
        dst_port = dst_node.get_input_port(edge.dst_port)
        if not dst_port or not is_flow_port_name(dst_port.name):
            continue
        if ignore_virtual_pin_roots and edge.src_node in virtual_pin_nodes:
            continue
        indegree[dst_id] += 1

    return indegree


def _partition_flow_in_edges(
    flow_in_edges_all: Dict[str, List],
    virtual_pin_nodes: Set[str],
) -> Tuple[Dict[str, List], Dict[str, List]]:
    """
    基于已缓存的流程入边索引，将其拆分为“来自虚拟引脚的入边”和“非虚拟引脚入边”。
    """
    flow_in_edges_non_pin: Dict[str, List] = {}
    flow_in_edges_from_pin: Dict[str, List] = {}
    if not flow_in_edges_all:
        return flow_in_edges_non_pin, flow_in_edges_from_pin

    for dst_id, edges in flow_in_edges_all.items():
        if not edges:
            continue
        for edge in edges:
            if edge.src_node in virtual_pin_nodes:
                flow_in_edges_from_pin.setdefault(dst_id, []).append(edge)
            else:
                flow_in_edges_non_pin.setdefault(dst_id, []).append(edge)

    return flow_in_edges_non_pin, flow_in_edges_from_pin



