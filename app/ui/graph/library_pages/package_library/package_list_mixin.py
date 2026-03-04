from __future__ import annotations

from typing import Optional

from PyQt6 import QtCore, QtWidgets

from app.ui.graph.library_mixins import rebuild_list_with_preserved_selection


class PackageLibraryPackageListMixin:
    """左侧项目存档列表相关逻辑（刷新/过滤/选中联动）。"""

    def _filter_packages(self, text: str) -> None:
        """根据搜索文本过滤项目存档列表。"""
        self.filter_list_items(self.package_list, text)
        self.ensure_current_item_visible_or_select_first(self.package_list)

    def refresh(self) -> None:
        """刷新项目存档列表。"""
        self._clear_display_name_cache()
        self._preview_scan_service.invalidate()
        previous_key = self._current_package_id or None

        def build_items() -> None:
            # 先插入共享资源视图
            item_global = QtWidgets.QListWidgetItem("共享资源")
            item_global.setData(QtCore.Qt.ItemDataRole.UserRole, "global_view")
            item_global.setToolTip("浏览共享资源（所有项目存档可见；不可重命名/删除）")
            self.package_list.addItem(item_global)

            # 再加载普通项目存档
            packages = self.pim.list_packages()
            for pkg in packages:
                item = QtWidgets.QListWidgetItem(pkg["name"])  # 文本为名称
                item.setData(QtCore.Qt.ItemDataRole.UserRole, pkg["package_id"])  # 存放ID
                description = pkg.get("description", "")
                if description:
                    item.setToolTip(description)
                self.package_list.addItem(item)

        def get_item_key(list_item: QtWidgets.QListWidgetItem) -> Optional[str]:
            value = list_item.data(QtCore.Qt.ItemDataRole.UserRole)
            if isinstance(value, str):
                return value
            return None

        rebuild_list_with_preserved_selection(
            self.package_list,
            previous_key=previous_key,
            had_selection_before_refresh=bool(previous_key),
            build_items=build_items,
            key_getter=get_item_key,
            on_restored_selection=None,
            on_first_selection=None,
            on_cleared_selection=None,
        )

        # 重新应用当前搜索过滤，保持搜索体验一致
        if hasattr(self, "search_edit") and self.search_edit is not None:
            self._filter_packages(self.search_edit.text())

    def _on_package_selected(self) -> None:
        items = self.package_list.selectedItems()
        if not items:
            self._current_package_id = ""
            self._render_empty_detail()
            self._update_action_state()
            return
        pkg_id = items[0].data(QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(pkg_id, str) or not pkg_id:
            self._current_package_id = ""
            self._render_empty_detail()
            self._update_action_state()
            return
        self._current_package_id = pkg_id
        self._render_package_detail(pkg_id)
        self._update_action_state()

    def _is_special_id(self, package_id: str) -> bool:
        return package_id == "global_view"

    def _update_action_state(self) -> None:
        is_special = self._is_special_id(self._current_package_id)
        can_edit = bool(self._current_package_id) and not is_special
        # 禁用“重命名项目存档”：当前项目显示名唯一真源为项目目录名（package_id），
        # 而目录级重命名影响导入路径与资源引用，风险较高，因此 UI 暂不开放入口。
        self.rename_btn.setEnabled(False)
        self.clone_btn.setEnabled(can_edit)
        self.delete_btn.setEnabled(can_edit)
        # 预览模式下允许切换到当前存档（含 global_view）；无选中则禁用。
        self.open_btn.setEnabled(bool(self._current_package_id))

