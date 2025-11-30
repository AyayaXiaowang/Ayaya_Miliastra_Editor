"""
块识别协调器

负责协调基本块的识别过程，包括：
- 递归识别流程节点序列
- 调用块内布局
- 分配块颜色和序号
- 处理分支递归
"""

from __future__ import annotations
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from engine.graph.models import GraphModel
from engine.configs.settings import settings
from ..core.layout_context import LayoutContext
from ..core.layout_models import LayoutBlock
from ..utils.edge_index_proxies import CopyOnWriteEdgeIndex
from ..utils.graph_query_utils import (
    count_outgoing_data_edges,
    build_event_title_lookup,
    resolve_event_title,
    get_ordered_flow_out_edges,
)
from ..core.constants import (
    DATA_BASE_EXTRA_MARGIN,
    DATA_STACK_GAP_DEFAULT,
    FLOW_TO_DATA_GAP_DEFAULT,
    INPUT_PORT_TO_DATA_GAP_DEFAULT,
    SLOT_WIDTH_MULTIPLIER,
    UI_NODE_HEADER_HEIGHT,
    UI_ROW_HEIGHT,
)

from .block_identifier import identify_block_flow_nodes
from .block_layout_context import BlockLayoutContext
from .data_chain_enumerator import DataChainEnumerator
from .data_node_placer import DataNodePlacer
from ..utils.coordinate_assigner import CoordinateAssigner
from .block_bounds_calculator import BlockBoundsCalculator
SharedEdgeIndexMap = Dict[str, CopyOnWriteEdgeIndex]

@dataclass(frozen=True)
class _BlockLayoutScalars:
    slot_width: float
    flow_y: float
    data_base_y: float
    data_y_spacing: float


def _make_block_layout_scalars(node_width: float, node_height: float) -> _BlockLayoutScalars:
    slot_width = node_width * float(SLOT_WIDTH_MULTIPLIER)
    flow_y = 0.0
    data_base_y = node_height + DATA_BASE_EXTRA_MARGIN
    data_y_spacing = node_height + DATA_STACK_GAP_DEFAULT
    return _BlockLayoutScalars(
        slot_width=slot_width,
        flow_y=flow_y,
        data_base_y=data_base_y,
        data_y_spacing=data_y_spacing,
    )


