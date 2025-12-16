from __future__ import annotations

from typing import Dict, Optional

from PyQt6 import QtWidgets, QtCore

from engine.configs.components.ui_control_group_model import UIControlGroupTemplate
from app.ui.panels.ui_control_group_template_helpers import build_template_tree_section, is_custom_template

__all__ = ["TemplateTreeWidget"]


class TemplateTreeWidget(QtWidgets.QTreeWidget):
    """封装模板树的构建与选择逻辑，供多个面板/对话框复用。"""

    def __init__(self, root_title: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._root_title = root_title
        self.setHeaderHidden(True)
        self.setUniformRowHeights(True)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self._templates: Dict[str, UIControlGroupTemplate] = {}
        self._predicate = is_custom_template
        self._filter_text: str = ""
        self._all_leaf_items: list[QtWidgets.QTreeWidgetItem] = []

    def refresh(
        self,
        templates: Dict[str, UIControlGroupTemplate],
        *,
        predicate=is_custom_template,
        query: str = "",
    ) -> None:
        """根据模板字典刷新树内容。"""
        self._templates = dict(templates)
        self._predicate = predicate
        self._filter_text = query
        self._rebuild_tree()

    def apply_filter(self, query: str) -> None:
        if query == self._filter_text:
            return
        self._filter_text = query
        self._apply_filter_to_items()

    def _rebuild_tree(self) -> None:
        selected_id = self.current_template_id()
        self.clear()
        self._all_leaf_items.clear()
        build_template_tree_section(
            self,
            self._templates,
            self._root_title,
            predicate=self._predicate,
            query=self._filter_text,
        )
        self.expandAll()
        self._collect_leaf_items()
        self._apply_filter_to_items()
        if selected_id:
            self.select_template(selected_id)

    def current_template_id(self) -> Optional[str]:
        current_item = self.currentItem()
        if not current_item:
            return None
        return current_item.data(0, QtCore.Qt.ItemDataRole.UserRole)

    def select_template(self, template_id: str) -> None:
        """根据模板 ID 定位树节点。"""
        if not template_id:
            return
        for row in range(self.topLevelItemCount()):
            match = self._find_by_id(self.topLevelItem(row), template_id)
            if match:
                self.setCurrentItem(match)
                break

    def _find_by_id(
        self,
        item: QtWidgets.QTreeWidgetItem,
        template_id: str,
    ) -> Optional[QtWidgets.QTreeWidgetItem]:
        if item.data(0, QtCore.Qt.ItemDataRole.UserRole) == template_id:
            return item
        for index in range(item.childCount()):
            result = self._find_by_id(item.child(index), template_id)
            if result:
                return result
        return None

    def _collect_leaf_items(self) -> None:
        self._all_leaf_items.clear()
        for row in range(self.topLevelItemCount()):
            self._collect_from_item(self.topLevelItem(row))

    def _collect_from_item(self, item: QtWidgets.QTreeWidgetItem) -> None:
        if item.childCount() == 0:
            self._all_leaf_items.append(item)
            return
        for idx in range(item.childCount()):
            self._collect_from_item(item.child(idx))

    def _apply_filter_to_items(self) -> None:
        if not self._all_leaf_items:
            return
        for leaf in self._all_leaf_items:
            matches = not self._filter_text or self._filter_text in leaf.text(0).casefold()
            leaf.setHidden(not matches)
        for row in range(self.topLevelItemCount()):
            self._update_parent_visibility(self.topLevelItem(row))

    def _update_parent_visibility(self, item: QtWidgets.QTreeWidgetItem) -> bool:
        if item.childCount() == 0:
            return not item.isHidden()
        has_visible_child = False
        for idx in range(item.childCount()):
            child_visible = self._update_parent_visibility(item.child(idx))
            has_visible_child = has_visible_child or child_visible
        item.setHidden(not has_visible_child)
        return has_visible_child

