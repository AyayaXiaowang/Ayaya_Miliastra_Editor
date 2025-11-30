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

        current_item = self.widget.tree.currentItem()
        if current_item is None:
            self.widget.tree.setCurrentItem(items[-1])
            return

        # 定位当前并循环到上一个
        current_index = items.index(current_item) if current_item in items else 0
        prev_index = (current_index - 1) % len(items)
        self.widget.tree.setCurrentItem(items[prev_index])

    def navigate_to_next_task(self) -> None:
        items = self._get_all_items_in_order()
        if not items:
            return

        current_item = self.widget.tree.currentItem()
        if current_item is None:
            self.widget.tree.setCurrentItem(items[0])
            return

        # 定位当前并循环到下一个
        current_index = items.index(current_item) if current_item in items else -1
        next_index = (current_index + 1) % len(items)
        self.widget.tree.setCurrentItem(items[next_index])

    # === Ctrl+P 路由 ===
    def _get_active_monitor(self):
        if self.widget._monitor_window and hasattr(self.widget._monitor_window, "request_pause"):
            return self.widget._monitor_window
        if self.widget.main_window and hasattr(self.widget.main_window, "execution_monitor_panel"):
            panel = self.widget.main_window.execution_monitor_panel
            if hasattr(panel, "request_pause"):
                return panel
        return None

    def on_global_ctrl_p(self) -> None:
        monitor = self._get_active_monitor()
        if monitor and getattr(monitor, "is_running", False) and not getattr(monitor, "is_paused", True):
            monitor.request_pause()


