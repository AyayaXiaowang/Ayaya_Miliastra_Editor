"""保存前/后资源库指纹基线同步策略。"""

from __future__ import annotations

from engine.resources.resource_manager import ResourceManager


class FingerprintBaselineService:
    def __init__(self, resource_manager: ResourceManager):
        self._resource_manager = resource_manager

    def sync_before_save(self) -> None:
        """在保存前同步资源库指纹基线，避免误判为“外部修改”。"""
        if self._resource_manager.has_resource_library_changed():
            print("[PACKAGE-SAVE] 检测到资源库指纹变化，同步基线后继续保存")
            self._resource_manager.refresh_resource_library_fingerprint()

    def refresh_after_write(self) -> None:
        """在本次保存确实写入磁盘后刷新指纹基线。"""
        self._resource_manager.refresh_resource_library_fingerprint()


