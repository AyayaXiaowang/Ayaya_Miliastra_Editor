"""
数据节点放置器

负责递归放置数据节点（记录放置顺序和堆叠层次）。

新流程：
- 复制逻辑已移到全局阶段（GlobalCopyManager）
- DataNodePlacer 只负责放置已存在的节点
- 通过 context.should_place_data_node() 判断节点是否应该放置
"""

from __future__ import annotations
from collections import deque
from dataclasses import dataclass
from typing import Set, Dict, Tuple, Optional, List, Callable, TYPE_CHECKING

from engine.graph.models import NodeModel

from .block_layout_context import BlockLayoutContext
from ..utils.graph_query_utils import collect_upstream_data_closure

if TYPE_CHECKING:
    from .data_chain_enumerator import ChainPlacementInfo


@dataclass(frozen=True)
class _PlacementPlan:
    """封装单条链指令的放置计划"""
    instruction: "ChainPlacementInfo"
    chain_nodes: List[str]


class DataNodePlacer:
    """数据节点放置器 - 负责放置数据节点
    
    新流程下的职责：
    - 消费链枚举器的放置指令
    - 按链编号为数据节点分配堆叠顺序
    - 不再负责跨块复制（已移到全局阶段）
    """

    def __init__(
        self,
        context: BlockLayoutContext,
        count_outgoing_data_edges_func: Callable,
        block_id: str = "",
        enable_copy: bool = False,  # 不再使用，保留参数兼容性
    ):
        self.context = context
        self.count_outgoing_data_edges = count_outgoing_data_edges_func
        self.block_id = block_id
        self._chain_upstream_map: Optional[Dict[str, List[str]]] = None

    def place_all_data_nodes(self, placement_instructions: List["ChainPlacementInfo"]) -> None:
        """为所有流程节点放置其数据依赖
        
        Args:
            placement_instructions: 链枚举器输出的放置指令列表
        """
        # 消费链枚举器的结构化输出
        self._place_from_instructions(placement_instructions)
        # 放置链枚举阶段未覆盖的本块局部数据节点
        self._place_downstream_data_nodes_by_ownership()

    def _place_from_instructions(self, instructions: List["ChainPlacementInfo"]) -> None:
        """基于链枚举器输出的结构化指令放置数据节点"""
        processed_chain_ids: Set[int] = set()
        placement_plans: List[_PlacementPlan] = []
        self._ensure_chain_upstream_map(instructions)

        for instruction in instructions:
            if instruction.chain_id in processed_chain_ids:
                continue
            processed_chain_ids.add(instruction.chain_id)
            plan = self._build_placement_plan(instruction)
            if plan is not None:
                placement_plans.append(plan)

        for plan in placement_plans:
            self._execute_plan(plan)

    def _build_placement_plan(self, instruction: "ChainPlacementInfo") -> Optional[_PlacementPlan]:
        chain_nodes = instruction.chain_nodes or []
        start_id = instruction.start_data_id
        if not chain_nodes and start_id:
            chain_nodes = [start_id]
        if not chain_nodes:
            return None

        return _PlacementPlan(
            instruction=instruction,
            chain_nodes=list(chain_nodes),
        )

    def _execute_plan(self, plan: _PlacementPlan) -> None:
        """执行放置计划"""
        self._place_chain_nodes(plan.chain_nodes)

    def _place_chain_nodes(self, chain_nodes: List[str]) -> None:
        """放置链上的节点"""
        if not chain_nodes:
            return
        for node_id in reversed(chain_nodes):
            self._place_node_if_valid(node_id)

    def _place_node_if_valid(self, node_id: Optional[str]) -> None:
        """如果节点有效且应该放置，则放置它"""
        if not node_id:
            return
        if node_id in self.context.placed_data_nodes:
            return
        if not self.context.is_pure_data_node(node_id):
            return
        # 使用新的判断方法
        if not self.context.should_place_data_node(node_id):
            return
        self._place_current_data_node(node_id)

    def _ensure_chain_upstream_map(self, instructions: List["ChainPlacementInfo"]) -> None:
        """构建链内上游映射"""
        if self._chain_upstream_map is not None:
            return
        upstream_map: Dict[str, List[str]] = {}
        for instruction in instructions:
            nodes_in_chain = instruction.chain_nodes or []
            for index in range(len(nodes_in_chain) - 1):
                downstream_id = nodes_in_chain[index]
                upstream_id = nodes_in_chain[index + 1]
                bucket = upstream_map.setdefault(downstream_id, [])
                if upstream_id not in bucket:
                    bucket.append(upstream_id)
        self._chain_upstream_map = upstream_map

    def apply_chain_based_stack_order(self) -> None:
        """根据链编号为数据节点分配堆叠顺序"""

        def sort_key(node_id: str) -> Tuple[int, int, int]:
            chain_ids = self.context.data_chain_ids_by_node.get(node_id)
            if chain_ids is None or len(chain_ids) == 0:
                original = self.context.node_stack_order.get(node_id, 10**6)
                return (1, 10**9, original)
            min_chain_id = min(chain_ids)
            return (0, min_chain_id, 0)

        ordered = sorted(self.context.data_nodes_in_order, key=sort_key)

        current_layer_index = 0
        for node_id in ordered:
            extra_down_layers = 1 if self.count_outgoing_data_edges(
                self.context.model,
                node_id,
                self.context.data_out_edges_by_src,
            ) >= 2 else 0
            start_layer = current_layer_index + extra_down_layers
            self.context.node_stack_order[node_id] = start_layer
            estimated_height = self.context.get_estimated_node_height(node_id)
            layers_occupied = 1 + (1 if estimated_height > self.context.node_height else 0)
            current_layer_index = start_layer + layers_occupied

    def _place_current_data_node(self, data_id: str) -> None:
        """记录当前数据节点的放置"""
        self.context.node_stack_order[data_id] = len(self.context.placed_data_nodes)
        self.context.placed_data_nodes.add(data_id)
        self.context.data_nodes_in_order.append(data_id)

    def _place_downstream_data_nodes_by_ownership(self) -> None:
        """下游数据节点放置：沿当前块节点的数据输出边向下游遍历"""
        if not self.context.flow_node_ids:
            return

        from .data_node_ownership import DataNodeOwnershipResolver

        ownership_resolver = DataNodeOwnershipResolver(self.context)

        current_block_node_ids: Set[str] = set(self.context.flow_node_ids)
        current_block_node_ids.update(self.context.placed_data_nodes)

        visited_downstream_ids: Set[str] = set()
        traversal_queue: "deque[str]" = deque()

        for flow_node_id in self.context.flow_node_ids:
            if isinstance(flow_node_id, str) and flow_node_id:
                traversal_queue.append(flow_node_id)

        for data_node_id in list(self.context.placed_data_nodes):
            if isinstance(data_node_id, str) and data_node_id:
                if data_node_id not in visited_downstream_ids:
                    traversal_queue.append(data_node_id)

        while traversal_queue:
            source_id = traversal_queue.popleft()
            outgoing_edges = self.context.get_data_out_edges(source_id)
            if not outgoing_edges:
                continue

            for edge in outgoing_edges:
                target_id = getattr(edge, "dst_node", None)
                if not isinstance(target_id, str) or target_id == "":
                    continue
                if target_id in visited_downstream_ids:
                    continue
                visited_downstream_ids.add(target_id)

                # 使用归属判定器判断是否应该放置
                decision = ownership_resolver.resolve(target_id, current_block_node_ids)

                if not decision.should_place:
                    continue

                traversal_queue.append(target_id)

                if (
                    target_id in self.context.placed_data_nodes
                    or target_id in self.context.shared_data_nodes
                ):
                    continue

                # 使用新的判断方法
                if not self.context.should_place_data_node(target_id):
                    continue

                self._place_current_data_node(target_id)
                current_block_node_ids.add(target_id)
