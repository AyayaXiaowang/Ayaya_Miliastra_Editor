"""文件监控管理器 - 监控外部文件修改和冲突解决"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional, Callable

from PyQt6 import QtCore, QtWidgets

from engine.resources.resource_manager import ResourceManager, ResourceType
from engine.resources.definition_schema_view import (
    invalidate_default_struct_cache,
    invalidate_default_signal_cache,
)
from engine.graph.models.graph_config import GraphConfig


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
        
        # 状态
        self.current_graph_file_path: Optional[Path] = None
        # 当前正在监控的节点图 ID（可能来自图编辑器或节点图库选中）
        self._watched_graph_id: Optional[str] = None
        self._last_save_time: float = 0  # 记录最后保存时间，用于防抖
        self._is_cleaning_up = False  # 标记是否正在清理（避免重复清理）
        
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

        # 启动时为资源库 JSON 目录建立监控
        self._setup_resource_watchers()
    
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

    def _setup_resource_watchers(self) -> None:
        """为资源库目录（含子目录）添加文件系统监控。
        
        QFileSystemWatcher.directoryChanged 只有在被监控的目录本身发生变化时才会触发，
        修改子目录中的文件不会触发上级目录的变更信号，因此需要递归监控所有子目录。
        """
        self._resource_watch_dirs.clear()
        resource_root = self.resource_manager.resource_library_dir
        if not resource_root.exists():
            return

        # 需要递归监控的根目录列表
        root_dirs_to_watch = [
            resource_root / "实例",
            resource_root / "元件库",
            resource_root / "管理配置",
            resource_root / "战斗预设",
            resource_root / "节点图",
            resource_root / "复合节点库",
            resource_root / "地图索引",
        ]
        
        # 应该忽略的目录名（如 __pycache__）
        ignored_dir_names = {"__pycache__", ".git", ".vscode", "__MACOSX"}
        
        # 收集所有需要监控的目录（包括根目录及其子目录）
        candidate_dirs = [resource_root]
        for root_dir in root_dirs_to_watch:
            if not root_dir.exists() or not root_dir.is_dir():
                continue
            candidate_dirs.append(root_dir)
            # 递归收集所有子目录
            for sub_dir in root_dir.rglob("*"):
                if sub_dir.is_dir() and sub_dir.name not in ignored_dir_names:
                    candidate_dirs.append(sub_dir)
        
        existing_dirs = set(self.file_watcher.directories())

        for directory in candidate_dirs:
            if not directory.exists() or not directory.is_dir():
                continue
            path_str = str(directory)
            if path_str in existing_dirs:
                self._resource_watch_dirs.append(directory)
                continue
            success = self.file_watcher.addPath(path_str)
            if success:
                self._resource_watch_dirs.append(directory)
                print(f"[文件监控] 开始监控资源库目录: {directory}")
    
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
        
        # 检查文件是否还存在
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            self.show_toast.emit("节点图文件已被删除", "error")
            return
        
        # 延迟一小段时间再处理（Windows文件系统延迟）
        QtCore.QTimer.singleShot(200, self._handle_file_change)
    
    def _handle_file_change(self) -> None:
        """实际处理文件变化（延迟执行）"""
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
        from ui.dialogs.conflict_resolution_dialog import ConflictResolutionDialog
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
        if self._is_cleaning_up:
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
        self.file_watcher.fileChanged.disconnect()
        self.file_watcher.directoryChanged.disconnect()
        
        print(f"[文件监控] 资源清理完成")
        self._is_cleaning_up = False
    
    def get_watched_files_count(self) -> int:
        """获取当前监控的文件数量（用于调试）"""
        return len(self.file_watcher.files())
    
    def __del__(self):
        """析构函数 - 确保资源被释放"""
        if not self._is_cleaning_up:
            self.cleanup()

