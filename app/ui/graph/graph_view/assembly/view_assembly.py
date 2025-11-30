"""视图装配器

负责 setScene 与 resizeEvent 期间的视图组件初始化与联动。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6 import QtGui

if TYPE_CHECKING:
    from ui.graph.graph_view import GraphView


class ViewAssembly:
    """视图装配器
    
    负责场景设置、窗口调整时的组件初始化与联动。
    """
    
    @staticmethod
    def attach_scene(view: "GraphView", scene) -> None:
        """重写setScene以创建小地图和overlay管理器"""
        # 设置一个非常大的场景矩形，允许用户拖动到节点图内容之外
        # 这样可以将边缘的节点居中显示
        if scene:
            # 使用一个足够大的场景矩形，以节点图内容为中心扩展
            items_rect = scene.itemsBoundingRect()
            if not items_rect.isEmpty():
                # 在内容周围添加大量空白区域（10倍的扩展）
                expansion = max(items_rect.width(), items_rect.height()) * 10
                expanded_rect = items_rect.adjusted(-expansion, -expansion, expansion, expansion)
                scene.setSceneRect(expanded_rect)
            else:
                # 如果没有内容，设置一个默认的大场景
                scene.setSceneRect(-10000, -10000, 20000, 20000)
            
            # 初始化overlay管理器
            from ui.overlays.node_detail_overlay import NodeDetailOverlayManager
            if not view.overlay_manager:
                view.overlay_manager = NodeDetailOverlayManager(view)
        
        # 创建小地图
        if view.show_mini_map and scene:
            if view.mini_map:
                view.mini_map.setParent(None)
                view.mini_map.deleteLater()
            
            from ui.graph.graph_view.overlays.minimap_widget import MiniMapWidget
            view.mini_map = MiniMapWidget(view, scene)
            view.mini_map.show()
            # 确保小地图位于顶层并正确定位
            view.mini_map.raise_()
            ViewAssembly.update_mini_map_position(view)
    
    @staticmethod
    def on_resize(view: "GraphView", event: QtGui.QResizeEvent) -> None:
        """窗口大小改变时更新小地图、overlay和自动排版按钮位置"""
        ViewAssembly.update_mini_map_position(view)
        if view.mini_map:
            view.mini_map.update_viewport_rect()
            view.mini_map.raise_()
        if view.overlay_manager:
            view.overlay_manager.update_on_resize()
        from ui.graph.graph_view.top_right.controls_manager import TopRightControlsManager
        TopRightControlsManager.update_position(view)
        scene = view.scene()
        if scene and hasattr(scene, "_reposition_ydebug_tooltip"):
            scene._reposition_ydebug_tooltip()
    
    @staticmethod
    def update_mini_map_position(view: "GraphView") -> None:
        """更新小地图位置到右下角"""
        if not view.mini_map:
            return
        
        viewport_rect = view.viewport().rect()
        mini_map_width = 200
        mini_map_height = 150
        margin = 20
        
        x = viewport_rect.width() - mini_map_width - margin
        y = viewport_rect.height() - mini_map_height - margin
        
        view.mini_map.setGeometry(x, y, mini_map_width, mini_map_height)