class BlockLayoutExecutor:
    """负责准备块上下文并串联块内布局管线。"""

    def __init__(
        self,
        model: GraphModel,
        global_layout_ctx: LayoutContext,
        node_width: float,
        node_height: float,
        block_padding: float,
        shared_edge_indices_provider: Optional[Callable[[], SharedEdgeIndexMap]] = None,
    ) -> None:
        self.model = model
        self.global_layout_ctx = global_layout_ctx
        self.node_width = node_width
        self.node_height = node_height
        self.block_padding = block_padding
        self._shared_edge_indices_provider = shared_edge_indices_provider
        self._scalars_cache: Optional[_BlockLayoutScalars] = None
        self._enable_copy = bool(getattr(settings, "DATA_NODE_CROSS_BLOCK_COPY", False))

    def _get_cached_scalars(self) -> _BlockLayoutScalars:
        if self._scalars_cache is None:
            self._scalars_cache = _make_block_layout_scalars(self.node_width, self.node_height)
        return self._scalars_cache

    def layout_block(
        self,
        flow_node_ids: List[str],
        global_visited: Set[str],
        block_order_index: int,
        event_metadata: Optional[Tuple[Optional[str], Optional[str]]] = None,
    ) -> Tuple["LayoutBlock", List[str]]:
        scalars = self._get_cached_scalars()
        context = self._prepare_block_context(
            flow_node_ids,
            global_visited,
            block_order_index,
            event_metadata=event_metadata,
            scalars=scalars,
        )
        return self._run_block_layout_pipeline(context, flow_node_ids, block_order_index, scalars)

    def _prepare_block_context(
        self,
        flow_node_ids: List[str],
        global_visited: Set[str],
        block_order_index: int,
        event_metadata: Optional[Tuple[Optional[str], Optional[str]]] = None,
        scalars: Optional[_BlockLayoutScalars] = None,
    ) -> "BlockLayoutContext":
        scalars = scalars or self._get_cached_scalars()
        shared_edge_indices = self._shared_edge_indices_provider() if self._shared_edge_indices_provider else None
        event_root_id: Optional[str] = None
        event_title: Optional[str] = None
        if event_metadata:
            event_root_id, event_title = event_metadata
        ctx_global = None if shared_edge_indices else self.global_layout_ctx

        return BlockLayoutContext(
            model=self.model,
            flow_node_ids=flow_node_ids,
            node_width=self.node_width,
            node_height=self.node_height,
            data_base_y=scalars.data_base_y,
            flow_to_data_gap=FLOW_TO_DATA_GAP_DEFAULT,
            data_stack_gap=DATA_STACK_GAP_DEFAULT,
            ui_node_header_height=UI_NODE_HEADER_HEIGHT,
            ui_row_height=UI_ROW_HEIGHT,
            input_port_to_data_gap=INPUT_PORT_TO_DATA_GAP_DEFAULT,
            skip_data_node_ids=global_visited,
            global_layout_context=ctx_global,
            block_order_index=block_order_index,
            event_flow_title=event_title,
            event_flow_id=event_root_id,
            shared_edge_indices=shared_edge_indices,
        )

    def _run_block_layout_pipeline(
        self,
        context: "BlockLayoutContext",
        flow_node_ids: List[str],
        block_order_index: int,
        scalars: _BlockLayoutScalars,
    ) -> Tuple["LayoutBlock", List[str]]:
        slot_width = scalars.slot_width
        flow_y = scalars.flow_y
        data_y_spacing = scalars.data_y_spacing

        chain_enum = DataChainEnumerator(context)
        chain_enum.enumerate_all_chains()

        data_placer = DataNodePlacer(
            context,
            count_outgoing_data_edges,
            block_id=f"block_{block_order_index}",
            enable_copy=self._enable_copy,
        )
        data_placer.place_all_data_nodes(placement_instructions=chain_enum.placement_instructions)
        data_placer.finalize_redirects_for_copies()
        data_placer.propagate_chain_indices_to_copies()
        data_placer.apply_chain_based_stack_order()

        coordinate_assigner = CoordinateAssigner(
            context,
            slot_width,
            flow_y,
            data_y_spacing,
        )
        coordinate_assigner.assign_all_coordinates()

        bounds_calculator = BlockBoundsCalculator(context, self.block_padding)
        width, height = bounds_calculator.compute_and_normalize()

        shared_nodes = context.shared_data_nodes
        filtered_data_nodes = (
            [node_id for node_id in context.data_nodes_in_order if node_id not in shared_nodes]
            if shared_nodes
            else list(context.data_nodes_in_order)
        )

        filtered_local_pos = (
            {
                node_id: position
                for node_id, position in context.node_local_pos.items()
                if node_id not in shared_nodes
            }
            if shared_nodes
            else dict(context.node_local_pos)
        )

        layout_block = LayoutBlock()
        layout_block.flow_nodes = list(flow_node_ids)
        layout_block.data_nodes = filtered_data_nodes
        layout_block.node_local_pos = filtered_local_pos
        layout_block.width = width
        layout_block.height = height
        layout_block.node_width = context.node_width
        layout_block.event_root_id = context.event_flow_id

        if flow_node_ids:
            seen_targets: Set[str] = set()
            deduplicated_branches: List[Tuple[str, str]] = []
            for flow_node_id in flow_node_ids:
                ordered_edges = get_ordered_flow_out_edges(self.global_layout_ctx, flow_node_id)
                if not ordered_edges:
                    continue
                for port_name, target_id in ordered_edges:
                    if target_id in flow_node_ids:
                        continue
                    if target_id in seen_targets:
                        continue
                    seen_targets.add(target_id)
                    deduplicated_branches.append((port_name, target_id))
            if deduplicated_branches:
                layout_block.last_node_branches = deduplicated_branches

        current_map = getattr(self.model, "_layout_y_debug_info", None)
        if current_map is None:
            current_map = {}
            setattr(self.model, "_layout_y_debug_info", current_map)
        for node_id, info in context.debug_y_info.items():
            current_map[node_id] = info

        data_nodes_for_visit: List[str] = []
        seen_data_nodes: Set[str] = set()
        for node_id in context.data_nodes_in_order:
            if node_id in shared_nodes:
                continue
            if node_id in seen_data_nodes:
                continue
            seen_data_nodes.add(node_id)
            data_nodes_for_visit.append(node_id)
        for node_id in context.placed_data_nodes:
            if node_id in shared_nodes:
                continue
            if node_id in seen_data_nodes:
                continue
            seen_data_nodes.add(node_id)
            data_nodes_for_visit.append(node_id)

        return layout_block, data_nodes_for_visit

