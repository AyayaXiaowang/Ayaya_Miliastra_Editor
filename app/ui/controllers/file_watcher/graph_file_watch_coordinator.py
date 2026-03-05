from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from PyQt6 import QtCore, QtWidgets

from engine.configs.settings import settings
from engine.resources.resource_manager import ResourceManager, ResourceType
from engine.utils.logging.logger import log_debug


@dataclass(frozen=True, slots=True)
class GraphWatchContext:
    graph_id: str | None
    graph_file_path: Path | None


class GraphFileWatchCoordinator(QtCore.QObject):
    """节点图文件监控：去抖、冲突检测、重载与视图状态恢复。"""

    def __init__(
        self,
        resource_manager: ResourceManager,
        file_watcher: QtCore.QFileSystemWatcher,
        *,
        emit_toast: Callable[[str, str], None],
        emit_graph_reloaded: Callable[[str, dict], None],
        request_force_save: Callable[[], None],
        get_active_graph_id: Callable[[], Optional[str]],
        get_scene: Callable[[], Any],
        get_view: Callable[[], Any],
        dialog_parent_provider: Callable[[], Optional[QtWidgets.QWidget]],
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._resource_manager = resource_manager
        self._file_watcher = file_watcher

        self._emit_toast = emit_toast
        self._emit_graph_reloaded = emit_graph_reloaded
        self._request_force_save = request_force_save

        self._get_active_graph_id = get_active_graph_id
        self._get_scene = get_scene
        self._get_view = get_view
        self._dialog_parent_provider = dialog_parent_provider

        self._context = GraphWatchContext(graph_id=None, graph_file_path=None)
        self._last_save_wall_time_seconds: float = 0.0

        self._debounce_timer: QtCore.QTimer = QtCore.QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._handle_debounced_file_change)

        self._ignore_seconds_after_save: float = float(getattr(settings, "GRAPH_FILE_WATCH_IGNORE_SECONDS", 1.0))
        self._debounce_ms: int = int(getattr(settings, "GRAPH_FILE_WATCH_DEBOUNCE_MS", 200))

    def set_watch_context(self, *, graph_id: str | None, graph_file_path: Path | None) -> None:
        self._context = GraphWatchContext(graph_id=(graph_id or None), graph_file_path=graph_file_path)

    def update_last_save_time(self) -> None:
        self._last_save_wall_time_seconds = float(time.time())

    def on_file_changed(self, file_path_text: str) -> None:
        # 防抖：如果是刚刚保存的，忽略这次变化
        current_time = time.time()
        if (current_time - self._last_save_wall_time_seconds) < float(self._ignore_seconds_after_save):
            log_debug("[文件监控] 忽略自身保存触发的变化")
            return

        if not file_path_text:
            return
        log_debug("[文件监控] 检测到文件变化: {}", str(file_path_text))

        # 延迟一小段时间再处理（Windows 文件系统 + 原子写入/重命名覆盖会造成短暂抖动）
        self._debounce_timer.start(int(self._debounce_ms))

    def cleanup(self) -> None:
        if self._debounce_timer.isActive():
            self._debounce_timer.stop()

    # ===== 内部实现 =====

    def _handle_debounced_file_change(self) -> None:
        graph_file_path = self._context.graph_file_path
        if graph_file_path is None or not graph_file_path.exists():
            self._emit_toast("节点图文件已被删除", "error")
            return

        watched_files = set(self._file_watcher.files())
        graph_file_path_text = str(graph_file_path)
        if graph_file_path_text not in watched_files:
            self._file_watcher.addPath(graph_file_path_text)
            log_debug("[文件监控] 已恢复监控: {}", str(graph_file_path))

        watched_graph_id = self._context.graph_id
        active_graph_id = self._get_active_graph_id() or None
        has_local_changes = self._has_local_changes(
            watched_graph_id=watched_graph_id,
            active_graph_id=active_graph_id,
        )

        if not has_local_changes:
            log_debug("[文件监控] 无本地修改，直接重新加载")
            self._reload_graph_from_file()
            self._emit_toast("节点图已更新", "info")
            return

        log_debug("[文件监控] 检测到本地修改，显示冲突对话框")
        self._show_conflict_dialog(graph_file_path)

    def _has_local_changes(self, *, watched_graph_id: Optional[str], active_graph_id: Optional[str]) -> bool:
        if not watched_graph_id or not active_graph_id:
            return False
        if watched_graph_id != active_graph_id:
            return False

        scene = self._get_scene()
        undo_manager = getattr(scene, "undo_manager", None)
        has_changes = getattr(undo_manager, "has_changes", None)
        if callable(has_changes):
            return bool(has_changes())
        return False

    def _reload_graph_from_file(self) -> None:
        # 优先使用当前监控的图 ID；若不存在则回退到主窗口提供的当前图 ID
        target_graph_id: Optional[str] = self._context.graph_id
        if not target_graph_id:
            target_graph_id = self._get_active_graph_id() or None
        if not target_graph_id:
            return

        active_graph_id: Optional[str] = self._get_active_graph_id() or None
        is_reloading_active_graph = bool(active_graph_id and active_graph_id == target_graph_id)

        graph_data = self._resource_manager.load_resource(ResourceType.GRAPH, target_graph_id)
        if not graph_data:
            self._emit_toast("无法加载节点图文件", "error")
            return

        view_transform = None
        view_center = None
        if is_reloading_active_graph:
            view = self._get_view()
            if view is not None:
                view_transform = view.transform()
                view_center = view.mapToScene(view.viewport().rect().center())

        self._emit_graph_reloaded(target_graph_id, graph_data.get("data", graph_data))

        if is_reloading_active_graph and view_transform is not None and view_center is not None:
            view = self._get_view()
            if view is not None:
                view.setTransform(view_transform)
                view.centerOn(view_center)

        if is_reloading_active_graph:
            scene = self._get_scene()
            undo_manager = getattr(scene, "undo_manager", None)
            clear_method = getattr(undo_manager, "clear", None)
            if callable(clear_method):
                clear_method()

        log_debug("[文件监控] 节点图已重新加载，视图位置已恢复")

    def _show_conflict_dialog(self, graph_file_path: Path) -> None:
        from app.ui.dialogs.conflict_resolution_dialog import ConflictResolutionDialog

        graph_name = self._context.graph_id or (self._get_active_graph_id() or "")
        external_modified_time = datetime.fromtimestamp(graph_file_path.stat().st_mtime)

        dialog_parent = self._dialog_parent_provider()
        dialog = ConflictResolutionDialog(
            dialog_parent,
            graph_name,
            local_modified_time=datetime.now(),
            external_modified_time=external_modified_time,
        )

        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return

        choice = dialog.get_user_choice()
        if choice == "keep_local":
            log_debug("[冲突解决] 用户选择保留本地修改")
            self.update_last_save_time()
            self._request_force_save()
            self._emit_toast("已保留您的修改", "info")
            return
        if choice == "use_external":
            log_debug("[冲突解决] 用户选择使用外部版本")
            self._reload_graph_from_file()
            self._emit_toast("已使用外部版本", "info")
            return


