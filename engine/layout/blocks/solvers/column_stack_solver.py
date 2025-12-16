from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from ...internal.layout_models import LayoutBlock
from ..block_relationship_analyzer import BlockShiftPlan

from .overlap_buckets import iter_overlap_candidates, register_block_in_buckets
from .tight_spacing_x_solver import compute_final_block_left_x, compute_min_left_from_port_gap
from .types import PositioningEngineConfig, PositioningRuntimeState


@dataclass(frozen=True)
class ColumnStackSolveInput:
    block_to_column_index: Dict[LayoutBlock, int]
    column_left_x: Dict[int, float]
    current_group_top_y: float
    group_blocks_set: Set[LayoutBlock]
    ordered_children: Dict[LayoutBlock, List[LayoutBlock]]
    shift_plans: Dict[LayoutBlock, BlockShiftPlan]
    parent_sets: Optional[Dict[LayoutBlock, Set[LayoutBlock]]] = None


def solve_stack_blocks_in_columns(
    config: PositioningEngineConfig,
    runtime: PositioningRuntimeState,
    solve_input: ColumnStackSolveInput,
) -> float:
    """
    在列内堆叠块并分配Y坐标。

    重要：该函数为“逻辑搬迁”，要求与 BlockPositioningEngine.stack_blocks_in_columns 完全一致。
    """
    block_to_column_index = solve_input.block_to_column_index
    column_left_x = solve_input.column_left_x
    current_group_top_y = solve_input.current_group_top_y
    group_blocks_set = solve_input.group_blocks_set
    ordered_children = solve_input.ordered_children
    shift_plans = solve_input.shift_plans
    parent_sets = solve_input.parent_sets
    _ = shift_plans  # 保持参数接口不变：该阶段刻意不使用 shift_plans，以免重复施加经验偏移

    if not block_to_column_index:
        return current_group_top_y

    distinct_columns = sorted({index for index in block_to_column_index.values()})
    if not distinct_columns:
        return current_group_top_y

    stable_group_blocks = sorted(group_blocks_set, key=config.stable_sort_key)

    # 构建父关系
    effective_parent_sets = parent_sets or {}

    # 1) 先在“Y 轴”上做多轮全局迭代：为每列求一个满足不重叠约束、且尽量靠近
    #    “多父合流/多子分叉”目标中心点的位置。该阶段只计算 top_y，不涉及 X 贴近。
    #
    # 说明（本函数必须能解释用户反馈的具体案例）：
    # - 旧的 shift_plans（BlockRelationshipAnalyzer.compute_y_shifts）对多父/多子块会施加一个
    #   “0.5×高度总和”的固定下移，能把块（例如 block_03）强行推离其父块中心区间；
    # - 为了让复杂图也能收敛到“居中 + 不重叠”的解，这里使用全局迭代 + 列内前/后向约束传播，
    #   允许块相对初始堆叠“上移或下移”，而不是只允许被动下移。
    #
    # 注意：本阶段不使用 shift_plans，以免重复施加“经验下移”导致过度偏移。
    column_to_blocks: Dict[int, List[LayoutBlock]] = {}
    for block in stable_group_blocks:
        column_index = block_to_column_index.get(block)
        if column_index is None:
            continue
        column_to_blocks.setdefault(int(column_index), []).append(block)
    for column_index, blocks in column_to_blocks.items():
        blocks.sort(key=lambda b: int(b.order_index))

    # children 去重（保持端口顺序稳定）
    unique_children_map: Dict[LayoutBlock, List[LayoutBlock]] = {}
    for parent_block in stable_group_blocks:
        children = (ordered_children or {}).get(parent_block, [])
        seen: Set[LayoutBlock] = set()
        unique_children: List[LayoutBlock] = []
        for child in (children or []):
            if child in seen:
                continue
            seen.add(child)
            if child in group_blocks_set:
                unique_children.append(child)
        unique_children_map[parent_block] = unique_children

    # 父集合以 ordered_children（已过滤 jump-out 边）为准，避免与外部 parent_sets/parents_map 出现语义偏差。
    parents_from_edges: Dict[LayoutBlock, Set[LayoutBlock]] = {block: set() for block in stable_group_blocks}
    for parent_block, children in unique_children_map.items():
        if parent_block not in group_blocks_set:
            continue
        for child_block in children:
            if child_block in parents_from_edges:
                parents_from_edges[child_block].add(parent_block)

    # 列内顺序微调（质量优化，保持确定性且不破坏列内整体结构）：
    # 对于“父块多分叉”的场景，让其多个子块在目标列内按端口顺序排列，减少交叉并增强“分支组”可读性。
    #
    # 关键点：只能做“局部互换”，不允许把分叉子块整体提前或越过其它非兄弟块，
    # 否则会破坏用户期望的列内上下结构（即使语义不变，也会导致观感与块组结构被打乱）。
    #
    # 约束：
    # - 仅对“单父且父块拥有多个子块”的子块生效（与 split_child_target_top 的语义一致）。
    # - 仅在这些子块原本占据的槽位上重排：其它块保持原位置不变。
    if unique_children_map:
        branching_parents = [
            parent_block
            for parent_block, children in unique_children_map.items()
            if parent_block in group_blocks_set and len(children) >= 2
        ]
        branching_parents.sort(key=config.stable_sort_key)

        for column_index, blocks in column_to_blocks.items():
            if len(blocks) < 2:
                continue

            # 对每个分叉父块分别处理，顺序确定可复现
            for parent_block in branching_parents:
                children = unique_children_map.get(parent_block, [])
                if len(children) < 2:
                    continue

                # 仅处理该父块的“单父子块”，并且它们必须实际出现在本列中
                candidate_children: List[LayoutBlock] = []
                for child_block in children:
                    child_parents = parents_from_edges.get(child_block, set())
                    if len(child_parents) == 1 and parent_block in child_parents:
                        # 该子块必须在本列中
                        if child_block in blocks:
                            candidate_children.append(child_block)

                if len(candidate_children) < 2:
                    continue

                # 找到这些子块在当前列中的“槽位”，只在这些槽位内按端口顺序重排
                slot_indices: List[int] = []
                candidate_set = set(candidate_children)
                for idx, block in enumerate(blocks):
                    if block in candidate_set:
                        slot_indices.append(int(idx))

                if len(slot_indices) < 2:
                    continue

                # 端口顺序即 children 列表顺序，candidate_children 已按该顺序收集
                slot_indices.sort()
                for slot_idx, desired_child in zip(slot_indices, candidate_children):
                    blocks[slot_idx] = desired_child

    spacing_y = float(config.block_y_spacing)
    current_top_y: Dict[LayoutBlock, float] = {}
    for column_index in distinct_columns:
        y_cursor = float(current_group_top_y)
        for block in column_to_blocks.get(int(column_index), []):
            current_top_y[block] = y_cursor
            y_cursor = y_cursor + float(block.height) + spacing_y

    def _center(block: LayoutBlock) -> float:
        return float(current_top_y.get(block, current_group_top_y)) + float(block.height) * 0.5

    # 迭代次数：复杂图也能收敛，同时避免过大开销
    max_rounds = 12
    epsilon = 0.5
    # 性能优化：若该事件组内不存在任何需要“对齐/居中”的目标约束，则跳过迭代松弛。
    # 在这种情况下，迭代阶段最终会收敛到“初始紧凑堆叠”的同一解，跳过不会改变排版结果，只减少开销。
    should_relax_y = False
    for block in stable_group_blocks:
        parents = parents_from_edges.get(block, set())
        if not parents:
            parents = effective_parent_sets.get(block, set())
        children = unique_children_map.get(block, [])
        if len(parents) >= 2 or len(children) >= 2:
            should_relax_y = True
            break
        if len(parents) == 1:
            parent = next(iter(parents))
            siblings = unique_children_map.get(parent, [])
            if len(siblings) >= 2:
                should_relax_y = True
                break
            if len(siblings) == 1 and siblings[0] is block:
                should_relax_y = True
                break

    if should_relax_y:
        for _ in range(max_rounds):
            desired_top: Dict[LayoutBlock, float] = {}
            has_target: Dict[LayoutBlock, bool] = {}
            for block in stable_group_blocks:
                current = float(current_top_y.get(block, current_group_top_y))
                parents = parents_from_edges.get(block, set())
                if not parents:
                    parents = effective_parent_sets.get(block, set())
                children = unique_children_map.get(block, [])

                # 子块在“父块多分叉”下的目标 top_y（若适用）
                split_child_target_top: Optional[float] = None
                if len(parents) == 1:
                    parent = next(iter(parents))
                    siblings = unique_children_map.get(parent, [])
                    if len(siblings) >= 2 and parent in current_top_y:
                        parent_center = float(_center(parent))
                        total_height = sum(float(sib.height) for sib in siblings) + spacing_y * float(len(siblings) - 1)
                        group_top = parent_center - total_height * 0.5
                        running_top = float(group_top)
                        for sib in siblings:
                            if int(sib.order_index) == int(block.order_index):
                                split_child_target_top = float(running_top)
                                break
                            running_top = running_top + float(sib.height) + spacing_y

                # 强约束 1：多父合流块居中到父块中心平均
                if len(parents) >= 2:
                    parent_centers = [_center(parent) for parent in parents if parent in current_top_y]
                    if len(parent_centers) >= 2:
                        avg_parent_center = sum(parent_centers) / float(len(parent_centers))
                        desired_top[block] = float(avg_parent_center) - float(block.height) * 0.5
                        has_target[block] = True
                        continue

                # 强约束 4（面向分叉）：子块围绕父块展开（默认目标）
                # 但注意：当该块自身也是“多子分叉父块”时，会出现“作为子块应贴近兄弟 / 作为父块应贴近子块组”冲突。
                # 这里采用阈值策略：冲突过大时优先维持兄弟分支紧凑，避免出现“兄弟分支之间大片空白带”。
                multi_child_target_top: Optional[float] = None
                if len(children) >= 2:
                    child_centers = [_center(child) for child in children if child in current_top_y]
                    if len(child_centers) >= 2:
                        avg_child_center = sum(child_centers) / float(len(child_centers))
                        multi_child_target_top = float(avg_child_center) - float(block.height) * 0.5

                if split_child_target_top is not None:
                    if multi_child_target_top is not None:
                        # 冲突阈值：差距过大说明下游太深，把本层兄弟分支拉开得难看，应优先紧凑
                        conflict_threshold = 500.0
                        if abs(float(split_child_target_top) - float(multi_child_target_top)) >= conflict_threshold:
                            desired_top[block] = float(split_child_target_top)
                            has_target[block] = True
                            continue
                        # 差距不大：折中（保持稳定，不会剧烈摇摆）
                        desired_top[block] = 0.5 * float(split_child_target_top) + 0.5 * float(multi_child_target_top)
                        has_target[block] = True
                        continue

                    desired_top[block] = float(split_child_target_top)
                    has_target[block] = True
                    continue

                # 强约束 2：多子分叉父块居中到子块中心平均（当它不是“分叉子块”时）
                if multi_child_target_top is not None:
                    desired_top[block] = float(multi_child_target_top)
                    has_target[block] = True
                    continue

                # 中约束：单父块对齐到父块中心
                # 仅当父块“唯一子块”为当前块时启用，避免在父块多分叉时把多个子块都拉向父块中心造成挤压与漂移。
                if len(parents) == 1:
                    parent = next(iter(parents))
                    parent_children = unique_children_map.get(parent, [])
                    if (
                        len(parent_children) == 1
                        and int(parent_children[0].order_index) == int(block.order_index)
                        and parent in current_top_y
                    ):
                        desired_top[block] = float(_center(parent)) - float(block.height) * 0.5
                        has_target[block] = True
                        continue

                # 弱约束：保持现状（由列内约束传播负责“紧凑堆叠”）
                desired_top[block] = current
                has_target[block] = False

            max_delta = 0.0
            for column_index in distinct_columns:
                blocks_in_column = column_to_blocks.get(int(column_index), [])
                if not blocks_in_column:
                    continue

                y_list = [
                    float(desired_top.get(block, current_top_y.get(block, current_group_top_y)))
                    for block in blocks_in_column
                ]

                # forward：
                # - 有对齐目标的块：尽量贴近 desired_top，但不允许与上一个块重叠
                # - 无对齐目标的块：忽略 desired_top，尽量向上紧凑堆叠，为有目标的块让出空间
                cursor = float(current_group_top_y)
                for index, block in enumerate(blocks_in_column):
                    use_target = bool(has_target.get(block, False))
                    if use_target:
                        if y_list[index] < cursor:
                            y_list[index] = cursor
                    else:
                        y_list[index] = cursor
                    cursor = y_list[index] + float(block.height) + spacing_y

                # backward：在不重叠前提下尽量“拉回”到期望（允许整体上移）
                for index in range(len(blocks_in_column) - 2, -1, -1):
                    block = blocks_in_column[index]
                    next_top = y_list[index + 1]
                    max_allowed = next_top - float(block.height) - spacing_y
                    if y_list[index] > max_allowed:
                        y_list[index] = max(float(current_group_top_y), max_allowed)

                # 再 forward 一次，确保 backward 没引入重叠
                cursor = float(current_group_top_y)
                for index, block in enumerate(blocks_in_column):
                    if y_list[index] < cursor:
                        y_list[index] = cursor
                    cursor = y_list[index] + float(block.height) + spacing_y

                for index, block in enumerate(blocks_in_column):
                    old = float(current_top_y.get(block, current_group_top_y))
                    new = float(y_list[index])
                    delta = abs(new - old)
                    if delta > max_delta:
                        max_delta = delta
                    current_top_y[block] = new

            if max_delta <= epsilon:
                break

    # 收敛后对“唯一父子链条”做 top_y 等式约束（允许入口块整体下移）：
    # - 定义：parent 的唯一子块为 child，且 child 的唯一父块为 parent（跳出循环边已过滤）。
    # - 目标：链条内所有块 top_y 相等；
    # - 策略：取链条组件内“当前最大 top_y”作为目标，仅将其它块向下平移到该 top_y（不做上移），
    #         从而满足“入口块可以跟着链条整体下移”而不会锁死下游分叉居中。
    #
    # 实现：按链条边构造无向组件，对每个组件做一次下移对齐，并保持列内不重叠（同列后续块一起下移）。
    index_in_column: Dict[LayoutBlock, int] = {}
    column_by_block: Dict[LayoutBlock, int] = {}
    for column_index in distinct_columns:
        blocks_in_column = column_to_blocks.get(int(column_index), [])
        for idx, blk in enumerate(blocks_in_column):
            index_in_column[blk] = int(idx)
            column_by_block[blk] = int(column_index)

    adjacency: Dict[LayoutBlock, List[LayoutBlock]] = {block: [] for block in stable_group_blocks}
    for parent_block, children in unique_children_map.items():
        if parent_block not in group_blocks_set:
            continue
        if len(children) != 1:
            continue
        child_block = children[0]
        if child_block not in group_blocks_set:
            continue
        child_parents = parents_from_edges.get(child_block, set())
        if len(child_parents) != 1 or (parent_block not in child_parents):
            continue
        adjacency[parent_block].append(child_block)
        adjacency[child_block].append(parent_block)

    visited_chain: Set[LayoutBlock] = set()
    for start in stable_group_blocks:
        if start in visited_chain:
            continue
        if not adjacency.get(start):
            visited_chain.add(start)
            continue
        # BFS 组件
        stack = [start]
        component: List[LayoutBlock] = []
        while stack:
            node = stack.pop()
            if node in visited_chain:
                continue
            visited_chain.add(node)
            component.append(node)
            for nb in adjacency.get(node, []):
                if nb not in visited_chain:
                    stack.append(nb)

        if len(component) < 2:
            continue

        target_top = max(float(current_top_y.get(node, current_group_top_y)) for node in component)

        # 组件内每个节点都必须满足同列前序块的最小约束
        required_min = float(current_group_top_y)
        for node in component:
            col = column_by_block.get(node)
            if col is None:
                continue
            idx = index_in_column.get(node, 0)
            if idx <= 0:
                continue
            blocks_in_column = column_to_blocks.get(int(col), [])
            if not blocks_in_column:
                continue
            prev_block = blocks_in_column[idx - 1]
            prev_top = float(current_top_y.get(prev_block, current_group_top_y))
            min_allowed = prev_top + float(prev_block.height) + spacing_y
            if min_allowed > required_min:
                required_min = float(min_allowed)
        if required_min > target_top:
            target_top = float(required_min)

        # 对齐：只允许向下平移
        for node in sorted(component, key=lambda b: (column_by_block.get(b, 0), index_in_column.get(b, 0))):
            col = column_by_block.get(node)
            if col is None:
                continue
            old_top = float(current_top_y.get(node, current_group_top_y))
            delta = float(target_top) - float(old_top)
            if delta <= 1e-6:
                continue
            blocks_in_column = column_to_blocks.get(int(col), [])
            start_idx = index_in_column.get(node, 0)
            for later in blocks_in_column[start_idx:]:
                current_top_y[later] = float(current_top_y.get(later, current_group_top_y)) + float(delta)

    # 2) 基于收敛后的 top_y 再做一次“X 贴近 + 避免重叠”放置（保持几何一致性）
    # 注意：不要清空 runtime.positioned_blocks / runtime.bucket_map。
    # 块间排版是按事件组逐组放置的，前序事件组已经放置的块必须保留在集合中：
    # - 否则末尾 place_orphan_blocks 会把前序事件组误判为“孤立块”并重新放置到右侧；
    # - 同时也会丢失跨事件组的矩形避让信息（当 event_y_gap 较小时尤为明显）。

    group_bottom_y = float(current_group_top_y)
    for column_index in distinct_columns:
        blocks_in_column = column_to_blocks.get(int(column_index), [])
        if not blocks_in_column:
            continue
        column_left = column_left_x.get(column_index, config.initial_x)

        # 小范围“避开轻微纵向擦边导致的巨大 X 推开”：
        # 若某块在当前 top_y 下仅与某个左侧已放置块发生很小的纵向重叠，
        # 但这会触发 compute_min_left_from_overlap 的巨大右移（例如某个左侧块过宽导致后继块被推远），
        # 则将该块及其后续同列块整体向下微调，消除纵向重叠，从而允许更贴近左侧。
        #
        # 该规则只做“向下微调”（保持列内顺序与不重叠），并限制在很小的重叠量内，避免对整体布局造成扰动。
        max_nudge_overlap = 20.0
        min_x_improvement = 120.0

        for index, block in enumerate(blocks_in_column):
            top_y = float(current_top_y.get(block, current_group_top_y))

            if config.enable_tight_block_spacing and config.global_context is not None:
                port_left = compute_min_left_from_port_gap(config, runtime, block)
                if port_left is None:
                    port_left = float(column_left)

                current_top = float(top_y)
                current_bottom = current_top + float(block.height)
                max_right: Optional[float] = None
                overlap_amount = 0.0
                for placed in iter_overlap_candidates(runtime, current_top, current_bottom):
                    if placed is block:
                        continue
                    placed_left = float(placed.top_left_pos[0])
                    placed_top = float(placed.top_left_pos[1])
                    placed_right = placed_left + float(placed.width)
                    placed_bottom = placed_top + float(placed.height)
                    if placed_bottom <= current_top or placed_top >= current_bottom:
                        continue
                    overlap_height = min(current_bottom, placed_bottom) - max(current_top, placed_top)
                    if overlap_height <= 0.0:
                        continue
                    if (max_right is None) or (placed_right > max_right):
                        max_right = placed_right
                        overlap_amount = float(overlap_height)

                if max_right is not None and overlap_amount > 0.0 and overlap_amount <= max_nudge_overlap:
                    required_from_overlap = float(max_right) + float(config.block_x_spacing)
                    if (required_from_overlap - float(port_left)) >= min_x_improvement:
                        delta = float(overlap_amount) + 1.0
                        for later in blocks_in_column[index:]:
                            current_top_y[later] = float(current_top_y.get(later, current_group_top_y)) + delta
                        top_y = float(current_top_y.get(block, current_group_top_y))
            base_left_x = column_left
            if config.enable_tight_block_spacing:
                left_x = compute_final_block_left_x(config, runtime, block, base_left_x, top_y)
            else:
                left_x = base_left_x
            block.top_left_pos = (float(left_x), float(top_y))
            runtime.positioned_blocks.add(block)
            register_block_in_buckets(runtime, block)

            bottom = float(top_y) + float(block.height)
            if bottom > group_bottom_y:
                group_bottom_y = bottom

    # 事件组/连通块的 X 起点归一化：
    # 期望：不同事件流的左侧起点应一致（均从 initial_x 开始），避免出现“事件A起点在右侧很远、事件B在左侧”的观感。
    # 说明：本步骤仅对当前 group_blocks_set 内的块做同向平移，不改变块间相对 X 关系，也不会影响列内 Y 约束。
    group_min_x: Optional[float] = None
    for block in stable_group_blocks:
        if block not in runtime.positioned_blocks:
            continue
        bx = float(getattr(block, "top_left_pos", (config.initial_x, 0.0))[0])
        if (group_min_x is None) or (bx < group_min_x):
            group_min_x = bx
    if group_min_x is not None:
        delta_x = float(config.initial_x) - float(group_min_x)
        if abs(delta_x) > 1e-6:
            for block in stable_group_blocks:
                if block not in runtime.positioned_blocks:
                    continue
                bx, by = getattr(block, "top_left_pos", (config.initial_x, 0.0))
                block.top_left_pos = (float(bx) + float(delta_x), float(by))

    return float(group_bottom_y)


