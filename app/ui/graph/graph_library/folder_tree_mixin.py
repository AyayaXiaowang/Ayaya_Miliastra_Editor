from PyQt6 import QtCore, QtWidgets
from pathlib import Path
from typing import Optional

from app.ui.foundation import input_dialogs
from app.ui.foundation.context_menu_builder import ContextMenuBuilder
from app.ui.foundation.folder_tree_helper import (
    FolderTreeBuilder,
    capture_expanded_paths,
    restore_expanded_paths,
)
from app.ui.foundation.dialog_utils import (
    ask_yes_no_dialog,
    show_info_dialog,
    show_warning_dialog,
)
from app.ui.foundation.toast_notification import ToastNotification
from engine.resources.resource_manager import ResourceType
from engine.resources.package_view import PackageView
from engine.utils.path_utils import normalize_slash



class FolderTreeMixin:
    """文件夹树与拖拽相关逻辑"""

    def _resolve_folder_write_root_dir(self, folder_scope: str) -> Path:
        """解析文件夹写入根目录（shared/package）。"""
        roots = list(self.resource_manager.get_current_resource_roots() or [])
        if not roots:
            raise ValueError("无法解析资源根目录：ResourceManager.get_current_resource_roots() 为空")
        scope = str(folder_scope or "").strip().lower() or "all"
        if scope == "shared":
            return roots[0]
        if scope == "package":
            return roots[1] if len(roots) > 1 else roots[0]
        # all：默认优先当前包（若存在），否则回退共享
        return roots[1] if len(roots) > 1 else roots[0]

    @staticmethod
    def _parse_folder_tree_item_data(data: object) -> Optional[tuple[str, str, str]]:
        """解析 QTreeWidgetItem.UserRole 中存放的目录信息。

        兼容：
        - (graph_type, folder_path) 旧格式
        - (graph_type, folder_scope, folder_path) 新格式（区分共享/当前存档）
        """
        if not isinstance(data, tuple):
            return None
        if len(data) == 2:
            graph_type, folder_path = data
            folder_scope = "all"
        elif len(data) == 3:
            graph_type, folder_scope, folder_path = data
        else:
            return None
        graph_type_text = str(graph_type or "")
        folder_scope_text = str(folder_scope or "") or "all"
        folder_path_text = str(folder_path or "")
        return graph_type_text, folder_scope_text, folder_path_text

    def _find_folder_tree_item(
        self,
        graph_type: str,
        folder_scope: str,
        folder_path: str,
    ) -> Optional[QtWidgets.QTreeWidgetItem]:
        """在文件夹树中查找匹配 (graph_type, folder_scope, folder_path) 的条目。"""
        tree = getattr(self, "folder_tree", None)
        if tree is None:
            return None
        iterator = QtWidgets.QTreeWidgetItemIterator(tree)
        while iterator.value() is not None:
            item = iterator.value()
            parsed = self._parse_folder_tree_item_data(item.data(0, QtCore.Qt.ItemDataRole.UserRole))
            if parsed is not None:
                item_graph_type, item_folder_scope, item_folder_path = parsed
                if (
                    item_graph_type == str(graph_type or "")
                    and item_folder_scope == str(folder_scope or "")
                    and item_folder_path == str(folder_path or "")
                ):
                    return item
            iterator += 1
        return None

    def _ensure_folder_tree_has_selection(self) -> None:
        """确保文件夹树始终存在一个“当前选中”的条目。

        约定：
        - 优先选中当前筛选条件（current_graph_type/current_folder）对应的条目；
        - 若不存在，回退选中该类型的根目录；
        - 若仍不可用，选中第一棵根节点（仅用于极端场景兜底）。
        """
        tree = getattr(self, "folder_tree", None)
        if tree is None:
            return

        current_item = tree.currentItem()
        if current_item is not None:
            return

        desired_graph_type = str(getattr(self, "current_graph_type", "") or "")
        desired_folder_scope = str(getattr(self, "current_folder_scope", "") or "") or "all"
        desired_folder_path = str(getattr(self, "current_folder", "") or "")

        if desired_graph_type:
            preferred = self._find_folder_tree_item(desired_graph_type, desired_folder_scope, desired_folder_path)
            if preferred is not None:
                tree.setCurrentItem(preferred)
                setattr(self, "current_graph_type", desired_graph_type)
                setattr(self, "current_folder_scope", desired_folder_scope)
                setattr(self, "current_folder", desired_folder_path)
                return
            root_item = self._find_folder_tree_item(desired_graph_type, "all", "")
            if root_item is not None:
                tree.setCurrentItem(root_item)
                setattr(self, "current_graph_type", desired_graph_type)
                setattr(self, "current_folder_scope", "all")
                setattr(self, "current_folder", "")
                return

        fallback_root = tree.topLevelItem(0)
        if fallback_root is not None:
            tree.setCurrentItem(fallback_root)
            fallback_data = self._parse_folder_tree_item_data(
                fallback_root.data(0, QtCore.Qt.ItemDataRole.UserRole)
            )
            if fallback_data is not None:
                fallback_graph_type, fallback_scope, fallback_folder_path = fallback_data
                setattr(self, "current_graph_type", fallback_graph_type)
                setattr(self, "current_folder_scope", fallback_scope)
                setattr(self, "current_folder", fallback_folder_path)

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
        # 目录视图过滤：只展示“当前作用域（共享 + 当前项目存档）”下的文件夹树，
        # 并在树上显式区分「共享 / 当前存档」两类目录，避免共享资源被误认作某个普通文件夹（如“模板示例”）。
        resource_roots = self.resource_manager.get_current_resource_roots()
        shared_root = resource_roots[0] if resource_roots else None
        package_root = resource_roots[1] if len(resource_roots) > 1 else None

        shared_folders_snapshot = (
            self.resource_manager.get_all_graph_folders(resource_roots=[shared_root])
            if isinstance(shared_root, Path)
            else {"server": [], "client": []}
        )
        package_folders_snapshot = (
            self.resource_manager.get_all_graph_folders(resource_roots=[package_root])
            if isinstance(package_root, Path)
            else {"server": [], "client": []}
        )

        snapshot_key = (
            tuple(sorted(shared_folders_snapshot.get("server", []))),
            tuple(sorted(shared_folders_snapshot.get("client", []))),
            tuple(sorted(package_folders_snapshot.get("server", []))),
            tuple(sorted(package_folders_snapshot.get("client", []))),
        )
        previous_snapshot = getattr(self, "_folder_tree_snapshot", None)
        if not force and previous_snapshot == snapshot_key:
            return

        self.folder_tree.clear()
        created_roots: list[QtWidgets.QTreeWidgetItem] = []

        if self.current_graph_type == "all":
            server_root = QtWidgets.QTreeWidgetItem(self.folder_tree)
            server_root.setText(0, "🔷 服务器节点图")
            server_root.setData(0, QtCore.Qt.ItemDataRole.UserRole, ("server", "all", ""))

            client_root = QtWidgets.QTreeWidgetItem(self.folder_tree)
            client_root.setText(0, "🔶 客户端节点图")
            client_root.setData(0, QtCore.Qt.ItemDataRole.UserRole, ("client", "all", ""))

            self._add_folders_to_tree(
                server_root,
                "server",
                shared_folders_snapshot=shared_folders_snapshot,
                package_folders_snapshot=package_folders_snapshot,
                has_package_root=isinstance(package_root, Path),
            )
            self._add_folders_to_tree(
                client_root,
                "client",
                shared_folders_snapshot=shared_folders_snapshot,
                package_folders_snapshot=package_folders_snapshot,
                has_package_root=isinstance(package_root, Path),
            )
            created_roots.extend([server_root, client_root])
        else:
            root_name = "🔷 服务器节点图" if self.current_graph_type == "server" else "🔶 客户端节点图"
            root = QtWidgets.QTreeWidgetItem(self.folder_tree)
            root.setText(0, root_name)
            root.setData(0, QtCore.Qt.ItemDataRole.UserRole, (self.current_graph_type, "all", ""))
            self._add_folders_to_tree(
                root,
                self.current_graph_type,
                shared_folders_snapshot=shared_folders_snapshot,
                package_folders_snapshot=package_folders_snapshot,
                has_package_root=isinstance(package_root, Path),
            )
            created_roots.append(root)

        self._folder_tree_snapshot = snapshot_key
        if (not force) and expanded_state:
            restore_expanded_paths(self.folder_tree, expanded_state, self._folder_tree_item_key)
            # 根节点（服务器/客户端）不参与 expanded_state（其 key 为 None）。
            # 若仅恢复子节点展开状态而根节点保持折叠，会导致“看起来只有根目录”的错觉。
            for root_item in created_roots:
                root_item.setExpanded(True)
                for index in range(root_item.childCount()):
                    root_item.child(index).setExpanded(True)
        else:
            self.folder_tree.expandAll()

        # 关键：无论何时都保证“左侧文件夹树”有当前选中项，避免用户误以为未选中目录
        # 却被中间列表的 current_folder 过滤（启动恢复/刷新等场景尤其明显）。
        self._ensure_folder_tree_has_selection()

    def _add_folders_to_tree(
        self,
        parent_item: QtWidgets.QTreeWidgetItem,
        graph_type: str,
        *,
        shared_folders_snapshot: dict,
        package_folders_snapshot: dict,
        has_package_root: bool,
    ) -> None:
        """添加文件夹到树（扁平展示：共享/当前存档同级）。

        设计目标：
        - 不额外增加“共享资源/当前存档”父节点层级（避免出现“共享资源->模板示例”的多一层体验）；
        - 共享目录在首层名称前增加 `🌐 ` 前缀，便于识别归属；
        - 当前存档目录按其真实 folder_path 构建；不再额外插入“📦 <当前存档>”父节点，
          从而避免出现“锻刀（存档节点）/锻刀（真实文件夹）/...”的重复层级。
        """
        graph_type_text = str(graph_type or "")

        def _normalize_folder_path(folder_path: object) -> str:
            return normalize_slash(str(folder_path or "")).strip("/")

        def _build_shared_mapping(folder_paths: list[str]) -> tuple[dict[str, str], list[str]]:
            display_to_actual: dict[str, str] = {}
            display_leaf_paths: list[str] = []
            for raw_path in folder_paths:
                normalized = _normalize_folder_path(raw_path)
                if not normalized:
                    continue
                actual_parts = [part for part in normalized.split("/") if part]
                if not actual_parts:
                    continue
                display_parts = list(actual_parts)
                display_parts[0] = f"🌐 {display_parts[0]}"
                display_leaf_paths.append("/".join(display_parts))

                actual_acc = ""
                display_acc = ""
                for actual_part, display_part in zip(actual_parts, display_parts):
                    actual_acc = actual_part if not actual_acc else f"{actual_acc}/{actual_part}"
                    display_acc = display_part if not display_acc else f"{display_acc}/{display_part}"
                    display_to_actual[display_acc] = actual_acc
            return display_to_actual, sorted(set(display_leaf_paths))

        def _build_package_mapping(folder_paths: list[str]) -> tuple[dict[str, str], list[str]]:
            """存档目录：按真实 folder_path 直接构建（不做额外折叠）。"""
            display_to_actual: dict[str, str] = {}
            display_leaf_paths: list[str] = []
            for raw_path in folder_paths:
                normalized = _normalize_folder_path(raw_path)
                if not normalized:
                    continue
                parts = [part for part in normalized.split("/") if part]
                if not parts:
                    continue
                display_leaf_paths.append(normalized)

                acc = ""
                for part in parts:
                    acc = part if not acc else f"{acc}/{part}"
                    display_to_actual[acc] = acc
            return display_to_actual, sorted(set(display_leaf_paths))

        def _shared_label_formatter(name: str) -> str:
            """共享目录的显示：所有层级都带 🌐 标记，避免子文件夹被误认为“当前项目目录”。

            注意：首层 display_path 已加过 `🌐 ` 前缀，这里避免重复叠加。
            """
            raw_name = str(name or "")
            if raw_name.startswith("🌐 "):
                return f"📁 {raw_name}"
            return f"📁 🌐 {raw_name}"

        # -------- 当前存档：按真实 folder_path 构建（优先展示）
        if has_package_root:
            package_folders = package_folders_snapshot.get(graph_type_text, [])
            package_display_to_actual, package_display_paths = _build_package_mapping(list(package_folders or []))
            if package_display_paths:
                package_builder = FolderTreeBuilder(
                    data_factory=lambda display_path, resolved_graph_type=graph_type_text: (
                        resolved_graph_type,
                        "package",
                        package_display_to_actual.get(str(display_path or ""), ""),
                    ),
                )
                package_builder.build(parent_item, package_display_paths)

        # -------- 共享：首层加 🌐 前缀；与存档目录同级展示（排在后面）
        shared_folders = shared_folders_snapshot.get(graph_type_text, [])
        shared_display_to_actual, shared_display_paths = _build_shared_mapping(list(shared_folders or []))
        if shared_display_paths:
            shared_builder = FolderTreeBuilder(
                label_formatter=_shared_label_formatter,
                data_factory=lambda display_path, resolved_graph_type=graph_type_text: (
                    resolved_graph_type,
                    "shared",
                    shared_display_to_actual.get(str(display_path or ""), ""),
                ),
            )
            shared_builder.build(parent_item, shared_display_paths)

    def _folder_tree_item_key(self, item: QtWidgets.QTreeWidgetItem) -> Optional[str]:
        parsed = self._parse_folder_tree_item_data(item.data(0, QtCore.Qt.ItemDataRole.UserRole))
        if parsed is None:
            return None
        graph_type, folder_scope, folder_path = parsed
        if not folder_path:
            return None
        return f"{graph_type}:{folder_scope}:{folder_path}"

    def _on_folder_clicked(self, item: QtWidgets.QTreeWidgetItem, column: int) -> None:
        """文件夹点击"""
        parsed = self._parse_folder_tree_item_data(item.data(0, QtCore.Qt.ItemDataRole.UserRole))
        if parsed is None:
            return
        graph_type, folder_scope, folder_path = parsed
        self.current_graph_type = graph_type
        setattr(self, "current_folder_scope", folder_scope)
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

        parsed = self._parse_folder_tree_item_data(item.data(0, QtCore.Qt.ItemDataRole.UserRole))
        if parsed is None:
            return
        graph_type, _folder_scope, folder_path = parsed
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
        parsed = self._parse_folder_tree_item_data(item.data(0, QtCore.Qt.ItemDataRole.UserRole))
        if parsed is None:
            return

        graph_type, _folder_scope, old_folder_path = parsed
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

        folders = self.resource_manager.get_all_graph_folders(
            resource_roots=self.resource_manager.get_current_resource_roots()
        )
        type_folders = folders.get(graph_type, [])
        if new_folder_path in type_folders:
            show_warning_dialog(self, "重名冲突", f"文件夹 '{new_folder_path}' 已存在，请使用其他名称。")
            return

        self.resource_manager.rename_graph_folder(graph_type, old_folder_path, new_folder_path)
        show_info_dialog(self, "成功", f"文件夹已重命名为: {new_folder_path}")
        # 文件系统与索引已变化：强制下一次图列表刷新不被签名短路
        setattr(self, "__graph_list_refresh_signature", None)
        self._refresh_folder_tree()
        self._refresh_graph_list()

    def _add_subfolder(self, parent_item: QtWidgets.QTreeWidgetItem) -> None:
        """在指定文件夹下新建子文件夹"""
        if self._is_read_only_library():
            show_warning_dialog(self, "只读模式", "节点图库为只读模式，不能在 UI 中新建子文件夹；请在文件系统中调整目录结构。")
            return
        parsed = self._parse_folder_tree_item_data(parent_item.data(0, QtCore.Qt.ItemDataRole.UserRole))
        if parsed is None:
            return

        graph_type, folder_scope, parent_folder_path = parsed
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
        write_root_dir = self._resolve_folder_write_root_dir(folder_scope)
        folder_dir = write_root_dir / "节点图" / graph_type / new_folder_path
        folder_dir.mkdir(parents=True, exist_ok=True)
        show_info_dialog(self, "成功", f"子文件夹 '{new_folder_path}' 已创建。")
        self._refresh_folder_tree()

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
        folders = self.resource_manager.get_all_graph_folders(
            resource_roots=self.resource_manager.get_current_resource_roots()
        )
        type_folders = folders.get(graph_type, [])
        if new_folder_path in type_folders:
            show_warning_dialog(self, "重名冲突", f"文件夹 '{new_folder_path}' 已存在。")
            return

        folder_scope = str(getattr(self, "current_folder_scope", "") or "").strip().lower() or "all"
        write_root_dir = self._resolve_folder_write_root_dir(folder_scope)
        folder_dir = write_root_dir / "节点图" / graph_type / new_folder_path
        folder_dir.mkdir(parents=True, exist_ok=True)
        show_info_dialog(self, "成功", f"文件夹 '{new_folder_path}' 已创建。")
        self._refresh_folder_tree()

    def _delete_folder(self, item: QtWidgets.QTreeWidgetItem) -> None:
        """删除文件夹"""
        if self._is_read_only_library():
            show_warning_dialog(self, "只读模式", "节点图库为只读模式，不能在 UI 中删除文件夹；请在文件系统中调整目录结构。")
            return
        parsed = self._parse_folder_tree_item_data(item.data(0, QtCore.Qt.ItemDataRole.UserRole))
        if parsed is None:
            return

        graph_type, _folder_scope, folder_path = parsed
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
                setattr(self, "__graph_list_refresh_signature", None)
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
                        parsed = self._parse_folder_tree_item_data(item.data(0, QtCore.Qt.ItemDataRole.UserRole))
                        if parsed is not None:
                            target_graph_type, _target_scope, target_folder_path = parsed
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
        setattr(self, "__graph_list_refresh_signature", None)
        self._refresh_folder_tree()
        self._refresh_graph_list()


