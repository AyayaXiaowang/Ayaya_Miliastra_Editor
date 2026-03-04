from __future__ import annotations

from app.ui.foundation import input_dialogs
from app.ui.graph.library_pages.library_scaffold import LibraryChangeEvent


class PackageLibraryActionsMixin:
    """项目存档页的重命名/复制/删除动作。"""

    def _on_rename(self) -> None:
        if not self._current_package_id or self._is_special_id(self._current_package_id):
            return
        current_item = self.package_list.currentItem()
        if not current_item:
            return
        current_name = current_item.text()
        new_name = input_dialogs.prompt_text(
            self,
            "重命名项目存档",
            "请输入新名称:",
            text=current_name,
        )
        if not new_name:
            return
        self.pim.rename_package(self._current_package_id, new_name)
        self.packages_changed.emit()
        self.refresh()

        event = LibraryChangeEvent(
            kind="package",
            id=self._current_package_id,
            operation="update",
            context={"field": "name"},
        )
        self.data_changed.emit(event)

    def _on_clone(self) -> None:
        """复制当前选中的项目存档为新的项目存档目录。"""
        if not self._current_package_id or self._is_special_id(self._current_package_id):
            return
        pkg_id = self._current_package_id
        current_item = self.package_list.currentItem()
        if not current_item:
            return
        current_name = current_item.text()
        default_name = f"{current_name}_副本" if current_name else f"{pkg_id}_副本"

        new_name = input_dialogs.prompt_text(
            self,
            "复制项目存档",
            "请输入新项目存档名称:",
            text=default_name,
        )
        if not new_name:
            return

        # 复制前尽量保存当前包（确保复制到的目录状态完整）
        window = self.window()
        package_controller = getattr(window, "package_controller", None) if window is not None else None
        if package_controller is not None:
            current_package_id = getattr(package_controller, "current_package_id", None)
            if current_package_id == pkg_id:
                save_now = getattr(package_controller, "save_now", None)
                if callable(save_now):
                    save_now()

        new_package_id = self.pim.clone_package(pkg_id, new_name)
        self.packages_changed.emit()
        self.refresh()

        # 复制完成后默认切换到新项目存档，方便继续编辑（交给主窗口的切包保护入口处理）
        self.package_load_requested.emit(str(new_package_id))

    def _on_delete(self) -> None:
        if not self._current_package_id or self._is_special_id(self._current_package_id):
            return
        pkg_id = self._current_package_id
        if not self.confirm(
            "删除项目存档",
            "仅删除项目存档本身，不会删除包内引用的资源。\n确定要删除吗？",
        ):
            return
        self.pim.delete_package(pkg_id)
        self._current_package_id = ""
        self.packages_changed.emit()
        self.refresh()

        event = LibraryChangeEvent(
            kind="package",
            id=pkg_id,
            operation="delete",
            context=None,
        )
        self.data_changed.emit(event)

