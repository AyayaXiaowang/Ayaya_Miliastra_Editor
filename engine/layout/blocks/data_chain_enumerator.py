"""
数据链枚举器

为块内"消费者→上游"的数据链编号，并推导链驱动的X轴间距需求。
遍历顺序：流程从左到右，端口自上而下；先到先编号。

优化：输出结构化的放置指令，供DataNodePlacer直接消费，避免重复遍历。
"""

from __future__ import annotations
from typing import Optional, Set, List, Tuple, Dict
from dataclasses import dataclass, field

from .block_layout_context import BlockLayoutContext
from ..utils.graph_query_utils import (
    ChainPathsResult,
    ChainTraversalBudget,
    collect_data_chain_paths,
    collect_upstream_data_closure,
    build_chain_signature,
    get_chain_traversal_budget,
)


@dataclass(frozen=True)
class CopyDecision:
    """跨块复制判定结果（供数据节点放置阶段统一消费）"""

    needs_copy: bool = False
    trigger: Optional[str] = None
    upstream_closure: List[str] = field(default_factory=list)
    pending_source_ids: List[str] = field(default_factory=list)

    def normalized_pending_sources(self) -> List[str]:
        """保持顺序地去重 pending_source_ids，避免放置阶段重复调度。"""
        ordered: List[str] = []
        seen: Set[str] = set()
        for node_id in self.pending_source_ids:
            if not node_id:
                continue
            if node_id in seen:
                continue
            seen.add(node_id)
            ordered.append(node_id)
        return ordered


@dataclass
class ChainPlacementInfo:
    """链的放置信息（用于DataNodePlacer消费）"""

    chain_id: int
    start_data_id: str  # 链的起始数据节点（最靠近消费者）
    consumer_flow_id: str  # 消费者流程节点ID
    consumer_port_name: Optional[str]  # 消费者端口名
    consumer_port_index: Optional[int]  # 消费者端口序号
    chain_nodes: List[str]  # 链上所有节点（从消费者到上游）
    needs_copy: bool  # 起始节点是否需要复制（命中跨块边界）
    upstream_closure: List[str]  # 需要强制复制的上游闭包节点列表（若needs_copy=True）
    copy_decision: CopyDecision = field(default_factory=CopyDecision)


