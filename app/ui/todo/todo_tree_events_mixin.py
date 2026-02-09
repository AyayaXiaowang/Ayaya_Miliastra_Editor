from __future__ import annotations

from PyQt6 import QtCore, QtWidgets, sip
from PyQt6.QtCore import Qt

from app.models.todo_detail_info_accessors import get_detail_type
from app.ui.todo.todo_config import StepTypeRules


class TodoTreeEventsMixin:
    """TodoTreeManager 的 Qt 槽与 tooltip 延迟计算 mixin。"""

    def _on_item_changed(self, item: QtWidgets.QTreeWidgetItem, column: int) -> None:
        if self._refresh_gate.is_refreshing:
            return
        if item is None or column != 0:
            return
        todo_id = item.data(0, Qt.ItemDataRole.UserRole)
        todo = self.todo_map.get(todo_id)
        if not todo:
            return

        detail_type = get_detail_type(todo)
        is_leaf_like = (not todo.children) and not StepTypeRules.is_graph_root(detail_type)
        if not is_leaf_like:
            # 父节点（模板图根/事件流根/有 children 的 todo）仅作为进度汇总节点，
            # 其三态与文本由内部逻辑驱动，这里忽略 itemChanged 以避免递归调用。
            return

        current_state = item.checkState(0)
        is_checked = current_state == Qt.CheckState.Checked
        # 重要：QTreeWidget 的 itemChanged 不仅会在勾选变化时触发，
        # 诸如 tooltip/tokens/置灰标记等 data 更新也会触发。
        # 为了保证“完成度写入入口单一”，这里统一委托给 TodoTreeManager.set_leaf_checked：
        # - 它内部会对比 todo_states 判定是否真的变化；
        # - 负责清理运行态、增量刷新与父级三态反推；
        # - 在变化时发出 todo_checked（用于落盘）。
        _ = self.set_leaf_checked(str(todo_id or ""), bool(is_checked))

    def _on_tree_item_expanded(self, item: QtWidgets.QTreeWidgetItem) -> None:
        if item is None:
            return
        todo_id = item.data(0, Qt.ItemDataRole.UserRole)
        todo = self.todo_map.get(todo_id)
        if not todo:
            return
        detail_type = (todo.detail_info or {}).get("type", "")
        if StepTypeRules.is_template_graph_root(detail_type) and not todo.children:
            self.expand_graph_on_demand(todo)
            return
        if StepTypeRules.is_event_flow_root(detail_type):
            # 事件流根的子步骤 UI 懒加载：仅在展开时创建树项
            self._expand_event_flow_children_on_demand(todo, item=item)
            return

        if StepTypeRules.should_have_virtual_detail_children(detail_type):
            has_virtual_children = False
            for child_index in range(item.childCount()):
                child = item.child(child_index)
                marker = child.data(0, Qt.ItemDataRole.UserRole + 1)
                if marker == "virtual_detail_child":
                    has_virtual_children = True
                    break
            if not has_virtual_children:
                self._graph_support.rebuild_virtual_detail_children(item, todo, self.todo_map)

    def _on_runtime_status_changed(self, todo_id: str) -> None:
        item = self._item_map.get(todo_id)
        todo = self.todo_map.get(todo_id)
        if item and todo:
            self.update_item_incrementally(item, todo)

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:  # noqa: N802
        """延迟 tooltip 计算：仅在 Qt 请求显示 tooltip 时才构建内容。"""
        if sip.isdeleted(self.tree):
            return False
        if self._viewport is None or sip.isdeleted(self._viewport):
            return False
        if watched is self._viewport and event.type() == QtCore.QEvent.Type.ToolTip:
            help_event = event  # QHelpEvent
            if help_event is None:
                return False
            position = help_event.pos() if hasattr(help_event, "pos") else None
            if position is None:
                return False
            item = self.tree.itemAt(position)
            if item is None:
                return False
            if sip.isdeleted(item):
                return False
            todo_id = item.data(0, Qt.ItemDataRole.UserRole)
            if not todo_id:
                return False
            todo = self.todo_map.get(todo_id)
            if todo is None:
                return False
            detail_type = (todo.detail_info or {}).get("type", "")
            if not StepTypeRules.is_graph_step(detail_type):
                return False
            tooltip_text = self._source_tooltip_provider.get_tooltip_for_todo(todo)
            item.setToolTip(0, tooltip_text)
            return False
        return super().eventFilter(watched, event)



