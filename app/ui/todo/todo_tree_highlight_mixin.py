from __future__ import annotations

from typing import List, Optional

from PyQt6 import QtCore, QtGui, QtWidgets, sip
from PyQt6.QtCore import Qt

from app.models import TodoItem
from app.ui.foundation.theme_manager import Colors as ThemeColors


class TodoTreeHighlightMixin:
    """TodoTreeManager 的节点联动高亮/置灰与 BasicBlock 分组高亮 mixin。"""

    def is_node_filter_active(self) -> bool:
        return bool(self._node_filter_active)

    def get_current_node_highlight_ids(self) -> set[str]:
        return set(self._current_node_highlight_ids)

    def is_block_header_item(self, item: QtWidgets.QTreeWidgetItem) -> bool:
        if item is None:
            return False
        marker = item.data(0, self.MARKER_ROLE)
        return marker == "block_header"

    # === 节点相关步骤查询与高亮 ===

    def get_related_todos_for_node(self, node_id: str) -> List[TodoItem]:
        """返回与给定节点 ID 相关的所有 Todo（创建/配置/连线等）。"""
        return self._node_highlighter.collect_related_todos_for_node(
            node_id,
            todos=self.todos,
        )

    def highlight_steps_for_node(self, node_id: str, anchor_todo_id: Optional[str] = None) -> None:
        """根据节点 ID 高亮任务树中与该节点相关的步骤。

        - anchor_todo_id: 主步骤（通常为创建步骤），若提供则使用更醒目的样式。
        """
        if not node_id:
            self.clear_node_highlight()
            return

        related_todos = self.get_related_todos_for_node(node_id)
        new_highlight_ids = {todo.todo_id for todo in related_todos if todo.todo_id in self._item_map}
        if not new_highlight_ids:
            self.clear_node_highlight()
            return

        resolved_anchor_id: Optional[str] = None
        if anchor_todo_id and anchor_todo_id in new_highlight_ids:
            resolved_anchor_id = anchor_todo_id
        else:
            # 保持确定性：避免 set 的非稳定顺序导致锚点跳动
            resolved_anchor_id = sorted(new_highlight_ids)[0]

        old_highlight_ids = set(self._current_node_highlight_ids)
        old_anchor_id = self._current_node_anchor_todo_id
        had_filter_active = bool(self._node_filter_active)

        # 纯粹重复点击同一节点/同一锚点：直接短路，避免无意义的 repaint
        if had_filter_active and old_highlight_ids == new_highlight_ids and old_anchor_id == resolved_anchor_id:
            return

        if sip.isdeleted(self.tree):
            return

        self.tree.setUpdatesEnabled(False)
        try:
            if not had_filter_active:
                # 第一次进入“节点过滤”模式：需要为整棵树写入 dimmed 标记
                for todo_id, item in self._item_map.items():
                    if item is None or sip.isdeleted(item):
                        continue
                    self._set_item_dimmed(item, dimmed=(todo_id not in new_highlight_ids))

                for todo_id in new_highlight_ids:
                    item = self._item_map.get(todo_id)
                    if item is None or sip.isdeleted(item):
                        continue
                    self._node_highlighter.apply_node_highlight_to_item(
                        item,
                        is_anchor=(todo_id == resolved_anchor_id),
                    )
            else:
                # 差量更新：避免每次点击都全树清空/全树置灰
                ids_to_remove = old_highlight_ids - new_highlight_ids
                ids_to_add = new_highlight_ids - old_highlight_ids

                for todo_id in ids_to_remove:
                    item = self._item_map.get(todo_id)
                    if item is None or sip.isdeleted(item):
                        continue
                    self._node_highlighter.clear_node_highlight_from_item(item)
                    self._set_item_dimmed(item, dimmed=True)

                for todo_id in ids_to_add:
                    item = self._item_map.get(todo_id)
                    if item is None or sip.isdeleted(item):
                        continue
                    self._set_item_dimmed(item, dimmed=False)
                    self._node_highlighter.apply_node_highlight_to_item(
                        item,
                        is_anchor=(todo_id == resolved_anchor_id),
                    )

                # 锚点变化时，仅更新受影响的两项，避免重算整套高亮
                if resolved_anchor_id != old_anchor_id:
                    if old_anchor_id and old_anchor_id in new_highlight_ids:
                        old_anchor_item = self._item_map.get(old_anchor_id)
                        if old_anchor_item is not None and not sip.isdeleted(old_anchor_item):
                            self._node_highlighter.apply_node_highlight_to_item(
                                old_anchor_item,
                                is_anchor=False,
                            )
                    if resolved_anchor_id and resolved_anchor_id in new_highlight_ids:
                        new_anchor_item = self._item_map.get(resolved_anchor_id)
                        if new_anchor_item is not None and not sip.isdeleted(new_anchor_item):
                            self._node_highlighter.apply_node_highlight_to_item(
                                new_anchor_item,
                                is_anchor=True,
                            )
        finally:
            # 兜底：不吞异常，只保证更新开关不会被永久关闭，避免出现“怎么选都没反应”。
            if not sip.isdeleted(self.tree):
                self.tree.setUpdatesEnabled(True)

        self._current_node_highlight_ids = set(new_highlight_ids)
        self._current_node_anchor_todo_id = resolved_anchor_id
        self._node_filter_active = True

    def clear_node_highlight(self) -> None:
        """清除因“节点选中”产生的所有步骤高亮与置灰效果，恢复默认样式。"""
        if not self._current_node_highlight_ids and not self._node_filter_active:
            return

        if sip.isdeleted(self.tree):
            return

        self.tree.setUpdatesEnabled(False)
        try:
            # 清理高亮样式（仅作用于此前高亮的少量步骤）
            for todo_id in list(self._current_node_highlight_ids):
                item = self._item_map.get(todo_id)
                if item is None or sip.isdeleted(item):
                    continue
                self._node_highlighter.clear_node_highlight_from_item(item)

            # 退出过滤模式：清理所有 Todo 树项上的 dimmed 标记（仅写 role，不触碰前景色）
            if self._node_filter_active:
                for item in self._item_map.values():
                    if item is None or sip.isdeleted(item):
                        continue
                    if bool(item.data(0, self.DIMMED_ROLE)):
                        item.setData(0, self.DIMMED_ROLE, None)

            self._current_node_highlight_ids.clear()
            self._current_node_anchor_todo_id = None
            self._node_filter_active = False
        finally:
            if not sip.isdeleted(self.tree):
                self.tree.setUpdatesEnabled(True)

    def _set_item_dimmed(self, item: QtWidgets.QTreeWidgetItem, *, dimmed: bool) -> None:
        """写入/清理 dimmed_role（只做差量写入）。"""
        if item is None:
            return
        current_dimmed = bool(item.data(0, self.DIMMED_ROLE))
        if current_dimmed == bool(dimmed):
            return
        item.setData(0, self.DIMMED_ROLE, True if dimmed else None)

    # === 内部：块分组高亮 ===

    def highlight_block_for_item(self, tree_item: QtWidgets.QTreeWidgetItem) -> None:
        """根据当前选中的树节点，高亮其所属的块分组头。"""
        if tree_item is None:
            # 清空高亮
            if self._current_block_header_item is not None:
                self._set_block_header_highlight(self._current_block_header_item, False)
                self._current_block_header_item = None
            return

        block_header_item = self._find_block_header_for_item(tree_item)
        if block_header_item is self._current_block_header_item:
            return

        if self._current_block_header_item is not None:
            self._set_block_header_highlight(self._current_block_header_item, False)

        self._current_block_header_item = block_header_item
        if block_header_item is not None:
            self._set_block_header_highlight(block_header_item, True)

    def _find_block_header_for_item(
        self,
        start_item: Optional[QtWidgets.QTreeWidgetItem],
    ) -> Optional[QtWidgets.QTreeWidgetItem]:
        """沿父链向上查找最近的块分组头节点。"""
        current_item = start_item
        while current_item is not None:
            marker = current_item.data(0, self.MARKER_ROLE)
            if marker == "block_header":
                return current_item
            current_item = current_item.parent()
        return None

    def _set_block_header_highlight(
        self,
        header_item: QtWidgets.QTreeWidgetItem,
        highlighted: bool,
    ) -> None:
        """切换块分组头的高亮样式。"""
        if header_item is None:
            return
        header_font = header_item.font(0)
        header_font.setBold(True)
        header_item.setFont(0, header_font)
        stored_color = header_item.data(0, Qt.ItemDataRole.UserRole + 3)
        if isinstance(stored_color, str) and stored_color:
            color_hex = stored_color
        else:
            color_hex = ThemeColors.TEXT_SECONDARY
        # 选中时使用统一选中背景，但前景色仍保持块颜色，保证与画布中的逻辑块颜色一致
        if highlighted:
            header_item.setBackground(0, QtGui.QBrush(QtGui.QColor(ThemeColors.BG_SELECTED)))
        else:
            header_item.setBackground(0, QtGui.QBrush())
        header_item.setForeground(0, QtGui.QBrush(QtGui.QColor(color_hex)))



