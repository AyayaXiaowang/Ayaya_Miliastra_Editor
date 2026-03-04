from __future__ import annotations

import hashlib
from typing import Dict, Iterable, List, Set, Tuple

from engine.graph.models import EdgeModel

from .copy_identity_utils import (
    ORDER_MAX_FALLBACK,
    infer_copy_block_id_from_node_id,
    is_data_node_copy,
    parse_copy_counter,
    resolve_copy_block_id,
)
from .graph_query_utils import is_data_edge
from .node_copy_utils import create_data_node_copy
from .global_copy_manager_types import (
    CopyNodeSpec,
    EdgeMutation,
    GlobalCopyApplicationPlan,
    NewEdgeSpec,
)


class _GlobalCopyManagerPlanMixin:
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

