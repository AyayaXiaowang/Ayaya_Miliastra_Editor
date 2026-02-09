from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Optional

from engine.configs.resource_types import ResourceType
from engine.resources.resource_index_builder import ResourceIndexData
from engine.utils.logging.logger import log_debug, log_warn
from engine.utils.resource_library_layout import (
    get_default_unclassified_package_root_dir,
    get_packages_root_dir,
    get_shared_root_dir,
)
from engine.utils.graph.node_defs_fingerprint import invalidate_composite_node_defs_fingerprint_cache


class ResourceManagerIndexMixin:
    """ResourceManager 的索引构建/重建与目录骨架相关方法。"""

    _ACTIVE_PACKAGE_ID_UNSET = object()

    # ===== 资源索引持久化缓存（启动加速） =====

    def _save_persistent_resource_index(self) -> None:
        """将当前内存中的资源索引写入磁盘缓存。

        注意：实际写入逻辑委托给 `ResourceIndexBuilder`，以保持职责单一。
        """
        self._index_service.save_persistent_index()

    def _ensure_directories(self) -> None:
        """确保所有资源目录存在"""
        self.resource_library_dir.mkdir(exist_ok=True)

        # 新布局基础目录：共享 / 项目存档（内部按需再创建各类型子目录）
        shared_root = get_shared_root_dir(self.resource_library_dir)
        packages_root = get_packages_root_dir(self.resource_library_dir)
        shared_root.mkdir(parents=True, exist_ok=True)
        packages_root.mkdir(parents=True, exist_ok=True)

        # 默认归档项目存档：用于承载未归属资源与“新建资源”的默认落点
        default_unclassified_pkg_root = get_default_unclassified_package_root_dir(self.resource_library_dir)
        default_unclassified_pkg_root.mkdir(parents=True, exist_ok=True)

        for resource_type in ResourceType:
            # 彻底包化：不在 legacy 根（assets/资源库/）创建按类型目录；只在共享根创建“目录骨架”。
            resource_dir = self._file_ops.get_resource_directory(resource_type, resource_root_dir=shared_root)
            resource_dir.mkdir(parents=True, exist_ok=True)

    def rebuild_index(self, *, active_package_id: str | None | object = _ACTIVE_PACKAGE_ID_UNSET) -> None:
        """重建资源索引（用于手动修改文件后的同步）。

        Args:
            active_package_id:
                - 省略：保持当前项目存档作用域不变；
                - None：切换为“仅共享根”作用域；
                - str：切换为“共享根 + 指定项目存档根”作用域。
        """
        started_monotonic = float(time.monotonic())
        before_active_package_id = str(self._active_package_id or "")
        requested_active_package_id = (
            None if active_package_id is self._ACTIVE_PACKAGE_ID_UNSET else (active_package_id if isinstance(active_package_id, str) else None)
        )
        if active_package_id is not self._ACTIVE_PACKAGE_ID_UNSET:
            set_scope_started = float(time.monotonic())
            self.set_active_package_id(active_package_id if isinstance(active_package_id, str) else None)
            log_debug(
                "[INDEX] set_active_package_id 完成：elapsed={:.2f}s, after_active_package_id='{}'",
                float(time.monotonic()) - set_scope_started,
                str(self._active_package_id or ""),
            )
        rebuild_started = float(time.monotonic())
        self._index_service.rebuild_index()
        rebuild_elapsed = float(time.monotonic()) - rebuild_started
        fingerprint_started = float(time.monotonic())
        latest_fingerprint = self.refresh_resource_library_fingerprint()
        fingerprint_elapsed = float(time.monotonic()) - fingerprint_started

        # 资源索引重建意味着“复合节点库（共享/当前存档）”可能发生变化；
        # 清空其指纹缓存，确保节点库缓存与 graph_cache 的 node_defs_fp 校验不会复用旧值。
        invalidate_composite_node_defs_fingerprint_cache()

        total_resources = 0
        for bucket in self.resource_index.values():
            if isinstance(bucket, dict):
                total_resources += len(bucket)
        after_active_package_id = str(self._active_package_id or "")
        log_warn(
            "[INDEX] rebuilt: scope='{}' -> '{}' total_resources={} elapsed_total={:.2f}s",
            before_active_package_id,
            after_active_package_id,
            int(total_resources),
            float(time.monotonic()) - started_monotonic,
        )
        log_debug(
            "[INDEX] rebuilt details: requested_scope='{}' rebuild_index={:.2f}s fingerprint={:.2f}s fingerprint_prefix='{}'",
            "" if requested_active_package_id is None else str(requested_active_package_id),
            float(rebuild_elapsed),
            float(fingerprint_elapsed),
            str(latest_fingerprint or "")[:120],
        )

    def apply_index_snapshot(
        self,
        *,
        index_data: ResourceIndexData,
        resource_library_fingerprint: str,
        active_package_id: str | None | object = _ACTIVE_PACKAGE_ID_UNSET,
    ) -> None:
        """将“预先构建完成”的资源索引快照一次性提交到当前 ResourceManager。

        设计动机：
        - 索引构建与指纹扫描是 I/O 密集型，适合后台执行；
        - UI 线程只做 O(1) 的“提交替换”，避免卡顿；
        - 该方法不再触发任何磁盘扫描（不会调用 build_index/rebuild_index）。
        """
        started_monotonic = float(time.monotonic())
        before_active_package_id = str(self._active_package_id or "")
        requested_active_package_id = (
            None
            if active_package_id is self._ACTIVE_PACKAGE_ID_UNSET
            else (active_package_id if isinstance(active_package_id, str) else None)
        )
        if active_package_id is not self._ACTIVE_PACKAGE_ID_UNSET:
            set_scope_started = float(time.monotonic())
            self.set_active_package_id(active_package_id if isinstance(active_package_id, str) else None)
            log_debug(
                "[INDEX] set_active_package_id (snapshot) 完成：elapsed={:.2f}s, after_active_package_id='{}'",
                float(time.monotonic()) - set_scope_started,
                str(self._active_package_id or ""),
            )

        apply_started = float(time.monotonic())
        self.resource_index.clear()
        self.resource_index.update(index_data.resource_index)
        self.name_to_id_index.clear()
        self.name_to_id_index.update(index_data.name_to_id_index)
        self.id_to_filename_cache.clear()
        self.id_to_filename_cache.update(index_data.id_to_filename_cache)
        self.set_resource_library_fingerprint(str(resource_library_fingerprint or ""))
        # apply snapshot 代表资源库视图发生切换/替换：复合节点库指纹缓存需失效以对齐新作用域
        invalidate_composite_node_defs_fingerprint_cache()
        apply_elapsed = float(time.monotonic()) - apply_started

        total_resources = 0
        for bucket in self.resource_index.values():
            if isinstance(bucket, dict):
                total_resources += len(bucket)
        after_active_package_id = str(self._active_package_id or "")
        log_warn(
            "[INDEX] applied snapshot: scope='{}' -> '{}' total_resources={} elapsed_total={:.2f}s apply={:.2f}s",
            before_active_package_id,
            after_active_package_id,
            int(total_resources),
            float(time.monotonic()) - started_monotonic,
            float(apply_elapsed),
        )
        log_debug(
            "[INDEX] applied snapshot details: requested_scope='{}' fingerprint_prefix='{}'",
            "" if requested_active_package_id is None else str(requested_active_package_id),
            str(resource_library_fingerprint or "")[:120],
        )



