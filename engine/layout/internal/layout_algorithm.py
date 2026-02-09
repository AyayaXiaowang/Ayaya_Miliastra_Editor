"""
核心布局算法模块

实现基于基本块的多阶段布局算法。
职责：高层编排和公共API，具体实现拆分到子模块。

新流程：
1. 发现事件节点
2. 识别所有块的流程节点（不放置数据节点）
3. 全局复制阶段：分析跨块共享，统一创建副本和重定向边
4. 数据节点放置阶段：为每个块放置数据节点并计算坐标
5. 块间排版
6. 应用最终位置
"""

from __future__ import annotations
from typing import Dict, Set, List, Tuple, Optional
from collections import deque

from engine.graph.models import GraphModel, NodeModel
from engine.configs.settings import settings

from .constants import (
    NODE_WIDTH_DEFAULT,
    NODE_HEIGHT_DEFAULT,
    BLOCK_PADDING_DEFAULT,
    BLOCK_X_SPACING_DEFAULT,
    BLOCK_Y_SPACING_DEFAULT,
    INITIAL_X_DEFAULT,
    INITIAL_Y_DEFAULT,
    EVENT_Y_GAP_DEFAULT,
    BLOCK_COLORS_DEFAULT,
    DATA_STACK_GAP_DEFAULT,
    compute_slot_width_from_node_width,
    scale_layout_gap_x,
    scale_layout_gap_y,
)
from ..utils.graph_query_utils import (
    get_node_order_key,
    build_event_title_lookup,
    resolve_event_title,
    estimate_node_height_ui_exact_with_context,
)
from ..flow.event_flow_analyzer import find_event_roots
from .layout_context import LayoutContext, get_or_build_layout_context_for_model
from .layout_registry_context import ensure_layout_registry_context_for_model
from ..blocks.block_relationship_analyzer import (
    BlockRelationshipAnalyzer,
    build_block_relationship_snapshot,
)
from ..blocks.block_positioning_engine import BlockPositioningEngine
from ..utils.position_applicator import PositionApplicator
from ..blocks.block_identification_coordinator import BlockIdentificationCoordinator
from ..utils.data_graph_utils import compute_data_components_layers_for_nodes
from ..utils.local_variable_relay_inserter import insert_local_variable_relays_after_global_copy
from .layout_models import LayoutBlock


