"""索引写盘服务：保存 PackageIndex 并刷新资源库指纹基线。"""

from __future__ import annotations

from engine.resources.package_index import PackageIndex
from engine.resources.package_index_manager import PackageIndexManager

from .fingerprint_baseline_service import FingerprintBaselineService


class PackageIndexPersistService:
    def __init__(
        self,
        package_index_manager: PackageIndexManager,
        fingerprint_baseline_service: FingerprintBaselineService,
    ):
        self._package_index_manager = package_index_manager
        self._fingerprint_baseline_service = fingerprint_baseline_service

    def persist(self, *, package_index: PackageIndex, current_package_id: str | None) -> None:
        self._package_index_manager.save_package_index(package_index)
        self._fingerprint_baseline_service.refresh_after_write()
        print(f"[PACKAGE-SAVE] 存档索引已写入：package_id={current_package_id!r}")

    def refresh_after_write(self) -> None:
        """当本次仅写入资源文件但未写入 PackageIndex 时，刷新指纹基线。"""
        self._fingerprint_baseline_service.refresh_after_write()


