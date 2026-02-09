"""管理配置保存服务：将 PackageView.management 写回资源库与 PackageIndex.resources.management。"""

from __future__ import annotations

from engine.resources.package_index import PackageIndex
from engine.resources.package_view import PackageView
from engine.resources.resource_manager import ResourceManager
from engine.utils.resource_library_layout import get_packages_root_dir
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
        """将管理页面编辑的配置写回资源库与 PackageIndex.resources.management。

        重要说明（目录即项目存档模式）：
        - 对于“已存在”的管理资源：资源层会保持其物理文件所在的资源根目录不变（共享/当前项目存档）。
        - 对于“新建且此前无文件落点”的管理资源：
          - 若不指定 `resource_root_dir`，资源层会把它写入默认归档项目（例如 “测试项目”）；
          - 这会导致新建记录在当前项目存档视图下不可见。
        - 因此这里需要把“新建管理资源”的默认落点明确写入当前项目存档根目录。
        """
        management = getattr(package, "management", None)
        if management is None:
            return

        package_root_dir = (
            get_packages_root_dir(self._resource_manager.resource_library_dir)
            / str(package_index.package_id)
        )

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
            existing_paths = self._resource_manager.list_resource_file_paths(resource_type)
            for resource_id, payload in value.items():
                if not isinstance(resource_id, str) or not resource_id:
                    continue
                if not isinstance(payload, dict):
                    continue

                # 仅对“新建资源”指定落点；已存在资源保持其原有根目录不变（由资源层根据 existing_file 推断）。
                existing_file = existing_paths.get(resource_id)
                if existing_file is None:
                    self._resource_manager.save_resource(
                        resource_type,
                        resource_id,
                        payload,
                        resource_root_dir=package_root_dir,
                    )
                else:
                    self._resource_manager.save_resource(resource_type, resource_id, payload)
                new_ids.append(resource_id)

            new_ids.sort()
            management_lists[resource_key] = new_ids


