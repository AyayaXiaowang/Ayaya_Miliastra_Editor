"""
流程树状图生成器模块（flow 子包）

将节点图转换为ASCII树状图，展示事件、顺序、分支、数据依赖与循环。
"""

from __future__ import annotations
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass

from engine.graph.models import GraphModel, NodeModel
from engine.utils.graph.graph_utils import is_flow_port_name
from ..core.layout_context import LayoutContext
from ..utils.data_graph_utils import compute_data_components_layers
from ..utils.graph_query_utils import has_flow_edges, is_flow_output_port, get_ordered_flow_out_edges
from ..core.constants import ORDER_MAX_FALLBACK
from .event_flow_analyzer import find_event_roots


@dataclass
class FlowTreeRenderContext:
    model: GraphModel
    layout_context: LayoutContext
    block_relations: Optional[dict]


def _build_flow_tree_context(model: GraphModel) -> FlowTreeRenderContext:
    cached_context: Optional[LayoutContext] = getattr(model, "_layout_context_cache", None)
    layout_context = (
        cached_context if isinstance(cached_context, LayoutContext) and cached_context.model is model else None
    )
    if layout_context is None:
        layout_context = LayoutContext(model)
    block_relations = _get_cached_block_relationships(model) if has_flow_edges(model) else None
    return FlowTreeRenderContext(model=model, layout_context=layout_context, block_relations=block_relations)


def generate_flow_tree(model: GraphModel) -> str:
    """
    生成节点图的流程树状图
    
    Args:
        model: 图模型
        
    Returns:
        ASCII树状图文本
    """
    if not model.nodes:
        return "空节点图"

    lines: List[str] = []
    lines.append("=" * 80)
    lines.append(f"节点图: {model.graph_name or '未命名'}")
    lines.append("=" * 80)

    ctx = _build_flow_tree_context(model)
    data_in_index = ctx.layout_context.dataInByNode
    data_out_index = ctx.layout_context.dataOutByNode
    flow_out_index = ctx.layout_context.flowOutByNode

    # 统一事件起点发现
    event_nodes = find_event_roots(model, include_virtual_pin_roots=True, layout_context=ctx.layout_context)
    if not event_nodes:
        if not has_flow_edges(model):
            # 纯数据节点图
            lines.append("\n⚠️  纯数据节点图（无流程控制）\n")
            lines.append(_generate_data_tree(model, data_in_index, data_out_index))
            return "\n".join(lines)
        lines.append("\n⚠️  未发现事件或可识别的流程根\n")
        return "\n".join(lines)

    event_nodes = _sort_event_nodes_with_blocks(event_nodes, model)
    expanded_nodes: Set[str] = set()

    # 为每个事件流生成树状图
    for index, event_node in enumerate(event_nodes):
        if index > 0:
            lines.append("\n" + "-" * 80 + "\n")

        lines.append(f"\n【事件】{event_node.title}")

        # 显示事件输出参数
        output_params = [port.name for port in event_node.outputs if port.name != "流程出"]
        if output_params:
            lines.append(f"  输出: {', '.join(output_params)}")

        lines.append("")

        # 从事件节点开始追踪流程
        visited: Set[str] = set()
        tree_lines = _trace_flow_tree(
            ctx,
            event_node.id,
            visited,
            "",
            True,
            data_in_index,
            flow_out_index,
            ctx.block_relations,
            expanded_nodes,
        )
        lines.extend(tree_lines)

    lines.append("\n" + "=" * 80)
    return "\n".join(lines)


