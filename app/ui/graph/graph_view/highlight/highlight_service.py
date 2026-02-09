"""高亮服务

负责节点、连线、端口的高亮显示与灰显操作。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.ui.graph.graph_view import GraphView


class HighlightService:
    """高亮服务
    
    提供节点、连线、端口的高亮与灰显操作。
    """
    
    @staticmethod
    def highlight_node(view: "GraphView", node_id: str) -> None:
        """高亮显示指定节点"""
        if not view.scene():
            return
        view.scene().highlight_node(node_id)
    
    @staticmethod
    def highlight_edge(view: "GraphView", edge_id: str, is_flow_edge: bool = None) -> None:
        """高亮显示指定连线
        
        Args:
            view: 图视图
            edge_id: 边的ID
            is_flow_edge: 是否是流程边（可选，用于兼容性，实际从边自身属性获取）
        """
        if not view.scene():
            return
        view.scene().highlight_edge(edge_id)
    
    @staticmethod
    def highlight_nodes_and_edge(
        view: "GraphView",
        first_node_id: str,
        second_node_id: str,
        edge_id: Optional[str] = None,
        src_port: Optional[str] = None,
        dst_port: Optional[str] = None
    ) -> None:
        """一次性高亮两个节点以及可选的连线和端口。
        
        说明：避免逐个高亮导致的 clear_highlights() 相互覆盖问题。
        """
        if not view.scene():
            return
        scene = view.scene()
        # 统一清除，再批量设置
        scene.clear_highlights()
        # 高亮两个节点
        first_item = scene.get_node_item(first_node_id)
        if first_item:
            first_item.setSelected(True)
        second_item = scene.get_node_item(second_node_id)
        if second_item:
            second_item.setSelected(True)
        # 高亮连线（如提供）
        if edge_id:
            edge_item = (getattr(scene, "edge_items", {}) or {}).get(edge_id)
            if edge_item is not None:
                edge_item.setSelected(True)
            else:
                # 批量渲染边（fast_preview_mode）：无 per-edge item 时，走场景层的批量边选中状态
                has_batched = getattr(scene, "has_batched_fast_preview_edges", None)
                set_batched_selected = getattr(scene, "set_batched_selected_edge_ids", None)
                if callable(has_batched) and has_batched() and callable(set_batched_selected):
                    set_batched_selected({str(edge_id)})
        # 高亮端口：优先使用传入端口名；若缺失则从边数据推断
        resolved_src_port = src_port
        resolved_dst_port = dst_port
        if (not resolved_src_port or not resolved_dst_port) and edge_id and hasattr(scene, 'model'):
            edge_model = scene.model.edges.get(edge_id)
            if edge_model:
                resolved_src_port = resolved_src_port or edge_model.src_port
                resolved_dst_port = resolved_dst_port or edge_model.dst_port
        if resolved_src_port:
            scene.highlight_port(first_node_id, resolved_src_port, is_input=False)
        if resolved_dst_port:
            scene.highlight_port(second_node_id, resolved_dst_port, is_input=True)
    
    @staticmethod
    def clear_highlights(view: "GraphView") -> None:
        """清除所有高亮"""
        if not view.scene():
            return
        view.scene().clear_highlights()
    
    @staticmethod
    def highlight_port(view: "GraphView", node_id: str, port_name: str, is_input: bool) -> None:
        """高亮显示指定端口
        
        Args:
            view: 图视图
            node_id: 节点ID
            port_name: 端口名称
            is_input: 是否是输入端口
        """
        if not view.scene():
            return
        view.scene().highlight_port(node_id, port_name, is_input)
    
    @staticmethod
    def dim_unrelated_items(view: "GraphView", focused_node_ids: list, focused_edge_ids: list) -> None:
        """将非焦点元素变灰（降低透明度）
        
        Args:
            view: 图视图
            focused_node_ids: 焦点节点ID列表
            focused_edge_ids: 焦点连线ID列表
        """
        if not view.scene():
            return

        scene = view.scene()
        node_items = getattr(scene, "node_items", {}) or {}
        edge_items = getattr(scene, "edge_items", {}) or {}
        has_batched = bool(
            callable(getattr(scene, "has_batched_fast_preview_edges", None))
            and scene.has_batched_fast_preview_edges()  # type: ignore[attr-defined]
        )

        focused_node_set = {
            str(node_identifier)
            for node_identifier in (focused_node_ids or [])
            if node_identifier is not None and str(node_identifier)
        }
        focused_edge_set = {
            str(edge_identifier)
            for edge_identifier in (focused_edge_ids or [])
            if edge_identifier is not None and str(edge_identifier)
        }

        # 差量更新：避免每次调用都遍历全图导致交互卡顿
        old_active = bool(getattr(scene, "_opacity_dim_mode_active", False))
        old_node_count = int(getattr(scene, "_opacity_dim_node_count", -1))
        old_edge_count = int(getattr(scene, "_opacity_dim_edge_count", -1))
        old_materialized_edge_count = int(getattr(scene, "_opacity_dim_materialized_edge_count", -1))
        old_batched = bool(getattr(scene, "_opacity_dim_batched_edges_active", False))
        old_focused_nodes = set(getattr(scene, "_opacity_dim_focused_node_ids", set()) or set())
        old_focused_edges = set(getattr(scene, "_opacity_dim_focused_edge_ids", set()) or set())

        new_node_count = len(node_items)
        materialized_edge_count = len(edge_items)
        if has_batched and hasattr(scene, "model"):
            new_edge_count = len(getattr(scene.model, "edges", {}) or {})
        else:
            new_edge_count = materialized_edge_count

        if (
            old_active
            and old_batched == has_batched
            and old_node_count == new_node_count
            and old_edge_count == new_edge_count
            and old_materialized_edge_count == materialized_edge_count
            and old_focused_nodes == focused_node_set
            and old_focused_edges == focused_edge_set
        ):
            return

        need_full_update = (
            (not old_active) or old_node_count != new_node_count or old_batched != has_batched
        )

        if need_full_update:
            for node_id, node_item in node_items.items():
                node_item.setOpacity(1.0 if node_id in focused_node_set else 0.3)
        else:
            nodes_to_dim = old_focused_nodes - focused_node_set
            nodes_to_undim = focused_node_set - old_focused_nodes
            for node_id in nodes_to_dim:
                node_item = node_items.get(node_id)
                if node_item is not None:
                    node_item.setOpacity(0.3)
            for node_id in nodes_to_undim:
                node_item = node_items.get(node_id)
                if node_item is not None:
                    node_item.setOpacity(1.0)

        if has_batched:
            # 批量渲染边：批量层内部维护 dim 状态；edge_items 仅包含“局部 materialize”的少量边，逐个设 opacity 即可
            set_batched_dim = getattr(scene, "set_batched_dim_state", None)
            if callable(set_batched_dim):
                set_batched_dim(active=True, focused_edge_ids=focused_edge_set)
            for edge_id, edge_item in edge_items.items():
                edge_item.setOpacity(1.0 if edge_id in focused_edge_set else 0.3)
        else:
            if need_full_update or old_edge_count != new_edge_count:
                for edge_id, edge_item in edge_items.items():
                    edge_item.setOpacity(1.0 if edge_id in focused_edge_set else 0.3)
            else:
                edges_to_dim = old_focused_edges - focused_edge_set
                edges_to_undim = focused_edge_set - old_focused_edges
                for edge_id in edges_to_dim:
                    edge_item = edge_items.get(edge_id)
                    if edge_item is not None:
                        edge_item.setOpacity(0.3)
                for edge_id in edges_to_undim:
                    edge_item = edge_items.get(edge_id)
                    if edge_item is not None:
                        edge_item.setOpacity(1.0)

        scene._opacity_dim_mode_active = True
        scene._opacity_dim_focused_node_ids = set(focused_node_set)
        scene._opacity_dim_focused_edge_ids = set(focused_edge_set)
        scene._opacity_dim_node_count = new_node_count
        scene._opacity_dim_edge_count = new_edge_count
        scene._opacity_dim_materialized_edge_count = materialized_edge_count
        scene._opacity_dim_batched_edges_active = has_batched
    
    @staticmethod
    def restore_all_opacity(view: "GraphView") -> None:
        """恢复所有元素的透明度"""
        if not view.scene():
            return

        scene = view.scene()
        if not bool(getattr(scene, "_opacity_dim_mode_active", False)):
            return

        node_items = getattr(scene, "node_items", {}) or {}
        edge_items = getattr(scene, "edge_items", {}) or {}

        for node_item in node_items.values():
            node_item.setOpacity(1.0)

        for edge_item in edge_items.values():
            edge_item.setOpacity(1.0)

        clear_batched_dim = getattr(scene, "clear_batched_dim_state", None)
        if callable(clear_batched_dim):
            clear_batched_dim()

        scene._opacity_dim_mode_active = False
        scene._opacity_dim_focused_node_ids = set()
        scene._opacity_dim_focused_edge_ids = set()
        scene._opacity_dim_node_count = len(node_items)
        scene._opacity_dim_edge_count = len(edge_items)
        scene._opacity_dim_materialized_edge_count = len(edge_items)
        scene._opacity_dim_batched_edges_active = False

