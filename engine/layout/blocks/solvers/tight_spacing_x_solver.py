from __future__ import annotations

from typing import List, Optional, Tuple, TYPE_CHECKING, cast

from ...internal.constants import BLOCK_X_SPACING_DEFAULT, NODE_WIDTH_DEFAULT
from ...internal.layout_models import LayoutBlock

from .overlap_buckets import iter_overlap_candidates
from .types import PositioningEngineConfig, PositioningRuntimeState

if TYPE_CHECKING:
    from engine.graph.models import EdgeModel


def compute_final_block_left_x(
    config: PositioningEngineConfig,
    runtime: PositioningRuntimeState,
    block: LayoutBlock,
    base_left_x: float,
    top_y: float,
) -> float:
    """
    计算块的最终left X：
    1) 确保“入口X >= 上一个出口X + 200”（使用最新已放置左侧块的坐标）
    2) 在满足(1)且不与左侧已放置块发生矩形重叠的前提下，尽量向左平移

    重要：该函数为“逻辑搬迁”，保持与旧实现完全一致。
    """
    if not config.global_context:
        # 无全局上下文时，保持基础X不变（安全回退）
        return base_left_x

    # 1) 端口约束：计算所有“来自已放置左侧块”的流程入边
    required_min_left_from_ports: Optional[float] = compute_min_left_from_port_gap(config, runtime, block)

    # 2) 几何约束：避免与左侧已放置块发生矩形重叠（仅考虑Y区间有交的块）
    required_min_left_from_overlap: Optional[float] = compute_min_left_from_overlap(config, runtime, block, top_y)

    # 汇总所有约束（取最大作为左边界）：
    left_bounds: List[float] = []
    if isinstance(required_min_left_from_ports, (int, float)):
        left_bounds.append(float(required_min_left_from_ports))
    if isinstance(required_min_left_from_overlap, (int, float)):
        left_bounds.append(float(required_min_left_from_overlap))

    if not left_bounds:
        # 无额外约束：保持基础X
        return base_left_x

    target_left = max(left_bounds)

    # 规则应用：
    # - 若基础X < 约束左界 → 右移到约束左界（保证入口≥出口+200）
    # - 若基础X > 约束左界 → 左移至约束左界（尽量左贴）
    # - 同时不越过初始锚点（initial_x）
    min_anchor = float(config.initial_x)
    final_left = max(target_left, min_anchor)
    return final_left


def compute_min_left_from_port_gap(
    config: PositioningEngineConfig,
    runtime: PositioningRuntimeState,
    block: LayoutBlock,
) -> Optional[float]:
    """
    计算由“流程入口X >= 上一个出口X + 200”产生的对当前块左边界的最小要求。

    Returns:
        required_min_left_from_ports 或 None（当不存在来自已放置块的入边时）

    重要：该函数为“逻辑搬迁”，保持与旧实现完全一致。
    """
    context = config.global_context
    if context is None:
        return None

    # 收集该块内所有流程节点的“来自流程的入边”
    incoming_pairs: List[Tuple[float, float]] = []  # [(prev_output_abs_x, target_entrance_local_x), ...]

    # 当前块内部节点的局部位置映射
    local_pos_map = block.node_local_pos or {}

    # 枚举该块的流程节点
    for dst_node_id in getattr(block, "flow_nodes", []):
        # 取所有流程入边（目标必须是流程端口）
        for raw_edge in context.get_in_flow_edges(dst_node_id):
            edge = cast("EdgeModel", raw_edge)
            src_node_id = edge.src_node
            dst_port_name = edge.dst_port
            _ = dst_port_name  # 保持与旧实现一致（dst_port_name 仅用于语义提示）

            # 源节点所属块
            src_block = config.block_map.get(src_node_id)
            if (src_block is None) or (src_block == block) or (src_block not in runtime.positioned_blocks):
                continue  # 只考虑来自左侧“已放置”的其他块

            # 源输出端口的绝对X ≈ 源块left + 源节点localX + 节点宽度（输出在右侧）
            if src_node_id not in (src_block.node_local_pos or {}):
                continue
            src_block_left = float(src_block.top_left_pos[0])
            src_node_local_x = float(src_block.node_local_pos[src_node_id][0])
            node_width = getattr(src_block, "node_width", NODE_WIDTH_DEFAULT) or NODE_WIDTH_DEFAULT
            prev_output_abs_x = src_block_left + src_node_local_x + float(node_width)

            # 目标入口端口的局部X（输入在左侧，取节点localX作为端口X）
            if dst_node_id not in local_pos_map:
                continue
            target_entrance_local_x = float(local_pos_map[dst_node_id][0])

            incoming_pairs.append((prev_output_abs_x, target_entrance_local_x))

    if not incoming_pairs:
        return None

    # 上一个出口X = 所有 prev_output_abs_x 的最大值
    prev_max_output_abs_x = max(px for px, _ in incoming_pairs)
    # 入口X（局部） = 所有入口端口的localX的最小值（确保所有入口同时满足）
    min_entrance_local_x = min(tx for _, tx in incoming_pairs)

    # 入口绝对X = 当前块left + min_entrance_local_x
    # 约束：当前块left + min_entrance_local_x >= prev_max_output_abs_x + 200
    # => 当前块left >= prev_max_output_abs_x + 200 - min_entrance_local_x
    effective_spacing = float(config.block_x_spacing or BLOCK_X_SPACING_DEFAULT)
    required_min_left = prev_max_output_abs_x + effective_spacing - min_entrance_local_x
    return float(required_min_left)


def compute_min_left_from_overlap(
    config: PositioningEngineConfig,
    runtime: PositioningRuntimeState,
    block: LayoutBlock,
    top_y: float,
) -> Optional[float]:
    """
    计算避免与左侧已放置块发生矩形重叠所需的最小left边界：
    - 仅考虑与当前块在Y轴上有交集的已放置块
    - 要求：当前块left >= max(这些块的right + 200)（空间判断加200像素缓冲）

    重要：该函数为“逻辑搬迁”，保持与旧实现完全一致。
    """
    current_top = float(top_y)
    current_bottom = current_top + float(block.height)

    max_right_among_overlaps: Optional[float] = None
    for placed in iter_overlap_candidates(runtime, current_top, current_bottom):
        if placed is block:
            continue
        placed_left = float(placed.top_left_pos[0])
        placed_top = float(placed.top_left_pos[1])
        placed_right = placed_left + float(placed.width)
        placed_bottom = placed_top + float(placed.height)
        # 判断Y轴是否有交集（半开区间不交）
        if not (placed_bottom <= current_top or placed_top >= current_bottom):
            if (max_right_among_overlaps is None) or (placed_right > max_right_among_overlaps):
                max_right_among_overlaps = placed_right

    if max_right_among_overlaps is None:
        return None
    # 空间判断也需要 +200 像素的水平缓冲
    effective_spacing = float(config.block_x_spacing or BLOCK_X_SPACING_DEFAULT)
    return float(max_right_among_overlaps + effective_spacing)


