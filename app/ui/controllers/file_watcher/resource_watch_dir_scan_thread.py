from __future__ import annotations

import os
from pathlib import Path

from PyQt6 import QtCore

from .resource_watch_policy import ResourceWatchPolicy


class ResourceWatchDirScanThread(QtCore.QThread):
    """后台线程：扫描资源库目录树，生成需要被监控的目录列表。

    说明：
    - 使用 QThread 子类而不是 `QThread + moveToThread(QObject)`，避免退出阶段 worker QObject
      在错误线程析构导致 Windows `access violation`。
    - 只负责“收集路径”，不触碰 `QFileSystemWatcher`（后者必须在主线程操作）。
    """

    scan_finished = QtCore.pyqtSignal(list)  # list[str]，每项为目录路径字符串

    def __init__(
        self,
        resource_root: Path,
        *,
        active_package_id: str | None = None,
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._resource_root = resource_root
        self._active_package_id = str(active_package_id or "").strip() or None
        self.setObjectName("ResourceWatchDirScanThread")

    def run(self) -> None:
        resource_root = self._resource_root
        if self.isInterruptionRequested():
            self.scan_finished.emit([])
            return
        if not resource_root.exists():
            self.scan_finished.emit([])
            return

        policy = ResourceWatchPolicy.create(
            resource_root_dir=resource_root,
            active_package_id=self._active_package_id,
        )
        packages_root_dir = policy.packages_root_dir
        shared_root_dir = policy.shared_root_dir
        allowed_top_level_names_lower = policy.allowed_top_level_dir_names_lower

        ignored_dir_names = {
            "__pycache__",
            ".git",
            ".idea",
            ".mypy_cache",
            ".pytest_cache",
            ".vscode",
            "__MACOSX",
        }

        def _walk_dirs(start_dir: Path) -> list[str]:
            """收集 start_dir 下所有目录（用于 addPath），并允许在 walk 中剪枝 ignored_dir_names。"""
            dirs: list[str] = []
            for current_dir, sub_dirs, _file_names in os.walk(start_dir):
                if self.isInterruptionRequested():
                    return []
                # 剪枝：避免进入明显无意义/高风险子树
                sub_dirs[:] = [name for name in sub_dirs if name not in ignored_dir_names]
                dirs.append(str(current_dir))
            return dirs

        candidate_dirs: list[str] = []

        # 1) 资源库根与两类入口根目录：必须被监控，用于发现新建的项目存档/共享目录
        candidate_dirs.append(str(resource_root))
        candidate_dirs.append(str(packages_root_dir))
        candidate_dirs.append(str(shared_root_dir))

        # 2) 共享根：只递归监控“资源顶层目录”子树，避免无关目录变化触发刷新
        if shared_root_dir.exists() and shared_root_dir.is_dir():
            candidate_dirs.append(str(shared_root_dir))
            for child in shared_root_dir.iterdir():
                if self.isInterruptionRequested():
                    self.scan_finished.emit([])
                    return
                if not child.is_dir():
                    continue
                if child.name in ignored_dir_names:
                    continue
                if child.name.lower() not in allowed_top_level_names_lower:
                    continue
                candidate_dirs.extend(_walk_dirs(child))

        # 3) 项目存档根：只监控“当前 package_id”（共享根始终监控）
        if packages_root_dir.exists() and packages_root_dir.is_dir():
            candidate_dirs.append(str(packages_root_dir))
            if self._active_package_id:
                package_dir = packages_root_dir / self._active_package_id
                if package_dir.exists() and package_dir.is_dir():
                    candidate_dirs.append(str(package_dir))
                    for child in package_dir.iterdir():
                        if self.isInterruptionRequested():
                            self.scan_finished.emit([])
                            return
                        if not child.is_dir():
                            continue
                        if child.name in ignored_dir_names:
                            continue
                        if child.name.lower() not in allowed_top_level_names_lower:
                            continue
                        candidate_dirs.extend(_walk_dirs(child))

        # 去重（保持大致顺序即可）
        unique_dirs: list[str] = list(dict.fromkeys(candidate_dirs))
        self.scan_finished.emit(unique_dirs)


