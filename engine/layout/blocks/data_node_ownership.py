"""
数据节点归属判定器

职责：给定一个数据节点和当前块上下文，判断该节点是否应该属于当前块。

设计背景：
- 数据节点的归属逻辑原本分散在多个地方（DataChainEnumerator、DataNodePlacer 等）
- 抽取为独立模块便于理解、测试和维护

归属规则（按优先级）：
1. 如果节点被当前块的流程节点直接消费 → 属于当前块
2. 如果节点被当前块已放置的数据节点消费 → 属于当前块
3. 如果节点没有出边（孤立节点）→ 属于入边来源所在的块
4. 否则 → 不属于当前块，等待后续块处理
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Set, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .block_layout_context import BlockLayoutContext


class OwnershipReason(Enum):
    """归属原因枚举"""
    CONSUMED_BY_FLOW_NODE = "consumed_by_flow_node"
    CONSUMED_BY_PLACED_DATA_NODE = "consumed_by_placed_data_node"
    ORPHAN_WITH_SOURCE_IN_BLOCK = "orphan_with_source_in_block"
    NOT_CONSUMED_BY_BLOCK = "not_consumed_by_block"
    SKIP_BOUNDARY_NODE = "skip_boundary_node"
    NOT_PURE_DATA_NODE = "not_pure_data_node"


@dataclass
class OwnershipDecision:
    """归属判定结果"""
    should_place: bool
    reason: OwnershipReason
    detail: str = ""


class DataNodeOwnershipResolver:
    """数据节点归属判定器
    
    集中管理"数据节点应该属于哪个块"的判定逻辑。
    """

    def __init__(self, context: "BlockLayoutContext"):
        self.context = context

    def resolve(
        self,
        data_node_id: str,
        block_node_ids: Set[str],
    ) -> OwnershipDecision:
        """判断数据节点是否应该放到当前块
        
        Args:
            data_node_id: 待判定的数据节点 ID
            block_node_ids: 当前块的节点集合（流程节点 + 已放置的数据节点）
            
        Returns:
            OwnershipDecision 包含是否放置、原因和详情
        """
        # 规则 0：跳过边界节点（已被前序块处理）
        if data_node_id in self.context.skip_data_ids:
            return OwnershipDecision(
                should_place=False,
                reason=OwnershipReason.SKIP_BOUNDARY_NODE,
                detail="节点在 skip_data_ids 中，已被前序块处理",
            )

        # 规则 0.1：必须是纯数据节点
        if not self.context.is_pure_data_node(data_node_id):
            return OwnershipDecision(
                should_place=False,
                reason=OwnershipReason.NOT_PURE_DATA_NODE,
                detail="节点不是纯数据节点",
            )

        # 获取出边
        outgoing_edges = self.context.get_data_out_edges(data_node_id)
        has_outgoing = bool(outgoing_edges)

        if has_outgoing:
            # 规则 1/2：检查是否被当前块消费
            return self._check_consumption_by_block(data_node_id, block_node_ids, outgoing_edges)
        else:
            # 规则 3：孤立节点（无出边）→ 检查入边来源
            return self._check_orphan_node_source(data_node_id, block_node_ids)

    def _check_consumption_by_block(
        self,
        data_node_id: str,
        block_node_ids: Set[str],
        outgoing_edges,
    ) -> OwnershipDecision:
        """检查有出边的节点是否被当前块消费"""
        for edge in outgoing_edges:
            consumer_id = getattr(edge, "dst_node", None)
            if not isinstance(consumer_id, str) or consumer_id == "":
                continue
            
            if consumer_id in self.context.flow_id_set:
                return OwnershipDecision(
                    should_place=True,
                    reason=OwnershipReason.CONSUMED_BY_FLOW_NODE,
                    detail=f"被当前块的流程节点 {consumer_id} 消费",
                )
            
            if consumer_id in block_node_ids:
                return OwnershipDecision(
                    should_place=True,
                    reason=OwnershipReason.CONSUMED_BY_PLACED_DATA_NODE,
                    detail=f"被当前块已放置的数据节点 {consumer_id} 消费",
                )

        return OwnershipDecision(
            should_place=False,
            reason=OwnershipReason.NOT_CONSUMED_BY_BLOCK,
            detail="输出边的目标节点均不在当前块",
        )

    def _check_orphan_node_source(
        self,
        data_node_id: str,
        block_node_ids: Set[str],
    ) -> OwnershipDecision:
        """检查孤立节点（无出边）的入边来源"""
        incoming_edges = self.context.get_in_data_edges(data_node_id)
        
        if not incoming_edges:
            # 既没有入边也没有出边 → 完全孤立，跳过
            return OwnershipDecision(
                should_place=False,
                reason=OwnershipReason.NOT_CONSUMED_BY_BLOCK,
                detail="节点既无入边也无出边",
            )

        # 检查入边来源是否在当前块
        for in_edge in incoming_edges:
            src_id = getattr(in_edge, "src_node", None)
            if isinstance(src_id, str) and src_id in block_node_ids:
                return OwnershipDecision(
                    should_place=True,
                    reason=OwnershipReason.ORPHAN_WITH_SOURCE_IN_BLOCK,
                    detail=f"孤立节点，入边来源 {src_id} 在当前块",
                )

        return OwnershipDecision(
            should_place=False,
            reason=OwnershipReason.NOT_CONSUMED_BY_BLOCK,
            detail="孤立节点的入边来源不在当前块",
        )


def assert_all_data_nodes_assigned(
    model,
    node_library=None,
) -> list:
    """检查是否所有数据节点都被分配到了某个块
    
    Args:
        model: GraphModel 实例
        node_library: 节点库（可选，用于判断是否为纯数据节点）
        
    Returns:
        未分配的节点 ID 列表（正常情况应为空）
    """
    from engine.utils.graph.graph_utils import is_pure_data_node as check_pure_data

    # 收集所有纯数据节点
    all_data_node_ids: Set[str] = set()
    for node_id, node in model.nodes.items():
        if check_pure_data(node, node_library):
            all_data_node_ids.add(node_id)

    # 收集所有块中的节点
    assigned_node_ids: Set[str] = set()
    for block in (model.basic_blocks or []):
        for node_id in (block.nodes or []):
            assigned_node_ids.add(node_id)

    # 找出未分配的
    orphan_ids = all_data_node_ids - assigned_node_ids
    return list(orphan_ids)

