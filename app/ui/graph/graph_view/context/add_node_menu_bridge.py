"""添加节点菜单桥接

负责创建并显示添加节点的右键菜单。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6 import QtCore

if TYPE_CHECKING:
    from ui.graph.graph_view import GraphView


class AddNodeMenuBridge:
    """添加节点菜单桥接
    
    封装右键空白处添加节点菜单的显示逻辑。
    """
    
    @staticmethod
    def show_add_node_popup(
        view: "GraphView",
        global_pos: QtCore.QPoint,
        scene_pos: QtCore.QPointF,
        filter_port_type: str = None,
        is_output: bool = True
    ) -> None:
        """显示添加节点的右键菜单
        
        Args:
            view: 图视图
            global_pos: 全局坐标
            scene_pos: 场景坐标
            filter_port_type: 过滤端口类型（如果从端口拖拽创建）
            is_output: 起始端口是否是输出
        """
        if not view.node_library or not view.on_add_node_callback:
            return
        
        # 关闭之前的菜单（如果存在）
        if hasattr(view, '_add_node_popup') and view._add_node_popup:
            view._add_node_popup.close()
        
        from ui.graph.graph_view.popups.add_node_popup import AddNodePopup
        
        # 创建非模态浮动菜单，传入auto_connect_callback用于自动连接
        def on_node_added(node_def, pos):
            # 先创建节点，并获取新节点ID
            # 记录创建前的节点数量
            scene = view.scene()
            if scene:
                old_node_ids = set(scene.model.nodes.keys())
            
            # 创建节点
            view.on_add_node_callback(node_def, pos)
            
            # 如果场景有待连接的端口，自动连接
            if scene and hasattr(scene, 'auto_connect_new_node'):
                # 找到新添加的节点ID
                new_node_ids = set(scene.model.nodes.keys()) - old_node_ids
                if new_node_ids:
                    new_node_id = list(new_node_ids)[0]
                    scene.auto_connect_new_node(new_node_id)
                else:
                    scene.auto_connect_new_node()
        
        view._add_node_popup = AddNodePopup(
            view.node_library,
            scene_pos,
            on_node_added,
            view,
            filter_port_type,
            is_output,
            view.current_scope
        )
        view._add_node_popup.move(global_pos)
        view._add_node_popup.show()

