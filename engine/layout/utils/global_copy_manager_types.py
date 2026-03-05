"""
GlobalCopyManager 的类型与常量定义。

说明：
- 该文件仅承载 dataclass/常量，供 GlobalCopyManager 的多个阶段实现复用；
- 不包含任何对 GraphModel 的修改逻辑（计划/应用逻辑在其它模块）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Set, Tuple


# 某些“查询节点”虽然没有流程端口，但其语义与块内作用域/状态绑定；
# 一旦在跨块复制阶段被复制，会产生“同名但不同实例”的状态分叉（例如局部变量句柄）。
# 这些节点必须禁止跨块复制，只允许保留单一原始实例，并在非 owner 块通过跨块数据边共享引用。
FORBIDDEN_CROSS_BLOCK_COPY_NODE_TITLES: Set[str] = {
    "获取局部变量",
}


@dataclass
class BlockDataDependency:
    """块的数据依赖信息"""

    block_id: str
    block_index: int
    flow_node_ids: Set[str]
    # 直接被流程节点消费的数据节点
    direct_data_consumers: Set[str] = field(default_factory=set)
    # 包含上游闭包的完整数据依赖
    full_data_closure: Set[str] = field(default_factory=set)


@dataclass
class CopyPlan:
    """复制计划：描述一个数据节点需要在哪些块创建副本"""

    original_node_id: str
    # 首个使用该节点的块（保留原始节点）
    owner_block_id: str
    owner_block_index: int
    # 需要创建副本的块列表（块ID -> 副本ID）
    copy_targets: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class CopyNodeSpec:
    """描述一个需要存在的副本节点（纯数据）。"""

    canonical_original_id: str
    block_id: str
    copy_node_id: str
    copy_counter: int


@dataclass(frozen=True)
class EdgeMutation:
    """对一条既有边进行原地重定向（保持 edge.id 不变）。"""

    edge_id: str
    new_src_node: str
    new_dst_node: str


@dataclass(frozen=True)
class NewEdgeSpec:
    """需要新增的一条数据边。"""

    edge_id: str
    src_node: str
    src_port: str
    dst_node: str
    dst_port: str


@dataclass(frozen=True)
class GlobalCopyApplicationPlan:
    """全局复制的“纯计划”输出：不包含 GraphModel 对象引用。"""

    copy_nodes: Tuple[CopyNodeSpec, ...]
    edge_mutations: Tuple[EdgeMutation, ...]
    new_edges: Tuple[NewEdgeSpec, ...]