class DataChainEnumerator:
    """
    数据链枚举器 - 为块内"消费者→上游"的数据链编号，并推导链驱动的X轴间距需求。
    遍历顺序：流程从左到右，端口自上而下；先到先编号。
    
    优化：输出结构化的放置指令列表，供DataNodePlacer直接消费。
    """

    def __init__(self, context: BlockLayoutContext):
        self.context = context
        self._budget: ChainTraversalBudget = get_chain_traversal_budget()
        # 输出的放置指令列表（按消费者从左到右、端口从上到下排序）
        self.placement_instructions: List[ChainPlacementInfo] = []
        # 链去重集合，避免在复杂图或跨块复制场景下为同一条逻辑链生成多个ID
        # 签名维度：链上节点序列 + 消费者流程ID + 端口信息 + 上游流程起源（若有）
        self._seen_chain_signatures: Set[tuple] = set()
        self._max_per_block = self._budget.max_per_block
        self._budget_remaining: Optional[int] = self._max_per_block if self._max_per_block > 0 else None
        self._exhausted_chain_budget = False
        # 共享“节点→路径列表”缓存，避免多个输入端口对同一数据子图重复 DFS
        self._shared_paths_cache: Dict[str, List[Tuple[List[str], Optional[str], bool]]] = {}

    def enumerate_all_chains(self) -> None:
        if not self.context.flow_node_ids:
            return
        for consumer_id in self.context.flow_node_ids:
            consumer_node = self.context.model.nodes.get(consumer_id)
            if not consumer_node:
                continue
            incoming_data_edges_view = self.context.get_data_in_edges(consumer_id)
            if not incoming_data_edges_view:
                continue
            # 输入端口自上而下
            incoming_data_edges = sorted(
                incoming_data_edges_view,
                key=lambda edge: self.context.get_input_port_index(consumer_id, edge.dst_port),
            )
            for edge in incoming_data_edges:
                if self._exhausted_chain_budget:
                    return
                start_data_id = edge.src_node
                if not self.context.is_pure_data_node(start_data_id):
                    continue
                consumer_port_name = edge.dst_port
                consumer_port_index = self.context.get_input_port_index(consumer_id, consumer_port_name)
                self._enumerate_from_start(start_data_id, consumer_id, consumer_port_name, consumer_port_index)
                if self._exhausted_chain_budget:
                    return

    def _enumerate_from_start(
        self,
        start_data_id: str,
        consumer_flow_id: str,
        consumer_port_name: Optional[str],
        consumer_port_index: Optional[int],
    ) -> None:
        # 枚举从起点出发的所有可能路径（允许多条链共享节点）
        # 使用通用函数，传入索引函数以保持性能；共享缓存减少重复 DFS
        budget_for_start = self._budget_remaining if self._budget_remaining is not None else None
        paths_result: ChainPathsResult = collect_data_chain_paths(
            model=self.context.model,
            start_data_id=start_data_id,
            flow_id_set=self.context.flow_id_set,
            skip_data_ids=self.context.skip_data_ids,
            get_data_in_edges_func=self.context.get_data_in_edges,
            include_skip_node_as_terminus=True,  # 边界节点作为链的终点，触发复制
            layout_context=self.context.get_port_layout_context(),
            shared_cache=self._shared_paths_cache,
            budget=self._budget,
            max_results=budget_for_start,
        )
        all_paths = paths_result.paths

        # 判断起始节点是否需要复制：
        # - 情况1：起始节点本身已经属于上一块（命中 skip 集合）
        # - 情况2：其上游闭包中存在属于上一块的节点（即使当前起点尚未被占用，也需要整链复制）
        skip_data_ids = self.context.skip_data_ids
        upstream_closure: List[str] = []

        def _ensure_upstream_closure() -> List[str]:
            nonlocal upstream_closure
            if not upstream_closure:
                upstream_closure = collect_upstream_data_closure(
                    model=self.context.model,
                    start_data_id=start_data_id,
                    skip_data_ids=skip_data_ids,
                    get_data_in_edges_func=self.context.get_data_in_edges,
                    respect_skip_ids=False,
                )
            return upstream_closure

        start_is_boundary = start_data_id in skip_data_ids
        boundary_nodes: List[str] = []
        copy_trigger: Optional[str] = "start_boundary" if start_is_boundary else None
        pending_sources: List[str] = [start_data_id] if start_is_boundary else []

        if skip_data_ids:
            closure_snapshot = _ensure_upstream_closure()
            if closure_snapshot:
                boundary_nodes = [node_id for node_id in closure_snapshot if node_id in skip_data_ids]
                if boundary_nodes and not start_is_boundary:
                    copy_trigger = "upstream_boundary"

        for node_id in boundary_nodes:
            if node_id not in pending_sources:
                pending_sources.append(node_id)

        needs_copy = start_is_boundary
        copy_decision = CopyDecision(
            needs_copy=needs_copy,
            trigger=copy_trigger,
            upstream_closure=list(boundary_nodes),
            pending_source_ids=pending_sources,
        )

        for path_nodes, src_flow_id, is_flow_origin in all_paths:
            if not path_nodes:
                continue
            if self._exhausted_chain_budget:
                break
            # ===== 链级去重：避免为同一条逻辑链生成多个链ID =====
            # 在启用“数据节点跨块复制”后，上游复制/重定向可能导致
            # collect_data_chain_paths 返回内容等价的多条路径（节点序列与消费者端口完全一致），
            # 进而在调试信息中出现“链 N / 链 M ...”都指向同一条可视链的现象。
            #
            # 这里通过稳定签名去重：完全相同的（节点序列 + 消费者流程 + 端口 + 上游流程起源标记）
            # 只保留一条，既不会影响布局几何约束，也能减少用户看到的冗余链条数量。
            signature = build_chain_signature(
                nodes_list=path_nodes,
                src_flow_id=src_flow_id,
                is_flow_origin=is_flow_origin,
                extra=(consumer_flow_id, consumer_port_name, consumer_port_index),
            )
            if signature in self._seen_chain_signatures:
                continue
            self._seen_chain_signatures.add(signature)

            chain_id = self.context.next_chain_id
            self.context.next_chain_id += 1
            self.context.chain_nodes[chain_id] = list(path_nodes)
            self.context.chain_length[chain_id] = len(path_nodes)
            self.context.chain_is_flow_origin[chain_id] = is_flow_origin
            self.context.chain_source_flow[chain_id] = src_flow_id if is_flow_origin else None
            self.context.chain_target_flow[chain_id] = consumer_flow_id
            # 记录消费者端口信息（该链起始于哪个输入端口）
            self.context.chain_consumer_port_name[chain_id] = consumer_port_name
            self.context.chain_consumer_port_index[chain_id] = consumer_port_index

            # 记录节点属于该链，并记录其在链上的位置（从消费者往回数）
            for position, node_id in enumerate(path_nodes):
                if node_id not in self.context.data_chain_ids_by_node:
                    self.context.data_chain_ids_by_node[node_id] = []
                self.context.data_chain_ids_by_node[node_id].append(chain_id)
                self.context.node_position_in_chain[(node_id, chain_id)] = position

            if is_flow_origin and src_flow_id in self.context.flow_id_set and consumer_flow_id in self.context.flow_id_set:
                pair_key = (src_flow_id, consumer_flow_id)
                # 仅按“消费者 → 链入口”之间的实际数据节点数量来约束流程槽位间距，
                # 避免将公共上游（在入口之前的共享子链）也计入 A→B 间距，导致执行节点被额外拉开。
                effective_chain_length = self._compute_effective_chain_length_for_flow_pair(path_nodes, src_flow_id)
                required_gap = 1 + effective_chain_length
                previous_gap = self.context.flow_pair_required_gap.get(pair_key, 0)
                if required_gap > previous_gap:
                    self.context.flow_pair_required_gap[pair_key] = required_gap

            # 生成放置指令（每条链生成一个指令）
            placement_info = ChainPlacementInfo(
                chain_id=chain_id,
                start_data_id=start_data_id,
                consumer_flow_id=consumer_flow_id,
                consumer_port_name=consumer_port_name,
                consumer_port_index=consumer_port_index,
                chain_nodes=list(path_nodes),
                needs_copy=copy_decision.needs_copy,
                upstream_closure=copy_decision.upstream_closure,
                copy_decision=copy_decision,
            )
            self.placement_instructions.append(placement_info)
            if self._budget_remaining is not None:
                self._budget_remaining -= 1
                if self._budget_remaining <= 0:
                    self._exhausted_chain_budget = True
                    break

        if paths_result.exhausted:
            self._exhausted_chain_budget = True

    # 便于外部调试时查看是否因为预算停止
    @property
    def exhausted_chain_budget(self) -> bool:
        return self._exhausted_chain_budget


    def _compute_effective_chain_length_for_flow_pair(
        self,
        path_nodes: List[str],
        src_flow_id: str,
    ) -> int:
        """
        计算当前链在 (src_flow_id → 消费者流程) 之间实际参与间距的“有效长度”。

        规则：
        - 若链上存在由 src_flow_id 直接驱动的数据节点，只统计从消费者一侧到
          第一个被该流程驱动的数据节点（含）之间的节点数量；
        - 若未能找到入口（理论上不应发生），则退回到整条链的长度。
        """
        effective_length = len(path_nodes)
        entry_index: Optional[int] = None

        for index, data_id in enumerate(path_nodes):
            incoming_edges = self.context.get_data_in_edges(data_id)
            if not incoming_edges:
                continue
            for edge in incoming_edges:
                if edge.src_node == src_flow_id:
                    entry_index = index
                    break
            if entry_index is not None:
                break

        if entry_index is not None:
            effective_length = entry_index + 1

        return effective_length