class LayoutOrchestrator:
    """布局编排器 - 高层协调者，委托具体任务给专门的模块
    
    新流程：
    1. 发现事件节点
    2. 识别所有块的流程节点（阶段1：只识别，不放置数据节点）
    3. 全局复制阶段：分析跨块共享，统一创建副本和重定向边
    4. 数据节点放置阶段：为每个块放置数据节点并计算坐标（阶段2）
    5. 块间排版
    6. 应用最终位置
    """

    def __init__(self, model: GraphModel) -> None:
        self.model = model
        self.layout_blocks: List[LayoutBlock] = []
        self.event_nodes: List[NodeModel] = []

        # 布局参数
        self.node_width = NODE_WIDTH_DEFAULT
        self.node_height = NODE_HEIGHT_DEFAULT
        self.block_padding = BLOCK_PADDING_DEFAULT
        # 注意：间距倍率只缩放“相邻节点之间的空隙”，不改变节点本身的宽高估算
        self.block_x_spacing = scale_layout_gap_x(BLOCK_X_SPACING_DEFAULT)
        self.block_y_spacing = scale_layout_gap_y(BLOCK_Y_SPACING_DEFAULT)
        self.initial_x = INITIAL_X_DEFAULT
        self.initial_y = INITIAL_Y_DEFAULT
        self.event_y_gap = scale_layout_gap_y(EVENT_Y_GAP_DEFAULT)
        self.block_colors = BLOCK_COLORS_DEFAULT

        # 全局只读布局上下文（索引缓存），避免每个块重复构建边索引
        # 同时显式注入 LayoutRegistryContext，彻底移除 graph_query_utils 的隐式 workspace_root 回退。
        registry_context = ensure_layout_registry_context_for_model(self.model)
        self.global_layout_context = get_or_build_layout_context_for_model(
            self.model,
            registry_context=registry_context,
        )
        self._cached_block_relationships: Optional[Dict[str, object]] = None
        self._event_metadata_lookup: Dict[str, Tuple[Optional[str], Optional[str]]] = {}
        self._event_title_lookup: Optional[Dict[str, Optional[str]]] = None
        
        # 全局复制管理器（在全局复制阶段创建）
        self._global_copy_manager: Optional["GlobalCopyManager"] = None
        # 块识别协调器（用于两阶段调用）
        self._coordinator: Optional[BlockIdentificationCoordinator] = None
        self._global_visited: Set[str] = set()

        # 长连线中转（获取局部变量）节点：强制放置映射（用于在阶段2覆盖 GlobalCopyManager 的归属结果）
        self._forced_local_var_relay_nodes_by_block_id: Dict[str, Set[str]] = {}
        self._forced_local_var_relay_node_ids: Set[str] = set()

    def execute_layout(self) -> None:
        """执行完整的布局流程（新流程）"""
        # 步骤1：发现事件节点
        if not self._discover_event_nodes():
            # 纯数据图，使用专门布局
            self._layout_pure_data_graph()
            return

        # 步骤2：识别所有块的流程节点（不放置数据节点）
        self._identify_all_blocks_flow_only()

        # 步骤3：全局复制阶段
        self._execute_global_copy()

        # 步骤3.5：长连线中转（跨块复制后、块内排版前）
        self._insert_local_var_relays_before_data_placement()

        # 步骤4：为每个块放置数据节点并计算坐标
        self._place_all_blocks_data_nodes()

        # 步骤4.5：识别“完全不与流程/事件块相连”的纯数据组件，并单独成块布局
        self._layout_orphan_pure_data_components_as_blocks()

        # 步骤5：块间排版
        self._layout_block_tree_stage()

        # 步骤6：应用最终位置到节点
        self._apply_final_positions()

    def _discover_event_nodes(self) -> bool:
        """发现事件节点，返回是否存在事件节点"""
        self.event_nodes = find_event_roots(
            self.model,
            include_virtual_pin_roots=True,
            layout_context=self.global_layout_context,
        )
        self._event_metadata_lookup = self._build_event_metadata_lookup()
        return bool(self.event_nodes)

    def _layout_pure_data_graph(self) -> None:
        """纯数据图布局"""
        from .data_graph_layout import layout_pure_data_graph

        layout_pure_data_graph(
            self.model,
            self.node_width,
            self.node_height,
            self.initial_x,
            self.initial_y,
            self.block_padding,
            self.block_x_spacing,
            self.block_colors,
            layout_context=self.global_layout_context,
        )

    def _identify_all_blocks_flow_only(self) -> None:
        """识别所有基本块的流程节点（阶段1：不放置数据节点）"""
        self._global_visited = set()

        self._coordinator = BlockIdentificationCoordinator(
            self.model,
            self.global_layout_context,
            self.layout_blocks,
            self.block_colors,
            self.node_width,
            self.node_height,
            self.block_padding,
            precomputed_event_metadata=self._event_metadata_lookup,
            event_title_lookup=self._event_title_lookup,
        )

        # 从事件节点开始识别（阶段1：只识别流程节点）
        for event_node in self.event_nodes:
            resolved_metadata = self._event_metadata_lookup.get(event_node.id)
            self._coordinator.identify_blocks_flow_only(
                event_node.id,
                self._global_visited,
                event_root_id=event_node.id,
                event_title=resolved_metadata[1] if resolved_metadata else getattr(event_node, "title", None),
            )

        # 处理孤立流程节点
        remaining_flow_ids = set(self.global_layout_context.flowCapableNodeIds) - self._global_visited
        if remaining_flow_ids:
            orphan_flow_nodes: List[NodeModel] = []
            for node_id in remaining_flow_ids:
                node = self.model.nodes.get(node_id)
                if node:
                    orphan_flow_nodes.append(node)

            orphan_flow_nodes.sort(key=get_node_order_key)

            for orphan_node in orphan_flow_nodes:
                if orphan_node.id not in self._global_visited:
                    self._coordinator.identify_blocks_flow_only(orphan_node.id, self._global_visited)

    def _execute_global_copy(self) -> None:
        """全局复制阶段：分析跨块共享，统一创建副本和重定向边"""
        from ..utils.global_copy_manager import GlobalCopyManager
        
        # 无论是否启用复制，都需要分析数据依赖以确定每个块的数据节点归属
        self._global_copy_manager = GlobalCopyManager(
            self.model,
            self.layout_blocks,
            self.global_layout_context,
        )

        # 分析所有块的数据依赖
        self._global_copy_manager.analyze_dependencies()

        # 只有启用复制时才执行复制计划
        enable_copy = getattr(settings, "DATA_NODE_CROSS_BLOCK_COPY", True)
        if enable_copy:
            self._global_copy_manager.execute_copy_plan()
            # 复制阶段会修改 model.nodes / model.edges，需要刷新 LayoutContext 的索引缓存；
            # 同时阶段1缓存的 BlockLayoutContext 也需要切换到新的全局索引视图，避免后续阶段读取过期边索引。
            self._refresh_global_layout_context_after_model_mutation()

    def _insert_local_var_relays_before_data_placement(self) -> None:
        """跨块复制完成后、块内排版前：按设置自动插入【获取局部变量】中转节点以拆分长数据边。"""
        self._forced_local_var_relay_nodes_by_block_id = {}
        self._forced_local_var_relay_node_ids = set()

        if self._global_copy_manager is None:
            return

        if not bool(getattr(settings, "LAYOUT_AUTO_INSERT_LOCAL_VAR_RELAY", False)):
            return

        threshold = int(getattr(settings, "LAYOUT_LOCAL_VAR_RELAY_MAX_BLOCK_DISTANCE", 5) or 5)

        registry_context = getattr(self.global_layout_context, "registry_context", None)
        node_registry = getattr(registry_context, "node_registry", None) if registry_context is not None else None
        if node_registry is None:
            return

        forced_by_block, all_relay_nodes, did_mutate = insert_local_variable_relays_after_global_copy(
            model=self.model,
            layout_blocks=self.layout_blocks,
            global_copy_manager=self._global_copy_manager,
            max_block_distance=threshold,
            node_registry=node_registry,
        )
        self._forced_local_var_relay_nodes_by_block_id = forced_by_block
        self._forced_local_var_relay_node_ids = all_relay_nodes

        if did_mutate:
            # 插入/改线会修改 model.nodes/model.edges，必须刷新 LayoutContext 与阶段1缓存的块上下文索引
            self._refresh_global_layout_context_after_model_mutation()

    def _refresh_global_layout_context_after_model_mutation(self) -> None:
        registry_context = getattr(self.global_layout_context, "registry_context", None)
        if registry_context is None:
            registry_context = ensure_layout_registry_context_for_model(self.model)
        refreshed = get_or_build_layout_context_for_model(
            self.model,
            registry_context=registry_context,
        )
        self.global_layout_context = refreshed
        if self._coordinator is not None:
            self._coordinator.refresh_global_layout_context(refreshed)

    def _place_all_blocks_data_nodes(self) -> None:
        """为每个块放置数据节点并计算坐标（阶段2）"""
        if self._coordinator is None:
            return

        # 为每个块执行数据节点放置和坐标计算
        for block in self.layout_blocks:
            block_id = f"block_{block.order_index}"
            
            # 获取该块应放置的数据节点
            block_data_nodes: Set[str] = set()
            if self._global_copy_manager:
                block_data_nodes = set(self._global_copy_manager.get_block_data_nodes(block_id) or set())

            # 强制放置：relay 节点以“编码的 block_id”为准，避免被依赖分析归属到消费者块导致长线回退
            if self._forced_local_var_relay_node_ids:
                block_data_nodes -= self._forced_local_var_relay_node_ids
                block_data_nodes |= set(self._forced_local_var_relay_nodes_by_block_id.get(block_id, set()) or set())
            
            # 执行阶段2：放置数据节点并计算坐标
            self._coordinator.layout_block_data_phase(block, block_data_nodes)

    def _layout_orphan_pure_data_components_as_blocks(self) -> None:
        """将未被任何流程块放置的纯数据节点组件作为独立块布局。

        典型场景：
        - 复合节点子图中存在“仅参与虚拟输出拼装”的纯数据链；
        - 这些节点不作为任何流程节点的输入，因此不会被依赖分析挂载到某个流程块；
        - 但用户仍希望它们在 UI 中作为独立块可见（而不是被强行塞进某个流程块或完全不显示）。
        """
        if not self.model.nodes:
            return

        placed_node_ids: Set[str] = set()
        for layout_block in self.layout_blocks:
            local_pos = getattr(layout_block, "node_local_pos", None) or {}
            placed_node_ids.update(local_pos.keys())

        # 仅处理“纯数据节点”且尚未被任何块放置的节点集合
        unplaced_pure_data_ids: Set[str] = set()
        for node_id in self.model.nodes.keys():
            if node_id in placed_node_ids:
                continue
            if self.global_layout_context.is_pure_data_node(node_id):
                unplaced_pure_data_ids.add(node_id)

        if not unplaced_pure_data_ids:
            return

        components = compute_data_components_layers_for_nodes(self.model, unplaced_pure_data_ids)
        if not components:
            return

        # 追加块：保持稳定序号与颜色分配
        max_order_index = 0
        for layout_block in self.layout_blocks:
            max_order_index = max(max_order_index, int(getattr(layout_block, "order_index", 0) or 0))
        next_order_index = max_order_index + 1

        color_index = len(self.layout_blocks)
        block_padding_local = float(self.block_padding)
        slot_width = compute_slot_width_from_node_width(float(self.node_width))
        data_stack_gap = float(scale_layout_gap_y(DATA_STACK_GAP_DEFAULT))

        for component in components:
            if not component.nodes:
                continue

            layers: List[List[str]] = component.layers or [list(component.nodes)]
            node_local_pos: Dict[str, Tuple[float, float]] = {}
            max_y_end = 0.0

            for layer_index, layer_nodes in enumerate(layers):
                x_coord = block_padding_local + float(layer_index) * float(slot_width)
                current_y = block_padding_local
                for data_node_id in layer_nodes:
                    node_local_pos[data_node_id] = (x_coord, current_y)
                    node_height_est = float(
                        estimate_node_height_ui_exact_with_context(self.global_layout_context, data_node_id)
                    )
                    current_y += node_height_est + data_stack_gap
                max_y_end = max(max_y_end, current_y)

            # 简单块边界：slot_width 已包含节点宽度与横向间距，下方预留 block_padding
            block_width = float(len(layers)) * float(slot_width) + 2.0 * block_padding_local
            block_height = float(max_y_end) + block_padding_local

            data_only_block = LayoutBlock()
            data_only_block.flow_nodes = []
            data_only_block.data_nodes = list(component.nodes)
            data_only_block.node_local_pos = node_local_pos
            data_only_block.width = block_width
            data_only_block.height = block_height
            data_only_block.node_width = float(self.node_width)
            data_only_block.last_node_branches = []
            data_only_block.event_root_id = None
            data_only_block.order_index = int(next_order_index)
            data_only_block.color = self.block_colors[color_index % len(self.block_colors)]

            next_order_index += 1
            color_index += 1
            self.layout_blocks.append(data_only_block)

    def _build_event_metadata_lookup(self) -> Dict[str, Tuple[Optional[str], Optional[str]]]:
        """预计算事件ID与标题映射，供块识别阶段复用。"""
        if not self.event_nodes:
            self.global_layout_context.set_event_metadata({})
            return {}
        title_lookup = build_event_title_lookup(self.model)
        self._event_title_lookup = title_lookup
        metadata: Dict[str, Tuple[Optional[str], Optional[str]]] = {}
        for node in self.event_nodes:
            resolved_title = resolve_event_title(
                self.model,
                node.id,
                title_lookup=title_lookup,
            )
            metadata[node.id] = (node.id, resolved_title)
        self._propagate_event_metadata(metadata)
        self.global_layout_context.set_event_metadata(metadata)
        return metadata

    def _propagate_event_metadata(self, metadata: Dict[str, Tuple[Optional[str], Optional[str]]]) -> None:
        """将事件ID/标题映射扩散到同一事件流内的所有流程节点。"""
        if not metadata:
            return

        visited: Set[str] = set()
        queue: deque[str] = deque(metadata.keys())
        while queue:
            current_id = queue.popleft()
            if current_id in visited:
                continue
            visited.add(current_id)
            event_id, title = metadata.get(current_id, (None, None))
            for edge in self.global_layout_context.get_out_flow_edges(current_id):
                dst_id = getattr(edge, "dst_node", None)
                if not dst_id or dst_id in visited or dst_id in metadata:
                    continue
                metadata[dst_id] = (event_id, title)
                queue.append(dst_id)

    def _layout_block_tree_stage(self) -> None:
        """
        基于事件链的新块间排版阶段（委托给专门模块）
        
        核心思想：
        - 每个事件组内，将基本块视作节点，从起始块出发按端口自上而下顺序收集整组块
        - 依据块间有向边执行最长路径动态规划，获得"最靠左且满足拓扑约束"的列索引
        - 在每一列内，按块的稳定编号（order_index）从小到大自上而下堆叠
        - 事件组之间按组整体垂直堆叠，组间距为 event_y_gap
        """
        # 阶段1：构建块间关系（委托给BlockRelationshipAnalyzer）
        analyzer = BlockRelationshipAnalyzer(self.model, self.layout_blocks)
        ordered_children = analyzer.analyze_relationships()

        # 阶段2：预计算Y轴偏移量（委托给BlockRelationshipAnalyzer）
        shift_plans = analyzer.compute_y_shifts(ordered_children)

        # 阶段3：为每个事件组布局块（委托给BlockPositioningEngine）
        event_start_lookup = self._build_event_start_block_lookup()
        engine = BlockPositioningEngine(
            self.model,
            self.layout_blocks,
            analyzer.block_map,  # 复用analyzer构建的block_map
            self.initial_x,
            self.initial_y,
            self.block_x_spacing,
            self.block_y_spacing,
            self.global_layout_context,
            analyzer.parent_map,
            event_start_block_lookup=event_start_lookup,
            enable_tight_block_spacing=bool(
                getattr(settings, "LAYOUT_TIGHT_BLOCK_PACKING", True)
            ),
        )

        current_group_top_y = float(self.initial_y)

        for event_node in self.event_nodes:
            # 定位事件起始块
            start_block = engine.find_start_block(event_node)
            if start_block is None:
                continue

            # 已排过的块无需重复处理
            if start_block in engine.positioned_blocks:
                continue

            # 收集事件组的所有块
            group_blocks_set = engine.collect_group_blocks(start_block, ordered_children)
            if not group_blocks_set:
                continue

            parent_sets = engine.build_group_parent_sets(group_blocks_set)

            # 计算块的列位置（基于最长路径约束）
            block_to_column_index = engine.compute_column_indices(
                group_blocks_set,
                ordered_children,
                parent_sets=parent_sets,
            )

            # 计算每列的像素X坐标
            column_left_x = engine.compute_column_x_positions(block_to_column_index)

            # 在列内堆叠块并分配Y坐标
            group_bottom_y = engine.stack_blocks_in_columns(
                block_to_column_index,
                column_left_x,
                current_group_top_y,
                group_blocks_set,
                ordered_children,
                shift_plans,
                parent_sets=parent_sets,
            )

            # 下一事件组整体向下堆叠
            current_group_top_y = float(group_bottom_y) + float(self.event_y_gap)

        # 放置孤立块（不属于任何事件组且未被放置的块）
        engine.place_orphan_blocks()
        self._cache_block_relationships_snapshot(analyzer, ordered_children)

    def _apply_final_positions(self) -> None:
        """应用最终位置到所有节点（委托给PositionApplicator）"""
        applicator = PositionApplicator(self.model, self.layout_blocks)
        applicator.apply_positions()

    def _cache_block_relationships_snapshot(
        self,
        analyzer: BlockRelationshipAnalyzer,
        ordered_children: Dict["LayoutBlock", List["LayoutBlock"]],
    ) -> None:
        snapshot = build_block_relationship_snapshot(self.layout_blocks, ordered_children, analyzer.block_map)
        self._cached_block_relationships = snapshot
        setattr(self.model, "_layout_block_relationships", snapshot)
        setattr(self.model, "_layout_blocks_cache", list(self.layout_blocks))
        setattr(self.model, "_layout_context_cache", self.global_layout_context)
        setattr(self.model, "_layout_cache_signature", LayoutContext.compute_signature_for_model(self.model))

    def _build_event_start_block_lookup(self) -> Dict[str, LayoutBlock]:
        """预先记录事件ID对应的起始块，避免重复遍历事件子图。"""
        lookup: Dict[str, LayoutBlock] = {}
        for block in sorted(self.layout_blocks, key=lambda blk: blk.order_index):
            if block.event_root_id and block.event_root_id not in lookup:
                lookup[block.event_root_id] = block
        return lookup


def layout_by_event_regions(model: GraphModel) -> None:
    """
    基于基本块的多阶段布局（使用Orchestrator编排器）
    
    新流程：
    1. 发现事件节点
    2. 识别所有块的流程节点（不放置数据节点）
    3. 全局复制阶段：分析跨块共享，统一创建副本和重定向边
    4. 数据节点放置阶段：为每个块放置数据节点并计算坐标
    5. 块间排版
    6. 应用最终位置
    
    Args:
        model: 图模型，会被就地修改（节点位置和基本块）
    """
    if not model.nodes:
        return
    # 确保 registry_context 已注入（来自显式 workspace_path 或 settings 单一真源）
    ensure_layout_registry_context_for_model(model)

    orchestrator = LayoutOrchestrator(model)
    orchestrator.execute_layout()


