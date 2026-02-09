from __future__ import annotations

import time
from collections import deque
from pathlib import Path
from typing import Deque, Optional

from PyQt6 import QtCore

from .resource_watch_dir_scan_thread import ResourceWatchDirScanThread
from .resource_watch_policy import ResourceWatchPolicy
from engine.utils.logging.logger import log_debug


class ResourceWatchRegistry(QtCore.QObject):
    """资源库目录 watcher 注册与维护。

    职责：
    - 后台扫描资源库目录树（QThread），收集目录列表；
    - 主线程分批 addPath，避免一次性 addPath 卡住 UI；
    - directoryChanged 事件触发时，增量扫描新增子目录并补齐 watcher；
    - 记录 addPath 失败次数，供上层决定是否启用“周期性指纹复核”兜底。
    """

    setup_finished = QtCore.pyqtSignal(int, int)  # watched_dir_count, add_failure_count

    def __init__(self, file_watcher: QtCore.QFileSystemWatcher, *, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self._file_watcher = file_watcher

        self._enabled: bool = True
        self._resource_root: Path | None = None
        self._active_package_id: str | None = None
        self._watch_policy: ResourceWatchPolicy | None = None

        self._watch_setup_scheduled: bool = False
        self._watch_scan_thread: Optional[ResourceWatchDirScanThread] = None

        self._pending_watch_dirs: Deque[Path] = deque()
        self._watch_owned_dir_texts: set[str] = set()
        self._watch_owned_dirs: list[Path] = []

        self._watch_setup_started_at: float = 0.0
        self._watch_added_count: int = 0
        self._watch_add_failure_count: int = 0

        self._pending_incremental_scan_roots: Deque[Path] = deque()
        self._incremental_scan_scheduled: bool = False

        self._batch_add_limit: int = 120
        self._incremental_scan_budget: int = 80

    @property
    def add_failure_count(self) -> int:
        return int(self._watch_add_failure_count)

    @property
    def owned_watch_dir_count(self) -> int:
        return len(self._watch_owned_dirs)

    def set_enabled(self, enabled: bool) -> None:
        normalized = bool(enabled)
        if normalized == self._enabled:
            return
        self._enabled = normalized
        if not self._enabled:
            self._stop_background_scan_if_any()
            self._pending_watch_dirs.clear()
            self._pending_incremental_scan_roots.clear()
            self._incremental_scan_scheduled = False
            self._watch_setup_scheduled = False
            self._remove_owned_watch_dirs()
            return

    def set_active_package_id(self, package_id: str | None) -> None:
        """设置 watcher 当前关注的项目存档作用域，并重建目录监控。

        约定：
        - None/""：仅监控共享根（共享对所有存档可见）；
        - 非空：监控共享根 + 项目存档/<package_id>/ 下的资源目录子树。
        """
        normalized = str(package_id or "").strip() or None
        if normalized == self._active_package_id:
            return
        self._active_package_id = normalized
        self._refresh_watch_policy()
        self.rebuild_watchers()

    def rebuild_watchers(self) -> None:
        """重建资源库目录 watcher（用于切换存档后收敛监听范围）。"""
        if not self._enabled:
            return
        resource_root = self._resource_root
        if resource_root is None:
            return
        self._stop_background_scan_if_any()
        self._pending_watch_dirs.clear()
        self._pending_incremental_scan_roots.clear()
        self._incremental_scan_scheduled = False
        self._watch_setup_scheduled = False
        self._remove_owned_watch_dirs()
        self.schedule_initial_setup(resource_root)

    def schedule_initial_setup(self, resource_root: Path) -> None:
        """延后初始化资源库目录监控（非阻塞 UI）。"""
        if not self._enabled:
            return
        if self._watch_setup_scheduled:
            return
        self._resource_root = resource_root
        self._refresh_watch_policy()
        self._watch_setup_scheduled = True
        QtCore.QTimer.singleShot(0, lambda: self._start_initial_setup(resource_root))

    def handle_directory_changed(self, changed_dir: Path) -> None:
        """记录近期触发 directoryChanged 的目录，用于增量补齐 watcher。"""
        if not self._enabled:
            return
        if not changed_dir:
            return
        self._pending_incremental_scan_roots.append(changed_dir)
        self._schedule_incremental_scan()

    # ===== 初始扫描与分批 addPath =====

    def _start_initial_setup(self, resource_root: Path) -> None:
        if not self._enabled:
            return
        if self._watch_scan_thread is not None:
            return

        self._watch_setup_started_at = time.monotonic()
        self._watch_added_count = 0
        self._watch_add_failure_count = 0

        self._watch_owned_dir_texts.clear()
        self._watch_owned_dirs.clear()

        scan_thread = ResourceWatchDirScanThread(
            resource_root,
            active_package_id=self._active_package_id,
            parent=self,
        )
        scan_thread.scan_finished.connect(self._on_scanned_dir_paths)
        scan_thread.finished.connect(self._on_scan_thread_finished)
        scan_thread.finished.connect(scan_thread.deleteLater)

        self._watch_scan_thread = scan_thread
        scan_thread.start()

    def _on_scanned_dir_paths(self, dir_paths: list) -> None:
        """后台扫描完成：将目录队列交给主线程分批添加。"""
        if not self._enabled:
            return
        pending_dirs: Deque[Path] = deque()
        for path_value in dir_paths:
            if not isinstance(path_value, str) or not path_value:
                continue
            candidate_path = Path(path_value)
            if not self._should_watch_directory(candidate_path):
                continue
            pending_dirs.append(candidate_path)

        self._pending_watch_dirs.extend(pending_dirs)
        self._add_watchers_in_batches()

    def _on_scan_thread_finished(self) -> None:
        # 线程对象由 Qt parent 关系托管；这里只清空引用，允许后续重新调度初始扫描。
        self._watch_scan_thread = None

    def _add_watchers_in_batches(self) -> None:
        """在主线程分批添加 watcher，避免一次性 addPath 卡住 UI。"""
        if not self._enabled:
            self._pending_watch_dirs.clear()
            return

        existing_dirs = set(self._file_watcher.directories())
        added_in_batch = 0

        while self._pending_watch_dirs and added_in_batch < self._batch_add_limit:
            directory_path = self._pending_watch_dirs.popleft()
            if not self._should_watch_directory(directory_path):
                continue
            if not directory_path.exists() or not directory_path.is_dir():
                continue

            path_text = str(directory_path)
            if path_text in self._watch_owned_dir_texts:
                continue

            if path_text in existing_dirs:
                self._watch_owned_dir_texts.add(path_text)
                self._watch_owned_dirs.append(directory_path)
                continue

            success = self._file_watcher.addPath(path_text)
            if success:
                self._watch_owned_dir_texts.add(path_text)
                self._watch_owned_dirs.append(directory_path)
                self._watch_added_count += 1
                existing_dirs.add(path_text)
            else:
                self._watch_add_failure_count += 1

            added_in_batch += 1

        if self._pending_watch_dirs:
            QtCore.QTimer.singleShot(0, self._add_watchers_in_batches)
            return

        elapsed_seconds = time.monotonic() - self._watch_setup_started_at
        log_debug(
            "[文件监控] 资源库目录监控已建立：watched_dirs={} added_new={} add_failures={} elapsed={:.2f}s",
            int(len(self._watch_owned_dirs)),
            int(self._watch_added_count),
            int(self._watch_add_failure_count),
            float(elapsed_seconds),
        )

        self.setup_finished.emit(int(len(self._watch_owned_dirs)), int(self._watch_add_failure_count))

    # ===== 增量补齐：扫描新增子目录 =====

    def _schedule_incremental_scan(self) -> None:
        if not self._enabled:
            self._pending_incremental_scan_roots.clear()
            self._incremental_scan_scheduled = False
            return
        if self._incremental_scan_scheduled:
            return
        self._incremental_scan_scheduled = True
        QtCore.QTimer.singleShot(0, self._scan_subdirs_in_batches)

    def _scan_subdirs_in_batches(self) -> None:
        """分批扫描近期变化目录的子目录，将新目录加入 watcher 队列。"""
        if not self._enabled:
            self._pending_incremental_scan_roots.clear()
            self._incremental_scan_scheduled = False
            return

        ignored_dir_names = {
            "__pycache__",
            ".git",
            ".idea",
            ".mypy_cache",
            ".pytest_cache",
            ".vscode",
            "__MACOSX",
        }

        existing_dir_texts = set(self._file_watcher.directories())
        existing_dir_texts.update(self._watch_owned_dir_texts)
        for queued_dir in self._pending_watch_dirs:
            existing_dir_texts.add(str(queued_dir))

        scanned_count = 0
        while self._pending_incremental_scan_roots and scanned_count < self._incremental_scan_budget:
            scan_root = self._pending_incremental_scan_roots.popleft()
            scanned_count += 1
            if not scan_root.exists() or not scan_root.is_dir():
                continue

            for child in scan_root.iterdir():
                if not child.is_dir():
                    continue
                if child.name in ignored_dir_names:
                    continue
                if not self._should_watch_directory(child):
                    continue
                child_text = str(child)
                if child_text in existing_dir_texts:
                    continue

                self._pending_watch_dirs.append(child)
                existing_dir_texts.add(child_text)
                # 仅对“新发现的目录”继续向下扫描，以覆盖“批量创建多级目录”的场景
                self._pending_incremental_scan_roots.append(child)

        # 追加 watcher（分批 addPath，避免 UI 卡顿）
        if self._pending_watch_dirs:
            self._add_watchers_in_batches()

        if self._pending_incremental_scan_roots:
            QtCore.QTimer.singleShot(0, self._scan_subdirs_in_batches)
            return

        self._incremental_scan_scheduled = False

    # ===== 过滤策略：仅监控“资源目录子树” =====

    def _should_watch_directory(self, directory_path: Path) -> bool:
        """决定某个目录是否应被 QFileSystemWatcher 递归监控。

        核心原则：仅监控“资源目录子树”（元件库/实体摆放/节点图/战斗预设/管理配置/复合节点库）。
        这能显著降低：
        - 非资源目录（解析产物/工具输出）导致的 directoryChanged 风暴；
        - 随之触发的无意义指纹扫描与 UI 卡顿/崩溃风险。
        """
        if directory_path is None:
            return False
        policy = self._watch_policy
        if policy is None:
            # 未完成 setup 前的兜底：保持旧行为（不拦截）。
            return True
        return bool(policy.should_watch_directory(directory_path))

    def _refresh_watch_policy(self) -> None:
        resource_root = self._resource_root
        if resource_root is None:
            self._watch_policy = None
            return
        self._watch_policy = ResourceWatchPolicy.create(
            resource_root_dir=resource_root,
            active_package_id=self._active_package_id,
        )

    # ===== 清理 =====

    def cleanup(self) -> None:
        # 关闭期间避免后续 singleShot 继续调度 addPath / 增量扫描
        self._enabled = False
        self._stop_background_scan_if_any()
        self._pending_watch_dirs.clear()
        self._pending_incremental_scan_roots.clear()
        self._incremental_scan_scheduled = False
        self._remove_owned_watch_dirs()

    def _stop_background_scan_if_any(self) -> None:
        scan_thread = self._watch_scan_thread
        if scan_thread is None:
            return
        scan_thread.requestInterruption()
        scan_thread.wait()
        self._watch_scan_thread = None

    def _remove_owned_watch_dirs(self) -> None:
        watched_directories = set(self._file_watcher.directories())
        for directory in self._watch_owned_dirs:
            path_text = str(directory)
            if path_text in watched_directories:
                self._file_watcher.removePath(path_text)
        self._watch_owned_dirs.clear()
        self._watch_owned_dir_texts.clear()


