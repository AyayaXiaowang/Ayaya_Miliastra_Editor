"""
测试数据节点分块逻辑

覆盖场景：
1. 数据节点只被后续块消费时，应该分配到首次消费的块
2. 没有出边的孤立数据节点应该分配到入边来源所在的块
3. 被多个块消费的数据节点应该在首次消费块放置原始节点
"""

import pytest
from typing import Set

from engine.layout.blocks.data_node_ownership import (
    DataNodeOwnershipResolver,
    OwnershipDecision,
    OwnershipReason,
)


class MockEdge:
    """模拟边对象"""
    def __init__(self, src_node: str, dst_node: str):
        self.src_node = src_node
        self.dst_node = dst_node


class MockBlockLayoutContext:
    """模拟 BlockLayoutContext"""

    def __init__(
        self,
        flow_ids: Set[str],
        skip_data_ids: Set[str] = None,
        pure_data_node_ids: Set[str] = None,
        out_edges: dict = None,
        in_edges: dict = None,
    ):
        self.flow_id_set = flow_ids
        self.skip_data_ids = skip_data_ids or set()
        self._pure_data_node_ids = pure_data_node_ids or set()
        self._out_edges = out_edges or {}
        self._in_edges = in_edges or {}

    def is_pure_data_node(self, node_id: str) -> bool:
        return node_id in self._pure_data_node_ids

    def get_data_out_edges(self, node_id: str):
        return self._out_edges.get(node_id, [])

    def get_in_data_edges(self, node_id: str):
        return self._in_edges.get(node_id, [])


class TestDataNodeOwnershipResolver:
    """测试数据节点归属判定器"""

    def test_consumed_by_flow_node_should_place(self):
        """数据节点被当前块的流程节点消费 → 应该放置"""
        context = MockBlockLayoutContext(
            flow_ids={"flow_1", "flow_2"},
            pure_data_node_ids={"data_1"},
            out_edges={
                "data_1": [MockEdge("data_1", "flow_2")],
            },
        )

        resolver = DataNodeOwnershipResolver(context)
        decision = resolver.resolve("data_1", {"flow_1", "flow_2"})

        assert decision.should_place is True
        assert decision.reason == OwnershipReason.CONSUMED_BY_FLOW_NODE

    def test_consumed_by_placed_data_node_should_place(self):
        """数据节点被当前块已放置的数据节点消费 → 应该放置"""
        context = MockBlockLayoutContext(
            flow_ids={"flow_1"},
            pure_data_node_ids={"data_1", "data_2"},
            out_edges={
                "data_1": [MockEdge("data_1", "data_2")],
            },
        )

        resolver = DataNodeOwnershipResolver(context)
        # data_2 已经在 block_node_ids 中
        decision = resolver.resolve("data_1", {"flow_1", "data_2"})

        assert decision.should_place is True
        assert decision.reason == OwnershipReason.CONSUMED_BY_PLACED_DATA_NODE

    def test_not_consumed_by_current_block_should_not_place(self):
        """数据节点不被当前块消费 → 不应该放置"""
        context = MockBlockLayoutContext(
            flow_ids={"flow_1"},
            pure_data_node_ids={"data_1"},
            out_edges={
                "data_1": [MockEdge("data_1", "flow_other_block")],
            },
        )

        resolver = DataNodeOwnershipResolver(context)
        decision = resolver.resolve("data_1", {"flow_1"})

        assert decision.should_place is False
        assert decision.reason == OwnershipReason.NOT_CONSUMED_BY_BLOCK

    def test_orphan_with_source_in_block_should_place(self):
        """孤立节点（无出边），入边来源在当前块 → 应该放置"""
        context = MockBlockLayoutContext(
            flow_ids={"flow_1"},
            pure_data_node_ids={"data_orphan", "data_source"},
            out_edges={
                "data_orphan": [],  # 无出边
            },
            in_edges={
                "data_orphan": [MockEdge("data_source", "data_orphan")],
            },
        )

        resolver = DataNodeOwnershipResolver(context)
        # data_source 在当前块
        decision = resolver.resolve("data_orphan", {"flow_1", "data_source"})

        assert decision.should_place is True
        assert decision.reason == OwnershipReason.ORPHAN_WITH_SOURCE_IN_BLOCK

    def test_orphan_with_source_not_in_block_should_not_place(self):
        """孤立节点（无出边），入边来源不在当前块 → 不应该放置"""
        context = MockBlockLayoutContext(
            flow_ids={"flow_1"},
            pure_data_node_ids={"data_orphan"},
            out_edges={
                "data_orphan": [],  # 无出边
            },
            in_edges={
                "data_orphan": [MockEdge("data_other_block", "data_orphan")],
            },
        )

        resolver = DataNodeOwnershipResolver(context)
        decision = resolver.resolve("data_orphan", {"flow_1"})

        assert decision.should_place is False
        assert decision.reason == OwnershipReason.NOT_CONSUMED_BY_BLOCK

    def test_skip_data_ids_should_not_place(self):
        """跳过边界节点（已被前序块处理）"""
        context = MockBlockLayoutContext(
            flow_ids={"flow_1"},
            skip_data_ids={"data_boundary"},
            pure_data_node_ids={"data_boundary"},
        )

        resolver = DataNodeOwnershipResolver(context)
        decision = resolver.resolve("data_boundary", {"flow_1"})

        assert decision.should_place is False
        assert decision.reason == OwnershipReason.SKIP_BOUNDARY_NODE

    def test_not_pure_data_node_should_not_place(self):
        """非纯数据节点 → 不应该放置"""
        context = MockBlockLayoutContext(
            flow_ids={"flow_1"},
            pure_data_node_ids=set(),  # 不在纯数据节点集合中
        )

        resolver = DataNodeOwnershipResolver(context)
        decision = resolver.resolve("some_node", {"flow_1"})

        assert decision.should_place is False
        assert decision.reason == OwnershipReason.NOT_PURE_DATA_NODE

    def test_completely_isolated_node_should_not_place(self):
        """既没有入边也没有出边的完全孤立节点 → 不应该放置"""
        context = MockBlockLayoutContext(
            flow_ids={"flow_1"},
            pure_data_node_ids={"data_isolated"},
            out_edges={
                "data_isolated": [],  # 无出边
            },
            in_edges={
                "data_isolated": [],  # 也无入边
            },
        )

        resolver = DataNodeOwnershipResolver(context)
        decision = resolver.resolve("data_isolated", {"flow_1"})

        assert decision.should_place is False
        assert decision.reason == OwnershipReason.NOT_CONSUMED_BY_BLOCK
        assert "既无入边也无出边" in decision.detail

