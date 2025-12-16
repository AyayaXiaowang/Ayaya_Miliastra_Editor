"""管理配置保存服务：将 PackageView.management 写回资源库与 PackageIndex.resources.management。"""

from __future__ import annotations

from engine.resources.package_index import PackageIndex
from engine.resources.package_view import PackageView
from engine.resources.resource_manager import ResourceManager
from app.ui.management.section_registry import MANAGEMENT_RESOURCE_BINDINGS


class ManagementSaveService:
    def __init__(self, resource_manager: ResourceManager):
        self._resource_manager = resource_manager

    def sync_to_index(
        self,
        *,
        package: PackageView,
        package_index: PackageIndex,
        allowed_keys: set[str] | None,
    ) -> None:
        """将管理页面编辑的配置写回资源库与 PackageIndex.resources.management。"""
        management = getattr(package, "management", None)
        if management is None:
            return

        for resource_key, resource_type in MANAGEMENT_RESOURCE_BINDINGS.items():
            if allowed_keys is not None and resource_key not in allowed_keys:
                continue
            if resource_key in {"signals", "struct_definitions"}:
                continue
            value = getattr(management, resource_key, None)

            if resource_key in {
                "save_points",
                "peripheral_systems",
                "currency_backpack",
                "level_settings",
            }:
                continue

            management_lists = package_index.resources.management

            if not isinstance(value, dict):
                management_lists[resource_key] = []
                continue

            new_ids: list[str] = []
            for resource_id, payload in value.items():
                if not isinstance(resource_id, str) or not resource_id:
                    continue
                if not isinstance(payload, dict):
                    continue
                self._resource_manager.save_resource(resource_type, resource_id, payload)
                new_ids.append(resource_id)

            new_ids.sort()
            management_lists[resource_key] = new_ids


