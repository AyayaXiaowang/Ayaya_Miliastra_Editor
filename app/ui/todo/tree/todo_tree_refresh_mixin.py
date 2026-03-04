from __future__ import annotations

from typing import Any

from PyQt6 import QtWidgets, sip
from PyQt6.QtCore import Qt

from app.models import TodoItem
from app.models.todo_detail_info_accessors import get_detail_type
from app.ui.todo.misc.todo_config import StepTypeRules
from app.ui.todo.tree.tree_check_helpers import apply_leaf_state, apply_parent_progress


class TodoTreeRefreshMixin:
    """TodoTreeManager 的整树/增量刷新与富文本 tokens mixin。"""

    def refresh_tree(self) -> None:
        if sip.isdeleted(self.tree):
            return

        self._refresh_gate.set_refreshing(True)
        self.tree.setUpdatesEnabled(False)
        try:
            # 清理依赖于现有树项的 UI 状态，避免在整树重建后访问已删除的 QTreeWidgetItem。
            self._current_block_header_item = None
            self._current_node_highlight_ids.clear()
            self._current_node_anchor_todo_id = None
            self._node_filter_active = False
            self._event_flow_children_pending.clear()
            self._event_flow_children_built.clear()
            self._event_flow_build_inflight.clear()
            self._event_flow_build_callbacks.clear()
            self._event_flow_loading_items.clear()
            self._event_flow_item_waiters.clear()

            self.tree.clear()
            self._item_map.clear()

            root_todos = [t for t in self.todos if t.level == 0]
            for root_todo in root_todos:
                root_item = self._create_tree_item(root_todo)
                self.tree.addTopLevelItem(root_item)
                self._build_tree_recursive(root_todo, root_item)
                # 首次进入任务清单页：仅展开根目录，其它目录默认折叠。
                # 外部跳转/执行联动会通过 select_task_by_id / ensure_item_built 按需展开路径。
                root_item.setExpanded(True)
        finally:
            # 兜底：任何异常都不应让树永久停留在 updatesDisabled/refreshing 状态。
            if not sip.isdeleted(self.tree):
                self.tree.setUpdatesEnabled(True)
            self._refresh_gate.set_refreshing(False)

    def update_item_incrementally(self, item: QtWidgets.QTreeWidgetItem, todo: TodoItem) -> None:
        self._refresh_gate.set_refreshing(True)
        if not todo.children:
            apply_leaf_state(item, todo, self.todo_states, self._get_task_icon, self._apply_item_style)
        self._refresh_gate.set_refreshing(False)
        self._update_ancestor_states(item)

    def refresh_entire_tree_display(self) -> None:
        if sip.isdeleted(self.tree):
            return
        self._refresh_gate.set_refreshing(True)
        self.tree.setUpdatesEnabled(False)
        try:
            root = self.tree.invisibleRootItem()
            if root is not None:
                self._refresh_item_and_children(root)
        finally:
            if not sip.isdeleted(self.tree):
                self.tree.setUpdatesEnabled(True)
            self._refresh_gate.set_refreshing(False)

    def ensure_tokens_for_todo(self, todo_id: str) -> list | None:
        item = self._item_map.get(todo_id)
        todo = self.todo_map.get(todo_id)
        if item is None or todo is None:
            return None

        # 仅对“支持富文本 token 的叶子图步骤”刷新 tokens，避免清空父级步骤或逻辑块
        # 自行设置的富文本（例如父级进度标签、逻辑块标题标签）。
        detail_info = todo.detail_info or {}
        detail_type = get_detail_type(detail_info)
        is_leaf = not bool(todo.children)
        if is_leaf and StepTypeRules.supports_rich_tokens(detail_type):
            self._graph_support.update_item_rich_tokens(
                item=item,
                todo=todo,
                todo_map=self.todo_map,
                get_task_icon=self._get_task_icon,
            )
        tokens = item.data(0, self.RICH_SEGMENTS_ROLE)
        return tokens if isinstance(tokens, list) else None

    def _refresh_item_and_children(self, parent_item: QtWidgets.QTreeWidgetItem) -> None:
        for child_index in range(parent_item.childCount()):
            item = parent_item.child(child_index)
            if item is None:
                continue
            todo_id = item.data(0, Qt.ItemDataRole.UserRole)
            todo = self.todo_map.get(todo_id)
            if not todo:
                # 可能是块头分组或虚拟子项，继续向下递归刷新其子节点
                self._refresh_item_and_children(item)
                continue
            if todo.children:
                apply_parent_progress(item, todo, self.todo_states, self._get_task_icon)
                self._apply_parent_style(item, todo)
                self._refresh_item_and_children(item)
            else:
                apply_leaf_state(item, todo, self.todo_states, self._get_task_icon, self._apply_item_style)
            # 仅当该树项已经存在虚拟明细子项时才重建，避免对大树全量刷新触发重计算。
            detail_type = (todo.detail_info or {}).get("type", "")
            if StepTypeRules.should_have_virtual_detail_children(detail_type) and item.childCount() > 0:
                self._graph_support.rebuild_virtual_detail_children(item, todo, self.todo_map)



