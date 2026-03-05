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
from typing import Dict, Set, List, Optional, TYPE_CHECKING

from ..internal.constants import NODE_HEIGHT_DEFAULT, PORT_EXIT_LOOP
from ..internal.layout_models import LayoutBlock
from .block_relationship_analyzer import BlockShiftPlan
from ..utils.graph_query_utils import is_flow_edge
from .solvers.types import PositioningEngineConfig, PositioningRuntimeState
from .solvers.column_assignment_solver import ColumnIndexSolveInput, solve_column_indices
from .solvers.column_x_solver import ColumnXSolveInput, solve_column_x_positions
from .solvers.column_stack_solver import ColumnStackSolveInput, solve_stack_blocks_in_columns
from .solvers.orphan_blocks_solver import OrphanPlacementInput, place_orphan_blocks

if TYPE_CHECKING:
    from engine.graph.models import GraphModel, NodeModel, EdgeModel
    from ..internal.layout_context import LayoutContext


class BlockPositioningEngine:
    """块间定位引擎"""

    @staticmethod
    def _stable_block_sort_key(block: "LayoutBlock") -> tuple[int, str, str]:
        """
        为布局阶段提供稳定排序 key，保证同一张图重复自动排版的结果完全可复现。

        说明：
        - `LayoutBlock` 在每次布局时都会新建对象；若直接遍历 `set[LayoutBlock]`，迭代顺序会随对象哈希变化，
          进而影响迭代收敛的浮点累计顺序，导致块坐标出现“轻微漂移”。
        - `order_index` 是分块阶段生成的稳定编号（从1开始），在同图内应当稳定且近似全局唯一；
          其余字段用于兜底，避免极端情况下排序键冲突。
        """
        order_index = int(getattr(block, "order_index", 0) or 0)
        event_root_id = str(getattr(block, "event_root_id", "") or "")
        flow_nodes = getattr(block, "flow_nodes", None) or []
        first_flow_node_id = str(flow_nodes[0]) if flow_nodes else ""
        return (order_index, event_root_id, first_flow_node_id)

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
        # 重要：`block_map` 在关系分析阶段通常只包含“流程节点 → LayoutBlock”。
        # 但 X 贴近/端口间距约束需要通过连线追溯到“源节点所属块”，其中源节点可能是纯数据节点。
        # 因此在定位引擎内补全为“任意节点 → LayoutBlock”，以便后续求解器能覆盖 data 边约束。
        self.block_map = dict(block_map or {})
        stable_blocks = sorted(self.layout_blocks, key=self._stable_block_sort_key)
        for layout_block in stable_blocks:
            # 优先使用已生成坐标的节点集合（node_local_pos），其语义最接近“该块真实包含的节点”。
            local_pos_map = getattr(layout_block, "node_local_pos", None) or {}
            for node_id in local_pos_map.keys():
                self.block_map.setdefault(str(node_id), layout_block)
            # 兜底：阶段1/极端情况下 node_local_pos 可能尚未填充，补充 flow/data 列表。
            for node_id in getattr(layout_block, "flow_nodes", None) or []:
                self.block_map.setdefault(str(node_id), layout_block)
            for node_id in getattr(layout_block, "data_nodes", None) or []:
                self.block_map.setdefault(str(node_id), layout_block)
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

    def _build_config(self) -> PositioningEngineConfig:
        return PositioningEngineConfig(
            initial_x=float(self.initial_x),
            initial_y=float(self.initial_y),
            block_x_spacing=float(self.block_x_spacing),
            block_y_spacing=float(self.block_y_spacing),
            enable_tight_block_spacing=bool(self.enable_tight_block_spacing),
            global_context=self.global_context,
            block_map=self.block_map,
            parents_map=self.parents_map,
            stable_sort_key=self._stable_block_sort_key,
        )

    def _build_runtime(self) -> PositioningRuntimeState:
        # 重要：返回的是运行期集合的“引用视图”，solver 会原地更新它们，从而保持旧实现的副作用语义不变。
        return PositioningRuntimeState(
            positioned_blocks=self.positioned_blocks,
            bucket_size=float(self._bucket_size),
            bucket_map=self._bucket_map,
        )

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

        # 当紧凑 X 贴近关闭时（块严格按列左对齐），若仅按 flow DAG 求列，会出现：
        # - 两块无 flow 关系但存在 data 依赖，且被分配到同列；
        # - 上方块很宽、下方块较窄时，data 边可能出现“右→左折返”。
        #
        # 因此在“列索引求解”阶段补充跨块 data 依赖边：保证任何跨块连线都满足 src_block 在 dst_block 左侧。
        effective_ordered_children = ordered_children
        effective_parent_sets = parent_sets or self._build_parent_sets(group_blocks_set)
        if not self.enable_tight_block_spacing:
            effective_ordered_children, effective_parent_sets = self._augment_block_dependencies_for_column_solve(
                group_blocks_set,
                ordered_children,
                base_parent_sets=effective_parent_sets,
            )

        return solve_column_indices(
            self._build_config(),
            ColumnIndexSolveInput(
                group_blocks_set=group_blocks_set,
                ordered_children=effective_ordered_children,
                parent_sets=effective_parent_sets,
            ),
        )

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
        return solve_column_x_positions(
            self._build_config(),
            ColumnXSolveInput(block_to_column_index=block_to_column_index),
        )

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
        parent_sets = parent_sets or self._build_parent_sets(group_blocks_set)
        return solve_stack_blocks_in_columns(
            self._build_config(),
            self._build_runtime(),
            ColumnStackSolveInput(
                block_to_column_index=block_to_column_index,
                column_left_x=column_left_x,
                current_group_top_y=float(current_group_top_y),
                group_blocks_set=group_blocks_set,
                ordered_children=ordered_children,
                shift_plans=shift_plans,
                parent_sets=parent_sets,
            ),
        )

    def _build_parent_sets(
        self,
        group_blocks_set: Set["LayoutBlock"],
    ) -> Dict["LayoutBlock", Set["LayoutBlock"]]:
        """返回限制在事件组内的父集合，避免重复构建。"""
        if not self.parents_map:
            return {}
        group_parents: Dict["LayoutBlock", Set["LayoutBlock"]] = {}
        stable_group_blocks = sorted(group_blocks_set, key=self._stable_block_sort_key)
        for block in stable_group_blocks:
            parents = self.parents_map.get(block)
            if not parents:
                continue
            filtered = {parent for parent in parents if parent in group_blocks_set}
            if filtered:
                group_parents[block] = filtered
        return group_parents

    def _augment_block_dependencies_for_column_solve(
        self,
        group_blocks_set: Set["LayoutBlock"],
        ordered_children: Dict["LayoutBlock", List["LayoutBlock"]],
        *,
        base_parent_sets: Dict["LayoutBlock", Set["LayoutBlock"]],
    ) -> tuple[Dict["LayoutBlock", List["LayoutBlock"]], Dict["LayoutBlock", Set["LayoutBlock"]]]:
        """
        为“列索引求解”补充跨块依赖边（主要用于 data 边），以避免在列对齐模式下出现右→左折返。

        关键点：
        - 不修改输入的 ordered_children/base_parent_sets（保持调用方可复用旧引用）；
        - 只在当前事件组 group_blocks_set 内生效，避免把不同事件流强行串成一个大组；
        - 跳过“跳出循环”类流程回边（否则会强行引入环导致列索引漂移）。
        """
        if not group_blocks_set:
            return ordered_children, base_parent_sets

        stable_group_blocks = sorted(group_blocks_set, key=self._stable_block_sort_key)
        group_lookup = set(group_blocks_set)

        # 复制一份 children 映射（只拷贝 group 内块，避免无关 key 扩散）
        augmented_children: Dict["LayoutBlock", List["LayoutBlock"]] = {}
        for block in stable_group_blocks:
            augmented_children[block] = list(ordered_children.get(block, []) or [])

        # 复制一份 parents 映射（保留 flow parents，再补充 data parents）
        augmented_parents: Dict["LayoutBlock", Set["LayoutBlock"]] = {
            block: set(base_parent_sets.get(block, set()) or set()) for block in stable_group_blocks
        }

        # 统计额外依赖：src_block -> {dst_block}
        extra_children: Dict["LayoutBlock", Set["LayoutBlock"]] = {block: set() for block in stable_group_blocks}

        for edge in (self.model.edges or {}).values():
            src_node_id = getattr(edge, "src_node", None)
            dst_node_id = getattr(edge, "dst_node", None)
            if not isinstance(src_node_id, str) or not isinstance(dst_node_id, str):
                continue

            src_block = self.block_map.get(src_node_id)
            dst_block = self.block_map.get(dst_node_id)
            if (src_block is None) or (dst_block is None) or (src_block is dst_block):
                continue
            if (src_block not in group_lookup) or (dst_block not in group_lookup):
                continue

            # 跳过“跳出循环”输入口所形成的回边（仅针对流程边）
            if is_flow_edge(self.model, edge):
                dst_node_obj = self.model.nodes.get(dst_node_id)
                if dst_node_obj is not None:
                    dst_port_obj = dst_node_obj.get_input_port(getattr(edge, "dst_port", None))
                    if dst_port_obj is not None and str(getattr(dst_port_obj, "name", "")) == str(PORT_EXIT_LOOP):
                        continue

            extra_children.setdefault(src_block, set()).add(dst_block)

        # 将 extra children 合并回 children 列表（保持确定性：按 stable_sort_key 追加）
        for src_block in stable_group_blocks:
            extras = extra_children.get(src_block)
            if not extras:
                continue

            existing_list = augmented_children.get(src_block, [])
            existing_set = set(existing_list)
            ordered_extras = sorted(extras, key=self._stable_block_sort_key)
            for child_block in ordered_extras:
                if (child_block is src_block) or (child_block in existing_set):
                    continue
                existing_list.append(child_block)
                existing_set.add(child_block)
                augmented_parents.setdefault(child_block, set()).add(src_block)

            augmented_children[src_block] = existing_list

        return augmented_children, augmented_parents

    def build_group_parent_sets(
        self,
        group_blocks_set: Set["LayoutBlock"],
    ) -> Dict["LayoutBlock", Set["LayoutBlock"]]:
        """对外暴露的父集合构建器，便于调用方重用缓存结果。"""
        return self._build_parent_sets(group_blocks_set)

    def place_orphan_blocks(self) -> None:
        """放置孤立块（动态按本列最大宽更新列宽，减少横向空间浪费）"""
        place_orphan_blocks(
            self._build_config(),
            self._build_runtime(),
            OrphanPlacementInput(layout_blocks=self.layout_blocks),
        )



