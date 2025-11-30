"""
块间定位引擎

负责计算基本块的位置，包括：
- 查找事件起始块
- 枚举流程链条
- 计算块的列索引（基于最长路径约束）
- 计算列的X坐标
- 在列内堆叠块并分配Y坐标
- 放置孤立块
"""

from __future__ import annotations
from typing import Dict, Set, List, Tuple, Optional, TYPE_CHECKING, cast
import math

from ..core.constants import NODE_WIDTH_DEFAULT, NODE_HEIGHT_DEFAULT, BLOCK_X_SPACING_DEFAULT
from ..core.layout_models import LayoutBlock
from ..utils.longest_path import resolve_levels_with_parents
from .block_relationship_analyzer import BlockShiftPlan

if TYPE_CHECKING:
    from engine.graph.models import GraphModel, NodeModel, EdgeModel
    from ..core.layout_context import LayoutContext


class BlockPositioningEngine:
    """块间定位引擎"""

    def __init__(
        self,
        model: GraphModel,
        layout_blocks: List["LayoutBlock"],
        block_map: Dict[str, "LayoutBlock"],
        initial_x: float,
        initial_y: float,
        block_x_spacing: float,
        block_y_spacing: float,
        global_layout_context: Optional["LayoutContext"] = None,
        parents_map: Optional[Dict["LayoutBlock", Set["LayoutBlock"]]] = None,
        event_start_block_lookup: Optional[Dict[str, "LayoutBlock"]] = None,
        enable_tight_block_spacing: bool = True,
    ):
        self.model = model
        self.layout_blocks = layout_blocks
        self.block_map = block_map
        self.initial_x = initial_x
        self.initial_y = initial_y
        self.block_x_spacing = block_x_spacing
        self.block_y_spacing = block_y_spacing
        self.global_context = global_layout_context
        self.parents_map: Dict["LayoutBlock", Set["LayoutBlock"]] = parents_map or {}
        self._event_start_block_lookup = event_start_block_lookup or {}
        self.enable_tight_block_spacing = bool(enable_tight_block_spacing)

        self.positioned_blocks: Set["LayoutBlock"] = set()
        base_bucket = float(self.block_y_spacing) + float(NODE_HEIGHT_DEFAULT) * 1.5
        self._bucket_size = max(200.0, base_bucket)
        self._bucket_map: Dict[int, List["LayoutBlock"]] = {}

    def find_start_block(self, event_node: NodeModel) -> Optional["LayoutBlock"]:
        """
        查找事件节点对应的起始块
        
        Args:
            event_node: 事件节点
            
        Returns:
            起始块，若未找到则返回None
        """
        start_block: Optional["LayoutBlock"] = self.block_map.get(event_node.id)
        if start_block is None:
            start_block = self._event_start_block_lookup.get(event_node.id)
        if start_block is None:
            candidates = [
                block for block in self.layout_blocks if block.event_root_id == event_node.id
            ]
            if candidates:
                start_block = min(candidates, key=lambda block: block.order_index)
        return start_block

    def collect_group_blocks(
        self,
        start_block: "LayoutBlock",
        ordered_children: Dict["LayoutBlock", List["LayoutBlock"]],
    ) -> Set["LayoutBlock"]:
        """
        收集事件组内的所有块
        
        Args:
            start_block: 起始块
            ordered_children: 每个块的子块列表
            
        Returns:
            事件组包含的块集合
        """

        stack: List["LayoutBlock"] = [start_block]
        visited: Set["LayoutBlock"] = set()
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            for child in ordered_children.get(current, []):
                if child not in visited:
                    stack.append(child)

        return visited

    def compute_column_indices(
        self,
        group_blocks_set: Set["LayoutBlock"],
        ordered_children: Dict["LayoutBlock", List["LayoutBlock"]],
        parent_sets: Optional[Dict["LayoutBlock", Set["LayoutBlock"]]] = None,
    ) -> Dict["LayoutBlock", int]:
        """
        计算每个块的列索引（基于最长路径约束）
        
        Args:
            group_blocks_set: 事件组包含的块集合
            ordered_children: 块的子块列表
            
        Returns:
            block_to_column_index: 每个块的列索引字典
        """
        if not group_blocks_set:
            return {}

        adjacency: Dict["LayoutBlock", List["LayoutBlock"]] = {}
        parent_sets = parent_sets or self._build_parent_sets(group_blocks_set)

        for block in group_blocks_set:
            adjacency[block] = [
                child
                for child in ordered_children.get(block, [])
                if child in group_blocks_set and child is not block
            ]

        def _children_provider(block: "LayoutBlock") -> List["LayoutBlock"]:
            return adjacency.get(block, [])

        resolved_levels = resolve_levels_with_parents(
            group_blocks_set,
            _children_provider,
            parent_provider=lambda blk: parent_sets.get(blk, set()),
            order_key=lambda blk: blk.order_index,
        )

        return {block: int(resolved_levels.get(block, 0.0)) for block in group_blocks_set}

    def compute_column_x_positions(
        self,
        block_to_column_index: Dict["LayoutBlock", int],
    ) -> Dict[int, float]:
        """
        计算每列的像素X坐标
        
        Args:
            block_to_column_index: 每个块的列索引
            
        Returns:
            column_left_x: 每列的左边界X坐标
        """
        if not block_to_column_index:
            return {}

        distinct_columns = sorted({column_index for column_index in block_to_column_index.values()})

        # 计算每一列的最大宽度（无块的列宽视为0）
        column_max_width: Dict[int, float] = {column_index: 0.0 for column_index in distinct_columns}
        for block, column_index in block_to_column_index.items():
            current_width = float(block.width)
            if current_width > column_max_width[column_index]:
                column_max_width[column_index] = current_width

        # 将稀疏列转为连续坐标（保持列差不变，不压缩"空列"）
        column_left_x: Dict[int, float] = {}
        if not distinct_columns:
            return column_left_x

        current_left_x = float(self.initial_x)
        previous_column_index: Optional[int] = None
        for column_index in distinct_columns:
            if previous_column_index is None:
                column_left_x[column_index] = current_left_x
            else:
                gap = column_index - previous_column_index
                previous_width = column_max_width.get(previous_column_index, 0.0)
                current_left_x = current_left_x + previous_width + float(self.block_x_spacing) * float(gap)
                column_left_x[column_index] = current_left_x
            previous_column_index = column_index

        return column_left_x

    def stack_blocks_in_columns(
        self,
        block_to_column_index: Dict["LayoutBlock", int],
        column_left_x: Dict[int, float],
        current_group_top_y: float,
        group_blocks_set: Set["LayoutBlock"],
        ordered_children: Dict["LayoutBlock", List["LayoutBlock"]],
        shift_plans: Dict["LayoutBlock", BlockShiftPlan],
        parent_sets: Optional[Dict["LayoutBlock", Set["LayoutBlock"]]] = None,
    ) -> float:
        """
        在列内堆叠块并分配Y坐标
        
        Args:
            block_to_column_index: 每个块的列索引
            column_left_x: 每列的左边界X坐标
            current_group_top_y: 当前事件组的顶部Y坐标
            group_blocks_set: 事件组包含的块集合
            ordered_children: 每个块的子块列表
            shift_plans: 每个块的Y轴偏移计划
            
        Returns:
            group_bottom_y: 事件组的底部Y坐标
        """
        if not block_to_column_index:
            return current_group_top_y

        distinct_columns = sorted({index for index in block_to_column_index.values()})
        if not distinct_columns:
            return current_group_top_y

        sorted_column_buckets, pre_start_y_by_block = self._preview_column_stacks(
            block_to_column_index,
            distinct_columns,
            current_group_top_y,
        )

        # 构建父关系
        effective_parent_sets = parent_sets or self._build_parent_sets(group_blocks_set)

        # 记录每个块"已放置的起始Y"
        placed_base_y_by_block: Dict["LayoutBlock", float] = {}

        # 列索引从小到大，列内按 order_index 从小到大
        group_bottom_y = current_group_top_y
        for column_index in distinct_columns:
            blocks_in_column = sorted_column_buckets.get(column_index, [])
            column_left = column_left_x.get(column_index, self.initial_x)
            cursor_y = current_group_top_y

            for block in blocks_in_column:
                # 计算起始高度（含父块对齐和抬升逻辑）
                base_y = self._compute_block_base_y(
                    block,
                    cursor_y,
                    effective_parent_sets,
                    placed_base_y_by_block,
                    ordered_children,
                    pre_start_y_by_block,
                    current_group_top_y,
                )

                # 应用Y偏移（含阈值保护）
                shift_y = self._compute_effective_shift_y(
                    block,
                    base_y,
                    shift_plans,
                    pre_start_y_by_block,
                    current_group_top_y,
                )

                adjusted_top = base_y + shift_y

                # 基础X = 当前列左边界
                base_left_x = column_left
                # 根据配置决定是否向左贴近
                if self.enable_tight_block_spacing:
                    adjusted_left_x = self._compute_final_block_left_x(block, base_left_x, adjusted_top)
                else:
                    adjusted_left_x = base_left_x

                block.top_left_pos = (adjusted_left_x, adjusted_top)
                self.positioned_blocks.add(block)
                self._register_block_in_buckets(block)

                # 记录该块"已放置起始Y"供右侧子块参考
                placed_base_y_by_block[block] = base_y

                # 下一个块从本块底部 + 间距开始
                cursor_y = adjusted_top + float(block.height) + float(self.block_y_spacing)

            # 记录本列底部，计算事件组底部
            if blocks_in_column:
                column_bottom = cursor_y - float(self.block_y_spacing)
                if column_bottom > group_bottom_y:
                    group_bottom_y = column_bottom

        return group_bottom_y

    def _preview_column_stacks(
        self,
        block_to_column_index: Dict["LayoutBlock", int],
        distinct_columns: List[int],
        current_group_top_y: float,
    ) -> Tuple[Dict[int, List["LayoutBlock"]], Dict["LayoutBlock", float]]:
        """按列预排序块并记录初始堆叠位置，供后续阶段复用。"""
        column_to_blocks: Dict[int, List["LayoutBlock"]] = {}
        for block, column_index in block_to_column_index.items():
            column_to_blocks.setdefault(column_index, []).append(block)

        pre_start_y_by_block: Dict["LayoutBlock", float] = {}
        sorted_column_buckets: Dict[int, List["LayoutBlock"]] = {}
        for column_index in distinct_columns:
            blocks_in_column_preview = column_to_blocks.get(column_index, [])
            if not blocks_in_column_preview:
                continue
            blocks_in_column_preview.sort(key=lambda block: block.order_index)
            sorted_column_buckets[column_index] = blocks_in_column_preview
            preview_cursor_y = current_group_top_y
            for block in blocks_in_column_preview:
                pre_start_y_by_block[block] = preview_cursor_y
                preview_cursor_y = preview_cursor_y + float(block.height) + float(self.block_y_spacing)

        return sorted_column_buckets, pre_start_y_by_block

    # ---------------- X轴补充规则：端口最小间距 + 可用空间尽量左移 ----------------
    def _compute_final_block_left_x(self, block: "LayoutBlock", base_left_x: float, top_y: float) -> float:
        """
        计算块的最终left X：
        1) 确保“入口X >= 上一个出口X + 200”（使用最新已放置左侧块的坐标）
        2) 在满足(1)且不与左侧已放置块发生矩形重叠的前提下，尽量向左平移
        
        Args:
            block: 当前要放置的块
            base_left_x: 基础X（列左边界）
            top_y: 该块的最终top（已含父对齐与抬升）
        """
        if not self.global_context:
            # 无全局上下文时，保持基础X不变（安全回退）
            return base_left_x

        # 1) 端口约束：计算所有“来自已放置左侧块”的流程入边，得到：
        #    required_min_left_from_ports = max_prev_output_abs_x + 200 - min_target_entrance_local_x
        required_min_left_from_ports: Optional[float] = self._compute_min_left_from_port_gap(block)

        # 2) 几何约束：避免与左侧已放置块发生矩形重叠（仅考虑Y区间有交的块）
        required_min_left_from_overlap: Optional[float] = self._compute_min_left_from_overlap(block, top_y)

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
        min_anchor = float(self.initial_x)
        final_left = max(target_left, min_anchor)
        return final_left

    def _compute_min_left_from_port_gap(self, block: "LayoutBlock") -> Optional[float]:
        """
        计算由“流程入口X >= 上一个出口X + 200”产生的对当前块左边界的最小要求。
        
        Returns:
            required_min_left_from_ports 或 None（当不存在来自已放置块的入边时）
        """
        context = self.global_context
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
                # 源节点所属块
                src_block = self.block_map.get(src_node_id)
                if (src_block is None) or (src_block == block) or (src_block not in self.positioned_blocks):
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
        effective_spacing = float(self.block_x_spacing or BLOCK_X_SPACING_DEFAULT)
        required_min_left = prev_max_output_abs_x + effective_spacing - min_entrance_local_x
        return float(required_min_left)

    def _compute_min_left_from_overlap(self, block: "LayoutBlock", top_y: float) -> Optional[float]:
        """
        计算避免与左侧已放置块发生矩形重叠所需的最小left边界：
        - 仅考虑与当前块在Y轴上有交集的已放置块
        - 要求：当前块left >= max(这些块的right + 200)（空间判断加200像素缓冲）
        """
        current_top = float(top_y)
        current_bottom = current_top + float(block.height)

        max_right_among_overlaps: Optional[float] = None
        for placed in self._iter_overlap_candidates(current_top, current_bottom):
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
        effective_spacing = float(self.block_x_spacing or BLOCK_X_SPACING_DEFAULT)
        return float(max_right_among_overlaps + effective_spacing)

    def _iter_overlap_candidates(self, top: float, bottom: float) -> List["LayoutBlock"]:
        """
        根据垂直区间仅返回可能重叠的已放置块，避免对整个集合进行O(N)扫描。
        """
        if not self._bucket_map:
            return list(self.positioned_blocks)
        start_bucket = int(math.floor(top / self._bucket_size)) - 1
        end_bucket = int(math.floor(bottom / self._bucket_size)) + 1
        candidates: List["LayoutBlock"] = []
        seen: Set["LayoutBlock"] = set()
        for bucket_index in range(start_bucket, end_bucket + 1):
            bucket_blocks = self._bucket_map.get(bucket_index)
            if not bucket_blocks:
                continue
            for block in bucket_blocks:
                if block in seen:
                    continue
                seen.add(block)
                candidates.append(block)
        return candidates

    def _register_block_in_buckets(self, block: "LayoutBlock") -> None:
        """
        将已放置块按垂直区间注册到桶中，供后续重叠检测快速查询。
        """
        top = float(block.top_left_pos[1])
        bottom = top + float(block.height)
        start_bucket = int(math.floor(top / self._bucket_size))
        end_bucket = int(math.floor(bottom / self._bucket_size))
        for bucket_index in range(start_bucket, end_bucket + 1):
            self._bucket_map.setdefault(bucket_index, []).append(block)

    def _build_parent_sets(
        self,
        group_blocks_set: Set["LayoutBlock"],
    ) -> Dict["LayoutBlock", Set["LayoutBlock"]]:
        """返回限制在事件组内的父集合，避免重复构建。"""
        if not self.parents_map:
            return {}
        group_parents: Dict["LayoutBlock", Set["LayoutBlock"]] = {}
        for block in group_blocks_set:
            parents = self.parents_map.get(block)
            if not parents:
                continue
            filtered = {parent for parent in parents if parent in group_blocks_set}
            if filtered:
                group_parents[block] = filtered
        return group_parents

    def build_group_parent_sets(
        self,
        group_blocks_set: Set["LayoutBlock"],
    ) -> Dict["LayoutBlock", Set["LayoutBlock"]]:
        """对外暴露的父集合构建器，便于调用方重用缓存结果。"""
        return self._build_parent_sets(group_blocks_set)

    def _compute_block_base_y(
        self,
        block: "LayoutBlock",
        cursor_y: float,
        parent_sets: Dict["LayoutBlock", Set["LayoutBlock"]],
        placed_base_y_by_block: Dict["LayoutBlock", float],
        ordered_children: Dict["LayoutBlock", List["LayoutBlock"]],
        pre_start_y_by_block: Dict["LayoutBlock", float],
        current_group_top_y: float,
    ) -> float:
        """计算块的基准Y坐标（含父块对齐和抬升逻辑）"""
        base_y = cursor_y
        parent_set = parent_sets.get(block, set())

        # 实时对齐到"所有已放置父块"的平均起始Y
        if parent_set:
            parent_bases: List[float] = []
            for parent in parent_set:
                if parent in placed_base_y_by_block:
                    parent_bases.append(placed_base_y_by_block[parent])
            if parent_bases:
                avg_parent_base = sum(parent_bases) / float(len(parent_bases))
                if avg_parent_base > base_y:
                    base_y = avg_parent_base

        # 父块足够高时的子块抬升
        if parent_set:
            lift_candidates: List[float] = []
            for parent in parent_set:
                if parent not in placed_base_y_by_block:
                    continue
                parent_children = ordered_children.get(parent, [])
                if not parent_children:
                    continue

                # 去重后的右子集合
                unique_parent_children: List["LayoutBlock"] = []
                seen_parent_children: Set["LayoutBlock"] = set()
                for child in parent_children:
                    if child not in seen_parent_children:
                        unique_parent_children.append(child)
                        seen_parent_children.add(child)

                if len(unique_parent_children) < 2:
                    continue

                sum_height = sum(float(child.height) for child in unique_parent_children)
                threshold_parent = 0.5 * sum_height

                # 以"预堆叠起始Y最小"的右子作为参考
                min_child_pre = None
                for child in unique_parent_children:
                    pre_y = pre_start_y_by_block.get(child, current_group_top_y)
                    if (min_child_pre is None) or (pre_y < min_child_pre):
                        min_child_pre = pre_y

                if min_child_pre is None:
                    continue

                parent_base = placed_base_y_by_block[parent]
                if (parent_base - float(min_child_pre)) >= threshold_parent and threshold_parent > 0.0:
                    lift_candidates.append(parent_base - threshold_parent)

            if lift_candidates:
                target_base = min(lift_candidates)
                if target_base < base_y:
                    # 不高于列游标，避免列内重叠
                    base_y = target_base if target_base >= cursor_y else cursor_y

        return base_y

    def _compute_effective_shift_y(
        self,
        block: "LayoutBlock",
        base_y: float,
        shift_plans: Dict["LayoutBlock", BlockShiftPlan],
        pre_start_y_by_block: Dict["LayoutBlock", float],
        current_group_top_y: float,
    ) -> float:
        """计算块的有效Y偏移量（含阈值保护）"""
        plan = shift_plans.get(block)
        if not plan or plan.shift <= 0.0:
            return 0.0

        reference_blocks = plan.reference_blocks
        if not reference_blocks:
            return plan.shift

        # 与参考集合中"预起始Y最小"者比较
        min_ref_pre_y = None
        for ref_block in reference_blocks:
            pre_y = pre_start_y_by_block.get(ref_block, current_group_top_y)
            if (min_ref_pre_y is None) or (pre_y < min_ref_pre_y):
                min_ref_pre_y = pre_y

        if min_ref_pre_y is not None:
            baseline_gap = base_y - float(min_ref_pre_y)
            if baseline_gap >= plan.shift:
                return 0.0

        return plan.shift

    def place_orphan_blocks(self) -> None:
        """放置孤立块（动态按本列最大宽更新列宽，减少横向空间浪费）"""
        orphan_blocks = [block for block in self.layout_blocks if block not in self.positioned_blocks]
        if not orphan_blocks:
            return

        if self.positioned_blocks:
            max_right = max(block.top_left_pos[0] + block.width for block in self.positioned_blocks)
        else:
            max_right = self.initial_x

        anchor_left = max_right + self.block_x_spacing
        current_y = self.initial_y
        current_column_max_width = 0.0  # 动态记录本列的最大宽度

        for orphan_block in orphan_blocks:
            orphan_block.top_left_pos = (anchor_left, current_y)
            self.positioned_blocks.add(orphan_block)
            self._register_block_in_buckets(orphan_block)

            # 更新本列最大宽度
            if orphan_block.width > current_column_max_width:
                current_column_max_width = orphan_block.width

            current_y += orphan_block.height + self.block_y_spacing

            # 换列条件：超过高度限制
            if current_y > self.initial_y + 2000:
                anchor_left += current_column_max_width + self.block_x_spacing
                current_y = self.initial_y
                current_column_max_width = 0.0  # 重置新列的最大宽度