def _trace_flow_tree(
    ctx: FlowTreeRenderContext,
    node_id: str,
    visited: Set[str],
    prefix: str,
    is_last: bool,
    data_in_index: Dict[str, List],
    flow_out_index: Dict[str, List],
    block_relations: Optional[dict],
    expanded_nodes: Set[str],
) -> List[str]:
    """
    递归追踪流程节点，生成树状图
    
    Args:
        ctx: 渲染上下文
        node_id: 当前节点ID
        visited: 已访问节点集合（防止循环）
        prefix: 当前行前缀（用于缩进）
        is_last: 是否是同级最后一个节点
        
    Returns:
        树状图文本行列表
    """
    lines: List[str] = []
    model = ctx.model

    # 检查循环
    if node_id in visited:
        node = model.nodes.get(node_id)
        if node:
            connector = "└─" if is_last else "├─"
            lines.append(f"{prefix}{connector}↻ 循环: {node.title}")
        return lines

    # 标记为已访问
    visited.add(node_id)

    node = model.nodes.get(node_id)
    if not node:
        visited.remove(node_id)
        return lines

    # 绘制当前节点
    connector = "└─" if is_last else "├─"
    node_info = _get_node_info(model, node)
    lines.append(f"{prefix}{connector}{node_info}")

    if node_id in expanded_nodes:
        child_prefix = prefix + ("    " if is_last else "│   ")
        lines.append(f"{child_prefix}↻ 已展开，参考上文")
        visited.remove(node_id)
        return lines

    successors = _get_ordered_successors(node_id, model, flow_out_index, block_relations, ctx.layout_context)

    if not successors:
        # 终点节点，显示数据输入
        data_info = _get_data_inputs_info(ctx.layout_context, node, data_in_index)
        if data_info:
            child_prefix = prefix + ("    " if is_last else "│   ")
            for info_line in data_info:
                lines.append(f"{child_prefix}{info_line}")
        visited.remove(node_id)
        expanded_nodes.add(node_id)
        return lines

    # 准备子树前缀
    child_prefix = prefix + ("    " if is_last else "│   ")

    if len(successors) == 1:
        # 单一出口，直接递归（与旧逻辑一致）
        _, next_node_id = successors[0]
        lines.extend(
            _trace_flow_tree(
                ctx,
                next_node_id,
                visited,
                child_prefix,
                True,
                data_in_index,
                flow_out_index,
                block_relations,
                expanded_nodes,
            )
        )
    else:
        # 多个出口（分支节点）
        for index, (port_name, next_node_id) in enumerate(successors):
            is_last_branch = index == len(successors) - 1
            branch_connector = "└─" if is_last_branch else "├─"
            lines.append(f"{child_prefix}{branch_connector}[{port_name}]")

            # 递归绘制分支
            branch_prefix = child_prefix + ("    " if is_last_branch else "│   ")
            lines.extend(
                _trace_flow_tree(
                    ctx,
                    next_node_id,
                    visited,
                    branch_prefix,
                    True,
                    data_in_index,
                    flow_out_index,
                    block_relations,
                    expanded_nodes,
                )
            )

    # 在节点后显示数据输入（如果有）
    data_info = _get_data_inputs_info(ctx.layout_context, node, data_in_index)
    if data_info:
        for info_line in data_info:
            lines.append(f"{child_prefix}{info_line}")

    visited.remove(node_id)
    expanded_nodes.add(node_id)
    return lines


def _get_node_info(model: GraphModel, node: NodeModel) -> str:
    """
    获取节点的显示信息
    
    Args:
        model: 图模型
        node: 节点对象
        
    Returns:
        节点信息字符串
    """
    info = f"【{node.title}】"

    # 显示类别
    if node.category != "事件节点":
        info += f" ({node.category})"

    # 显示常量输入
    if node.input_constants:
        constants: List[str] = []
        for port_name, value in node.input_constants.items():
            # 简化显示（去掉引号，截断过长内容）
            display_value = value.strip("\"'")
            if len(display_value) > 20:
                display_value = display_value[:17] + "..."
            constants.append(f"{port_name}={display_value}")
        if constants:
            info += f" {{{', '.join(constants)}}}"

    return info


def _get_data_inputs_info(
    layout_context: LayoutContext,
    node: NodeModel,
    data_in_index: Dict[str, List],
) -> List[str]:
    """
    获取节点的数据输入信息
    
    Args:
        model: 图模型
        node: 节点对象
        
    Returns:
        数据输入信息行列表
    """
    lines: List[str] = []

    # 查找所有数据输入边
    data_inputs: List[Tuple[str, NodeModel, str]] = []
    for edge in data_in_index.get(node.id, []):
        src_node = layout_context.model.nodes.get(edge.src_node)
        if src_node:
            data_inputs.append((edge.dst_port, src_node, edge.src_port))

    if data_inputs:
        lines.append("◈ 数据输入:")
        for dst_port, src_node, src_port in data_inputs:
            lines.append(f"  • {dst_port} ← {src_node.title}.{src_port}")

    return lines


