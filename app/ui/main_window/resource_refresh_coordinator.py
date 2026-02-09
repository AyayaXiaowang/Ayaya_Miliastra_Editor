from __future__ import annotations

import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from PyQt6 import QtCore

from engine.resources.resource_file_ops import ResourceFileOps
from engine.resources.resource_index_builder import ResourceIndexBuilder, ResourceIndexData
from engine.resources.resource_index_service import ResourceIndexService
from engine.resources.resource_state import ResourceIndexState
from engine.utils.logging.logger import log_debug, log_warn
from engine.utils.resource_library_layout import get_packages_root_dir, get_shared_root_dir


@dataclass(frozen=True, slots=True)
class ResourceIndexSnapshot:
    """后台构建完成的“资源索引 + 指纹”快照（主线程提交替换用）。"""

    index_data: ResourceIndexData
    resource_library_fingerprint: str
    active_package_id: str | None


def _compute_composite_library_fingerprint(
    *,
    resource_library_dir: Path,
    active_package_id: str | None,
    should_abort: Optional[Callable[[], bool]] = None,
) -> str:
    """计算“复合节点库”指纹片段（与 ResourceManagerFingerprintMixin 口径一致）。"""
    roots: list[Path] = []
    shared_root = get_shared_root_dir(resource_library_dir)
    if shared_root.exists() and shared_root.is_dir():
        roots.append(shared_root)
    active_package_text = str(active_package_id or "").strip()
    if active_package_text:
        package_root = get_packages_root_dir(resource_library_dir) / active_package_text
        if package_root.exists() and package_root.is_dir():
            roots.append(package_root)

    composite_file_count = 0
    composite_latest_mtime = 0.0
    for root in roots:
        if should_abort is not None and should_abort():
            break
        composite_dir = (root / "复合节点库").resolve()
        count, latest_mtime = ResourceIndexBuilder._scan_dir_for_fingerprint(  # type: ignore[attr-defined]
            composite_dir,
            file_suffix=".py",
            recursive=True,
            should_abort=should_abort,
        )
        composite_file_count += int(count)
        if float(latest_mtime) > composite_latest_mtime:
            composite_latest_mtime = float(latest_mtime)

    return f"复合节点库:{int(composite_file_count)}:{round(float(composite_latest_mtime), 3)}"


def build_resource_index_snapshot(
    *,
    workspace_path: Path,
    resource_library_dir: Path,
    active_package_id: str | None,
) -> ResourceIndexSnapshot:
    """构建资源索引快照（后台线程执行）。

    约束：
    - 不触碰主进程内的 ResourceManager 状态（避免线程不安全）；
    - 仅做磁盘扫描/缓存命中与必要的“文件名同步”写回；
    - 输出结果由主线程一次性提交替换（O(1)）。
    """
    started_monotonic = float(time.monotonic())
    active_package_text = str(active_package_id or "").strip() or None
    builder = ResourceIndexBuilder(workspace_path, resource_library_dir)
    builder.set_active_package_id(active_package_text)

    # 复用 ResourceIndexService 的 name 同步策略（并写入其去重状态文件），但索引状态使用临时对象，
    # 仅用于产出“快照结果”，避免后台线程写入主进程内的索引 dict。
    index_state = ResourceIndexState()
    file_ops = ResourceFileOps(resource_library_dir)
    index_service = ResourceIndexService(
        workspace_path,
        builder,
        file_ops,
        index_state,
    )
    index_service.load_name_sync_state()

    cached = builder.try_load_from_cache()
    if cached is not None:
        index_data = cached
    else:
        index_data = builder.build_index(index_service._check_and_sync_name)  # type: ignore[attr-defined]

    base_fingerprint = builder.compute_resources_fingerprint()
    composite_fingerprint = _compute_composite_library_fingerprint(
        resource_library_dir=resource_library_dir,
        active_package_id=active_package_text,
        should_abort=None,
    )
    full_fingerprint = "|".join([str(base_fingerprint or ""), str(composite_fingerprint or "")])

    log_warn(
        "[REFRESH][bg] index snapshot ready: scope='{}' resources={} elapsed={:.2f}s",
        str(active_package_text or ""),
        int(sum(len(bucket) for bucket in index_data.resource_index.values())),
        float(time.monotonic()) - started_monotonic,
    )
    return ResourceIndexSnapshot(
        index_data=index_data,
        resource_library_fingerprint=full_fingerprint,
        active_package_id=active_package_text,
    )


class ResourceRefreshCoordinator(QtCore.QObject):
    """资源库刷新后台化协调器：singleflight + pending 合并，UI 线程只做 O(1)。

    - 同一时刻最多跑一个后台索引构建任务；
    - 运行中收到新请求只记 pending（coalesce），结束后最多再跑一次；
    - 后台任务完成后通过信号把快照交回主线程提交替换。
    """

    refresh_started = QtCore.pyqtSignal()
    snapshot_ready = QtCore.pyqtSignal(object)  # ResourceIndexSnapshot
    refresh_completed = QtCore.pyqtSignal()
    _future_done = QtCore.pyqtSignal(object)  # Future[ResourceIndexSnapshot]

    def __init__(
        self,
        *,
        workspace_path: Path,
        resource_library_dir: Path,
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._workspace_path = Path(workspace_path).resolve()
        self._resource_library_dir = Path(resource_library_dir).resolve()

        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ResourceRefresh")
        self._in_progress: bool = False
        self._pending: bool = False
        self._latest_active_package_id: str | None = None
        self._future: Future[ResourceIndexSnapshot] | None = None
        self._future_done.connect(self._handle_future_done_in_main_thread)

    def request_refresh(self, *, active_package_id: str | None) -> None:
        normalized = str(active_package_id or "").strip() or None
        self._latest_active_package_id = normalized
        if self._in_progress:
            self._pending = True
            log_debug(
                "[REFRESH][bg] request coalesced: in_progress=True pending=True scope='{}'",
                str(normalized or ""),
            )
            return
        self._start_job(active_package_id=normalized)

    def cleanup(self) -> None:
        """退出阶段清理（幂等）。"""
        self._pending = False
        self._in_progress = False
        self._future = None
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _start_job(self, *, active_package_id: str | None) -> None:
        self._in_progress = True
        self._pending = False
        self.refresh_started.emit()

        future = self._executor.submit(
            build_resource_index_snapshot,
            workspace_path=self._workspace_path,
            resource_library_dir=self._resource_library_dir,
            active_package_id=active_package_id,
        )
        self._future = future
        future.add_done_callback(self._on_future_done)

    def _on_future_done(self, future: Future[ResourceIndexSnapshot]) -> None:
        # Future 回调发生在后台线程：用 Qt signal 把处理转回主线程。
        self._future_done.emit(future)

    def _handle_future_done_in_main_thread(self, future: object) -> None:
        if not isinstance(future, Future):
            raise TypeError("ResourceRefreshCoordinator: future 类型不正确")
        typed_future: Future[ResourceIndexSnapshot] = future
        try:
            snapshot = typed_future.result()
        finally:
            # 无论成功/失败，都必须复位互斥并尝试处理 pending，避免自动刷新永久停在 in_progress。
            self._in_progress = False
            self._future = None
            self.refresh_completed.emit()

        self.snapshot_ready.emit(snapshot)

        if self._pending and (not self._in_progress):
            latest_scope = self._latest_active_package_id
            log_debug(
                "[REFRESH][bg] pending consumed: scope='{}'",
                str(latest_scope or ""),
            )
            self._start_job(active_package_id=latest_scope)

