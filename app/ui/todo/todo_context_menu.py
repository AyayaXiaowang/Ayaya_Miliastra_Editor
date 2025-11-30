from __future__ import annotations

from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import Qt

from ui.foundation.context_menu_builder import ContextMenuBuilder
from ui.todo.todo_config import StepTypeRules


class TodoContextMenu:
    """右键菜单与动作。

    仅负责创建菜单并触发执行桥的入口。
    """

    def __init__(self, parent_widget: QtWidgets.QWidget, tree_widget: QtWidgets.QTreeWidget, tree_manager):
        self.parent_widget = parent_widget
        self.tree = tree_widget
        # 统一依赖 TodoTreeManager 的 todo_map 作为权威数据源，避免在宿主侧维护副本。
        self.tree_manager = tree_manager

    def show_menu(self, pos: QtCore.QPoint, executor_bridge) -> None:
        item = self.tree.itemAt(pos)
        if item is None:
            return
        todo_id = item.data(0, Qt.ItemDataRole.UserRole)
        todo_map = getattr(self.tree_manager, "todo_map", {}) if self.tree_manager is not None else {}
        todo = todo_map.get(todo_id)
        if not todo:
            return
        step_type = todo.detail_info.get("type")
        if not StepTypeRules.supports_context_menu_execution(step_type):
            return

        builder = ContextMenuBuilder(self.parent_widget)
        builder.add_action("仅执行此步骤（从此步到末尾）", lambda: executor_bridge.execute_from_this_step(todo))
        builder.add_action("仅执行此步骤（一步）", lambda: executor_bridge.execute_single_step(todo))
        builder.exec_for(self.tree, pos)


