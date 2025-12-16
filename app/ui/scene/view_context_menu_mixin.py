"""视图右键菜单桥接 Mixin

将 `GraphView.contextMenuEvent` 的“决策逻辑”从 `GraphScene` 主文件中剥离，
使 `GraphScene` 保持薄层入口：仅装配 mixin 与少量核心状态。

该 Mixin 约定宿主场景提供：
- model / undo_manager
-（可选）signal/struct 相关上下文：由 `ui.graph.signal_node_service` 与 `ui.graph.struct_node_service`
  通过 duck-typing 访问 scene.model / scene.signal_edit_context / scene.views() 等。
"""

from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets
from typing import Optional

from app.ui.foundation.context_menu_builder import ContextMenuBuilder
from app.ui.graph.signal_node_service import contribute_context_menu_for_node as contribute_signal_node_menu
from app.ui.graph.struct_node_service import contribute_context_menu_for_node as contribute_struct_node_menu


class SceneViewContextMenuMixin:
    """提供 GraphView 右键菜单的场景侧处理入口。"""

    # === 视图上下文菜单桥接（由 GraphView 委托调用） ===
    def handle_view_context_menu(
        self,
        view: QtWidgets.QGraphicsView,
        event: QtGui.QContextMenuEvent,
        scene_pos: QtCore.QPointF,
        item: Optional[QtWidgets.QGraphicsItem],
    ) -> bool:
        """处理由 GraphView 转发的右键菜单请求。

        返回:
            bool: 若已处理并接受事件, 返回 True; 否则返回 False 交由默认逻辑处理。
        """
        # 运行时导入避免循环依赖：GraphView -> GraphScene -> Scene*Mixin -> GraphView
        from app.ui.graph.items.port_item import PortGraphicsItem
        from app.ui.graph.items.node_item import NodeGraphicsItem
        from app.ui.graph.items.edge_item import EdgeGraphicsItem
        from app.ui.graph.graph_undo import DeleteEdgeCommand

        # 在端口上右键：保留原有端口自身的菜单行为（由 Qt 标准分发负责）
        if isinstance(item, PortGraphicsItem):
            return False

        # 在节点上右键：允许由“领域服务”注入节点级菜单（例如信号/结构体节点）
        node_item: Optional[NodeGraphicsItem] = None
        if isinstance(item, NodeGraphicsItem):
            node_item = item
        elif item is not None and isinstance(item.parentItem(), NodeGraphicsItem):
            parent_node_item = item.parentItem()
            if isinstance(parent_node_item, NodeGraphicsItem):
                node_item = parent_node_item

        if node_item is not None:
            node_title = getattr(node_item.node, "title", "") or ""
            node_id = getattr(node_item.node, "id", "") or ""
            if node_id:
                menu_builder = ContextMenuBuilder(view)
                has_action = False
                # 信号节点菜单
                has_action = contribute_signal_node_menu(
                    self,  # type: ignore[arg-type]
                    menu_builder,
                    node_id=str(node_id),
                    node_title=str(node_title),
                    add_separator_before=has_action,
                ) or has_action
                # 结构体节点菜单
                has_action = contribute_struct_node_menu(
                    self,  # type: ignore[arg-type]
                    menu_builder,
                    node_id=str(node_id),
                    node_title=str(node_title),
                    add_separator_before=has_action,
                ) or has_action

                if has_action:
                    menu_builder.exec_global(event.globalPos())
                    event.accept()
                    return True

        # 在连线上右键：显示“删除连线”菜单（统一构建与样式）
        if isinstance(item, EdgeGraphicsItem):
            edge_id = item.edge_id

            def _delete_edge() -> None:
                command = DeleteEdgeCommand(self.model, self, edge_id)  # type: ignore[attr-defined]
                self.undo_manager.execute_command(command)  # type: ignore[attr-defined]

            ContextMenuBuilder(view).add_action("删除连线", _delete_edge).exec_global(event.globalPos())
            event.accept()
            return True

        # 在空白处右键：显示“添加节点”菜单（仍复用 GraphView 提供的桥接方法）
        if item is None and hasattr(view, "_show_add_node_menu"):
            view._show_add_node_menu(event.globalPos(), scene_pos)
            event.accept()
            return True

        # 其它情况：不处理, 交由默认逻辑(例如图元自身的 contextMenuEvent)
        return False


