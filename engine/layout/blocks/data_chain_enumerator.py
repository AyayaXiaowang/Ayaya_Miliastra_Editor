"""
数据链枚举器

为块内"消费者→上游"的数据链编号，并推导链驱动的X轴间距需求。
遍历顺序：流程从左到右，端口自上而下；先到先编号。

新流程：
- 复制决策已移到全局阶段（GlobalCopyManager）
- 枚举器只负责链编号和放置指令生成
"""

from __future__ import annotations
from typing import Optional, Set, List, Dict
from dataclasses import dataclass, field

from .block_layout_context import BlockLayoutContext
from ..utils.graph_query_utils import (
    ChainPathsResult,
    ChainTraversalBudget,
    collect_data_chain_paths,
    build_chain_signature,
    get_chain_traversal_budget,
)


@dataclass
class ChainPlacementInfo:
    """链的放置信息（用于DataNodePlacer消费）"""

    chain_id: int
    start_data_id: str  # 链的起始数据节点（最靠近消费者）
    consumer_flow_id: str  # 消费者流程节点ID
    consumer_port_name: Optional[str]  # 消费者端口名
    consumer_port_index: Optional[int]  # 消费者端口序号
    chain_nodes: List[str]  # 链上所有节点（从消费者到上游）


class DataChainEnumerator:
    """数据链枚举器 - 为块内"消费者→上游"的数据链编号
    
    新流程下的职责：
    - 枚举数据链并分配链编号
    - 生成放置指令供 DataNodePlacer 消费
    - 不再负责复制决策（已移到全局阶段）
    """

    def __init__(self, context: BlockLayoutContext):
        self.context = context
        self._budget: ChainTraversalBudget = get_chain_traversal_budget()
        # 输出的放置指令列表
        self.placement_instructions: List[ChainPlacementInfo] = []
        # 链去重集合
        self._seen_chain_signatures: Set[tuple] = set()
        self._max_per_block = self._budget.max_per_block
        self._budget_remaining: Optional[int] = self._max_per_block if self._max_per_block > 0 else None
        self._exhausted_chain_budget = False
        # 共享"节点→路径列表"缓存
        self._shared_paths_cache: Dict[str, List[tuple]] = {}

    def enumerate_all_chains(self) -> None:
        """枚举所有数据链"""
        if not self.context.flow_node_ids:
            return
        for consumer_id in self.context.flow_node_ids:
            consumer_node = self.context.model.nodes.get(consumer_id)
            if not consumer_node:
                continue
            incoming_data_edges_view = self.context.get_in_data_edges(consumer_id)
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
        """从起始节点枚举链"""
        budget_for_start = self._budget_remaining if self._budget_remaining is not None else None
        
        # 新流程：不再使用 skip_data_ids，直接遍历所有数据链
        paths_result: ChainPathsResult = collect_data_chain_paths(
            model=self.context.model,
            start_data_id=start_data_id,
            flow_id_set=self.context.flow_id_set,
            skip_data_ids=set(),  # 不再需要 skip 集合
            get_data_in_edges_func=self.context.get_in_data_edges,
            include_skip_node_as_terminus=False,
            layout_context=self.context.get_port_layout_context(),
            shared_cache=self._shared_paths_cache,
            budget=self._budget,
            max_results=budget_for_start,
        )
        all_paths = paths_result.paths

        for path_nodes, src_flow_id, is_flow_origin in all_paths:
            if not path_nodes:
                continue
            if self._exhausted_chain_budget:
                break
            
            # 链级去重
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
            self.context.chain_consumer_port_name[chain_id] = consumer_port_name
            self.context.chain_consumer_port_index[chain_id] = consumer_port_index

            # 记录节点属于该链
            for position, node_id in enumerate(path_nodes):
                if node_id not in self.context.data_chain_ids_by_node:
                    self.context.data_chain_ids_by_node[node_id] = []
                self.context.data_chain_ids_by_node[node_id].append(chain_id)
                self.context.node_position_in_chain[(node_id, chain_id)] = position

            if is_flow_origin and src_flow_id in self.context.flow_id_set and consumer_flow_id in self.context.flow_id_set:
                pair_key = (src_flow_id, consumer_flow_id)
                effective_chain_length = self._compute_effective_chain_length_for_flow_pair(path_nodes, src_flow_id)
                required_gap = 1 + effective_chain_length
                previous_gap = self.context.flow_pair_required_gap.get(pair_key, 0)
                if required_gap > previous_gap:
                    self.context.flow_pair_required_gap[pair_key] = required_gap

            # 生成放置指令（简化版，不再包含复制决策）
            placement_info = ChainPlacementInfo(
                chain_id=chain_id,
                start_data_id=start_data_id,
                consumer_flow_id=consumer_flow_id,
                consumer_port_name=consumer_port_name,
                consumer_port_index=consumer_port_index,
                chain_nodes=list(path_nodes),
            )
            self.placement_instructions.append(placement_info)
            
            if self._budget_remaining is not None:
                self._budget_remaining -= 1
                if self._budget_remaining <= 0:
                    self._exhausted_chain_budget = True
                    break

        if paths_result.exhausted:
            self._exhausted_chain_budget = True

    @property
    def exhausted_chain_budget(self) -> bool:
        return self._exhausted_chain_budget

    def _compute_effective_chain_length_for_flow_pair(
        self,
        path_nodes: List[str],
        src_flow_id: str,
    ) -> int:
        """计算链在流程对之间的有效长度"""
        effective_length = len(path_nodes)
        entry_index: Optional[int] = None

        for index, data_id in enumerate(path_nodes):
            incoming_edges = self.context.get_in_data_edges(data_id)
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
