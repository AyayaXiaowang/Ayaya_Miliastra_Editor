"""文件监控管理器 - 监控外部文件修改和冲突解决"""

from __future__ import annotations

from collections import deque
import time
from pathlib import Path
from typing import Optional, Callable, Deque, Iterable

from PyQt6 import QtCore, QtWidgets

from engine.configs.settings import settings
from engine.resources.resource_manager import ResourceManager, ResourceType
from engine.resources.definition_schema_view import (
    invalidate_default_struct_cache,
    invalidate_default_signal_cache,
)
from engine.graph.models.graph_config import GraphConfig


class _ResourceWatchDirScanner(QtCore.QObject):
    """后台线程：扫描资源库目录树，生成需要被监控的目录列表。

    设计目标：
    - 避免在主线程内执行 `Path.rglob()` 等可能耗时的 IO 扫描；
    - 仅负责“收集路径”，不触碰 `QFileSystemWatcher`（后者必须在主线程操作）。
    """

    scan_finished = QtCore.pyqtSignal(list)  # list[str]，每项为目录路径字符串

    def __init__(self, resource_root: Path) -> None:
        super().__init__()
        self._resource_root = resource_root

    @QtCore.pyqtSlot()
    def run(self) -> None:
        resource_root = self._resource_root
        if not resource_root.exists():
            self.scan_finished.emit([])
            return

        # 需要递归监控的根目录列表
        root_dirs_to_watch: list[Path] = [
            resource_root,
            resource_root / "实例",
            resource_root / "元件库",
            resource_root / "管理配置",
            resource_root / "战斗预设",
            resource_root / "节点图",
            resource_root / "复合节点库",
            resource_root / "功能包索引",
        ]

        ignored_dir_names = {"__pycache__", ".git", ".vscode", "__MACOSX"}

        candidate_dirs: list[str] = []
        for root_dir in root_dirs_to_watch:
            if not root_dir.exists() or not root_dir.is_dir():
                continue
            candidate_dirs.append(str(root_dir))
            for sub_dir in root_dir.rglob("*"):
                if not sub_dir.is_dir():
                    continue
                if sub_dir.name in ignored_dir_names:
                    continue
                candidate_dirs.append(str(sub_dir))

        # 去重（保持大致顺序即可）
        unique_dirs: list[str] = list(dict.fromkeys(candidate_dirs))
        self.scan_finished.emit(unique_dirs)


