"""
全局跨块数据节点复制管理器（确定性）

负责在所有块识别完成后，统一分析跨块共享的数据节点，批量创建副本并重定向边。

重要约束：
- 可复现：同一输入图在同一配置下重复执行得到相同结果（不使用 uuid 生成边 ID）。
- 幂等：在已存在副本节点/已重定向边的图上重复执行不会无限膨胀，优先复用现有副本。

调用时机：所有块的流程节点识别完成后、数据节点放置前。

实现说明：
- 为降低单文件体积并提升可维护性，GlobalCopyManager 的实现按“索引/分析/计划/应用/查询”拆分到同目录模块；
- 本文件作为稳定入口，保留旧 import 路径：`engine.layout.utils.global_copy_manager.GlobalCopyManager`。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple, TYPE_CHECKING

from engine.graph.models import EdgeModel, GraphModel

from .global_copy_manager_analysis import _GlobalCopyManagerAnalysisMixin
from .global_copy_manager_indices import _GlobalCopyManagerIndicesMixin
from .global_copy_manager_plan import _GlobalCopyManagerPlanMixin
from .global_copy_manager_queries import _GlobalCopyManagerQueryMixin
from .global_copy_manager_types import (
    FORBIDDEN_CROSS_BLOCK_COPY_NODE_TITLES,
    BlockDataDependency,
    CopyNodeSpec,
    CopyPlan,
    EdgeMutation,
    GlobalCopyApplicationPlan,
    NewEdgeSpec,
)

if TYPE_CHECKING:
    from ..internal.layout_context import LayoutContext
    from ..internal.layout_models import LayoutBlock


__all__ = [
    "FORBIDDEN_CROSS_BLOCK_COPY_NODE_TITLES",
    "BlockDataDependency",
    "CopyPlan",
    "CopyNodeSpec",
    "EdgeMutation",
    "NewEdgeSpec",
    "GlobalCopyApplicationPlan",
    "GlobalCopyManager",
]


class GlobalCopyManager(
    _GlobalCopyManagerIndicesMixin,
    _GlobalCopyManagerAnalysisMixin,
    _GlobalCopyManagerPlanMixin,
    _GlobalCopyManagerQueryMixin,
):
    """全局跨块数据节点复制管理器

    职责：
    1. 分析所有块的数据依赖，识别跨块共享的数据节点
    2. 生成复制计划
    3. 统一创建所有需要的副本
    4. 统一执行边重定向（断开旧边，创建新边）

    使用方式：
        manager = GlobalCopyManager(model, layout_blocks, layout_context)
        manager.analyze_dependencies()
        manager.execute_copy_plan()
    """

    def __init__(
        self,
        model: GraphModel,
        layout_blocks: List["LayoutBlock"],
        layout_context: Optional["LayoutContext"] = None,
    ):
        self.model = model
        self.layout_blocks = layout_blocks
        self.layout_context = layout_context

        # 分析结果
        self.block_dependencies: Dict[str, BlockDataDependency] = {}
        # 数据节点 -> 使用它的块ID列表（按块序号排序）
        self.data_node_consumers: Dict[str, List[str]] = {}
        # 复制计划
        self.copy_plans: Dict[str, CopyPlan] = {}
        # 已存在或创建的副本映射：(canonical_original_id, block_id) -> copy_id
        self.created_copies: Dict[Tuple[str, str], str] = {}
        # 流程节点所属块的映射：流程节点ID -> 块ID
        self._flow_to_block: Dict[str, str] = {}

        # 既有副本索引：(canonical_original_id, block_id) -> node_id
        self._existing_copy_by_original_and_block: Dict[Tuple[str, str], str] = {}
        self._build_existing_copy_index()

        # 物理数据边索引（只读快照，用于计划构建，按 edge.id 固定排序）
        self._data_in_edges_by_dst: Dict[str, List[EdgeModel]] = {}
        self._data_out_edges_by_src: Dict[str, List[EdgeModel]] = {}
        self._build_data_edge_indices_snapshot()

        # 逻辑数据依赖索引（canonical 视图）：dst_canonical -> {src_canonical,...}
        self._logical_upstream_by_data_dst: Dict[str, Set[str]] = {}
        # 逻辑数据依赖索引（canonical 视图）：src_canonical -> {dst_canonical,...}
        # 用于识别“仅由输出引脚消费”的纯数据尾部子图，并在块归属阶段做兜底挂载。
        self._logical_downstream_by_data_src: Dict[str, Set[str]] = {}
        # 逻辑入边模板（用于为副本补齐输入）：dst_canonical -> {(src_id_or_canonical, src_port, dst_port, src_is_pure_data)}
        self._incoming_edge_templates_by_canonical_dst: Dict[str, Set[Tuple[str, str, str, bool]]] = {}
        self._build_logical_dependency_views()

        # 最近一次生成的“纯计划”
        self._application_plan: Optional[GlobalCopyApplicationPlan] = None

        # 禁止跨块复制的 canonical 节点 → owner block_id（仅用于闭包扩展的“上游截断”）
        # 说明：语义敏感节点（如【获取局部变量】）不会被复制；在非 owner 块中不应继续
        # 将其纯数据上游闭包计入本块依赖，否则会触发“上游被复制但下游未复制”的孤立副本。
        self._forbidden_owner_block_by_canonical: Dict[str, str] = {}
        # 块列索引（column）缓存：block_id -> column_index。
        #
        # 背景：
        # - block_index(order_index) 是稳定编号，但不等同于块在布局中的横向列位置；
        # - 对“禁止跨块复制”的语义敏感纯数据节点（如【获取局部变量】），只能保留单一实例，
        #   因此必须选择一个 owner 块来放置该节点；
        # - 若按 block_index 选 owner，可能出现 owner 位于更右侧列，从而在 UI 中产生跨块回头线（右→左）。
        # - 这里预计算 column_index，并在 owner 选择/排序中优先使用它，确保跨块数据边尽量从左到右。
        self._block_column_index_by_block_id: Dict[str, int] = {}

