from PyQt6 import QtCore, QtWidgets
from typing import Optional

from ui.foundation import input_dialogs
from ui.foundation.context_menu_builder import ContextMenuBuilder
from ui.foundation.folder_tree_helper import (
    FolderTreeBuilder,
    capture_expanded_paths,
    restore_expanded_paths,
)
from ui.foundation.dialog_utils import (
    ask_yes_no_dialog,
    show_info_dialog,
    show_warning_dialog,
)
from ui.foundation.toast_notification import ToastNotification
from engine.resources.resource_manager import ResourceType


class FolderTreeMixin:
    """文件夹树与拖拽相关逻辑"""

    def _is_read_only_library(self) -> bool:
        """当前节点图库是否处于只读模式。

        说明：GraphLibraryWidget 默认将 `graph_library_read_only` 设为 True，
        在该模式下不允许通过 UI 新建/重命名/删除文件夹，也不允许拖拽移动图。
        """
        return bool(getattr(self, "graph_library_read_only", False))

    def _refresh_folder_tree(self, *, force: bool = False) -> None:
        """刷新文件夹树"""
        # 非强制刷新时，保留当前展开状态；切换类型等强制刷新场景下，忽略旧状态，统一重新展开，
        # 避免 server/client 之间的展开快照串扰导致新类型下根节点默认收起。
        if force:
            expanded_state: set[str] = set()
        else:
            expanded_state = capture_expanded_paths(self.folder_tree, self._folder_tree_item_key)
        folders_snapshot = self.resource_manager.get_all_graph_folders()
        snapshot_key = (
            tuple(sorted(folders_snapshot.get("server", []))),
            tuple(sorted(folders_snapshot.get("client", []))),
        )
        previous_snapshot = getattr(self, "_folder_tree_snapshot", None)
        if not force and previous_snapshot == snapshot_key:
            return

        self.folder_tree.clear()

        if self.current_graph_type == "all":
            server_root = QtWidgets.QTreeWidgetItem(self.folder_tree)
            server_root.setText(0, "🔷 服务器节点图")
            server_root.setData(0, QtCore.Qt.ItemDataRole.UserRole, ("server", ""))

            client_root = QtWidgets.QTreeWidgetItem(self.folder_tree)
            client_root.setText(0, "🔶 客户端节点图")
            client_root.setData(0, QtCore.Qt.ItemDataRole.UserRole, ("client", ""))

            self._add_folders_to_tree(server_root, "server")
            self._add_folders_to_tree(client_root, "client")
        else:
            root_name = "🔷 服务器节点图" if self.current_graph_type == "server" else "🔶 客户端节点图"
            root = QtWidgets.QTreeWidgetItem(self.folder_tree)
            root.setText(0, root_name)
            root.setData(0, QtCore.Qt.ItemDataRole.UserRole, (self.current_graph_type, ""))
            self._add_folders_to_tree(root, self.current_graph_type)

        self._folder_tree_snapshot = snapshot_key
        if (not force) and expanded_state:
            restore_expanded_paths(self.folder_tree, expanded_state, self._folder_tree_item_key)
        else:
            self.folder_tree.expandAll()

    def _add_folders_to_tree(self, parent_item: QtWidgets.QTreeWidgetItem, graph_type: str) -> None:
        """添加文件夹到树"""
        folders = self.resource_manager.get_all_graph_folders()
        type_folders = folders.get(graph_type, [])
        builder = FolderTreeBuilder(
            data_factory=lambda path, gt=graph_type: (gt, path),
        )
        builder.build(parent_item, type_folders)

    def _folder_tree_item_key(self, item: QtWidgets.QTreeWidgetItem) -> Optional[str]:
        data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not data:
            return None
        graph_type, folder_path = data
        if not folder_path:
            return None
        return f"{graph_type}:{folder_path}"

    def _on_folder_clicked(self, item: QtWidgets.QTreeWidgetItem, column: int) -> None:
        """文件夹点击"""
        data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if data:
            graph_type, folder_path = data
            self.current_graph_type = graph_type
            self.current_folder = folder_path
            self._refresh_graph_list()

    def _show_folder_context_menu(self, pos: QtCore.QPoint) -> None:
        """显示文件夹右键菜单"""
        item = self.folder_tree.itemAt(pos)
        if not item:
            return

        # 节点图库只读模式下：不提供任何会修改目录结构的操作，仅保留刷新入口
        if self._is_read_only_library():
            builder = ContextMenuBuilder(self)
            builder.add_action("刷新", self.refresh)
            builder.exec_for(self.folder_tree, pos)
            return

        data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not data:
            return

        graph_type, folder_path = data
        builder = ContextMenuBuilder(self)
        if not folder_path:
            builder.add_action("+ 新建文件夹", self._add_folder)
            builder.add_separator()
            builder.add_action("刷新", self.refresh)
        else:
            builder.add_action("重命名", lambda: self._rename_folder(item))
            builder.add_separator()
            builder.add_action("+ 新建子文件夹", lambda: self._add_subfolder(item))
            builder.add_separator()
            builder.add_action("删除文件夹", lambda: self._delete_folder(item))
        builder.exec_for(self.folder_tree, pos)

    def _rename_folder(self, item: QtWidgets.QTreeWidgetItem) -> None:
        """重命名文件夹"""
        if self._is_read_only_library():
            show_warning_dialog(self, "只读模式", "节点图库为只读模式，不能在 UI 中重命名文件夹；请在文件系统中调整目录结构。")
            return
        data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not data:
            return

        graph_type, old_folder_path = data
        if not old_folder_path:
            show_warning_dialog(self, "警告", "不能重命名根目录")
            return

        old_name = old_folder_path.split("/")[-1]
        new_name = input_dialogs.prompt_text(
            self,
            "重命名文件夹",
            "请输入新的文件夹名称:",
            text=old_name,
        )
        if not new_name or new_name == old_name:
            return

        if not self.resource_manager.is_valid_folder_name(new_name):
            show_warning_dialog(
                self,
                "无效名称",
                "文件夹名称包含非法字符或格式不正确。\n不允许使用: \\ / : * ? \" < > |\n不允许前后空格或以'.'结尾",
            )
            return

        path_parts = old_folder_path.split("/")
        path_parts[-1] = new_name
        new_folder_path = "/".join(path_parts)

        folders = self.resource_manager.get_all_graph_folders()
        type_folders = folders.get(graph_type, [])
        if new_folder_path in type_folders:
            show_warning_dialog(self, "重名冲突", f"文件夹 '{new_folder_path}' 已存在，请使用其他名称。")
            return

        self.resource_manager.rename_graph_folder(graph_type, old_folder_path, new_folder_path)
        show_info_dialog(self, "成功", f"文件夹已重命名为: {new_folder_path}")
        self._refresh_folder_tree()
        self._refresh_graph_list()

    def _add_subfolder(self, parent_item: QtWidgets.QTreeWidgetItem) -> None:
        """在指定文件夹下新建子文件夹"""
        if self._is_read_only_library():
            show_warning_dialog(self, "只读模式", "节点图库为只读模式，不能在 UI 中新建子文件夹；请在文件系统中调整目录结构。")
            return
        data = parent_item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not data:
            return

        graph_type, parent_folder_path = data
        folder_name = input_dialogs.prompt_text(self, "新建子文件夹", "请输入子文件夹名称:")
        if not folder_name:
            return

        if not self.resource_manager.is_valid_folder_name(folder_name):
            show_warning_dialog(
                self,
                "无效名称",
                "文件夹名称包含非法字符或格式不正确。\n不允许使用: \\ / : * ? \" < > |\n不允许前后空格或以'.'结尾",
            )
            return

        new_folder_path = f"{parent_folder_path}/{folder_name}" if parent_folder_path else folder_name
        success = self.resource_manager.create_graph_folder(graph_type, new_folder_path)
        if success:
            show_info_dialog(self, "成功", f"子文件夹 '{new_folder_path}' 已创建。")
            self._refresh_folder_tree()
        else:
            show_warning_dialog(self, "失败", f"创建子文件夹 '{new_folder_path}' 失败。")

    def _add_folder(self) -> None:
        """新建文件夹"""
        if self._is_read_only_library():
            show_warning_dialog(self, "只读模式", "节点图库为只读模式，不能在 UI 中新建文件夹；请在文件系统中调整目录结构。")
            return
        folder_name = input_dialogs.prompt_text(self, "新建文件夹", "请输入文件夹名称:")
        if not folder_name:
            return

        if not self.resource_manager.is_valid_folder_name(folder_name):
            show_warning_dialog(
                self,
                "无效名称",
                "文件夹名称包含非法字符或格式不正确。\n不允许使用: \\ / : * ? \" < > |\n不允许前后空格或以'.'结尾",
            )
            return

        if self.current_graph_type == "all":
            type_choice = input_dialogs.prompt_item(
                self,
                "选择类型",
                "请选择文件夹类型:",
                ["服务器", "客户端"],
                current_index=0,
                editable=False,
            )
            if not type_choice:
                return
            graph_type = "server" if type_choice == "服务器" else "client"
        else:
            graph_type = self.current_graph_type

        new_folder_path = f"{self.current_folder}/{folder_name}" if self.current_folder else folder_name
        folders = self.resource_manager.get_all_graph_folders()
        type_folders = folders.get(graph_type, [])
        if new_folder_path in type_folders:
            show_warning_dialog(self, "重名冲突", f"文件夹 '{new_folder_path}' 已存在。")
            return

        success = self.resource_manager.create_graph_folder(graph_type, new_folder_path)
        if success:
            show_info_dialog(self, "成功", f"文件夹 '{new_folder_path}' 已创建。")
            self._refresh_folder_tree()
        else:
            show_warning_dialog(self, "失败", f"创建文件夹 '{new_folder_path}' 失败。")

    def _delete_folder(self, item: QtWidgets.QTreeWidgetItem) -> None:
        """删除文件夹"""
        if self._is_read_only_library():
            show_warning_dialog(self, "只读模式", "节点图库为只读模式，不能在 UI 中删除文件夹；请在文件系统中调整目录结构。")
            return
        data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not data:
            return

        graph_type, folder_path = data
        if not folder_path:
            show_warning_dialog(self, "警告", "无法删除根节点")
            return

        graphs = self.resource_manager.list_graphs_by_folder(folder_path)
        if graphs:
            if ask_yes_no_dialog(
                self,
                "确认删除",
                f"文件夹 '{folder_path}' 中有 {len(graphs)} 个节点图。\n删除文件夹会将这些节点图移动到根目录，确定继续吗？",
            ):
                for graph_info in graphs:
                    graph_id = graph_info["graph_id"]
                    self.resource_manager.move_graph_to_folder(graph_id, "")
                success = self.resource_manager.remove_graph_folder_if_empty(graph_type, folder_path)
                if success:
                    ToastNotification.show_message(self, f"文件夹 '{folder_path}' 已删除", "success")
                self._refresh_folder_tree()
                self._refresh_graph_list()
        else:
            success = self.resource_manager.remove_graph_folder_if_empty(graph_type, folder_path)
            if success:
                ToastNotification.show_message(self, f"文件夹 '{folder_path}' 已删除", "success")
                self._refresh_folder_tree()
            else:
                show_warning_dialog(self, "无法删除", f"文件夹 '{folder_path}' 包含子文件夹或其他文件，请先清空或移动。")

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        """事件过滤器 - 处理文件夹树拖放"""
        # 只读模式下，不处理任何拖放事件，保持默认行为
        if self._is_read_only_library():
            if isinstance(self, QtWidgets.QWidget):
                return QtWidgets.QWidget.eventFilter(self, watched, event)
            return False
        if watched == self.folder_tree.viewport():
            if event.type() == QtCore.QEvent.Type.DragEnter:
                drag_event = event
                if drag_event.mimeData().hasFormat("application/x-graph-id"):
                    drag_event.acceptProposedAction()
                    return True
            elif event.type() == QtCore.QEvent.Type.DragMove:
                drag_event = event
                if drag_event.mimeData().hasFormat("application/x-graph-id"):
                    pos = drag_event.position().toPoint()
                    item = self.folder_tree.itemAt(pos)
                    if item:
                        drag_event.acceptProposedAction()
                        if item != self._drag_hover_item:
                            self._drag_hover_item = item
                            self._drag_hover_timer.start(400)
                    else:
                        drag_event.ignore()
                    return True
            elif event.type() == QtCore.QEvent.Type.DragLeave:
                self._drag_hover_timer.stop()
                self._drag_hover_item = None
                return True
            elif event.type() == QtCore.QEvent.Type.Drop:
                drop_event = event
                if drop_event.mimeData().hasFormat("application/x-graph-id"):
                    graph_id = drop_event.mimeData().data("application/x-graph-id").data().decode("utf-8")
                    pos = drop_event.position().toPoint()
                    item = self.folder_tree.itemAt(pos)
                    if item:
                        data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
                        if data:
                            target_graph_type, target_folder_path = data
                            self._move_graph_to_folder_via_drag(graph_id, target_graph_type, target_folder_path)
                            drop_event.acceptProposedAction()
                self._drag_hover_timer.stop()
                self._drag_hover_item = None
                return True
        if isinstance(self, QtWidgets.QWidget):
            return QtWidgets.QWidget.eventFilter(self, watched, event)
        return False

    def _expand_hovered_item(self) -> None:
        """展开悬停的项"""
        if self._drag_hover_item:
            self.folder_tree.expandItem(self._drag_hover_item)

    def _move_graph_to_folder_via_drag(self, graph_id: str, target_graph_type: str, target_folder_path: str) -> None:
        """通过拖拽移动节点图"""
        graph_data = self.resource_manager.load_resource(ResourceType.GRAPH, graph_id)
        if not graph_data:
            show_warning_dialog(self, "错误", "无法加载节点图数据")
            return

        source_graph_type = graph_data.get("graph_type", "server")
        if source_graph_type != target_graph_type:
            show_warning_dialog(self, "类型不匹配", f"不能将 {source_graph_type} 类型的节点图移动到 {target_graph_type} 文件夹")
            return

        self.resource_manager.move_graph_to_folder(graph_id, target_folder_path)
        self._refresh_folder_tree()
        self._refresh_graph_list()


