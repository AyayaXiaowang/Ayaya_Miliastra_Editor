"""
块内布局上下文

定义块内布局过程中的共享状态和查询方法。
"""

from __future__ import annotations
from typing import Dict, List, Set, Optional

from engine.graph.models import GraphModel
from ..utils.graph_query_utils import (
    is_pure_data_node as graph_query_is_pure_data_node,
    build_edge_indices,
    estimate_node_height_ui_exact_with_context,
)
from ..core.layout_context import LayoutContext


class BlockLayoutContext:
    """块内布局的上下文信息（共享状态）"""

    def __init__(
        self,
        model: GraphModel,
        flow_node_ids: List[str],
        node_width: float,
        node_height: float,
        data_base_y: float,
        flow_to_data_gap: float,
        data_stack_gap: float,
        ui_node_header_height: float,
        ui_row_height: float,
        input_port_to_data_gap: float,
        skip_data_node_ids: Optional[Set[str]] = None,
        global_layout_context: Optional[LayoutContext] = None,
        block_order_index: int = 0,
        event_flow_title: Optional[str] = None,
        event_flow_id: Optional[str] = None,
        shared_edge_indices: Optional[dict] = None,
    ):
        self.model = model
        self.flow_node_ids = flow_node_ids
        self.node_width = node_width
        self.node_height = node_height
        self.data_base_y = data_base_y
        self.flow_to_data_gap = flow_to_data_gap
        self.data_stack_gap = data_stack_gap
        self.ui_node_header_height = ui_node_header_height
        self.ui_row_height = ui_row_height
        self.input_port_to_data_gap = input_port_to_data_gap

        # 衍生数据
        self.flow_id_set: Set[str] = set(flow_node_ids)
        # 块编号与事件流信息（用于调试展示）
        self.block_order_index: int = int(block_order_index) if block_order_index is not None else 0
        self.block_id_string: str = f"block_{self.block_order_index}" if self.block_order_index > 0 else ""
        self.event_flow_title: Optional[str] = event_flow_title
        self.event_flow_id: Optional[str] = event_flow_id

        # === 阶段1：相对排序记录（不含坐标） ===
        self.node_slot_index: Dict[str, int] = {}  # 记录每个节点的目标槽位索引
        self.node_stack_order: Dict[str, int] = {}  # 记录同一槽位内的堆叠顺序（用于Y坐标）

        # 数据节点相关状态
        self.placed_data_nodes: Set[str] = set()
        self.data_nodes_in_order: List[str] = []
        self.flow_bottom_by_slot: Dict[int, float] = {}
        self.shared_data_nodes: Set[str] = set()
        # 该块应放置的数据节点集合（由全局复制管理器在阶段2设置）
        self.block_data_nodes: Set[str] = set()
        self._block_data_nodes_set: bool = False  # 标记是否已通过 set_block_data_nodes 设置
        # 兼容性：保留 skip_data_ids 和 pending_copy_sources，但不再使用
        self.skip_data_ids: Set[str] = set(skip_data_node_ids or [])
        self.pending_copy_sources: Set[str] = set()
        # 全局索引上下文（只读复用，避免重复构建）
        self._global_layout_context: Optional[LayoutContext] = global_layout_context
        if self._global_layout_context is None:
            cached_ctx = getattr(self.model, "_layout_context_cache", None)
            if isinstance(cached_ctx, LayoutContext) and getattr(cached_ctx, "model", None) is self.model:
                self._global_layout_context = cached_ctx
            else:
                self._global_layout_context = LayoutContext(self.model)
        self._shared_edge_indices = shared_edge_indices
        self._edge_indices_are_mutable = bool(shared_edge_indices)
        self._global_edge_api: Optional[LayoutContext] = None

        # 链编号与元信息（用于链驱动的X/Y策略）
        self.data_chain_ids_by_node: Dict[str, List[int]] = {}  # 数据节点 -> 链ID列表（支持一个节点属于多条链）
        self.node_position_in_chain: Dict[tuple[str, int], int] = {}  # (节点ID, 链ID) -> 该节点在链上的位置
        self.chain_nodes: Dict[int, List[str]] = {}  # 链ID -> 节点序列（从靠消费者一侧向上游延伸）
        self.chain_is_flow_origin: Dict[int, bool] = {}  # 是否以"流程输出→数据"为上游终止
        self.chain_source_flow: Dict[int, Optional[str]] = {}  # 若流程起源：上游流程节点ID
        self.chain_target_flow: Dict[int, Optional[str]] = {}  # 该链服务的消费者流程节点ID
        self.chain_length: Dict[int, int] = {}  # 链长度（数据节点数）
        # 消费者端口信息（该链起始于消费者的哪个输入端口）
        self.chain_consumer_port_name: Dict[int, Optional[str]] = {}  # 链ID -> 消费者输入端口名
        self.chain_consumer_port_index: Dict[int, Optional[int]] = {}  # 链ID -> 消费者输入端口序
        self.flow_pair_required_gap: Dict[tuple[str, str], int] = {}  # (src_flow, dst_flow) -> 最小槽位差
        self.next_chain_id: int = 1

        # === 阶段2：坐标分配结果 ===
        # 节点位置映射（将在布局过程中填充）
        self.node_local_pos: Dict[str, tuple[float, float]] = {}
        # Y轴调试信息（节点ID -> 文本/结构化详情），用于UI叠加展示
        self.debug_y_info: Dict[str, dict] = {}

        # 边索引缓存（一次性构建，避免重复O(E)扫描）
        self.data_in_edges_by_dst: Dict[str, List] = {}
        self.data_out_edges_by_src: Dict[str, List] = {}
        self.flow_in_edges_by_dst: Dict[str, List] = {}
        self._node_height_cache: Dict[str, float] = {}
        self._build_edge_indices()

    def _build_edge_indices(self) -> None:
        """构建边索引缓存，避免重复O(E)扫描"""
        if self._shared_edge_indices is not None:
            self.data_in_edges_by_dst = self._shared_edge_indices.get("data_in_edges_by_dst", {})
            self.data_out_edges_by_src = self._shared_edge_indices.get("data_out_edges_by_src", {})
            self.flow_in_edges_by_dst = self._shared_edge_indices.get("flow_in_edges_by_dst", {})
            self._global_edge_api = self._global_layout_context
            return
        # 优先复用全局 LayoutContext 的只读索引，避免每个块重复构建
        if self._global_layout_context is not None:
            self.data_in_edges_by_dst = self._global_layout_context.dataInByNode
            self.data_out_edges_by_src = self._global_layout_context.dataOutByNode
            self.flow_in_edges_by_dst = self._global_layout_context.flowInByNode
            self._global_edge_api = self._global_layout_context
            return

        _, flow_in_edges_by_dst, data_out_edges_by_src, data_in_edges_by_dst = build_edge_indices(self.model)
        self.data_in_edges_by_dst = data_in_edges_by_dst
        self.data_out_edges_by_src = data_out_edges_by_src
        self.flow_in_edges_by_dst = flow_in_edges_by_dst

    def is_pure_data_node(self, node_id: str) -> bool:
        """判断节点是否为纯数据节点（无流程端口）"""
        if self._global_edge_api is not None:
            return self._global_edge_api.is_pure_data_node(node_id)
        return graph_query_is_pure_data_node(node_id, self.model)

    def get_input_port_index(self, node_id: str, port_name: str) -> int:
        """获取输入端口索引，优先复用全局上下文"""
        assert self._global_layout_context is not None
        return self._global_layout_context.get_input_port_index(node_id, port_name)

    def get_output_port_index(self, node_id: str, port_name: str) -> int:
        """获取输出端口索引，优先复用全局上下文"""
        assert self._global_layout_context is not None
        return self._global_layout_context.get_output_port_index(node_id, port_name)

    def iter_out_data_edges(self, src_id: str):
        """迭代从指定节点出发的数据边（使用索引）"""
        if self._global_edge_api is not None and not self._edge_indices_are_mutable:
            source_edges = self._global_edge_api.get_out_data_edges(src_id)
        else:
            source_edges = self.data_out_edges_by_src.get(src_id, [])
        for edge in source_edges:
            dst_node = self.model.nodes.get(edge.dst_node)
            if not dst_node:
                continue

            # 流程输入上的数据边
            if edge.dst_node in self.flow_id_set:
                yield edge
            else:
                # 数据→数据边
                if self.is_pure_data_node(edge.dst_node):
                    yield edge

    def get_port_layout_context(self) -> Optional[LayoutContext]:
        """返回可用于端口索引的全局上下文"""
        return self._global_layout_context

    def get_in_data_edges(self, node_id: str) -> List:
        """获取节点的数据输入边（使用索引）"""
        if self._global_edge_api is not None and not self._edge_indices_are_mutable:
            return self._global_edge_api.get_in_data_edges(node_id)
        return self.data_in_edges_by_dst.get(node_id, [])

    def get_data_out_edges(self, node_id: str) -> List:
        """获取节点的数据输出边（使用索引）"""
        if self._global_edge_api is not None and not self._edge_indices_are_mutable:
            return self._global_edge_api.get_out_data_edges(node_id)
        return self.data_out_edges_by_src.get(node_id, [])

    def get_estimated_node_height(self, node_id: str) -> float:
        """缓存节点高度估算，避免重复调用"""
        cached_value = self._node_height_cache.get(node_id)
        if cached_value is not None:
            return cached_value
        height = estimate_node_height_ui_exact_with_context(self, node_id)
        self._node_height_cache[node_id] = height
        return height

    # ===== 全局复制阶段接口 =====
    def set_block_data_nodes(self, data_nodes: Set[str]) -> None:
        """设置该块应放置的数据节点集合（由全局复制管理器调用）
        
        Args:
            data_nodes: 该块应放置的数据节点ID集合
        """
        self.block_data_nodes = set(data_nodes)
        self._block_data_nodes_set = True  # 标记已设置（即使是空集合）
    
    def should_place_data_node(self, node_id: str) -> bool:
        """判断数据节点是否应该在该块放置
        
        新逻辑：如果 block_data_nodes 已设置（包括空集合），则只放置其中的节点；
        否则回退到旧逻辑（放置所有遇到的数据节点）。
        """
        # 使用标记判断是否已设置，而不是检查集合是否非空
        if self._block_data_nodes_set:
            return node_id in self.block_data_nodes
        # 兼容旧逻辑
        return node_id not in self.skip_data_ids

    # ===== 链枚举状态复位（支持复制后重枚举）=====
    def reset_chain_enumeration_state(self) -> None:
        """复位与链枚举相关的所有状态，以便在复制与边重定向之后重新枚举数据链。"""
        self.data_chain_ids_by_node.clear()
        self.node_position_in_chain.clear()
        self.chain_nodes.clear()
        self.chain_is_flow_origin.clear()
        self.chain_source_flow.clear()
        self.chain_target_flow.clear()
        self.chain_length.clear()
        self.chain_consumer_port_name.clear()
        self.chain_consumer_port_index.clear()
        self.flow_pair_required_gap.clear()
        # 链读集合以跨块边界为初始"已读"集合
        self.next_chain_id = 1



