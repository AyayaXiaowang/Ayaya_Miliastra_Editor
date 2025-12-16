"""
基本块识别模块

负责识别流程图中的基本块和收集相关节点。
"""

from __future__ import annotations
from typing import List, Set, Tuple, TYPE_CHECKING

from engine.graph.models import GraphModel
from engine.utils.graph.graph_algorithms import collect_event_flow_nodes as collect_event_flow_nodes_util

if TYPE_CHECKING:
    from ..internal.layout_context import LayoutContext


def identify_block_flow_nodes(
    model: GraphModel,
    start_node_id: str,
    visited_readonly: Set[str],
    layout_context: "LayoutContext",
) -> List[str]:
    """
    识别从起点出发的"单链基本块"的流程节点序列（纯函数，不修改 visited）。
    
    规则：
    - 从起点沿着"单一流程出口"向前推进，直到遇到分支节点（多个流程出口）或汇合点（流程入度>1）或终点
    - 若遇到已访问节点（visited_readonly），则终止（避免跨块重复）
    
    Args:
        model: 图模型
        start_node_id: 起始节点ID
        visited_readonly: 已访问节点集合（只读）
        layout_context: 布局上下文（提供边索引，避免O(E)扫描）
        
    Returns:
        流程节点ID列表
    """
    if layout_context is None:
        raise ValueError("identify_block_flow_nodes requires a LayoutContext instance.")
    if start_node_id in visited_readonly:
        return []
    current_block_nodes: List[str] = []
    current_node_id = start_node_id
    while current_node_id:
        if current_node_id in visited_readonly:
            break
        # 防御性处理：若在同一基本块识别过程中再次遇到已加入的节点，
        # 说明流程图中存在环路（例如 A→B→A 或自环），继续前进将导致无限循环。
        # 这里直接终止当前块的扩展，将环入口视为块的终点，并交由后续块/关系分析处理。
        if current_node_id in current_block_nodes:
            break
        node = model.nodes.get(current_node_id)
        if not node:
            break

        # 检查是否为汇合点（流程入度>1）
        flow_in_count = len(layout_context.get_in_flow_edges(current_node_id))

        if current_block_nodes and flow_in_count > 1:
            break

        # 归入当前块
        current_block_nodes.append(current_node_id)

        # 发现流程出边（兼容：目标口为流程输入 也视为流程边）
        flow_out_edges_objs = layout_context.get_out_flow_edges(current_node_id)
        flow_out_edges: List[Tuple[str, str]] = [(edge.src_port, edge.dst_node) for edge in flow_out_edges_objs]

        if not flow_out_edges:
            break
        if len(flow_out_edges) == 1:
            current_node_id = flow_out_edges[0][1]
        else:
            # 分支节点，当前块到此结束
            break
    return current_block_nodes


collect_event_flow_nodes = collect_event_flow_nodes_util


