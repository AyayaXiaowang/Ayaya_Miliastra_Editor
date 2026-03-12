from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from ...internal.layout_models import LayoutBlock
from ...internal.constants import UI_HEADER_EXTRA, UI_NODE_PADDING, UI_ROW_HEIGHT
from ..block_relationship_analyzer import BlockShiftPlan

from ...utils.graph_query_utils import build_input_port_layout_plan, is_flow_edge

from .overlap_buckets import iter_overlap_candidates, register_block_in_buckets
from .tight_spacing_x_solver import compute_final_block_left_x, compute_min_left_from_port_gap
from .types import PositioningEngineConfig, PositioningRuntimeState


MAX_Y_RELAXATION_ROUNDS: int = 32
Y_RELAXATION_EPSILON: float = 1e-6
MAX_POST_CENTERING_PROJECTION_ROUNDS: int = 16

HALF_ROW_HEIGHT_PX: int = int(UI_ROW_HEIGHT) // 2
NODE_HEADER_HEIGHT_PX: int = int(UI_ROW_HEIGHT) + int(UI_HEADER_EXTRA)
PORT_START_Y_PX: int = int(NODE_HEADER_HEIGHT_PX) + int(UI_NODE_PADDING)
MAX_PORT_INDEX_SENTINEL: int = 10**9


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

    # === 端口锚点（用于“视觉居中”：以连线端口Y为准，而不是块矩形中心） ===
    layout_context = config.global_context
    model = getattr(layout_context, "model", None) if layout_context is not None else None
    registry_context = getattr(layout_context, "registry_context", None) if layout_context is not None else None

    # 端口行号缓存：node_id -> row_index_by_port
    _input_row_index_cache: Dict[str, Dict[str, int]] = {}

    def _connected_input_ports(node_id: str) -> Set[str]:
        if model is None:
            return set()
        edges = getattr(model, "edges", None)
        if not isinstance(edges, dict):
            return set()
        ports: Set[str] = set()
        for edge in edges.values():
            if str(getattr(edge, "dst_node", "") or "") != str(node_id):
                continue
            dst_port = str(getattr(edge, "dst_port", "") or "")
            if dst_port:
                ports.add(dst_port)
        return ports

    def _get_input_row_index(*, node_obj: object, node_id: str, port_name: str) -> int:
        cached = _input_row_index_cache.get(node_id)
        if cached is None:
            if registry_context is None:
                raise AssertionError("缺少 LayoutRegistryContext：无法按 UI 口径计算输入端口行号")
            connected = _connected_input_ports(node_id)
            plan = build_input_port_layout_plan(node_obj, connected, registry_context=registry_context)
            cached = {str(k): int(v) for k, v in dict(getattr(plan, "row_index_by_port", {}) or {}).items()}
            _input_row_index_cache[node_id] = cached
        return int(cached.get(port_name, 0))

    def _node_global_y(*, block: LayoutBlock, node_id: str) -> float:
        # node_local_pos 为 block 内相对坐标（以 node top-left 为基准）
        local = getattr(block, "node_local_pos", None)
        if not isinstance(local, dict):
            return float(current_top_y.get(block, current_group_top_y))
        pos = local.get(node_id)
        if not isinstance(pos, (list, tuple)) or len(pos) < 2:
            return float(current_top_y.get(block, current_group_top_y))
        return float(current_top_y.get(block, current_group_top_y)) + float(pos[1])

    def _port_y_output(*, node_y: float, output_index: int) -> float:
        local_y = float(PORT_START_Y_PX + int(output_index) * int(UI_ROW_HEIGHT) + int(HALF_ROW_HEIGHT_PX))
        return float(node_y) + local_y

    def _port_y_input(*, node_y: float, row_index: int) -> float:
        local_y = float(PORT_START_Y_PX + int(row_index) * int(UI_ROW_HEIGHT) + int(HALF_ROW_HEIGHT_PX))
        return float(node_y) + local_y

    # parent->child 的“代表性 flow 边”缓存：用于从端口坐标推导块间居中约束
    # 选择策略：同一 parent->child 若存在多条边，优先选择 src 输出端口 index 更小的那条（更符合 UI 端口从上到下顺序）。
    edge_ref_by_pair: Dict[tuple[LayoutBlock, LayoutBlock], object] = {}

    if (layout_context is not None) and (model is not None):
        edges = getattr(model, "edges", None)
        nodes = getattr(model, "nodes", None)
        out_index_by_node = getattr(layout_context, "portIndexByNodeOut", None)
        if isinstance(edges, dict) and isinstance(nodes, dict) and isinstance(out_index_by_node, dict):
            # 快速判定：只保留 ordered_children 中真实存在的 parent->child 对
            allowed_child_set_by_parent: Dict[LayoutBlock, Set[LayoutBlock]] = {
                p: set(cs) for p, cs in unique_children_map.items()
            }
            for edge in edges.values():
                if not is_flow_edge(model, edge):
                    continue
                src_node_id = str(getattr(edge, "src_node", "") or "")
                dst_node_id = str(getattr(edge, "dst_node", "") or "")
                if not src_node_id or not dst_node_id:
                    continue
                parent_block = config.block_map.get(src_node_id)
                child_block = config.block_map.get(dst_node_id)
                if parent_block is None or child_block is None:
                    continue
                if parent_block not in group_blocks_set or child_block not in group_blocks_set:
                    continue
                if child_block not in allowed_child_set_by_parent.get(parent_block, set()):
                    continue
                src_port = str(getattr(edge, "src_port", "") or "")
                if not src_port:
                    continue
                out_index_map = out_index_by_node.get(src_node_id)
                if not isinstance(out_index_map, dict):
                    continue
                out_index = out_index_map.get(src_port)
                if out_index is None:
                    continue
                key = (parent_block, child_block)
                prev = edge_ref_by_pair.get(key)
                if prev is None:
                    edge_ref_by_pair[key] = edge
                    continue
                prev_src = str(getattr(prev, "src_node", "") or "")
                prev_port = str(getattr(prev, "src_port", "") or "")
                prev_map = out_index_by_node.get(prev_src, {}) if isinstance(out_index_by_node.get(prev_src), dict) else {}
                prev_index = prev_map.get(prev_port, MAX_PORT_INDEX_SENTINEL)
                if int(out_index) < int(prev_index):
                    edge_ref_by_pair[key] = edge

    def _exclusive_children(parent_block: LayoutBlock) -> List[LayoutBlock]:
        children = unique_children_map.get(parent_block, [])
        if not children:
            return []
        result: List[LayoutBlock] = []
        for child in children:
            ps = parents_from_edges.get(child, set())
            if len(ps) == 1 and parent_block in ps:
                result.append(child)
        return result

    def _pair_port_anchor_y(*, parent_block: LayoutBlock, child_block: LayoutBlock) -> Optional[tuple[float, float]]:
        """
        返回 (src_port_y, dst_port_y)，分别为 parent->child 代表性 flow 边的端口中心点 Y（全局坐标）。
        """
        if model is None or layout_context is None:
            return None
        edge = edge_ref_by_pair.get((parent_block, child_block))
        if edge is None:
            return None
        nodes = getattr(model, "nodes", None)
        if not isinstance(nodes, dict):
            return None
        src_node_id = str(getattr(edge, "src_node", "") or "")
        dst_node_id = str(getattr(edge, "dst_node", "") or "")
        src_port = str(getattr(edge, "src_port", "") or "")
        dst_port = str(getattr(edge, "dst_port", "") or "")
        if not src_node_id or not dst_node_id or not src_port or not dst_port:
            return None
        src_node = nodes.get(src_node_id)
        dst_node = nodes.get(dst_node_id)
        if src_node is None or dst_node is None:
            return None
        out_index_by_node = getattr(layout_context, "portIndexByNodeOut", None)
        if not isinstance(out_index_by_node, dict):
            return None
        out_index_map = out_index_by_node.get(src_node_id)
        if not isinstance(out_index_map, dict):
            return None
        out_index = out_index_map.get(src_port)
        if out_index is None:
            return None

        src_node_y = _node_global_y(block=parent_block, node_id=src_node_id)
        dst_node_y = _node_global_y(block=child_block, node_id=dst_node_id)
        src_port_y = _port_y_output(node_y=src_node_y, output_index=int(out_index))
        dst_row_index = _get_input_row_index(node_obj=dst_node, node_id=dst_node_id, port_name=dst_port)
        dst_port_y = _port_y_input(node_y=dst_node_y, row_index=int(dst_row_index))
        return float(src_port_y), float(dst_port_y)

    # 迭代次数：复杂图也能收敛，同时避免过大开销
    max_rounds = MAX_Y_RELAXATION_ROUNDS
    epsilon = Y_RELAXATION_EPSILON
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
                        # 用户期望：居中不必严格等于均值；只要落在“父中心点范围”之内即可。
                        # 因此这里采用 clamp：仅当当前中心点在范围外时，才把它拉回到边界（最小移动）。
                        current_center = float(_center(block))
                        lo_parent = float(min(parent_centers))
                        hi_parent = float(max(parent_centers))
                        if current_center < lo_parent:
                            desired_center = float(lo_parent)
                        elif current_center > hi_parent:
                            desired_center = float(hi_parent)
                        else:
                            desired_center = float(current_center)
                        desired_top[block] = float(desired_center) - float(block.height) * 0.5
                        has_target[block] = True
                        continue

                # 强约束 4（面向分叉）：子块围绕父块展开（默认目标）
                # 但注意：当该块自身也是“多子分叉父块”时，会出现“作为子块应贴近兄弟 / 作为父块应贴近子块组”冲突。
                # 这里采用阈值策略：冲突过大时优先维持兄弟分支紧凑，避免出现“兄弟分支之间大片空白带”。
                multi_child_target_top: Optional[float] = None
                if len(children) >= 2:
                    # 优先使用“端口锚点”口径（更贴近用户看到的连线扇出位置）：
                    exclusive_children = _exclusive_children(block)
                    anchors: List[tuple[float, float]] = []
                    for ch in exclusive_children:
                        a = _pair_port_anchor_y(parent_block=block, child_block=ch)
                        if a is not None:
                            anchors.append(a)
                    if len(anchors) >= 2:
                        src_mean = sum(a[0] for a in anchors) / float(len(anchors))
                        dst_ys = [a[1] for a in anchors]
                        lo_child = float(min(dst_ys))
                        hi_child = float(max(dst_ys))
                        # 只在越界时才拉回（紧密优先）。注意：这里只能通过下移父块来修正“父块过高”。
                        if float(src_mean) < lo_child:
                            delta = float(lo_child) - float(src_mean)
                            multi_child_target_top = float(current) + float(delta)
                        else:
                            multi_child_target_top = float(current)
                    else:
                        # 回退：缺少端口锚点（例如无 layout_context / 边缺失），使用块中心点范围 clamp。
                        child_centers = [_center(child) for child in children if child in current_top_y]
                        if len(child_centers) >= 2:
                            current_center = float(_center(block))
                            lo_child = float(min(child_centers))
                            hi_child = float(max(child_centers))
                            if current_center < lo_child:
                                desired_center = float(lo_child)
                            elif current_center > hi_child:
                                desired_center = float(hi_child)
                            else:
                                desired_center = float(current_center)
                            multi_child_target_top = float(desired_center) - float(block.height) * 0.5

                if split_child_target_top is not None:
                    if multi_child_target_top is not None:
                        # 冲突场景：该块既是“某父块的分叉子块”，又是“自己的分叉父块”。
                        # 用户期望：保持紧凑堆叠，不追求严格均值；因此仍优先使用“落在范围内”的子块 clamp 目标。
                        desired_top[block] = float(multi_child_target_top)
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

    # 1.5) 居中“范围夹紧”投影（确定性；只做向下平移；保持紧凑）：
    # 居中口径：按“连线端口锚点Y”判断，而不是块矩形中心点。
    #
    # 对 parent->children（exclusive children, 且数量>=2）：
    # - parent_anchor = mean(src_port_y(parent->child_i))
    # - children_range = [min(dst_port_y_i), max(dst_port_y_i)]
    #
    # 仅当 parent_anchor 越界时做最小修正：
    # - parent_anchor < lo：下移 parent（同列后续一起下移）直到 parent_anchor == lo
    # - parent_anchor > hi：下移所有 children（各自列后续一起下移）直到 hi == parent_anchor

    for _ in range(MAX_POST_CENTERING_PROJECTION_ROUNDS):
        any_shift = False
        for parent_block in stable_group_blocks:
            children = _exclusive_children(parent_block)
            if len(children) < 2:
                continue
            anchors: List[tuple[float, float]] = []
            for child in children:
                a = _pair_port_anchor_y(parent_block=parent_block, child_block=child)
                if a is not None:
                    anchors.append(a)
            if len(anchors) < 2:
                # 无端口锚点时不做投影（保持旧行为：靠迭代松弛 + 列内堆叠）
                continue
            parent_anchor = sum(a[0] for a in anchors) / float(len(anchors))
            child_anchor_ys = [a[1] for a in anchors]
            lo = float(min(child_anchor_ys))
            hi = float(max(child_anchor_ys))

            if parent_anchor < lo - epsilon:
                delta = float(lo - parent_anchor)
                col = column_by_block.get(parent_block)
                if col is None:
                    continue
                blocks_in_column = column_to_blocks.get(int(col), [])
                if not blocks_in_column:
                    continue
                start_idx = index_in_column.get(parent_block, 0)
                for later in blocks_in_column[start_idx:]:
                    current_top_y[later] = float(current_top_y.get(later, current_group_top_y)) + float(delta)
                any_shift = True
                continue

            if parent_anchor > hi + epsilon:
                delta = float(parent_anchor - hi)
                for child_block in children:
                    col = column_by_block.get(child_block)
                    if col is None:
                        continue
                    blocks_in_column = column_to_blocks.get(int(col), [])
                    if not blocks_in_column:
                        continue
                    start_idx = index_in_column.get(child_block, 0)
                    for later in blocks_in_column[start_idx:]:
                        current_top_y[later] = float(current_top_y.get(later, current_group_top_y)) + float(delta)
                any_shift = True

        if not any_shift:
            break

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

        for index, block in enumerate(blocks_in_column):
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