class FileWatcherManager(QtCore.QObject):
    """文件系统监控和冲突解决管理器"""
    
    # 信号定义
    reload_graph_requested = QtCore.pyqtSignal()
    show_toast = QtCore.pyqtSignal(str, str)  # message, type
    conflict_detected = QtCore.pyqtSignal()
    graph_reloaded = QtCore.pyqtSignal(str, dict)  # graph_id, graph_data
    force_save_requested = QtCore.pyqtSignal()  # 强制保存本地版本
    
    def __init__(
        self,
        resource_manager: ResourceManager,
        parent: Optional[QtCore.QObject] = None
    ):
        super().__init__(parent)
        
        self.resource_manager = resource_manager
        
        # 文件监控器
        self.file_watcher = QtCore.QFileSystemWatcher()
        self.file_watcher.fileChanged.connect(self._on_graph_file_changed)
        self.file_watcher.directoryChanged.connect(self._on_resource_directory_changed)
        self._watcher_signals_connected: bool = True
        
        # 状态
        self.current_graph_file_path: Optional[Path] = None
        # 当前正在监控的节点图 ID（可能来自图编辑器或节点图库选中）
        self._watched_graph_id: Optional[str] = None
        self._last_save_time: float = 0  # 记录最后保存时间，用于防抖
        self._is_cleaning_up = False  # 标记是否正在清理（避免重复清理）
        self._has_cleaned_up: bool = False  # 标记是否已完成清理（确保 cleanup 幂等）
        
        # 用于获取当前图ID和场景（由主窗口设置）
        self.get_current_graph_id = None
        self.get_scene = None
        self.get_view = None
        # 资源库变更时由主窗口注入的刷新回调
        self.on_resource_library_changed: Optional[Callable[[], None]] = None
        
        # 清理定时器（延迟处理文件变化）
        self._change_timer: Optional[QtCore.QTimer] = None
        # 资源库目录变化的防抖定时器
        self._resource_change_timer: Optional[QtCore.QTimer] = None
        # 已监控的资源库子目录
        self._resource_watch_dirs: list[Path] = []
        # 最近一次记录的资源库指纹
        self._resource_library_fingerprint: str = self.resource_manager.get_resource_library_fingerprint()
        # 是否启用资源库自动刷新（由全局设置控制，可在运行时切换）
        self._resource_auto_refresh_enabled: bool = bool(
            getattr(settings, "RESOURCE_LIBRARY_AUTO_REFRESH_ENABLED", True)
        )

        # 资源库目录监控初始化：延后到事件循环启动后再进行，
        # 避免在主线程构造阶段（窗口尚未显示）执行递归扫描导致启动卡顿。
        self._resource_watch_setup_scheduled: bool = False
        self._resource_watch_scan_thread: Optional[QtCore.QThread] = None
        self._resource_watch_scanner: Optional[_ResourceWatchDirScanner] = None
        self._pending_resource_watch_dirs: Deque[Path] = deque()
        self._resource_watch_setup_started_at: float = 0.0
        self._resource_watch_added_count: int = 0

        if self._resource_auto_refresh_enabled:
            self._schedule_resource_watchers_setup()
    
    def setup_file_watcher(self, graph_id: str) -> None:
        """设置文件监控（带资源清理）"""
        # 记录当前监控的图 ID
        self._watched_graph_id = graph_id or None
        # 取消之前的延迟计时器
        if self._change_timer and self._change_timer.isActive():
            self._change_timer.stop()
            self._change_timer = None
        
        # 移除之前的监控（带安全检查）
        if self.current_graph_file_path:
            watched_files = self.file_watcher.files()
            if str(self.current_graph_file_path) in watched_files:
                self.file_watcher.removePath(str(self.current_graph_file_path))
                print(f"[文件监控] 停止监控: {self.current_graph_file_path}")
            self.current_graph_file_path = None
        
        # 添加新的监控（节点图文件）
        if graph_id:
            file_path = self._get_graph_file_path(graph_id)
            if file_path and file_path.exists():
                self.current_graph_file_path = file_path
                success = self.file_watcher.addPath(str(file_path))
                if success:
                    print(f"[文件监控] 开始监控: {file_path}")
                else:
                    print(f"[文件监控] 监控添加失败: {file_path}")
                    self.current_graph_file_path = None

    def _schedule_resource_watchers_setup(self) -> None:
        """延后初始化资源库目录监控（非阻塞 UI）。"""
        if not self._resource_auto_refresh_enabled:
            return
        if self._resource_watch_setup_scheduled:
            return
        self._resource_watch_setup_scheduled = True
        QtCore.QTimer.singleShot(0, self._start_resource_watchers_setup)

    def _start_resource_watchers_setup(self) -> None:
        """启动后台扫描线程，扫描完成后在主线程分批添加 watcher。"""
        if not self._resource_auto_refresh_enabled:
            return
        if self._resource_watch_scan_thread is not None:
            return

        self._resource_watch_setup_started_at = time.monotonic()
        self._resource_watch_added_count = 0
        self._resource_watch_dirs.clear()

        resource_root = self.resource_manager.resource_library_dir
        scan_thread = QtCore.QThread(self)
        scanner = _ResourceWatchDirScanner(resource_root)
        scanner.moveToThread(scan_thread)

        scan_thread.started.connect(scanner.run)
        scanner.scan_finished.connect(self._on_resource_watch_dirs_scanned)
        scanner.scan_finished.connect(scan_thread.quit)
        scan_thread.finished.connect(scanner.deleteLater)
        scan_thread.finished.connect(scan_thread.deleteLater)

        self._resource_watch_scan_thread = scan_thread
        self._resource_watch_scanner = scanner
        scan_thread.start()

    def _on_resource_watch_dirs_scanned(self, dir_paths: list) -> None:
        """后台扫描完成：将目录队列交给主线程分批添加。"""
        # 这里使用 list（来自 Qt 信号），元素为 str
        pending_dirs: Deque[Path] = deque()
        for path_value in dir_paths:
            if not isinstance(path_value, str) or not path_value:
                continue
            pending_dirs.append(Path(path_value))

        self._pending_resource_watch_dirs = pending_dirs
        self._add_resource_watchers_in_batches()

    def _add_resource_watchers_in_batches(self) -> None:
        """在主线程分批添加 watcher，避免一次性 addPath 卡住 UI。"""
        if not self._resource_auto_refresh_enabled:
            self._pending_resource_watch_dirs.clear()
            return

        existing_dirs = set(self.file_watcher.directories())
        batch_limit = 120  # 每帧最多添加多少个目录 watcher
        added_in_batch = 0

        while self._pending_resource_watch_dirs and added_in_batch < batch_limit:
            directory_path = self._pending_resource_watch_dirs.popleft()
            if not directory_path.exists() or not directory_path.is_dir():
                continue
            path_str = str(directory_path)
            if path_str in existing_dirs:
                self._resource_watch_dirs.append(directory_path)
                continue
            success = self.file_watcher.addPath(path_str)
            if success:
                self._resource_watch_dirs.append(directory_path)
                self._resource_watch_added_count += 1
                existing_dirs.add(path_str)
            added_in_batch += 1

        if self._pending_resource_watch_dirs:
            QtCore.QTimer.singleShot(0, self._add_resource_watchers_in_batches)
            return

        elapsed_seconds = time.monotonic() - self._resource_watch_setup_started_at
        print(
            "[文件监控] 资源库目录监控已建立："
            f"watched_dirs={len(self._resource_watch_dirs)}, "
            f"added_new={self._resource_watch_added_count}, "
            f"elapsed={elapsed_seconds:.2f}s"
        )

        self._resource_watch_scan_thread = None
        self._resource_watch_scanner = None
    
    def _get_graph_file_path(self, graph_id: str) -> Optional[Path]:
        """获取节点图的文件路径"""
        if not graph_id:
            return None
        return self.resource_manager.get_graph_file_path(graph_id)
    
    def _on_graph_file_changed(self, file_path: str) -> None:
        """文件变化处理"""
        # 防抖：如果是刚刚保存的，忽略这次变化
        current_time = time.time()
        if current_time - self._last_save_time < 1.0:  # 1秒内的变化忽略
            print(f"[文件监控] 忽略自身保存触发的变化")
            return
        
        print(f"[文件监控] 检测到文件变化: {file_path}")

        # 延迟一小段时间再处理（Windows 文件系统 + 编辑器原子写入/重命名会造成短暂抖动）
        # 使用可取消的单次计时器合并多次 fileChanged 事件，避免重复重载。
        if self._change_timer is None:
            self._change_timer = QtCore.QTimer(self)
            self._change_timer.setSingleShot(True)
            self._change_timer.timeout.connect(self._handle_file_change)
        self._change_timer.start(200)
    
    def _handle_file_change(self) -> None:
        """实际处理文件变化（延迟执行）"""
        # 某些编辑器会用“删除旧文件→写新文件→重命名覆盖”的方式保存，
        # 这会导致 QFileSystemWatcher 在一次变更中短暂失去监控或看到文件不存在。
        # 这里统一在延迟后检查一次当前监控目标，并尽量恢复对该路径的 watcher。
        graph_file_path = self.current_graph_file_path
        if graph_file_path is None or not graph_file_path.exists():
            self.show_toast.emit("节点图文件已被删除", "error")
            return

        watched_files = set(self.file_watcher.files())
        graph_file_path_text = str(graph_file_path)
        if graph_file_path_text not in watched_files:
            self.file_watcher.addPath(graph_file_path_text)
            print(f"[文件监控] 已恢复监控: {graph_file_path}")

        # 检测是否有本地未保存的修改（仅当当前编辑的图与监控目标相同时才认为有冲突）
        has_local_changes = False
        active_graph_id: Optional[str] = None
        if callable(self.get_current_graph_id):
            active_graph_id = self.get_current_graph_id() or None
        watched_graph_id = self._watched_graph_id
        if watched_graph_id and active_graph_id and watched_graph_id == active_graph_id and self.get_scene:
            scene = self.get_scene()
            if scene and hasattr(scene, "undo_manager"):
                has_local_changes = scene.undo_manager.has_changes()
        
        if not has_local_changes:
            # 无冲突：直接重新加载
            print(f"[文件监控] 无本地修改，直接重新加载")
            self._reload_graph_from_file()
            self.show_toast.emit("节点图已更新", "info")
        else:
            # 有冲突：显示冲突对话框
            print(f"[文件监控] 检测到本地修改，显示冲突对话框")
            self._show_conflict_dialog()
    
    def _on_resource_directory_changed(self, directory_path: str) -> None:
        """资源库目录发生变化（新增/删除/重命名 JSON 等）。"""
        if not self._resource_auto_refresh_enabled:
            return
        if not directory_path:
            return
        if self._resource_change_timer is None:
            self._resource_change_timer = QtCore.QTimer(self)
            self._resource_change_timer.setSingleShot(True)
            self._resource_change_timer.timeout.connect(self._handle_resource_directory_change)
        # 合并短时间内的多次目录变更事件
        self._resource_change_timer.start(200)
    
    def _handle_resource_directory_change(self) -> None:
        """处理资源库目录变化：触发资源刷新与提示。"""
        latest_fingerprint = self.resource_manager.compute_resource_library_fingerprint()
        baseline_fingerprint = self.resource_manager.get_resource_library_fingerprint()
        if latest_fingerprint == baseline_fingerprint:
            return

        self.resource_manager.set_resource_library_fingerprint(latest_fingerprint)
        self._resource_library_fingerprint = latest_fingerprint

        # 刷新结构体和信号定义的全局缓存
        # 这些定义存放在 管理配置/结构体定义/ 和 管理配置/信号/ 目录下
        # 由于是全局单例，直接调用刷新函数即可
        invalidate_default_struct_cache()
        invalidate_default_signal_cache()
        print("[文件监控] 已刷新结构体和信号定义缓存")

        if self.on_resource_library_changed is not None:
            self.on_resource_library_changed()

        # 刷新 UI 后再次同步指纹基线，确保后续保存不会因为 UI 刷新过程中的
        # 自动保存操作而误判为"外部修改"
        self.resource_manager.refresh_resource_library_fingerprint()
        self._resource_library_fingerprint = self.resource_manager.get_resource_library_fingerprint()

        self.show_toast.emit("资源库已更新", "info")
    
    def _reload_graph_from_file(self) -> None:
        """从文件重新加载节点图"""
        # 优先使用当前监控的图 ID；若不存在则回退到主窗口提供的当前图 ID
        target_graph_id: Optional[str] = self._watched_graph_id
        if not target_graph_id and callable(self.get_current_graph_id):
            target_graph_id = self.get_current_graph_id() or None
        if not target_graph_id:
            return

        # 判断此次重载是否针对当前编辑器正在编辑的图，用于决定是否需要维护视图与撤销栈
        active_graph_id: Optional[str] = None
        if callable(self.get_current_graph_id):
            active_graph_id = self.get_current_graph_id() or None
        is_reloading_active_graph = bool(active_graph_id and active_graph_id == target_graph_id)
        
        # 加载最新的节点图数据
        graph_data = self.resource_manager.load_resource(
            ResourceType.GRAPH,
            target_graph_id,
        )
        
        if not graph_data:
            self.show_toast.emit("无法加载节点图文件", "error")
            return
        
        # 若正在重载当前编辑器中的图，则保存视图状态（变换矩阵 + 场景中心点）
        view_transform = None
        view_center = None
        if is_reloading_active_graph and self.get_view:
            view = self.get_view()
            if view:
                view_transform = view.transform()
                view_center = view.mapToScene(view.viewport().rect().center())
        
        # 发送重新加载信号（由 GraphEditorController 和主窗口处理）
        self.graph_reloaded.emit(target_graph_id, graph_data.get("data", graph_data))
        
        # 若重载的是当前编辑器中的图，则恢复视图状态
        if is_reloading_active_graph and view_transform and view_center and self.get_view:
            view = self.get_view()
            if view:
                view.setTransform(view_transform)
                view.centerOn(view_center)
        
        # 仅在重载当前编辑器中的图时清空撤销记录（因为加载了新版本）
        if is_reloading_active_graph and self.get_scene:
            scene = self.get_scene()
            if scene and hasattr(scene, "undo_manager"):
                scene.undo_manager.clear()
        
        print(f"[文件监控] 节点图已重新加载，视图位置已恢复")
    
    def _show_conflict_dialog(self) -> None:
        """显示冲突解决对话框"""
        from app.ui.dialogs.conflict_resolution_dialog import ConflictResolutionDialog
        from datetime import datetime
        
        # 获取节点图名称
        graph_name = ""
        # 优先使用监控目标 ID，回退到当前编辑图 ID
        if self._watched_graph_id:
            graph_name = self._watched_graph_id
        elif callable(self.get_current_graph_id):
            graph_name = self.get_current_graph_id() or ""
        
        # 创建对话框
        dialog = ConflictResolutionDialog(
            None,  # parent会在显示时设置
            graph_name,
            local_modified_time=datetime.now(),  # 本地修改时间（近似）
            external_modified_time=None  # 外部修改时间（可以从文件属性获取）
        )
        
        # 显示对话框
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            choice = dialog.get_user_choice()
            
            if choice == "keep_local":
                # 保留本地修改：重新保存（覆盖外部版本）
                print(f"[冲突解决] 用户选择保留本地修改")
                self._last_save_time = time.time()
                self.force_save_requested.emit()
                self.show_toast.emit("已保留您的修改", "info")
            
            elif choice == "use_external":
                # 使用外部版本：重新加载
                print(f"[冲突解决] 用户选择使用外部版本")
                self._reload_graph_from_file()
                self.show_toast.emit("已使用外部版本", "info")
    
    def update_last_save_time(self) -> None:
        """更新最后保存时间（由外部在保存时调用）"""
        self._last_save_time = time.time()
    
    def cleanup(self) -> None:
        """清理文件监控（防止资源泄露）"""
        if self._is_cleaning_up or self._has_cleaned_up:
            return  # 避免重复清理
        
        self._is_cleaning_up = True
        # 停止所有计时器
        if self._change_timer and self._change_timer.isActive():
            self._change_timer.stop()
            self._change_timer.deleteLater()
            self._change_timer = None
        if self._resource_change_timer and self._resource_change_timer.isActive():
            self._resource_change_timer.stop()
            self._resource_change_timer.deleteLater()
            self._resource_change_timer = None
        
        # 移除所有文件与目录监控
        watched_files = self.file_watcher.files()
        if watched_files:
            for file_path in watched_files:
                self.file_watcher.removePath(file_path)
                print(f"[文件监控] 清理监控: {file_path}")
        watched_dirs = self.file_watcher.directories()
        if watched_dirs:
            for directory_path in watched_dirs:
                self.file_watcher.removePath(directory_path)
                print(f"[文件监控] 清理目录监控: {directory_path}")
        
        # 清空状态
        self.current_graph_file_path = None
        
        # 断开信号连接（防止内存泄露）
        if self._watcher_signals_connected:
            self.file_watcher.fileChanged.disconnect(self._on_graph_file_changed)
            self.file_watcher.directoryChanged.disconnect(self._on_resource_directory_changed)
            self._watcher_signals_connected = False
        
        print(f"[文件监控] 资源清理完成")
        self._has_cleaned_up = True
        self._is_cleaning_up = False
    
    def set_resource_auto_refresh_enabled(self, enabled: bool) -> None:
        """启用或关闭资源库自动刷新（仅影响资源库目录监控，不影响当前图文件监控）。

        Args:
            enabled: True 启用自动刷新；False 关闭自动刷新，仅保留手动“更新”入口。
        """
        normalized_enabled = bool(enabled)
        if normalized_enabled == self._resource_auto_refresh_enabled:
            return
        
        self._resource_auto_refresh_enabled = normalized_enabled
        
        if not normalized_enabled:
            # 关闭自动刷新：移除所有资源库目录监控，保留当前图文件监控。
            if self._resource_watch_dirs:
                watched_directories = set(self.file_watcher.directories())
                for directory in self._resource_watch_dirs:
                    path_str = str(directory)
                    if path_str in watched_directories:
                        self.file_watcher.removePath(path_str)
                self._resource_watch_dirs.clear()
            self._pending_resource_watch_dirs.clear()
            self._resource_watch_setup_scheduled = False
            return
        
        # 启用自动刷新：根据当前资源库目录结构重新建立监控。
        self._schedule_resource_watchers_setup()
    
    def get_watched_files_count(self) -> int:
        """获取当前监控的文件数量（用于调试）"""
        return len(self.file_watcher.files())
    