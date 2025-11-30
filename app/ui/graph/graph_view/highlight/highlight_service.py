"""高亮服务

负责节点、连线、端口的高亮显示与灰显操作。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ui.graph.graph_view import GraphView


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
        if edge_id and edge_id in getattr(scene, 'edge_items', {}):
            edge_item = scene.edge_items.get(edge_id)
            if edge_item:
                edge_item.setSelected(True)
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
        
        # 设置焦点节点和连线为正常透明度，其他为半透明
        for node_id, node_item in view.scene().node_items.items():
            if node_id in focused_node_ids:
                node_item.setOpacity(1.0)
            else:
                node_item.setOpacity(0.3)
        
        for edge_id, edge_item in view.scene().edge_items.items():
            if edge_id in focused_edge_ids:
                edge_item.setOpacity(1.0)
            else:
                edge_item.setOpacity(0.3)
    
    @staticmethod
    def restore_all_opacity(view: "GraphView") -> None:
        """恢复所有元素的透明度"""
        if not view.scene():
            return
        
        for node_item in view.scene().node_items.values():
            node_item.setOpacity(1.0)
        
        for edge_item in view.scene().edge_items.values():
            edge_item.setOpacity(1.0)