def _generate_data_tree(
    model: GraphModel,
    data_in_index: Dict[str, List],
    data_out_index: Dict[str, List],
) -> str:
    """
    生成纯数据节点图的树状图（按依赖关系）
    
    Args:
        model: 图模型
        
    Returns:
        数据树状图文本
    """
    lines: List[str] = []
    components = compute_data_components_layers(model)
    node_table: Dict[str, NodeModel] = model.nodes

    lines.append("数据流层次:")
    layer_counter = 0

    for component in components:
        for layer in component.layers or [[]]:
            if not layer:
                continue
            layer_counter += 1
            lines.append(f"\n第 {layer_counter} 层:")
            for node_index, node_id in enumerate(layer):
                node = node_table.get(node_id)
                if not node:
                    continue
                is_last = node_index == len(layer) - 1
                connector = "└─" if is_last else "├─"

                node_info = f"{node.title}"
                if node.input_constants:
                    constants = ", ".join(
                        f"{key}={value.strip('\"')[:10]}"
                        for key, value in node.input_constants.items()
                    )
                    node_info += f" {{{constants}}}"

                lines.append(f"  {connector}{node_info}")

                outputs: List[str] = []
                for edge in data_out_index.get(node_id, []):
                    if edge.dst_node in node_table:
                        dst_node = node_table[edge.dst_node]
                        outputs.append(f"{dst_node.title}.{edge.dst_port}")

                if outputs:
                    prefix = "      " if is_last else "  │   "
                    lines.append(f"{prefix}→ {', '.join(outputs)}")

    return "\n".join(lines)


def _get_cached_block_relationships(model: GraphModel) -> Optional[dict]:
    """
    仅复用模型中已缓存的块关系，避免为生成树重复运行完整布局。
    """
    snapshot = getattr(model, "_layout_block_relationships", None)
    if snapshot:
        return snapshot
    return None


def _sort_event_nodes_with_blocks(event_nodes: List[NodeModel], model: GraphModel) -> List[NodeModel]:
    """
    若模型已经缓存块顺序，则按块序号稳定排序事件节点，保持与布局展示一致。
    """
    cached_blocks = getattr(model, "_layout_blocks_cache", None)
    if not isinstance(cached_blocks, list) or not cached_blocks:
        return event_nodes
    order_lookup: Dict[str, int] = {}
    for block in cached_blocks:
        block_event_root = getattr(block, "event_root_id", None)
        block_order = getattr(block, "order_index", 0)
        if block_event_root and block_event_root not in order_lookup and block_order:
            order_lookup[block_event_root] = int(block_order)
    if not order_lookup:
        return event_nodes
    return sorted(
        event_nodes,
        key=lambda node: order_lookup.get(node.id, ORDER_MAX_FALLBACK),
    )


def _get_ordered_successors(
    node_id: str,
    model: GraphModel,
    flow_out_index: Dict[str, List],
    block_relations: Optional[dict],
    layout_context: LayoutContext,
) -> List[Tuple[Optional[str], str]]:
    """
    根据块关系（若可用）获取与布局一致的子节点顺序；否则回退到端口排序。
    """
    if block_relations:
        block = block_relations["block_map"].get(node_id)
        if block is not None:
            node_index = block_relations["node_index_in_block"].get(node_id)
            if node_index is not None:
                if node_index < len(block.flow_nodes) - 1:
                    # 块内线性流程
                    return [(None, block.flow_nodes[node_index + 1])]
                # 使用块间关系（最后一个节点的分支）
                branch_pairs = block_relations["branches_by_block"].get(block)
                if branch_pairs:
                    return branch_pairs

    # 回退：直接读取边并按端口顺序排序
    if layout_context is not None:
        return get_ordered_flow_out_edges(layout_context, node_id)
    node = model.nodes.get(node_id)
    if not node:
        return []
    flow_out_edges: List[Tuple[str, str]] = [
        (edge.src_port, edge.dst_node) for edge in flow_out_index.get(node_id, [])
    ]
    if not flow_out_edges:
        return []

    def _fallback_output_port_index(node_obj: Optional[NodeModel], port_name: str) -> int:
        if not node_obj:
            return 999
        for index, port in enumerate(node_obj.outputs):
            if port.name == port_name:
                return index
        return 999

    flow_out_edges.sort(key=lambda pair: _fallback_output_port_index(node, pair[0]))
    return flow_out_edges



