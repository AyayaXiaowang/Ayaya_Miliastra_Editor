"""CompositeNodeManagerWidget 的右键菜单与库 CRUD mixin。"""

from __future__ import annotations

from PyQt6 import QtCore

from app.ui.foundation import input_dialogs
from app.ui.foundation.context_menu_builder import ContextMenuBuilder
from app.ui.foundation.dialog_utils import ask_yes_no_dialog, show_warning_dialog
from app.ui.foundation.toast_notification import ToastNotification


class CompositeNodeManagerContextMenuMixin:
    # ------------------------------------------------------------------ 右键菜单与 CRUD（库结构）

    def _show_folder_context_menu(self, position: QtCore.QPoint) -> None:
        if self.folder_tree is None:
            return
        item = self.folder_tree.itemAt(position)
        if item is None:
            return
        item_data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(item_data, dict) or item_data.get("type") != "folder":
            return
        builder = ContextMenuBuilder(self)
        if not self.can_persist_composite:
            builder.add_action("刷新列表", self._reload_library_from_disk_from_user_action)
            builder.exec_for(self.folder_tree.viewport(), position)
            return
        folder_scope = str(item_data.get("scope") or "project").strip() or "project"
        folder_path = str(item_data.get("path") or "")

        # 复合节点库的写入能力目前只面向“当前项目”侧（避免在 UI 中误操作共享根目录）。
        if folder_scope in ("all", "shared"):
            builder.add_action("刷新列表", self._reload_library_from_disk_from_user_action)
            builder.exec_for(self.folder_tree.viewport(), position)
            return

        if not folder_path:
            builder.add_action("+ 新建文件夹", self._create_folder)
            builder.add_separator()
            builder.add_action("+ 新建节点", self._create_composite_node)
            builder.add_separator()
            builder.add_action("刷新列表", self._reload_library_from_disk_from_user_action)
        else:
            builder.add_action("+ 新建子文件夹", self._create_folder)
            builder.add_separator()
            builder.add_action("+ 新建节点", self._create_composite_node)
            builder.add_separator()
            builder.add_action("删除文件夹", lambda: self._delete_folder(folder_path))
        builder.exec_for(self.folder_tree.viewport(), position)

    def _show_composite_list_context_menu(self, position: QtCore.QPoint) -> None:
        if self.composite_list is None:
            return
        item = self.composite_list.itemAt(position)
        builder = ContextMenuBuilder(self)

        if item is not None:
            composite_id_value = item.data(QtCore.Qt.ItemDataRole.UserRole)
            composite_id = str(composite_id_value or "")
            if composite_id:
                builder.add_action("打开预览", lambda: self._select_composite(composite_id, open_preview=True))
                builder.add_separator()
                builder.add_action("移动到...", lambda: self._move_node_to_folder(composite_id), enabled=self.can_persist_composite)
                builder.add_separator()
                builder.add_action("删除", lambda: self._delete_composite_node(composite_id), enabled=self.can_persist_composite)
        else:
            builder.add_action("+ 新建节点", self._create_composite_node, enabled=self.can_persist_composite)
            builder.add_separator()
            builder.add_action("+ 新建文件夹", self._create_folder, enabled=self.can_persist_composite)
            builder.add_separator()
            builder.add_action("刷新列表", self._reload_library_from_disk_from_user_action)

        builder.exec_for(self.composite_list.viewport(), position)

    def _create_composite_node(self) -> None:
        """创建新的复合节点（默认自动命名，无弹窗）。"""
        if not self.can_persist_composite:
            show_warning_dialog(self, "只读模式", "当前复合节点库为只读模式，不能在 UI 中新建复合节点。")
            return
        folder_path = ""
        if self.folder_tree is not None:
            current_item = self.folder_tree.currentItem()
            if current_item is not None:
                item_data = current_item.data(0, QtCore.Qt.ItemDataRole.UserRole)
                if isinstance(item_data, dict) and item_data.get("type") == "folder":
                    folder_scope = str(item_data.get("scope") or "project").strip() or "project"
                    if folder_scope in ("all", "shared"):
                        show_warning_dialog(
                            self,
                            "不支持的操作",
                            "请选择“当前项目”下的目标文件夹再新建。\n共享复合节点库与“全部”视图不支持在此处直接新建。",
                        )
                        return
                    folder_path = str(item_data.get("path") or "")

        composite_id = self._service.create_composite(folder_path)
        self._refresh_composite_list()
        self._try_select_composite_in_list(composite_id, trigger_selection=True)
        self.composite_library_updated.emit()

    def _create_folder(self) -> None:
        """创建新文件夹。"""
        if not self.can_persist_composite:
            show_warning_dialog(self, "只读模式", "当前复合节点库为只读模式，不能在 UI 中新建文件夹。")
            return

        parent_folder_path = ""
        if self.folder_tree is not None:
            current_item = self.folder_tree.currentItem()
            if current_item is not None:
                item_data = current_item.data(0, QtCore.Qt.ItemDataRole.UserRole)
                if isinstance(item_data, dict) and item_data.get("type") == "folder":
                    folder_scope = str(item_data.get("scope") or "project").strip() or "project"
                    if folder_scope in ("all", "shared"):
                        show_warning_dialog(
                            self,
                            "不支持的操作",
                            "请选择“当前项目”下的目标文件夹再新建。\n共享复合节点库与“全部”视图不支持在此处直接新建文件夹。",
                        )
                        return
                    parent_folder_path = str(item_data.get("path") or "")

        folder_name = input_dialogs.prompt_text(self, "新建文件夹", "请输入文件夹名称:")
        if not folder_name:
            return

        if self._service.create_folder(folder_name, parent_folder_path):
            self._refresh_composite_list()
        else:
            show_warning_dialog(self, "错误", f"创建文件夹失败：{folder_name}")

    def _delete_item(self) -> None:
        """删除选中的项（节点或文件夹）。"""
        if not self.can_persist_composite:
            show_warning_dialog(self, "只读模式", "当前复合节点库为只读模式，不能在 UI 中删除复合节点或文件夹。")
            return

        # 优先删除“当前列表选中的复合节点”
        if self.composite_list is not None:
            list_item = self.composite_list.currentItem()
            if list_item is not None:
                composite_id_value = list_item.data(QtCore.Qt.ItemDataRole.UserRole)
                composite_id = str(composite_id_value or "")
                if composite_id:
                    self._delete_composite_node(composite_id)
                    return

        # 若列表未选中，则尝试删除当前选中的文件夹
        if self.folder_tree is None:
            return
        folder_item = self.folder_tree.currentItem()
        if folder_item is None:
            show_warning_dialog(self, "提示", "请先选择一个项")
            return
        item_data = folder_item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(item_data, dict) or item_data.get("type") != "folder":
            return
        folder_scope = str(item_data.get("scope") or "project").strip() or "project"
        folder_path = str(item_data.get("path") or "")
        if folder_scope in ("all", "shared"):
            show_warning_dialog(self, "不支持的操作", "共享复合节点库与“全部”视图不支持在此处删除文件夹。")
            return
        if not folder_path:
            show_warning_dialog(self, "提示", "根目录不能删除")
            return
        self._delete_folder(folder_path)

    def _delete_composite_node(self, composite_id: str) -> None:
        """删除指定的复合节点。"""
        if not self.can_persist_composite:
            return

        composite_config = self.manager.get_composite_node(composite_id)
        if composite_config is None:
            return

        if not ask_yes_no_dialog(
            self,
            "确认删除",
            f"确定要删除复合节点 '{composite_config.node_name}' 吗？\n此操作不可撤销。",
        ):
            return

        self._service.delete_composite(composite_id)
        if self.current_composite_id == composite_id:
            self._clear_current_composite_context()

        self._refresh_composite_list()
        self.composite_library_updated.emit()
        ToastNotification.show_message(self, f"已删除复合节点 '{composite_config.node_name}'。", "success")

    def _delete_folder(self, folder_path: str) -> None:
        """删除指定的文件夹。"""
        if not self.can_persist_composite:
            return

        if not ask_yes_no_dialog(
            self,
            "确认删除",
            f"确定要删除文件夹 '{folder_path}' 吗？\n如果文件夹不为空，将删除其中所有复合节点。\n此操作不可撤销。",
        ):
            return

        if self._service.delete_folder(folder_path):
            self._refresh_composite_list()
            self.composite_library_updated.emit()
            ToastNotification.show_message(self, f"已删除复合节点文件夹 '{folder_path}'。", "success")

    def _move_node_to_folder(self, composite_id: str) -> None:
        """移动节点到文件夹。"""
        if not self.can_persist_composite:
            show_warning_dialog(self, "只读模式", "当前复合节点库为只读模式，不能在 UI 中移动复合节点。")
            return

        folders = ["(根目录)"] + self.manager.folder_manager.folders
        target_folder_caption = input_dialogs.prompt_item(
            self,
            "移动到文件夹",
            "选择目标文件夹:",
            folders,
            current_index=0,
            editable=False,
        )
        if not target_folder_caption:
            return

        target_folder_path = "" if target_folder_caption == "(根目录)" else target_folder_caption
        if self._service.move_composite(composite_id, target_folder_path):
            self._refresh_composite_list()
            self.composite_library_updated.emit()



