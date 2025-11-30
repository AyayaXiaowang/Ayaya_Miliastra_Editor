"""
纯数据图布局模块

为没有流程连线的纯数据节点图提供专门的布局算法：
- 基于连通分量分块
- 块内拓扑分层
- 层从左到右排列，层内垂直堆叠
"""

from typing import Dict, List, Optional, Callable

from engine.graph.models import GraphModel, NodeModel

from ..utils.data_graph_utils import compute_data_components_layers
from ..core.layout_context import LayoutContext
from ..utils.graph_query_utils import estimate_node_height_ui_exact_with_context
from ..core.constants import SLOT_WIDTH_MULTIPLIER
from ..utils.basic_block_utils import build_basic_block


def layout_pure_data_graph(
    model: GraphModel,
    node_width_default: float,
    node_height_default: float,
    initial_x: float,
    initial_y: float,
    block_padding: float,
    block_x_spacing: float,
    block_colors: List[str],
    estimate_node_height_func: Optional[Callable[[NodeModel], float]] = None,
    layout_context: Optional["LayoutContext"] = None,
) -> None:
    """
    为纯数据节点图进行简单排版：分块=连通分量，块内=拓扑分层
    
    规则（最小可行）：
    - 将所有节点视为数据节点，连线仅统计数据边（目标端口非流程口）
    - 以数据边构建无向图，求连通分量作为"块"
    - 每个块内做拓扑分层（按入度0→1→...）；有环则剩余节点归为同一层
    - 层从左到右，层内垂直堆叠（使用简单高度估算避免重叠）
    - 各块在全局坐标中自左向右排列
    
    Args:
        model: 图模型
        node_width_default: 默认节点宽度
        node_height_default: 默认节点高度
        initial_x: 初始X坐标
        initial_y: 初始Y坐标
        block_padding: 块内边距
        block_x_spacing: 块间距
        block_colors: 块颜色列表
        estimate_node_height_func: 估算节点高度的函数
    """
    if not model.nodes:
        return

    if layout_context is None:
        layout_context = LayoutContext(model)

    # 参数
    node_width = node_width_default
    node_height = node_height_default
    slot_width = node_width * SLOT_WIDTH_MULTIPLIER
    block_padding_local = block_padding
    component_x_spacing = block_x_spacing

    components = compute_data_components_layers(model)

    # 逐块排版
    current_left = initial_x
    basic_blocks = []
    color_index = 0

    for component in components:
        if not component.nodes:
            continue

        layers: List[List[str]] = component.layers or [[]]
        # 层从左到右，层内垂直堆叠
        layer_width = slot_width
        max_height_in_component = 0.0
        layer_positions: Dict[str, tuple] = {}

        for layer_index, layer_nodes in enumerate(layers):
            x_center = current_left + block_padding_local + layer_index * layer_width

            # 层内顺序固定为拓扑输出顺序（保持稳定可视化）
            current_y = block_padding_local
            for node_id in layer_nodes:
                node = model.nodes.get(node_id)
                if not node:
                    continue
                if layout_context:
                    node_height_est = estimate_node_height_ui_exact_with_context(layout_context, node_id)
                elif estimate_node_height_func:
                    node_height_est = estimate_node_height_func(node)
                else:
                    node_height_est = node_height_default
                layer_positions[node_id] = (x_center, current_y)
                current_y += node_height_est + 20.0  # 间距

            if current_y > max_height_in_component:
                max_height_in_component = current_y

        # 应用坐标到模型
        for node_id, (x_local, y_local) in layer_positions.items():
            node = model.nodes.get(node_id)
            if node:
                node.pos = (x_local, initial_y + y_local)

        block = build_basic_block(
            node_ids=component.nodes,
            color=block_colors[color_index % len(block_colors)],
        )
        color_index += 1
        basic_blocks.append(block)

        # 下一个块向右偏移（计算块宽度）
        block_width = len(layers) * layer_width + 2 * block_padding_local
        current_left += block_width + component_x_spacing

    # 将基本块信息存储到模型
    model.basic_blocks = basic_blocks
    setattr(model, "_layout_context_cache", layout_context)



