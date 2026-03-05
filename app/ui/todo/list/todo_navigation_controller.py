from __future__ import annotations

"""
Todo 导航与全局热键控制器

职责：
- 提供上/下一个任务的导航行为
- 处理 Ctrl+P 全局暂停请求的路由

说明：
- 持有对 `TodoListWidget` 的引用，操作其 `tree` 与内部状态，但不直接修改样式或布局。
"""

from typing import List, Optional, Any

from PyQt6 import QtWidgets
from PyQt6.QtCore import Qt


class TodoNavigationController:
    def __init__(self, widget: Any) -> None:
        self.widget = widget

    # === 列表收集 ===
    def _get_all_items_in_order(self) -> List[QtWidgets.QTreeWidgetItem]:
        """获取树中所有任务项（按显示顺序，含父与叶）。"""
        items: List[QtWidgets.QTreeWidgetItem] = []

        def collect_items(parent_item: Optional[QtWidgets.QTreeWidgetItem]) -> None:
            if parent_item is None:
                for i in range(self.widget.tree.topLevelItemCount()):
                    item = self.widget.tree.topLevelItem(i)
                    if item:
                        items.append(item)
                        if item.isExpanded():
                            collect_items(item)
            else:
                for i in range(parent_item.childCount()):
                    child = parent_item.child(i)
                    if child:
                        items.append(child)
                        if child.isExpanded():
                            collect_items(child)

        collect_items(None)
        # 仅在导航中保留真正对应 TodoItem 的树项（存在有效 todo_id）
        filtered_items: List[QtWidgets.QTreeWidgetItem] = []
        for tree_item in items:
            todo_id = tree_item.data(0, Qt.ItemDataRole.UserRole)
            if todo_id:
                filtered_items.append(tree_item)
        return filtered_items

    # === 导航行为 ===
    def navigate_to_prev_task(self) -> None:
        items = self._get_all_items_in_order()
        if not items:
            return

        tree_manager = getattr(self.widget, "tree_manager", None)
        current_item = self.widget.tree.currentItem()
        if current_item is None:
            target_id = items[-1].data(0, Qt.ItemDataRole.UserRole)
            if tree_manager is not None and target_id:
                tree_manager.select_task_by_id(str(target_id))
            return

        # 定位当前并循环到上一个
        current_index = items.index(current_item) if current_item in items else 0
        prev_index = (current_index - 1) % len(items)
        target_id = items[prev_index].data(0, Qt.ItemDataRole.UserRole)
        if tree_manager is not None and target_id:
            tree_manager.select_task_by_id(str(target_id))

    def navigate_to_next_task(self) -> None:
        items = self._get_all_items_in_order()
        if not items:
            return

        tree_manager = getattr(self.widget, "tree_manager", None)
        current_item = self.widget.tree.currentItem()
        if current_item is None:
            target_id = items[0].data(0, Qt.ItemDataRole.UserRole)
            if tree_manager is not None and target_id:
                tree_manager.select_task_by_id(str(target_id))
            return

        # 定位当前并循环到下一个
        current_index = items.index(current_item) if current_item in items else -1
        next_index = (current_index + 1) % len(items)
        target_id = items[next_index].data(0, Qt.ItemDataRole.UserRole)
        if tree_manager is not None and target_id:
            tree_manager.select_task_by_id(str(target_id))

    # === Ctrl+P 路由 ===
    def _get_active_monitor(self):
        if self.widget._monitor_window is not None:
            return self.widget._monitor_window
        return self.widget.ui_context.try_get_execution_monitor()

    def on_global_ctrl_p(self) -> None:
        monitor = self._get_active_monitor()
        if monitor is None:
            return
        if monitor.is_running and not monitor.is_paused:
            monitor.request_pause()


