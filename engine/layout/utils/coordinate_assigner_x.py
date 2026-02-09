"""
X 轴坐标规划工具。

将流程节点与数据节点的列索引计算从 `CoordinateAssigner` 中拆分出来，形成
纯函数式的辅助模块，便于单独测试与复用。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from ..blocks.block_layout_context import BlockLayoutContext
from .local_variable_relay_inserter import (
    is_local_var_relay_node_id,
    parse_local_var_relay_forced_slot_index,
)
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

    # 为缺少链信息的数据节点准备列回退：靠在当前流程列的右侧。
    # 注意：这类节点往往只参与“输出组装”（例如 拼装字典/拼装列表），并不会被数据链枚举覆盖；
    # 若简单按出现顺序递增分配，会导致块内数据边出现“回头线”。
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

    def _assign_fallback_slots_within_block_by_data_topology() -> Dict[str, float]:
        """
        为“无链信息”的纯数据节点分配稳定的回退列索引，并尽量保证：
        - 若存在数据边 A -> B（且 A/B 均为无链节点），则 B 的列索引应 >= A 的列索引 + 1；
        - 从而避免在同一块内出现明显的回头线。
        """
        fallback_nodes: List[str] = []
        order_map: Dict[str, int] = {}
        for index, data_id in enumerate(context.data_nodes_in_order):
            chain_ids = context.data_chain_ids_by_node.get(data_id, [])
            if chain_ids:
                continue
            fallback_nodes.append(data_id)
            order_map[data_id] = index

        if not fallback_nodes:
            return {}

        fallback_set: Set[str] = set(fallback_nodes)
        adjacency_map: Dict[str, List[str]] = {node_id: [] for node_id in fallback_nodes}
        parent_sets: Dict[str, Set[str]] = {node_id: set() for node_id in fallback_nodes}

        for src_id in fallback_nodes:
            for edge in context.get_data_out_edges(src_id) or []:
                dst_id = getattr(edge, "dst_node", None)
                if not isinstance(dst_id, str) or dst_id == "":
                    continue
                if dst_id not in fallback_set:
                    continue
                if not context.is_pure_data_node(dst_id):
                    continue
                if dst_id not in adjacency_map[src_id]:
                    adjacency_map[src_id].append(dst_id)
                parent_sets[dst_id].add(src_id)

        levels = resolve_levels_with_parents(
            fallback_nodes,
            adjacency_provider=lambda node_id: adjacency_map.get(node_id, []),
            parent_provider=lambda node_id: parent_sets.get(node_id, set()),
            order_key=lambda node_id: order_map.get(node_id, 0),
            default_level=0.0,
        )
        base = float(max_flow_column + 1.0 if flow_x_positions else 0.0)
        resolved: Dict[str, float] = {}
        for node_id in fallback_nodes:
            resolved[node_id] = base + float(levels.get(node_id, 0.0))
        return resolved

    fallback_positions_by_topology = _assign_fallback_slots_within_block_by_data_topology()

    for data_id in context.data_nodes_in_order:
        # 局部变量中转节点：若 node_id 编码了强制槽位索引，则优先使用该槽位，
        # 让 relay 真正落在“距离阈值处”的中间列，而不是默认贴近消费者一列。
        if is_local_var_relay_node_id(data_id):
            forced_slot_index = parse_local_var_relay_forced_slot_index(str(data_id))
            if forced_slot_index is not None:
                data_x_positions[data_id] = float(forced_slot_index)
                context.node_slot_index[data_id] = int(forced_slot_index)
                continue

        chain_ids = context.data_chain_ids_by_node.get(data_id, [])

        if not chain_ids:
            # 没有链信息的数据节点，分配回退槽位（固定在流程列右侧依次递增）
            if data_id in fallback_positions_by_topology:
                slot_index = float(fallback_positions_by_topology[data_id])
                context.node_slot_index[data_id] = int(slot_index)
            else:
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

    # ------------------------------------------------------------------
    # 关键不变量：禁止块内出现 data 连线“右→左折返”
    # ------------------------------------------------------------------
    #
    # 背景：
    # - data_x_positions 主要依赖“链枚举”结果驱动（消费者 flow 的列索引 + 链内位置回溯）；
    # - 当链枚举因限流被截断（LAYOUT_MAX_CHAINS_PER_NODE 等）时，可能出现：
    #   - 某条 data→data 边的上游节点未被覆盖到相同链里，导致其 X 值不受该消费者约束；
    #   - 进而出现 src_x > dst_x 的折返线（UI 观感与规则均不允许）。
    #
    # 这里在“初始 X 分配”之后，基于真实 data 边做一次收敛式约束传播：
    # - 对任意 data→data 边 A->B：强制 A 的列索引 <= B 的列索引 - 1；
    # - 对任意 data→flow 边 A->F：强制 A 的列索引 <= flow(F) - 1；
    #
    # 该过程只会把节点向左移动（减小列索引），不会把节点推到更右侧，因此不会引入新的折返。
    data_id_set: Set[str] = set(context.data_nodes_in_order)
    if data_id_set and flow_x_positions:
        max_iterations = len(data_id_set) + 2
        iteration_count = 0
        changed = True
        while changed and iteration_count < max_iterations:
            changed = False
            iteration_count += 1
            for src_id in context.data_nodes_in_order:
                if src_id not in data_x_positions:
                    continue
                current_x = float(data_x_positions[src_id])
                out_edges = context.get_data_out_edges(src_id) or []
                if not out_edges:
                    continue

                min_allowed_x: Optional[float] = None
                for edge in out_edges:
                    dst_id = getattr(edge, "dst_node", None)
                    if not isinstance(dst_id, str) or dst_id == "":
                        continue

                    if dst_id in flow_x_positions:
                        candidate_allowed = float(flow_x_positions[dst_id]) - 1.0
                    elif dst_id in data_id_set and context.is_pure_data_node(dst_id):
                        dst_x = data_x_positions.get(dst_id)
                        if dst_x is None:
                            continue
                        candidate_allowed = float(dst_x) - 1.0
                    else:
                        continue

                    if min_allowed_x is None or candidate_allowed < min_allowed_x:
                        min_allowed_x = candidate_allowed

                if min_allowed_x is None:
                    continue

                if current_x > min_allowed_x + 1e-9:
                    data_x_positions[src_id] = float(min_allowed_x)
                    context.node_slot_index[src_id] = int(min_allowed_x)
                    changed = True

    return data_x_positions


