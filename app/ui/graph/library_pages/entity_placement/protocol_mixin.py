"""实体摆放页面协议实现与选中联动。"""

from __future__ import annotations

from typing import Optional, Union

from PyQt6 import QtCore, QtWidgets

from app.ui.graph.library_pages.entity_placement.constants import (
    CATEGORY_ALL,
    CATEGORY_LEVEL_ENTITY,
    SEARCH_TEXT_ROLE,
)
from app.ui.graph.library_pages.library_scaffold import LibrarySelection
from app.ui.graph.library_pages.library_view_scope import describe_resource_view_scope
from engine.resources.global_resource_view import GlobalResourceView
from engine.resources.package_view import PackageView


class EntityPlacementProtocolMixin:
    """实体摆放页面协议实现 mixin。"""

    def set_context(self, view: Union[PackageView, GlobalResourceView]) -> None:
        """设置当前资源视图并刷新页面内容。"""
        self.current_package = view

        is_global_view = isinstance(view, GlobalResourceView)
        level_item = self._category_items.get(CATEGORY_LEVEL_ENTITY)
        if level_item:
            level_item.setDisabled(False)
            if is_global_view:
                level_item.setToolTip(
                    0,
                    "关卡实体在全局视图下用于统一编辑本体，具体归属由属性页中的“所属存档”控制（每个存档最多一个）。",
                )
            else:
                level_item.setToolTip(
                    0,
                    "关卡实体（唯一，承载关卡逻辑），可通过属性页中的“所属存档”与当前存档建立或解除绑定。",
                )

        self._rebuild_instances()

    def reload(self) -> None:
        """在当前上下文下全量刷新实体列表。"""
        self._rebuild_instances()

    def get_selection(self) -> Optional[LibrarySelection]:
        """返回当前选中的实体对应的 LibrarySelection。"""
        instance_id = self._current_instance_id()
        if not instance_id:
            if self.current_category == CATEGORY_LEVEL_ENTITY and getattr(self.current_package, "level_entity", None):
                level_instance = getattr(self.current_package, "level_entity")
                level_id = getattr(level_instance, "instance_id", "")
                value = level_id if isinstance(level_id, str) else ""
                return LibrarySelection(
                    kind="level_entity",
                    id=value,
                    context={"scope": describe_resource_view_scope(self.current_package)},
                )
            return None

        kind = "level_entity" if self._is_level_entity_instance_id(instance_id) else "instance"
        return LibrarySelection(
            kind=kind,
            id=instance_id,
            context={"scope": describe_resource_view_scope(self.current_package)},
        )

    def set_selection(self, selection: Optional[LibrarySelection]) -> None:
        """根据 LibrarySelection 恢复页面选中状态。"""
        if selection is None:
            self.entity_list.setCurrentItem(None)
            return

        if selection.kind == "level_entity":
            self._ensure_level_entity_exists()
            self.current_category = CATEGORY_LEVEL_ENTITY
            self._rebuild_instances()
            level_id = selection.id
            if level_id:
                self.select_instance(level_id)
            else:
                if self.entity_list.count() > 0:
                    self.entity_list.setCurrentRow(0)
                    self._emit_current_selection_or_clear()
            return

        if selection.kind != "instance":
            return
        if not selection.id:
            return
        self.select_instance(selection.id)

    def _on_category_clicked(self, item: QtWidgets.QTreeWidgetItem, column: int) -> None:
        """响应左侧分类树的点击事件。"""
        category = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if category == CATEGORY_LEVEL_ENTITY:
            self.current_category = CATEGORY_LEVEL_ENTITY
            self._rebuild_instances()
            self._emit_current_selection_or_clear()
            return

        self.current_category = category or CATEGORY_ALL
        self._rebuild_instances()

    def _get_search_text_for_item(self, item: QtWidgets.QListWidgetItem) -> str:
        """返回实体列表项的搜索文本。"""
        value = item.data(SEARCH_TEXT_ROLE)
        return str(value) if value is not None else item.text()

    def _on_search_text_changed(self, text: str) -> None:
        """根据搜索框文本过滤右侧实体列表。"""
        self.filter_list_items(self.entity_list, text, text_getter=self._get_search_text_for_item)

    def _on_selection_changed(self) -> None:
        """响应实体列表选中变化并向上层发射统一信号。"""
        self._emit_current_selection_or_clear()

    def _emit_current_selection_or_clear(self) -> None:
        """根据当前选中项发射 selection_changed 或清空选中。"""
        selection = self.get_selection()
        if selection is None:
            self.notify_selection_state(False, context={"source": "instance"})
            self.selection_changed.emit(None)
            return
        self.notify_selection_state(True, context={"source": "instance"})
        self.selection_changed.emit(selection)

    def refresh_instances(self) -> None:
        """供上层在属性面板写回后触发列表刷新。"""
        self._rebuild_instances()

