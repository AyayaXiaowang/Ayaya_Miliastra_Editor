"""
X 轴坐标规划工具。

将流程节点与数据节点的列索引计算从 `CoordinateAssigner` 中拆分出来，形成
纯函数式的辅助模块，便于单独测试与复用。
"""

from __future__ import annotations

from typing import Dict, List, Set, Tuple

from ..blocks.block_layout_context import BlockLayoutContext
from .longest_path import resolve_levels_with_parents


def compute_flow_x_positions(context: BlockLayoutContext) -> dict[str, float]:
    """
    计算流程节点的 X 位置（列索引）。

    策略：
    - 先为顺序相邻的流程节点建立最小间距为 1 的约束边；
    - 再结合 `flow_pair_required_gap` 中的跨节点槽位间距要求建立加权有向边；
    - 最终将整张图视作带权 DAG，调用 `resolve_levels_with_parents` 计算最长路径，
      得到每个流程节点的列索引。
    """
    flow_ids = list(context.flow_node_ids)
    flow_x_positions: dict[str, float] = {}

    if not flow_ids:
        return flow_x_positions

    order_map: Dict[str, int] = {flow_id: index for index, flow_id in enumerate(flow_ids)}
    adjacency_map: Dict[str, List[str]] = {flow_id: [] for flow_id in flow_ids}
    parent_sets: Dict[str, Set[str]] = {flow_id: set() for flow_id in flow_ids}
    edge_weights: Dict[Tuple[str, str], float] = {}

    def register_edge(src_flow_id: str, dst_flow_id: str, weight: float) -> None:
        """
        在 DAG 中注册一条有向加权边。

        若同一对节点已存在边，则保留更大的权重（更大的最小槽位间距）。
        """
        if src_flow_id not in adjacency_map or dst_flow_id not in adjacency_map:
            return
        if dst_flow_id not in adjacency_map[src_flow_id]:
            adjacency_map[src_flow_id].append(dst_flow_id)
        parent_sets.setdefault(dst_flow_id, set()).add(src_flow_id)
        existing = edge_weights.get((src_flow_id, dst_flow_id))
        if existing is None or weight > existing:
            edge_weights[(src_flow_id, dst_flow_id)] = weight

    # 顺序相邻流程节点之间至少间隔 1 个槽位
    for index in range(1, len(flow_ids)):
        previous_flow_id = flow_ids[index - 1]
        current_flow_id = flow_ids[index]
        register_edge(previous_flow_id, current_flow_id, 1.0)

    # 引入布局前分析阶段得到的“需要额外槽位间距”的约束
    for (src_flow_id, dst_flow_id), gap in context.flow_pair_required_gap.items():
        weight = float(gap)
        if weight <= 0.0:
            weight = 1.0
        register_edge(src_flow_id, dst_flow_id, weight)

    def children_provider(flow_id: str) -> List[str]:
        """提供给最长路径算法的子节点访问器。"""
        return adjacency_map.get(flow_id, [])

    flow_levels = resolve_levels_with_parents(
        flow_ids,
        children_provider,
        parent_provider=lambda flow_id: parent_sets.get(flow_id, set()),
        weight_provider=lambda src, dst: edge_weights.get((src, dst), 1.0),
        order_key=lambda flow_id: order_map.get(flow_id, 0),
    )

    for flow_id in flow_ids:
        flow_x_positions[flow_id] = float(flow_levels.get(flow_id, 0.0))

    return flow_x_positions


def compute_data_x_positions(
    context: BlockLayoutContext,
    flow_x_positions: dict[str, float],
) -> dict[str, float]:
    """
    计算数据节点的 X 坐标（列索引）。

    对每个数据节点：
    - 若存在链条信息：对每条链，取消费者流程节点的列索引，向左回溯（位置编号从 0
      开始，表示最靠近消费者），得到候选列索引，最终取所有候选中的最小值；
    - 若不存在链条信息：为该节点分配“回退槽位”，从当前最大流程列右侧开始依次递增，
      并同步更新 `context.node_slot_index`。
    """
    data_x_positions: dict[str, float] = {}

    # 为缺少链信息的数据节点准备列回退：靠在当前流程列的右侧
    max_flow_column = max(flow_x_positions.values(), default=-1.0)
    next_fallback_slot = max_flow_column + 1.0 if flow_x_positions else 0.0

    def assign_fallback_slot(node_id: str) -> float:
        """
        为没有链信息的数据节点分配回退槽位。

        若 `node_slot_index` 已有值则复用，否则从当前回退槽位开始递增分配。
        """
        nonlocal next_fallback_slot
        existing_slot = context.node_slot_index.get(node_id)
        if existing_slot is not None:
            return float(existing_slot)
        slot = next_fallback_slot
        next_fallback_slot += 1.0
        context.node_slot_index[node_id] = int(slot)
        return slot

    for data_id in context.data_nodes_in_order:
        chain_ids = context.data_chain_ids_by_node.get(data_id, [])

        if not chain_ids:
            # 没有链信息的数据节点，分配回退槽位（固定在流程列右侧依次递增）
            slot_index = assign_fallback_slot(data_id)
            data_x_positions[data_id] = slot_index
            continue

        # 计算所有链的 X 候选值
        x_candidates: List[float] = []
        for chain_id in chain_ids:
            target_flow_id = context.chain_target_flow.get(chain_id)
            if target_flow_id and target_flow_id in flow_x_positions:
                # 消费者流程位置
                consumer_x = flow_x_positions[target_flow_id]
                # 该节点在链上的位置（从消费者往回数，0 表示最靠近消费者）
                position = context.node_position_in_chain.get((data_id, chain_id), 0)
                # X 候选 = 消费者位置 - (位置 + 1)
                # 例如：链 [a] 只有一个节点，position=0，a 的 X = consumer_x - 1
                x_candidate = consumer_x - (position + 1)
                x_candidates.append(x_candidate)

        if x_candidates:
            # 取所有候选中的最小值
            resolved_position = min(x_candidates)
        else:
            # 如果没有有效的候选值，使用回退槽位，确保不会与流程列冲突
            resolved_position = assign_fallback_slot(data_id)

        data_x_positions[data_id] = resolved_position
        context.node_slot_index[data_id] = int(resolved_position)

    return data_x_positions


