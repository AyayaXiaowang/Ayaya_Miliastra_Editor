"""CompositeNodeManagerWidget 的浏览页/列表刷新/搜索/文件夹树 mixin。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6 import QtCore, QtWidgets

from engine.resources.package_index import PackageIndex
from engine.utils.path_utils import normalize_slash
from app.ui.foundation.folder_tree_helper import (
    FolderTreeBuilder,
    capture_expanded_paths,
    restore_expanded_paths,
)
from app.ui.foundation.shared_resource_badge_delegate import SHARED_RESOURCE_BADGE_ROLE
from app.ui.foundation.toast_notification import ToastNotification
from app.ui.composite.composite_node_manager_service import CompositeNodeRow


class CompositeNodeManagerBrowseMixin:
    # ------------------------------------------------------------------ 存档上下文（过滤）

    def set_context(
        self,
        current_package_id: str | None,
        current_package_index: PackageIndex | None,
    ) -> None:
        """注入当前存档上下文，用于过滤左侧复合节点树。

        设计约定：
        - <共享资源>：显示所有复合节点（不启用过滤）
        - 具体存档：仅显示 current_package_index.resources.composites
        """
        self._active_composite_id_filter = self._compute_active_composite_id_filter(
            current_package_id,
            current_package_index,
        )
        self._refresh_composite_list()

    def _compute_active_composite_id_filter(
        self,
        current_package_id: str | None,
        current_package_index: PackageIndex | None,
    ) -> set[str] | None:
        package_id = str(current_package_id or "")
        if not package_id or package_id == "global_view":
            return None
        if current_package_index is None:
            return set()

        allowed_ids: set[str] = {
            composite_id
            for composite_id in current_package_index.resources.composites
            if isinstance(composite_id, str) and composite_id
        }

        # 关键：具体存档视图下同样需要可见共享根目录中的复合节点（所有存档可见）。
        allowed_ids.update(self._get_shared_composite_ids())

        return allowed_ids

    @staticmethod
    def _collect_visible_folder_paths(rows: list[CompositeNodeRow]) -> list[str]:
        """由可见的复合节点行推导需要构建的文件夹路径集合（含父路径）。"""
        folder_paths: set[str] = set()
        for row in rows:
            raw_folder_path = str(row.folder_path or "")
            normalized = normalize_slash(raw_folder_path).strip("/").strip()
            if not normalized:
                continue
            parts = [part for part in normalized.split("/") if part]
            accumulated = ""
            for part in parts:
                accumulated = part if not accumulated else f"{accumulated}/{part}"
                folder_paths.add(accumulated)
        return sorted(folder_paths)

    # ------------------------------------------------------------------ 列表刷新与搜索

    def reload_library_from_disk(self, *, reload_manager: bool = True) -> None:
        """从磁盘重新扫描复合节点库，并刷新浏览/预览 UI。

        设计目标：
        - 同步外部工具/编辑器对 `复合节点库/**/*.py` 的修改；
        - 尽量保持当前文件夹与列表选中不跳变；
        - 若当前处于“预览页”，且当前复合节点仍存在，则重新加载子图以反映最新落盘内容。
        """
        was_preview_open = False
        if self._page_stack is not None and self._preview_page is not None:
            was_preview_open = self._page_stack.currentWidget() is self._preview_page

        preferred_composite_id = str(self.current_composite_id or "")

        if reload_manager:
            self.manager.reload_library_from_disk()
        self._refresh_composite_list()

        # 若原先正在预览某个复合节点：仅在该节点仍存在时重载预览，避免“预览页静默切到别的节点”。
        if was_preview_open:
            if preferred_composite_id and self.manager.get_composite_node(preferred_composite_id) is not None:
                self._try_select_composite_in_list(preferred_composite_id, trigger_selection=False)
                self._select_composite(preferred_composite_id, open_preview=True)
                self._try_select_composite_in_list(preferred_composite_id, trigger_selection=False)
                return
            self._show_browse_page()
            return

        # 浏览页：重载当前选中（更新右侧面板数据）
        current_selected_composite_id = str(self.current_composite_id or "")
        if current_selected_composite_id and self.manager.get_composite_node(current_selected_composite_id) is not None:
            self._select_composite(current_selected_composite_id, open_preview=False)
            self._try_select_composite_in_list(current_selected_composite_id, trigger_selection=False)

    def _reload_library_from_disk_from_user_action(self) -> None:
        """用户显式触发的“刷新列表”：重载磁盘版本并通知主窗口更新节点库。"""
        # 先重扫磁盘版本，确保后续 NodeRegistry 刷新能看到最新复合节点定义文件集合
        self.manager.reload_library_from_disk()
        # 再通知主窗口刷新节点库（含复合节点 NodeDef），并同步更新解析所依赖的 base_node_library
        self.composite_library_updated.emit()
        # 最后在更新后的 node_library 下刷新 UI（列表/右侧面板/预览）
        self.reload_library_from_disk(reload_manager=False)
        ToastNotification.show_message(self, "复合节点库已刷新。", "success")

    def _refresh_composite_list(self) -> None:
        """刷新复合节点库浏览页（左侧文件夹树 + 中间复合节点列表）。

        约定：
        - 单击列表仅选中并更新右侧面板，不自动进入预览页；
        - 双击列表条目才进入预览页并加载子图到画布。
        """
        if self.folder_tree is None or self.composite_list is None:
            return

        visible_rows = self._get_visible_rows()
        self._refresh_folder_tree(visible_rows)
        self._refresh_composite_items(visible_rows)

    def _folder_item_key(self, item: QtWidgets.QTreeWidgetItem) -> Optional[str]:
        item_data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if isinstance(item_data, dict) and item_data.get("type") == "folder":
            path_value = str(item_data.get("path") or "")
            if not path_value:
                # 根节点（scope 根）不参与 expanded_state；与节点图库一致，避免根折叠造成“看起来只有根”的错觉。
                return None
            scope_value = str(item_data.get("scope") or "").strip() or "project"
            return f"{scope_value}:{path_value}"
        return None

    def _on_search_text_changed(self, text: str) -> None:
        """根据关键字过滤中间复合节点列表（匹配名称/描述/路径）。"""
        if self.composite_list is None:
            return
        normalized_query = self.normalize_query(text)
        self._apply_composite_list_filter(normalized_query)

    def _get_visible_rows(self) -> list[CompositeNodeRow]:
        allowed_composite_ids = self._active_composite_id_filter
        all_rows = self._service.iter_rows()
        if allowed_composite_ids is None:
            return all_rows
        return [row for row in all_rows if row.composite_id in allowed_composite_ids]

    def _get_shared_composite_ids(self) -> set[str]:
        """计算当前工作区中属于“共享/复合节点库”的复合节点 ID 集合。"""
        shared_composite_ids: set[str] = set()
        resource_library_root = self.workspace_path / "assets" / "资源库"
        shared_composite_root_dir = (resource_library_root / "共享" / "复合节点库").resolve()
        for composite_id, file_path in self.manager.composite_index.items():
            if not isinstance(composite_id, str) or not composite_id:
                continue
            if not isinstance(file_path, Path):
                continue
            resolved_file = file_path.resolve()
            if hasattr(resolved_file, "is_relative_to"):
                if resolved_file.is_relative_to(shared_composite_root_dir):  # type: ignore[attr-defined]
                    shared_composite_ids.add(composite_id)
            else:
                shared_parts = shared_composite_root_dir.parts
                file_parts = resolved_file.parts
                if len(file_parts) >= len(shared_parts) and file_parts[: len(shared_parts)] == shared_parts:
                    shared_composite_ids.add(composite_id)
        return shared_composite_ids

    @staticmethod
    def _normalize_folder_path(folder_path: str) -> str:
        return normalize_slash(str(folder_path or "")).strip("/").strip()

    def _resolve_composite_scope(self, composite_id: str, *, shared_composite_ids: set[str]) -> str:
        normalized_id = str(composite_id or "")
        return "shared" if normalized_id and normalized_id in shared_composite_ids else "project"

    def _refresh_folder_tree(self, visible_rows: list[CompositeNodeRow]) -> None:
        if self.folder_tree is None:
            return
        expanded_state = capture_expanded_paths(self.folder_tree, self._folder_item_key)
        selected_scope = str(self._current_folder_scope or "all").strip() or "all"
        selected_folder_path = self._normalize_folder_path(str(self._current_folder_path or ""))

        self.folder_tree.clear()

        shared_composite_ids = self._get_shared_composite_ids()
        project_rows = [row for row in visible_rows if row.composite_id not in shared_composite_ids]
        shared_rows = [row for row in visible_rows if row.composite_id in shared_composite_ids]
        allowed_scopes = {"all", "project", "shared"}
        if selected_scope not in allowed_scopes:
            selected_scope = "all"

        def _shared_label_formatter(name: str) -> str:
            """共享目录：所有层级都带 🌐 标记，避免子文件夹被误认为项目目录。"""
            raw_name = str(name or "")
            return f"📁 🌐 {raw_name}"

        # 目录树：显式区分“当前项目 / 共享”两个根分支，避免共享节点都在根目录时看不出来归属。
        root_item = QtWidgets.QTreeWidgetItem(self.folder_tree)
        root_item.setText(0, "🧩 复合节点库")
        root_item.setData(
            0,
            QtCore.Qt.ItemDataRole.UserRole,
            {"type": "folder", "scope": "all", "path": ""},
        )

        project_root_item = QtWidgets.QTreeWidgetItem(root_item)
        project_root_item.setText(0, "📁 当前项目")
        project_root_item.setData(
            0,
            QtCore.Qt.ItemDataRole.UserRole,
            {"type": "folder", "scope": "project", "path": ""},
        )

        shared_root_item = QtWidgets.QTreeWidgetItem(root_item)
        shared_root_item.setText(0, "📁 🌐 共享")
        shared_root_item.setData(
            0,
            QtCore.Qt.ItemDataRole.UserRole,
            {"type": "folder", "scope": "shared", "path": ""},
        )

        project_visible_folders = self._collect_visible_folder_paths(project_rows)
        if project_visible_folders:
            project_builder = FolderTreeBuilder(
                data_factory=lambda folder_path: {"type": "folder", "scope": "project", "path": folder_path},
            )
            project_builder.build(project_root_item, project_visible_folders)

        shared_visible_folders = self._collect_visible_folder_paths(shared_rows)
        if shared_visible_folders:
            shared_builder = FolderTreeBuilder(
                label_formatter=_shared_label_formatter,
                data_factory=lambda folder_path: {"type": "folder", "scope": "shared", "path": folder_path},
            )
            shared_builder.build(shared_root_item, shared_visible_folders)

        if expanded_state:
            restore_expanded_paths(self.folder_tree, expanded_state, self._folder_item_key)
            root_item.setExpanded(True)
            # 根节点不参与 expanded_state（其 key 为 None），防止“只剩根目录”的错觉。
            for index in range(root_item.childCount()):
                root_item.child(index).setExpanded(True)
        else:
            self.folder_tree.expandAll()

        # 恢复当前选中的文件夹；若不存在则回退到根（all）
        target_item = self._find_folder_item(selected_scope, selected_folder_path)
        if target_item is None:
            target_item = root_item
            self._current_folder_scope = "all"
            self._current_folder_path = ""
        else:
            item_data = target_item.data(0, QtCore.Qt.ItemDataRole.UserRole)
            if isinstance(item_data, dict) and item_data.get("type") == "folder":
                restored_scope = str(item_data.get("scope") or "all").strip() or "all"
                restored_path = self._normalize_folder_path(str(item_data.get("path") or ""))
                self._current_folder_scope = restored_scope
                self._current_folder_path = restored_path

        self.folder_tree.setCurrentItem(target_item)

    def _filter_rows_by_folder(self, rows: list[CompositeNodeRow], folder_path: str) -> list[CompositeNodeRow]:
        sanitized_folder = self._normalize_folder_path(folder_path)
        if not sanitized_folder:
            return rows
        prefix = f"{sanitized_folder}/"
        scoped_rows: list[CompositeNodeRow] = []
        for row in rows:
            row_folder = self._normalize_folder_path(row.folder_path)
            if row_folder == sanitized_folder or row_folder.startswith(prefix):
                scoped_rows.append(row)
        return scoped_rows

    def _refresh_composite_items(self, visible_rows: list[CompositeNodeRow]) -> None:
        if self.composite_list is None:
            return

        shared_composite_ids = self._get_shared_composite_ids()
        current_scope = str(self._current_folder_scope or "all").strip() or "all"
        if current_scope == "all":
            scope_rows = visible_rows
        elif current_scope == "shared":
            scope_rows = [row for row in visible_rows if row.composite_id in shared_composite_ids]
        else:
            scope_rows = [row for row in visible_rows if row.composite_id not in shared_composite_ids]

        folder_scoped_rows = self._filter_rows_by_folder(scope_rows, self._current_folder_path)
        # 约定：项目优先、共享靠后（即使在“全部”视图下亦保持分组顺序）。
        folder_scoped_rows.sort(key=lambda row: (row.composite_id in shared_composite_ids, str(row.node_name or "").casefold()))

        preferred_composite_id = str(self.current_composite_id or "")

        self.composite_list.clear()
        for row in folder_scoped_rows:
            display_name = str(row.node_name or row.composite_id)
            is_shared_composite = row.composite_id in shared_composite_ids
            item = QtWidgets.QListWidgetItem(f"🧩 {display_name}")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, row.composite_id)
            item.setData(SHARED_RESOURCE_BADGE_ROLE, bool(is_shared_composite))
            search_tokens = [row.node_name, row.description, row.folder_path, row.composite_id]
            search_value = " ".join(str(token) for token in search_tokens if token).casefold()
            item.setData(QtCore.Qt.ItemDataRole.UserRole + 1, search_value)

            tooltip_lines = [
                f"名称: {display_name}",
                f"ID: {row.composite_id}",
            ]
            if is_shared_composite:
                tooltip_lines.insert(0, "归属: 共享（所有存档可见）")
            if row.folder_path:
                tooltip_lines.append(f"文件夹: {row.folder_path}")
            if row.description:
                tooltip_lines.append(f"描述: {row.description}")
            item.setToolTip("\n".join(tooltip_lines))
            self.composite_list.addItem(item)

        # 搜索过滤（不改变选中，仅切可见性）
        normalized_query = ""
        if self._search_line_edit is not None:
            normalized_query = self.normalize_query(self._search_line_edit.text())
        self._apply_composite_list_filter(normalized_query)

        # 尝试恢复当前选中项；若不可见则不强行切换（避免隐式换选中）。
        if preferred_composite_id:
            restored = self._try_select_composite_in_list(preferred_composite_id, trigger_selection=False)
            if restored:
                return

        # 没有选中或无法恢复：默认选中第一项（只做选中，不自动打开预览）
        first_item = self._get_first_visible_composite_item()
        if first_item is not None:
            composite_id_value = first_item.data(QtCore.Qt.ItemDataRole.UserRole)
            composite_id = str(composite_id_value or "")
            if composite_id:
                self._select_composite(composite_id, open_preview=False)
                self._try_select_composite_in_list(composite_id, trigger_selection=False)
                return

        # 列表为空：清空上下文
        self.current_composite = None
        self.current_composite_id = ""
        self.composite_selected.emit("")
        if self._page_stack is not None and self._browse_page is not None:
            self._page_stack.setCurrentWidget(self._browse_page)

    def _apply_composite_list_filter(self, normalized_query: str) -> None:
        if self.composite_list is None:
            return
        for index in range(self.composite_list.count()):
            item = self.composite_list.item(index)
            search_value = item.data(QtCore.Qt.ItemDataRole.UserRole + 1) or ""
            value_text = str(search_value).casefold()
            if not normalized_query:
                item.setHidden(False)
            else:
                item.setHidden(normalized_query not in value_text)

    def _get_first_visible_composite_item(self) -> Optional[QtWidgets.QListWidgetItem]:
        if self.composite_list is None:
            return None
        for index in range(self.composite_list.count()):
            item = self.composite_list.item(index)
            if item is not None and not item.isHidden():
                return item
        return None

    def _try_select_composite_in_list(self, composite_id: str, *, trigger_selection: bool) -> bool:
        if self.composite_list is None:
            return False
        for index in range(self.composite_list.count()):
            item = self.composite_list.item(index)
            if item is None:
                continue
            item_composite_id_value = item.data(QtCore.Qt.ItemDataRole.UserRole)
            item_composite_id = str(item_composite_id_value or "")
            if item_composite_id == composite_id:
                self.composite_list.setCurrentItem(item)
                if trigger_selection:
                    self._on_composite_item_clicked(item)
                return True
        return False

    # ------------------------------------------------------------------ 选择与图加载（页切换）

    def reset_to_library_list_view(self) -> None:
        """重置为“库列表视图”（与节点图库一致：返回列表通过再次点击左侧导航进入本模式）。"""
        self._show_browse_page()

    def _show_browse_page(self) -> None:
        if self._page_stack is None or self._browse_page is None:
            return
        self._page_stack.setCurrentWidget(self._browse_page)

    def _show_preview_page(self) -> None:
        if self._page_stack is None or self._preview_page is None:
            return
        self._page_stack.setCurrentWidget(self._preview_page)

    def _on_folder_item_clicked(self, item: QtWidgets.QTreeWidgetItem, column: int) -> None:
        """左侧文件夹点击：仅刷新中间列表范围，不直接打开预览。"""
        if self._suppress_tree_item_clicked:
            return
        _ = column

        item_data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(item_data, dict) or item_data.get("type") != "folder":
            return

        folder_scope = str(item_data.get("scope") or "project").strip() or "project"
        new_folder_raw = str(item_data.get("path") or "")
        normalized_folder = self._normalize_folder_path(new_folder_raw)

        previous_scope = str(self._current_folder_scope or "project")
        previous_folder = str(self._current_folder_path or "")
        if folder_scope == previous_scope and normalized_folder == self._normalize_folder_path(previous_folder):
            return

        visible_rows = self._get_visible_rows()
        shared_composite_ids = self._get_shared_composite_ids()
        if folder_scope == "all":
            scope_rows = visible_rows
        elif folder_scope == "shared":
            scope_rows = [row for row in visible_rows if row.composite_id in shared_composite_ids]
        else:
            scope_rows = [row for row in visible_rows if row.composite_id not in shared_composite_ids]
        rows_in_target = self._filter_rows_by_folder(scope_rows, normalized_folder)
        current_id = str(self.current_composite_id or "")
        current_still_visible = True
        if current_id:
            current_scope = self._resolve_composite_scope(current_id, shared_composite_ids=shared_composite_ids)
            if folder_scope != "all" and current_scope != folder_scope:
                current_still_visible = False
            else:
                current_still_visible = any(row.composite_id == current_id for row in rows_in_target)

        if (not current_still_visible) and current_id:
            if not self._confirm_leave_current_composite():
                self._restore_folder_selection(previous_scope, previous_folder)
                return
            self._clear_current_composite_context()

        self._current_folder_scope = folder_scope
        self._current_folder_path = normalized_folder
        self._refresh_composite_items(visible_rows)

    def _on_composite_item_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        composite_id_value = item.data(QtCore.Qt.ItemDataRole.UserRole)
        composite_id = str(composite_id_value or "")
        if not composite_id:
            return
        self._select_composite(composite_id, open_preview=False)

    def _on_composite_item_double_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        composite_id_value = item.data(QtCore.Qt.ItemDataRole.UserRole)
        composite_id = str(composite_id_value or "")
        if not composite_id:
            return
        self._select_composite(composite_id, open_preview=True)

    # ------------------------------------------------------------------ 文件夹选择辅助

    def _restore_folder_selection(self, folder_scope: str, folder_path: str) -> None:
        if self.folder_tree is None:
            return
        self._suppress_tree_item_clicked = True
        try:
            target = self._find_folder_item(folder_scope, folder_path)
            if target is not None:
                self.folder_tree.setCurrentItem(target)
        finally:
            self._suppress_tree_item_clicked = False

    def _find_folder_item(self, folder_scope: str, folder_path: str) -> Optional[QtWidgets.QTreeWidgetItem]:
        if self.folder_tree is None:
            return None
        normalized_scope = str(folder_scope or "project").strip() or "project"
        normalized_target = self._normalize_folder_path(folder_path)

        def find_recursively(parent_item: QtWidgets.QTreeWidgetItem) -> Optional[QtWidgets.QTreeWidgetItem]:
            item_data = parent_item.data(0, QtCore.Qt.ItemDataRole.UserRole)
            if isinstance(item_data, dict) and item_data.get("type") == "folder":
                item_scope = str(item_data.get("scope") or "project").strip() or "project"
                item_path = self._normalize_folder_path(str(item_data.get("path") or ""))
                if item_scope == normalized_scope and item_path == normalized_target:
                    return parent_item

            for child_index in range(parent_item.childCount()):
                child_item = parent_item.child(child_index)
                result = find_recursively(child_item)
                if result is not None:
                    return result
            return None

        for index in range(self.folder_tree.topLevelItemCount()):
            top_item = self.folder_tree.topLevelItem(index)
            if top_item is None:
                continue
            found = find_recursively(top_item)
            if found is not None:
                return found
        return None



