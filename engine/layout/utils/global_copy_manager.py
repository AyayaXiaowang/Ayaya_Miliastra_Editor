"""
全局跨块数据节点复制管理器（确定性）

负责在所有块识别完成后，统一分析跨块共享的数据节点，批量创建副本并重定向边。

重要约束：
- 可复现：同一输入图在同一配置下重复执行得到相同结果（不使用 uuid 生成边 ID）。
- 幂等：在已存在副本节点/已重定向边的图上重复执行不会无限膨胀，优先复用现有副本。

调用时机：所有块的流程节点识别完成后、数据节点放置前。
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import hashlib
from typing import Dict, List, Set, Optional, Tuple, TYPE_CHECKING, Iterable

from engine.graph.models import GraphModel, NodeModel, EdgeModel
from .node_copy_utils import create_data_node_copy
from .graph_query_utils import build_edge_indices, is_data_edge, is_pure_data_node
from .copy_identity_utils import (
    ORDER_MAX_FALLBACK,
    infer_copy_block_id_from_node_id,
    is_data_node_copy,
    parse_copy_counter,
    resolve_canonical_original_id,
    resolve_copy_block_id,
)

if TYPE_CHECKING:
    from ..internal.layout_models import LayoutBlock
    from ..internal.layout_context import LayoutContext


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


class GlobalCopyManager:
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
        # 逻辑入边模板（用于为副本补齐输入）：dst_canonical -> {(src_id_or_canonical, src_port, dst_port, src_is_pure_data)}
        self._incoming_edge_templates_by_canonical_dst: Dict[str, Set[Tuple[str, str, str, bool]]] = {}
        self._build_logical_dependency_views()

        # 最近一次生成的“纯计划”
        self._application_plan: Optional[GlobalCopyApplicationPlan] = None
    
    def _build_existing_copy_index(self) -> None:
        """扫描现有副本节点，构建 (canonical_original_id, block_id) -> copy_node_id 映射。"""
        existing: Dict[Tuple[str, str], str] = {}
        for node in self.model.nodes.values():
            if not is_data_node_copy(node):
                continue
            canonical_original = self._resolve_canonical_original_id(node.id)
            if not canonical_original:
                continue
            block_id = resolve_copy_block_id(node)
            if not block_id:
                continue
            existing.setdefault((canonical_original, block_id), node.id)
        self._existing_copy_by_original_and_block = existing

    def _build_data_edge_indices_snapshot(self) -> None:
        """构建物理数据边索引快照（用于计划构建，按 edge.id 排序确保可复现）。"""
        if self.layout_context is not None:
            data_in = self.layout_context.dataInByNode
            data_out = self.layout_context.dataOutByNode
            self._data_in_edges_by_dst = {
                node_id: sorted(list(edges or []), key=lambda edge: getattr(edge, "id", ""))
                for node_id, edges in (data_in or {}).items()
            }
            self._data_out_edges_by_src = {
                node_id: sorted(list(edges or []), key=lambda edge: getattr(edge, "id", ""))
                for node_id, edges in (data_out or {}).items()
            }
            return

        _, _, data_out, data_in = build_edge_indices(self.model)
        self._data_in_edges_by_dst = {
            node_id: sorted(list(edges or []), key=lambda edge: getattr(edge, "id", ""))
            for node_id, edges in (data_in or {}).items()
        }
        self._data_out_edges_by_src = {
            node_id: sorted(list(edges or []), key=lambda edge: getattr(edge, "id", ""))
            for node_id, edges in (data_out or {}).items()
        }

    def _build_logical_dependency_views(self) -> None:
        """构建 canonical 视图的依赖与入边模板，兼容图中已存在副本与已重定向边。"""
        upstream_by_dst: Dict[str, Set[str]] = {}
        templates_by_dst: Dict[str, Set[Tuple[str, str, str, bool]]] = {}

        for edge in sorted(self.model.edges.values(), key=lambda item: getattr(item, "id", "")):
            if not is_data_edge(self.model, edge):
                continue
            if not edge.dst_node or not edge.src_node:
                continue
            dst_node_obj = self.model.nodes.get(edge.dst_node)
            if dst_node_obj is None:
                continue

            dst_is_pure = self._is_pure_data_node(edge.dst_node)
            if not dst_is_pure:
                continue

            dst_canonical = self._resolve_canonical_original_id(edge.dst_node)
            if not dst_canonical:
                continue

            src_is_pure = self._is_pure_data_node(edge.src_node)
            src_template_id = self._resolve_canonical_original_id(edge.src_node) if src_is_pure else edge.src_node
            if not src_template_id:
                continue

            templates_by_dst.setdefault(dst_canonical, set()).add(
                (str(src_template_id), str(edge.src_port), str(edge.dst_port), bool(src_is_pure))
            )

            # 逻辑闭包只沿纯数据上游扩展（遇到流程/非纯数据即终止）
            if not src_is_pure:
                continue
            src_canonical = self._resolve_canonical_original_id(edge.src_node)
            if not src_canonical:
                continue
            upstream_by_dst.setdefault(dst_canonical, set()).add(src_canonical)

        self._logical_upstream_by_data_dst = upstream_by_dst
        self._incoming_edge_templates_by_canonical_dst = templates_by_dst

    def _is_pure_data_node(self, node_id: str) -> bool:
        if self.layout_context is not None:
            return self.layout_context.is_pure_data_node(node_id)
        return is_pure_data_node(node_id, self.model)

    def _resolve_canonical_original_id(self, node_id: str) -> str:
        """将任意数据节点（含副本）归一到其 canonical original id。"""
        return resolve_canonical_original_id(node_id, model=self.model)
    
    def analyze_dependencies(self) -> None:
        """分析所有块的数据依赖"""
        # 步骤1：构建流程节点到块的映射
        self._build_flow_to_block_mapping()
        
        # 步骤2：收集每个块直接消费的数据节点
        self._collect_direct_consumers()
        
        # 步骤3：扩展到完整的上游闭包
        self._expand_to_full_closure()
        
        # 步骤4：识别跨块共享的数据节点
        self._identify_shared_nodes()
        
        # 步骤5：生成复制计划
        self._generate_copy_plans()
    
    def _build_flow_to_block_mapping(self) -> None:
        """构建流程节点到块的映射"""
        for block in self.layout_blocks:
            block_id = f"block_{block.order_index}"
            for flow_id in block.flow_nodes:
                self._flow_to_block[flow_id] = block_id
    
    def _collect_direct_consumers(self) -> None:
        """收集每个块直接消费的数据节点"""
        for block in self.layout_blocks:
            block_id = f"block_{block.order_index}"
            flow_ids = set(block.flow_nodes)
            
            dependency = BlockDataDependency(
                block_id=block_id,
                block_index=block.order_index,
                flow_node_ids=flow_ids,
            )
            
            # 遍历流程节点的输入边，找到直接消费的数据节点
            for flow_id in sorted(flow_ids):
                in_edges = self._data_in_edges_by_dst.get(flow_id, [])
                for edge in in_edges:
                    src_id = getattr(edge, "src_node", None)
                    if not isinstance(src_id, str) or not src_id:
                        continue
                    if self._is_pure_data_node(src_id):
                        dependency.direct_data_consumers.add(self._resolve_canonical_original_id(src_id))
            
            self.block_dependencies[block_id] = dependency
    
    def _expand_to_full_closure(self) -> None:
        """将直接消费扩展到完整的上游闭包"""
        for block_id, dependency in self.block_dependencies.items():
            visited: Set[str] = set()
            traversal_queue: deque[str] = deque(sorted(dependency.direct_data_consumers))

            while traversal_queue:
                current_canonical_id = traversal_queue.popleft()
                if current_canonical_id in visited:
                    continue
                visited.add(current_canonical_id)

                if not current_canonical_id:
                    continue
                dependency.full_data_closure.add(current_canonical_id)

                upstream_candidates = self._logical_upstream_by_data_dst.get(current_canonical_id, set())
                for upstream_canonical in sorted(upstream_candidates):
                    if upstream_canonical and upstream_canonical not in visited:
                        traversal_queue.append(upstream_canonical)
    
    def _identify_shared_nodes(self) -> None:
        """识别被多个块使用的数据节点"""
        # 收集每个数据节点被哪些块使用
        for block_id, dependency in self.block_dependencies.items():
            for data_id in dependency.full_data_closure:
                if data_id not in self.data_node_consumers:
                    self.data_node_consumers[data_id] = []
                if block_id not in self.data_node_consumers[data_id]:
                    self.data_node_consumers[data_id].append(block_id)
        
        # 按块序号排序（首个块保留原始节点）
        for data_id, block_ids in self.data_node_consumers.items():
            block_ids.sort(key=lambda bid: self.block_dependencies[bid].block_index)
    
    def _generate_copy_plans(self) -> None:
        """生成复制计划"""
        for data_id, block_ids in self.data_node_consumers.items():
            if len(block_ids) <= 1:
                # 只被一个块使用，不需要复制
                continue
            
            # 首个块保留原始节点
            owner_block_id = block_ids[0]
            owner_index = self.block_dependencies[owner_block_id].block_index
            
            plan = CopyPlan(
                original_node_id=data_id,
                owner_block_id=owner_block_id,
                owner_block_index=owner_index,
            )
            
            # 其他块需要创建/复用副本（每个块只创建一个副本）
            for block_id in block_ids[1:]:
                existing_copy_id = self._existing_copy_by_original_and_block.get((data_id, block_id))
                if existing_copy_id:
                    plan.copy_targets[block_id] = existing_copy_id
                else:
                    plan.copy_targets[block_id] = f"{data_id}_copy_{block_id}_1"
            
            self.copy_plans[data_id] = plan
    
    def execute_copy_plan(self) -> None:
        """执行复制计划：创建副本并重定向边"""
        if not self.copy_plans:
            return

        plan = self.build_application_plan()
        self.apply_application_plan(plan)
    
    def build_application_plan(self) -> GlobalCopyApplicationPlan:
        """基于当前 copy_plans 构建纯计划（不修改 model）。"""
        owner_block_by_canonical: Dict[str, str] = {}
        for canonical_id, block_ids in self.data_node_consumers.items():
            if not block_ids:
                continue
            owner_block_by_canonical[canonical_id] = block_ids[0]

        copy_nodes: List[CopyNodeSpec] = []
        for canonical_id in sorted(self.copy_plans.keys()):
            plan = self.copy_plans[canonical_id]
            for block_id in sorted(plan.copy_targets.keys()):
                copy_id = plan.copy_targets[block_id]
                copy_counter = self._parse_copy_counter(copy_id)
                copy_nodes.append(
                    CopyNodeSpec(
                        canonical_original_id=canonical_id,
                        block_id=block_id,
                        copy_node_id=copy_id,
                        copy_counter=copy_counter,
                    )
                )

        # 边重定向计划：针对现有数据边，按“目标实例所属块”把 src/dst 归一到同一块内的实例。
        edge_mutations: List[EdgeMutation] = []
        for edge in sorted(self.model.edges.values(), key=lambda item: getattr(item, "id", "")):
            if not is_data_edge(self.model, edge):
                continue

            dst_id = getattr(edge, "dst_node", "") or ""
            src_id = getattr(edge, "src_node", "") or ""
            if not dst_id or not src_id:
                continue

            edge_block_id = self._resolve_edge_block_id(dst_id, owner_block_by_canonical)
            if not edge_block_id:
                continue

            desired_src = src_id
            if self._is_pure_data_node(src_id):
                src_canonical = self._resolve_canonical_original_id(src_id)
                desired_src = self._resolve_data_instance_id_for_block(src_canonical, edge_block_id, owner_block_by_canonical)

            desired_dst = dst_id
            if self._is_pure_data_node(dst_id):
                dst_canonical = self._resolve_canonical_original_id(dst_id)
                desired_dst = self._resolve_data_instance_id_for_block(dst_canonical, edge_block_id, owner_block_by_canonical)

            if desired_src != src_id or desired_dst != dst_id:
                edge_mutations.append(
                    EdgeMutation(
                        edge_id=str(edge.id),
                        new_src_node=str(desired_src),
                        new_dst_node=str(desired_dst),
                    )
                )

        # 为每个副本补齐输入边：使用 canonical 入边模板，按块解析 src 实例
        new_edges: List[NewEdgeSpec] = []
        for spec in sorted(copy_nodes, key=lambda item: (item.canonical_original_id, item.block_id, item.copy_node_id)):
            templates = self._incoming_edge_templates_by_canonical_dst.get(spec.canonical_original_id, set())
            for template_src, src_port, dst_port, src_is_pure in sorted(templates):
                resolved_src = template_src
                if src_is_pure:
                    resolved_src = self._resolve_data_instance_id_for_block(
                        template_src,
                        spec.block_id,
                        owner_block_by_canonical,
                    )
                edge_id = self._make_deterministic_edge_id(
                    resolved_src,
                    src_port,
                    spec.copy_node_id,
                    dst_port,
                )
                new_edges.append(
                    NewEdgeSpec(
                        edge_id=edge_id,
                        src_node=resolved_src,
                        src_port=src_port,
                        dst_node=spec.copy_node_id,
                        dst_port=dst_port,
                    )
                )

        planned = GlobalCopyApplicationPlan(
            copy_nodes=tuple(copy_nodes),
            edge_mutations=tuple(sorted(edge_mutations, key=lambda item: item.edge_id)),
            new_edges=tuple(sorted(new_edges, key=lambda item: item.edge_id)),
        )
        self._application_plan = planned
        return planned

    def apply_application_plan(self, plan: GlobalCopyApplicationPlan) -> None:
        """执行纯计划：创建缺失副本、原地重定向边、补齐输入边，并去重。"""
        self._ensure_copy_nodes(plan.copy_nodes)
        self._apply_edge_mutations(plan.edge_mutations)
        self._ensure_new_edges(plan.new_edges)
        self._dedupe_edges_after_application()

    def _ensure_copy_nodes(self, copy_nodes: Iterable[CopyNodeSpec]) -> None:
        """确保副本节点存在（优先复用已有副本）。"""
        for spec in copy_nodes:
            key = (spec.canonical_original_id, spec.block_id)
            existing = self._existing_copy_by_original_and_block.get(key)
            if existing and existing in self.model.nodes:
                self.created_copies[key] = existing
                continue
            if spec.copy_node_id in self.model.nodes:
                self.created_copies[key] = spec.copy_node_id
                continue
            source_node = self.model.nodes.get(spec.canonical_original_id)
            if source_node is None:
                continue
            created = create_data_node_copy(
                original_node=source_node,
                model=self.model,
                block_id=spec.block_id,
                copy_counter=max(spec.copy_counter, 1),
            )
            self.created_copies[key] = created.id

    def _apply_edge_mutations(self, edge_mutations: Iterable[EdgeMutation]) -> None:
        """原地重定向既有数据边（保持 edge.id 不变）。"""
        for mutation in edge_mutations:
            edge = self.model.edges.get(mutation.edge_id)
            if edge is None:
                continue
            edge.src_node = mutation.new_src_node
            edge.dst_node = mutation.new_dst_node

    def _ensure_new_edges(self, new_edges: Iterable[NewEdgeSpec]) -> None:
        """新增副本输入边（若同构边已存在则跳过）。"""
        existing_keys: Set[Tuple[str, str, str, str]] = set()
        for edge in self.model.edges.values():
            existing_keys.add((edge.src_node, edge.src_port, edge.dst_node, edge.dst_port))

        for spec in new_edges:
            key = (spec.src_node, spec.src_port, spec.dst_node, spec.dst_port)
            if key in existing_keys:
                continue
            if spec.edge_id in self.model.edges:
                # 若 ID 已存在但内容不同，仍然保持确定性：生成基于 key 的替代 ID
                fallback_id = self._make_deterministic_edge_id(
                    spec.src_node,
                    spec.src_port,
                    spec.dst_node,
                    spec.dst_port,
                )
                edge_id = fallback_id
            else:
                edge_id = spec.edge_id
            self.model.edges[edge_id] = EdgeModel(
                id=edge_id,
                src_node=spec.src_node,
                src_port=spec.src_port,
                dst_node=spec.dst_node,
                dst_port=spec.dst_port,
            )
            existing_keys.add(key)

    def _dedupe_edges_after_application(self) -> None:
        """去重（防止既有边与新边形成重复）。"""
        from .node_copy_utils import _dedupe_edges  # type: ignore

        _dedupe_edges(self.model)

    def _resolve_edge_block_id(
        self,
        dst_node_id: str,
        owner_block_by_canonical: Dict[str, str],
    ) -> str:
        """确定一条数据边应归属的块：优先使用目标节点实例的块语义。"""
        if dst_node_id in self._flow_to_block:
            return self._flow_to_block[dst_node_id]
        dst_node = self.model.nodes.get(dst_node_id)
        if dst_node is None:
            return ""
        if is_data_node_copy(dst_node):
            block_id = resolve_copy_block_id(dst_node)
            if block_id:
                return str(block_id)
            return infer_copy_block_id_from_node_id(dst_node_id)
        if self._is_pure_data_node(dst_node_id):
            canonical = self._resolve_canonical_original_id(dst_node_id)
            return owner_block_by_canonical.get(canonical, "")
        return ""

    def _resolve_data_instance_id_for_block(
        self,
        canonical_original_id: str,
        block_id: str,
        owner_block_by_canonical: Dict[str, str],
    ) -> str:
        """解析“某 canonical 数据节点在某块内应使用哪个实例 ID”。"""
        if not canonical_original_id or not block_id:
            return canonical_original_id
        owner_block = owner_block_by_canonical.get(canonical_original_id, "")
        if not owner_block or owner_block == block_id:
            return canonical_original_id
        plan = self.copy_plans.get(canonical_original_id)
        if plan is None:
            # 该节点未被识别为共享节点，不应在非 owner 块引用；保持原值让后续校验发现问题
            return canonical_original_id
        copy_id = plan.copy_targets.get(block_id)
        if not copy_id:
            # 计划缺失时保持原值，避免抛异常污染布局；调用方可通过断言检查发现
            return canonical_original_id
        return copy_id

    @staticmethod
    def _parse_copy_counter(node_id: str) -> int:
        parsed = parse_copy_counter(node_id)
        return int(parsed) if parsed < ORDER_MAX_FALLBACK else 1

    @staticmethod
    def _make_deterministic_edge_id(src_node: str, src_port: str, dst_node: str, dst_port: str) -> str:
        """基于边语义生成确定性的 edge id。"""
        payload = f"{src_node}|{src_port}|{dst_node}|{dst_port}".encode("utf-8")
        digest = hashlib.sha1(payload).hexdigest()[:12]
        return f"edge_copy_{digest}"
    
    def get_block_copy_mapping(self, block_id: str) -> Dict[str, str]:
        """获取指定块的副本映射：原始ID -> 副本ID"""
        mapping: Dict[str, str] = {}
        for (original_id, bid), copy_id in self.created_copies.items():
            if bid == block_id:
                mapping[original_id] = copy_id
        return mapping
    
    def get_block_owned_nodes(self, block_id: str) -> Set[str]:
        """获取指定块"拥有"的数据节点（原始节点，非副本）"""
        owned: Set[str] = set()
        for original_id, plan in self.copy_plans.items():
            if plan.owner_block_id == block_id:
                owned.add(original_id)
        
        # 加上只被这个块使用的节点
        dependency = self.block_dependencies.get(block_id)
        if dependency:
            for data_id in dependency.full_data_closure:
                if data_id not in self.copy_plans:
                    owned.add(data_id)
        
        return owned
    
    def get_block_data_nodes(self, block_id: str) -> Set[str]:
        """获取指定块应该放置的所有数据节点ID
        
        包括：拥有的原始节点 + 该块的副本节点
        """
        result: Set[str] = set()
        
        # 该块拥有的原始节点
        result.update(self.get_block_owned_nodes(block_id))
        
        # 该块的副本节点
        for (original_id, bid), copy_id in self.created_copies.items():
            if bid == block_id:
                result.add(copy_id)
        
        return result
