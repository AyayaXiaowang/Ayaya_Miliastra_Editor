from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple, TYPE_CHECKING

from engine.graph.models import EdgeModel

from .copy_identity_utils import (
    is_data_node_copy,
    resolve_canonical_original_id,
    resolve_copy_block_id,
)
from .graph_query_utils import build_edge_indices, is_data_edge, is_pure_data_node

if TYPE_CHECKING:
    from engine.graph.models import GraphModel, NodeModel
    from ..internal.layout_context import LayoutContext


class _GlobalCopyManagerIndicesMixin:
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
        downstream_by_src: Dict[str, Set[str]] = {}
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
            downstream_by_src.setdefault(src_canonical, set()).add(dst_canonical)

        self._logical_upstream_by_data_dst = upstream_by_dst
        self._logical_downstream_by_data_src = downstream_by_src
        self._incoming_edge_templates_by_canonical_dst = templates_by_dst

    def _is_pure_data_node(self, node_id: str) -> bool:
        if self.layout_context is not None:
            return self.layout_context.is_pure_data_node(node_id)
        return is_pure_data_node(node_id, self.model)

    def _resolve_canonical_original_id(self, node_id: str) -> str:
        """将任意数据节点（含副本）归一到其 canonical original id。"""
        return resolve_canonical_original_id(node_id, model=self.model)

