"""
数据节点放置器

负责递归放置数据节点（记录放置顺序和堆叠层次）。

优化：直接消费链枚举器输出的结构化放置指令，避免重复遍历。
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Set, Dict, Tuple, Optional, List, Callable, TYPE_CHECKING

from engine.graph.models import NodeModel

from .block_layout_context import BlockLayoutContext
from .data_chain_enumerator import CopyDecision
from ..utils.graph_query_utils import collect_upstream_data_closure

if TYPE_CHECKING:
    from .data_chain_enumerator import ChainPlacementInfo


FORBIDDEN_COPY_NODE_TITLES: Set[str] = {"获取局部变量"}


class _DataCopySupport:
    """封装跨块数据节点复制与重定向的流程，减轻 DataNodePlacer 职责。"""

    def __init__(self, context: BlockLayoutContext, block_id: str):
        self.context = context
        self.block_id = block_id
        self.node_copy_counter: Dict[str, int] = {}
        self.copied_nodes: Dict[str, str] = {}

    def instruction_contains_forbidden_node(self, instruction: "ChainPlacementInfo") -> bool:
        candidate_ids = [instruction.start_data_id]
        candidate_ids.extend(instruction.upstream_closure or [])
        for node_id in candidate_ids:
            if self._is_copy_forbidden_node_id(node_id):
                return True
        return False

    def batch_copy_upstream_closure(
        self,
        upstream_closure: List[str],
        place_fn: Callable[[str], None],
    ) -> None:
        for upstream_id in reversed(upstream_closure):
            place_fn(upstream_id)

    def create_copy_if_needed(self, original_id: str) -> Optional[str]:
        from ..utils.node_copy_utils import create_data_node_copy

        if original_id in self.copied_nodes:
            return self.copied_nodes[original_id]

        original_node = self.context.model.nodes.get(original_id)
        if not original_node:
            return None
        if self._is_copy_forbidden_node(original_node):
            return None

        counter = self.node_copy_counter.get(original_id, 0) + 1
        self.node_copy_counter[original_id] = counter

        copy_node = create_data_node_copy(
            original_node,
            self.context.model,
            self.block_id,
            counter,
        )
        self.copied_nodes[original_id] = copy_node.id
        return copy_node.id

    def finalize_redirects(self) -> None:
        if not self.copied_nodes:
            return
        from ..utils.node_copy_utils import redirect_edges_to_copy

        edge_indices = {
            "data_in_edges_by_dst": self.context.data_in_edges_by_dst,
            "data_out_edges_by_src": self.context.data_out_edges_by_src,
        }
        for original_id, copy_id in self.copied_nodes.items():
            redirect_edges_to_copy(
                self.context.model,
                original_id,
                copy_id,
                self.context.flow_id_set,
                self.context.placed_data_nodes,
                edge_indices,
                block_id=self.block_id,
                copy_map=self.copied_nodes,
            )

    def propagate_chain_indices(self) -> None:
        for original_id, copy_id in self.copied_nodes.items():
            chain_ids = self.context.data_chain_ids_by_node.get(original_id) or []
            if not chain_ids:
                continue

            self.context.data_chain_ids_by_node[copy_id] = list(chain_ids)

            for chain_id in chain_ids:
                position = self.context.node_position_in_chain.get((original_id, chain_id))
                if position is not None:
                    self.context.node_position_in_chain[(copy_id, chain_id)] = position

    def _is_copy_forbidden_node_id(self, node_id: Optional[str]) -> bool:
        if not node_id:
            return False
        node = self.context.model.nodes.get(node_id)
        return self._is_copy_forbidden_node(node)

    @staticmethod
    def _is_copy_forbidden_node(node: Optional[NodeModel]) -> bool:
        if not node:
            return False
        normalized_title = (node.title or "").strip()
        return normalized_title in FORBIDDEN_COPY_NODE_TITLES


@dataclass(frozen=True)
class _PlacementPlan:
    """封装单条链指令的放置计划（便于在执行前统一整理状态）。"""

    instruction: "ChainPlacementInfo"
    chain_nodes: List[str]
    copy_decision: CopyDecision


class DataNodePlacer:
    """数据节点放置器 - 负责递归放置数据节点"""

    def __init__(
        self,
        context: BlockLayoutContext,
        count_outgoing_data_edges_func,
        block_id: str = "",  # 当前块ID
        enable_copy: bool = True,  # 是否启用复制
    ):
        self.context = context
        self.count_outgoing_data_edges = count_outgoing_data_edges_func
        self.block_id = block_id
        self.enable_copy = enable_copy
        self._copy_support = _DataCopySupport(context, block_id)
        self._chain_upstream_map: Optional[Dict[str, List[str]]] = None

    def place_all_data_nodes(self, placement_instructions: List["ChainPlacementInfo"]) -> None:
        """
        为所有流程节点放置其数据依赖
        
        Args:
            placement_instructions: 链枚举器输出的放置指令列表（必需参数）
        
        优化：完全基于链枚举器的结构化输出，消除重复的端口排序和遍历
        """
        # 直接消费链枚举器的结构化输出
        self._place_from_instructions(placement_instructions)
        self._ensure_pending_copy_sources_processed()

    def _place_from_instructions(self, instructions: List["ChainPlacementInfo"]) -> None:
        """
        基于链枚举器输出的结构化指令放置数据节点
        
        优势：
        1. 避免重复遍历流程节点和端口
        2. 直接利用已知的端口顺序和链信息
        3. 上游闭包已预先计算，无需递归查找
        """
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

        decision = instruction.copy_decision
        if decision is None:
            decision = CopyDecision(
                needs_copy=instruction.needs_copy,
                upstream_closure=list(instruction.upstream_closure or []),
            )

        return _PlacementPlan(
            instruction=instruction,
            chain_nodes=list(chain_nodes),
            copy_decision=decision,
        )

    def _execute_plan(self, plan: _PlacementPlan) -> None:
        instruction = plan.instruction
        decision = plan.copy_decision
        self._register_pending_sources(decision, instruction.start_data_id)

        requires_start_copy = bool(decision and decision.needs_copy)
        requires_upstream_copies = bool(decision and decision.upstream_closure)

        if requires_start_copy or requires_upstream_copies:
            if not self.enable_copy or self._instruction_contains_forbidden_copy_node(instruction):
                self._place_chain_nodes_without_copy_support(
                    plan.chain_nodes,
                    instruction.start_data_id,
                    allow_skip_relaxation=True,
                )
                self._mark_copy_sources_resolved(decision, instruction.start_data_id)
                return

            if requires_start_copy:
                executed = self._execute_copy_plan(plan)
                if executed:
                    return
                self._place_chain_nodes_without_copy_support(
                    plan.chain_nodes,
                    instruction.start_data_id,
                    allow_skip_relaxation=True,
                )
                self._mark_copy_sources_resolved(decision, instruction.start_data_id)
                return

            # 仅需复制上游边界节点（链首仍留在当前块）
            self._batch_copy_upstream_closure(decision.upstream_closure)
            self._place_chain_nodes_without_recursion(plan.chain_nodes)
            self._mark_copy_sources_resolved(decision, instruction.start_data_id)
            return

        self._place_chain_nodes_without_recursion(plan.chain_nodes)

    def _execute_copy_plan(self, plan: _PlacementPlan) -> bool:
        start_id = plan.instruction.start_data_id
        if not start_id:
            return False
        copy_id = self._create_copy_if_needed(start_id)
        if copy_id is None:
            return False

        self._batch_copy_upstream_closure(plan.copy_decision.upstream_closure)
        self._place_data_recursive(
            copy_id,
            force_copy=True,
            skip_upstream_traversal=True,
        )
        self._mark_copy_sources_resolved(plan.copy_decision, start_id)
        return True

    def _register_pending_sources(self, decision: CopyDecision, start_node_id: Optional[str]) -> None:
        if not decision:
            return

        pending_targets = decision.normalized_pending_sources()
        if decision.needs_copy and start_node_id and start_node_id not in pending_targets:
            pending_targets.append(start_node_id)
        if not pending_targets and decision.upstream_closure:
            pending_targets = list(decision.upstream_closure)

        for node_id in pending_targets:
            if node_id:
                self.context.pending_copy_sources.add(node_id)

    def _ensure_chain_upstream_map(self, instructions: List["ChainPlacementInfo"]) -> None:
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

    def _batch_copy_upstream_closure(self, upstream_closure: List[str]) -> None:
        """
        批量复制并放置上游闭包节点
        """
        if not upstream_closure:
            return

        def _place(upstream_id: str) -> None:
            if upstream_id not in self.context.placed_data_nodes:
                self._place_data_recursive(
                    upstream_id,
                    force_copy=True,
                    skip_upstream_traversal=True,
                )

        self._copy_support.batch_copy_upstream_closure(upstream_closure, _place)

    def finalize_redirects_for_copies(self) -> None:
        """
        收尾重定向：在本块内所有数据节点放置完成后，
        对已创建的每个（原始→副本）再次执行一次边重定向，
        以覆盖先前由于"目标尚未放置"而遗漏的同块下游连接。
        """
        if not self.enable_copy:
            return
        self._copy_support.finalize_redirects()

    def propagate_chain_indices_to_copies(self) -> None:
        """
        将原节点的链索引信息增量复制到副本节点，避免二次重枚举
        
        优化（方案A）：复制后直接同步链信息，无需全量重新枚举所有链。
        同步项：data_chain_ids_by_node、node_position_in_chain
        """
        if not self.enable_copy:
            return
        self._copy_support.propagate_chain_indices()

    def apply_chain_based_stack_order(self) -> None:
        """
        根据链编号为数据节点分配堆叠顺序：
        - 按最小 chain_id 升序排列（编号小者更靠上）；
        - 无链编号的数据节点排在已编号之后，保持原有相对顺序；
        - 恢复高度占层与"多输出额外下移"的行为，避免重叠。
        
        注意：新X轴算法下，数据节点Y排序按链编号全局排序，不再按槽位分组
        """

        def sort_key(node_id: str) -> Tuple[int, int, int]:
            chain_ids = self.context.data_chain_ids_by_node.get(node_id)
            if chain_ids is None or len(chain_ids) == 0:
                # 无链号：归到末尾，并用原先的 stack_order 作为稳定次序
                original = self.context.node_stack_order.get(node_id, 10**6)
                return (1, 10**9, original)
            # 有链号：使用最小链号作为排序依据
            min_chain_id = min(chain_ids)
            return (0, min_chain_id, 0)

        ordered = sorted(self.context.data_nodes_in_order, key=sort_key)

        # 重新按"层"计算 stack_order：考虑额外下移与高度占层
        current_layer_index = 0
        for node_id in ordered:
            # 额外下移：若该节点的数据输出边数量≥2，则下移一层
            extra_down_layers = 1 if self.count_outgoing_data_edges(
                self.context.model,
                node_id,
                self.context.data_out_edges_by_src,
            ) >= 2 else 0
            # 该节点的起始层
            start_layer = current_layer_index + extra_down_layers
            self.context.node_stack_order[node_id] = start_layer
            # 占用层数：高度>基准高度则占2层，否则占1层
            estimated_height = self.context.get_estimated_node_height(node_id)
            layers_occupied = 1 + (1 if estimated_height > self.context.node_height else 0)
            # 更新游标：下一节点从本节点末尾的下一层开始
            current_layer_index = start_layer + layers_occupied

    def _place_data_recursive(
        self,
        data_id: str,
        force_copy: bool = False,
        skip_upstream_traversal: bool = False,
    ) -> None:
        """以拓扑顺序放置数据节点及必要的上游副本。"""
        ordered_nodes = self._build_ordered_node_sequence(
            data_id,
            skip_upstream_traversal=skip_upstream_traversal,
            initial_force_copy=force_copy,
        )
        if not ordered_nodes:
            return

        copy_flags = self._resolve_copy_flags(ordered_nodes, initial_force_copy=force_copy)

        for node_id in ordered_nodes:
            if not self.context.is_pure_data_node(node_id):
                continue
            node_obj = self.context.model.nodes.get(node_id)
            is_existing_copy = bool(getattr(node_obj, "is_data_node_copy", False))
            self.context.pending_copy_sources.discard(node_id)
            is_boundary_node = node_id in self.context.skip_data_ids
            need_copy_here = copy_flags.get(node_id, False) or is_boundary_node
            actual_node_id = node_id
            if need_copy_here and self.enable_copy:
                # 对当前块中新创建的副本：仅放置一次，不再在本块内继续复制；
                # 对来自前序块的节点（含其已有副本）：若命中跨块边界则在本块内再创建一份副本。
                should_create_new_copy = (not is_existing_copy) or is_boundary_node
                if should_create_new_copy:
                    actual_node_id = self._create_copy_if_needed(node_id)
                    if actual_node_id is None:
                        continue
                    self.context.pending_copy_sources.discard(actual_node_id)
            if actual_node_id in self.context.placed_data_nodes:
                continue
            self._place_current_data_node(actual_node_id)

    def _build_ordered_node_sequence(
        self,
        data_id: str,
        *,
        skip_upstream_traversal: bool,
        initial_force_copy: bool,
    ) -> List[str]:
        """构建从最远上游到当前节点的顺序列表。"""
        sequence: List[str] = []
        allow_skip_penetration = bool(initial_force_copy or data_id in self.context.skip_data_ids)
        if not skip_upstream_traversal:
            upstream_ids = self._collect_upstream_node_ids(
                data_id,
                allow_skip_penetration=allow_skip_penetration,
            )
            if upstream_ids:
                sequence.extend(reversed(upstream_ids))
        sequence.append(data_id)
        return sequence

    def _resolve_copy_flags(
        self,
        ordered_nodes: List[str],
        *,
        initial_force_copy: bool,
    ) -> Dict[str, bool]:
        """根据下游复制需求向上游传播复制标记。"""
        copy_flags: Dict[str, bool] = {}
        propagate = initial_force_copy
        for node_id in reversed(ordered_nodes):
            need_copy = propagate or node_id in self.context.skip_data_ids
            copy_flags[node_id] = need_copy
            propagate = need_copy
        return copy_flags

    def _collect_upstream_node_ids(
        self,
        source_node_id: str,
        *,
        allow_skip_penetration: bool,
    ) -> List[str]:
        """根据端口索引收集需要处理的上游节点列表。"""
        precomputed_upstreams = self._get_precomputed_upstreams(source_node_id)
        if precomputed_upstreams:
            return list(precomputed_upstreams)

        upstream_closure = collect_upstream_data_closure(
            model=self.context.model,
            start_data_id=source_node_id,
            skip_data_ids=self.context.skip_data_ids,
            get_data_in_edges_func=self.context.get_in_data_edges,
            respect_skip_ids=not allow_skip_penetration,
        )
        return list(upstream_closure)

    def _place_current_data_node(self, data_id: str) -> None:
        """记录当前数据节点的放置顺序（初始堆叠顺序，后续会按链编号重排）"""
        # 初始堆叠顺序（后续会被 apply_chain_based_stack_order 覆盖）
        self.context.node_stack_order[data_id] = len(self.context.placed_data_nodes)

        # 记录已放置
        self.context.placed_data_nodes.add(data_id)
        self.context.data_nodes_in_order.append(data_id)

    def _ensure_pending_copy_sources_processed(self) -> None:
        """
        兜底复制：针对链枚举阶段未能生成放置指令的跨块节点逐一复制，避免整图扫描。
        """
        if not self.enable_copy or not self.context.pending_copy_sources:
            self.context.pending_copy_sources.clear()
            return
        pending_sources = list(self.context.pending_copy_sources)
        self.context.pending_copy_sources.clear()
        for source_id in pending_sources:
            self._place_data_recursive(
                source_id,
                force_copy=True,
            )

    def _place_chain_nodes_without_recursion(self, chain_nodes: List[str]) -> None:
        if not chain_nodes:
            return
        for node_id in reversed(chain_nodes):
            self._place_node_if_unseen(node_id)

    def _place_chain_nodes_without_copy_support(
        self,
        chain_nodes: Optional[List[str]],
        fallback_start: Optional[str],
        *,
        allow_skip_relaxation: bool = False,
    ) -> None:
        """
        在未启用跨块复制时，仍然按原始链条顺序放置数据节点。

        说明：
        - 这些节点即便需要跨块共享，也直接复用现有节点，不再强制创建副本；
        - 保证布局阶段不会遗漏链条，避免节点停留在默认位置。
        """
        effective_nodes: List[str] = list(chain_nodes or [])
        if not effective_nodes and fallback_start:
            effective_nodes = [fallback_start]
        if not effective_nodes:
            return
        for node_id in reversed(effective_nodes):
            if allow_skip_relaxation and node_id in self.context.skip_data_ids:
                self._place_shared_node_if_unseen(node_id)
            else:
                self._place_node_if_unseen(node_id)

    def _mark_copy_sources_resolved(
        self,
        decision: Optional[CopyDecision],
        start_node_id: Optional[str],
    ) -> None:
        """
        将本次计划关联的 pending copy 源头标记为已处理，避免兜底阶段重复调度。
        """
        if not decision:
            return

        resolved_ids: List[str] = list(decision.normalized_pending_sources())
        if decision.needs_copy and start_node_id and start_node_id not in resolved_ids:
            resolved_ids.append(start_node_id)
        if not resolved_ids and decision.upstream_closure:
            resolved_ids = list(decision.upstream_closure)

        for node_id in resolved_ids:
            if node_id:
                self.context.pending_copy_sources.discard(node_id)

    def _place_node_if_unseen(self, node_id: Optional[str]) -> None:
        if not node_id:
            return
        if node_id in self.context.placed_data_nodes:
            return
        if node_id in self.context.skip_data_ids:
            return
        if not self.context.is_pure_data_node(node_id):
            return
        self._place_current_data_node(node_id)

    def _place_shared_node_if_unseen(self, node_id: Optional[str]) -> None:
        if not node_id:
            return
        if node_id in self.context.placed_data_nodes:
            return
        if not self.context.is_pure_data_node(node_id):
            return
        self.context.shared_data_nodes.add(node_id)
        self._place_current_data_node(node_id)

    def _get_precomputed_upstreams(self, node_id: Optional[str]) -> List[str]:
        if not node_id or self._chain_upstream_map is None:
            return []
        return self._chain_upstream_map.get(node_id, [])

    def _create_copy_if_needed(self, original_id: str) -> Optional[str]:
        return self._copy_support.create_copy_if_needed(original_id)

    def cleanup_orphan_copies(self) -> None:
        """
        占位函数：当前不再在布局阶段主动删除“孤立副本”。

        说明：
        - 早期版本会在块内布局完成后，扫描所有数据副本节点，删除“没有数据输出边”的副本及相关边；
        - 在复杂跨块复制场景下，该清理步骤依赖的边索引可能与实际 `model.edges` 轻微不同步，
          会出现“节点已被删除但仍残留指向该节点的边”的情况，从而写出包含幽灵节点引用的缓存。
        - 为避免破坏图结构完整性，当前阶段关闭这一步清理逻辑，改由复制决策阶段控制“不要创建多余的副本”。
        """
        return

    def _instruction_contains_forbidden_copy_node(self, instruction: "ChainPlacementInfo") -> bool:
        """检测放置指令中是否包含禁止复制的节点"""
        return self._copy_support.instruction_contains_forbidden_node(instruction)