class BlockIdentificationCoordinator:
    """块识别协调器"""

    def __init__(
        self,
        model: GraphModel,
        global_layout_ctx: LayoutContext,
        layout_blocks: List["LayoutBlock"],
        colors: List[str],
        node_width: float,
        node_height: float,
        block_padding: float,
        precomputed_event_metadata: Optional[Dict[str, Tuple[Optional[str], Optional[str]]]] = None,
        event_title_lookup: Optional[Dict[str, Optional[str]]] = None,
    ):
        self.model = model
        self.global_layout_ctx = global_layout_ctx
        self.layout_blocks = layout_blocks
        self.colors = colors
        self.node_width = node_width
        self.node_height = node_height
        self.block_padding = block_padding

        self._color_index = 0
        self._block_sequence = 1
        self._event_metadata_cache: Dict[str, Tuple[Optional[str], Optional[str]]] = {}
        self._precomputed_event_metadata: Dict[str, Tuple[Optional[str], Optional[str]]] = dict(
            precomputed_event_metadata or {}
        )
        self._has_precomputed_event_metadata = bool(self._precomputed_event_metadata)
        if self._precomputed_event_metadata:
            self._event_metadata_cache.update(self._precomputed_event_metadata)
        self._shared_edge_indices: Optional[SharedEdgeIndexMap] = None
        if event_title_lookup is not None:
            self._event_title_lookup = dict(event_title_lookup)
        else:
            self._event_title_lookup = build_event_title_lookup(self.model)

        shared_indices_provider = self._ensure_shared_edge_indices if getattr(
            settings, "DATA_NODE_CROSS_BLOCK_COPY", False
        ) else None
        self._layout_executor = BlockLayoutExecutor(
            model=self.model,
            global_layout_ctx=self.global_layout_ctx,
            node_width=self.node_width,
            node_height=self.node_height,
            block_padding=self.block_padding,
            shared_edge_indices_provider=shared_indices_provider,
        )
        setattr(self.model, "_layout_y_debug_info", {})

    def identify_and_layout_blocks(
        self,
        start_node_id: str,
        global_visited: Set[str],
        event_root_id: Optional[str] = None,
        event_title: Optional[str] = None,
    ) -> None:
        """
        递归识别基本块并进行块内布局（委托两个纯函数完成识别/布局）
        
        Args:
            start_node_id: 起始节点ID
            global_visited: 全局已访问节点集合
        """
        if start_node_id in global_visited:
            return

        metadata: Optional[Tuple[Optional[str], Optional[str]]] = None
        if event_root_id:
            resolved_title = self._precomputed_event_metadata.get(event_root_id, (None, None))[1]
            if resolved_title is None:
                fallback_title = event_title or getattr(self.model.nodes.get(event_root_id), "title", None)
                resolved_title = self._resolve_event_title_from_model(event_root_id, fallback_title)
            metadata = (event_root_id, resolved_title)
            self._event_metadata_cache[event_root_id] = metadata

        # 阶段1：识别流程节点序列（纯函数，传入 layout_context 优化边查询）
        current_block_nodes = identify_block_flow_nodes(
            self.model,
            start_node_id,
            global_visited,
            self.global_layout_ctx,
        )
        if not current_block_nodes:
            return

        if metadata:
            for flow_node_id in current_block_nodes:
                self._event_metadata_cache.setdefault(flow_node_id, metadata)

        # 标记流程节点为已访问
        for node_id in current_block_nodes:
            global_visited.add(node_id)

        # 阶段2：块内局部布局（纯函数）
        block_order_index = self._block_sequence
        layout_block, placed_data_nodes = self._layout_block_internal(
            current_block_nodes,
            global_visited,
            block_order_index=block_order_index,
            event_metadata=metadata,
        )

        # 分配颜色与稳定序号
        layout_block.color = self.colors[self._color_index % len(self.colors)]
        self._color_index += 1
        layout_block.order_index = block_order_index
        self._block_sequence += 1

        # 记录块内数据节点为已访问，避免跨块重复
        for data_node_id in placed_data_nodes:
            global_visited.add(data_node_id)

        self.layout_blocks.append(layout_block)

        # 递归处理分支
        for _, next_node_id in layout_block.last_node_branches:
            if metadata:
                self.identify_and_layout_blocks(next_node_id, global_visited, metadata[0], metadata[1])
            else:
                self.identify_and_layout_blocks(next_node_id, global_visited)

    def _layout_block_internal(
        self,
        flow_node_ids: List[str],
        global_visited: Set[str],
        block_order_index: int = 0,
        event_metadata: Optional[Tuple[Optional[str], Optional[str]]] = None,
    ) -> Tuple["LayoutBlock", List[str]]:
        """
        基于已识别的流程节点序列，完成"块内局部布局与边界计算"（纯函数）
        
        本函数作为协调器，将布局任务委派给专门的类来完成。
        返回（布局块，块内放置的数据节点集合）。
        
        Args:
            flow_node_ids: 流程节点ID列表
            global_visited: 全局已访问节点集合
            block_order_index: 块序号
            
        Returns:
            (布局块, 块内数据节点ID列表)
        """
        resolved_metadata = event_metadata or self._resolve_event_metadata(flow_node_ids)

        return self._layout_executor.layout_block(
            flow_node_ids=flow_node_ids,
            global_visited=global_visited,
            block_order_index=block_order_index,
            event_metadata=resolved_metadata,
        )

    def _ensure_shared_edge_indices(self) -> SharedEdgeIndexMap:
        """
        构建（或返回已有的）可变边索引副本，供跨块复制场景共享。
        """
        if self._shared_edge_indices is not None:
            return self._shared_edge_indices

        def _clone_index(index: Dict[str, List[Any]]) -> CopyOnWriteEdgeIndex:
            return CopyOnWriteEdgeIndex(index)

        layout_ctx = self.global_layout_ctx
        self._shared_edge_indices = {
            "data_in_edges_by_dst": _clone_index(layout_ctx.dataInByNode),
            "data_out_edges_by_src": _clone_index(layout_ctx.dataOutByNode),
            "flow_in_edges_by_dst": _clone_index(layout_ctx.flowInByNode),
            "flow_out_edges_by_src": _clone_index(layout_ctx.flowOutByNode),
        }
        return self._shared_edge_indices

    def _resolve_event_metadata(self, flow_node_ids: List[str]) -> Tuple[Optional[str], Optional[str]]:
        """
        获取块所属事件流的 ID 与标题，优先使用缓存避免重复回溯。
        """
        for flow_node_id in flow_node_ids:
            cached_value = self._event_metadata_cache.get(flow_node_id)
            if cached_value is not None:
                return cached_value

        if hasattr(self.global_layout_ctx, "get_event_metadata"):
            for flow_node_id in flow_node_ids:
                resolved = self.global_layout_ctx.get_event_metadata(flow_node_id)
                if resolved:
                    self._event_metadata_cache.setdefault(flow_node_id, resolved)
                    return resolved

        return self._compute_event_metadata(flow_node_ids)

    def _compute_event_metadata(self, flow_node_ids: List[str]) -> Tuple[Optional[str], Optional[str]]:
        """
        回溯到事件节点并批量缓存结果，避免后续块重复遍历。
        """
        visited_nodes: Set[str] = set()
        traversal_queue: deque[str] = deque(flow_node_ids)
        resolved_event_id: Optional[str] = None
        resolved_event_title: Optional[str] = None

        while traversal_queue:
            current_node_id = traversal_queue.popleft()
            if current_node_id in visited_nodes:
                continue
            visited_nodes.add(current_node_id)
            current_node = self.model.nodes.get(current_node_id)
            if not current_node:
                continue

            if current_node.category == "事件节点":
                resolved_event_id = current_node_id
                resolved_event_title = self._precomputed_event_metadata.get(current_node_id, (None, None))[1]
                if resolved_event_title is None:
                    resolved_event_title = self._resolve_event_title_from_model(
                        current_node_id,
                        current_node.title,
                    )
                break

            for inbound_edge in self.global_layout_ctx.get_in_flow_edges(current_node_id):
                src_node_id = getattr(inbound_edge, "src_node", None)
                if src_node_id:
                    traversal_queue.append(src_node_id)

        for tracked_node_id in visited_nodes:
            self._event_metadata_cache[tracked_node_id] = (resolved_event_id, resolved_event_title)

        return resolved_event_id, resolved_event_title

    def _resolve_event_title_from_model(
        self,
        event_node_id: str,
        fallback_title: Optional[str],
    ) -> Optional[str]:
        """统一通过 graph_query_utils 的工具解析事件标题"""
        return resolve_event_title(
            self.model,
            event_node_id,
            fallback_title=fallback_title,
            title_lookup=self._event_title_lookup,
        )

