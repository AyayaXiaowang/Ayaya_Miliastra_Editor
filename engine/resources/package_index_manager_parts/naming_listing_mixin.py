"""PackageIndexManager：命名/列表相关职责拆分。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from engine.configs.resource_types import ResourceType
from engine.utils.name_utils import sanitize_package_filename


class PackageIndexNamingListingMixin:
    @staticmethod
    def sanitize_package_id(name: str) -> str:
        """清理项目存档目录名（package_id）的统一规则（公开 API）。

        说明：
        - 该规则与目录模式下 `PackageIndexManager` 内部使用的命名清洗规则一致；
        - 供 UI/私有扩展等上层代码调用，避免依赖 `_sanitize_package_filename` 这类下划线私有方法。
        """
        return sanitize_package_filename(name)

    @staticmethod
    def _sanitize_package_filename(name: str) -> str:
        """清理存档文件名（无前缀）。"""
        return sanitize_package_filename(name)

    def _resolve_display_name(self, resource_type: ResourceType, resource_id: str) -> str:
        """根据资源类型解析可读名称，未命名时回退到ID。"""
        # 节点图：列表展示/索引派生字段刷新时不要触发完整解析与自动布局。
        # 这里仅需要“可读名称”，因此优先走轻量元数据路径。
        if resource_type == ResourceType.GRAPH:
            graph_meta = self.resource_manager.load_graph_metadata(resource_id)
            if graph_meta:
                raw_name = graph_meta.get("name")
                if isinstance(raw_name, str):
                    cleaned_name = raw_name.strip()
                    if cleaned_name:
                        return cleaned_name
            return resource_id

        metadata = self.resource_manager.get_resource_metadata(resource_type, resource_id)
        if metadata:
            raw_name = metadata.get("name")
            if isinstance(raw_name, str):
                cleaned_name = raw_name.strip()
                if cleaned_name:
                    return cleaned_name
        return resource_id

    def _build_resource_names(self, package_index) -> Dict[str, dict]:
        """为当前存档引用的资源生成 ID->可读名 映射。"""
        resource_names: Dict[str, dict] = {
            "templates": {},
            "instances": {},
            "graphs": {},
            "composites": {},
            "combat_presets": {key: {} for key in self._COMBAT_RESOURCE_TYPE_MAP},
            "management": {key: {} for key in self._MANAGEMENT_RESOURCE_TYPE_MAP},
        }

        def fill_bucket(
            target: Dict[str, str],
            resource_ids: List[str],
            resource_type: Optional[ResourceType],
        ) -> None:
            for resource_id in resource_ids:
                if not isinstance(resource_id, str) or not resource_id:
                    continue
                if resource_type is None:
                    target[resource_id] = resource_id
                else:
                    target[resource_id] = self._resolve_display_name(resource_type, resource_id)

        fill_bucket(resource_names["templates"], package_index.resources.templates, ResourceType.TEMPLATE)
        fill_bucket(resource_names["instances"], package_index.resources.instances, ResourceType.INSTANCE)
        fill_bucket(resource_names["graphs"], package_index.resources.graphs, ResourceType.GRAPH)
        fill_bucket(resource_names["composites"], package_index.resources.composites, None)

        for bucket_name, resource_type in self._COMBAT_RESOURCE_TYPE_MAP.items():
            bucket_ids = package_index.resources.combat_presets.get(bucket_name, [])
            fill_bucket(resource_names["combat_presets"][bucket_name], bucket_ids, resource_type)

        for bucket_name, resource_type in self._MANAGEMENT_RESOURCE_TYPE_MAP.items():
            bucket_ids = package_index.resources.management.get(bucket_name, [])
            fill_bucket(resource_names["management"][bucket_name], bucket_ids, resource_type)

        return resource_names

    def _refresh_resource_names(self, package_index) -> bool:
        """刷新并写回资源名称映射，返回是否发生变更。"""
        latest_names = self._build_resource_names(package_index)
        if package_index.resource_names != latest_names:
            package_index.resource_names = latest_names
            return True
        return False

    def list_packages(self) -> List[dict]:
        """列出所有存档的基本信息"""
        return self._list_packages_from_directories()

    @staticmethod
    def _is_path_under(root_dir: Path, file_path: Path) -> bool:
        root_parts = root_dir.resolve().parts
        target_parts = file_path.resolve().parts
        if len(target_parts) < len(root_parts):
            return False
        return target_parts[: len(root_parts)] == root_parts

    def _list_packages_from_directories(self) -> List[dict]:
        packages_root = self._packages_root_dir
        if not packages_root.exists() or not packages_root.is_dir():
            return []

        package_dirs = [path for path in packages_root.iterdir() if path.is_dir()]
        results: List[dict] = []

        for package_dir in sorted(package_dirs, key=lambda path: path.name.casefold()):
            package_id = package_dir.name
            if not package_id:
                continue

            name = self._infer_package_display_name(package_dir, package_id)
            latest_mtime = self._get_latest_mtime_under_dir(package_dir)
            updated_at = datetime.fromtimestamp(latest_mtime).isoformat() if latest_mtime > 0 else ""

            results.append(
                {
                    "package_id": package_id,
                    "name": name,
                    "description": "",
                    "created_at": "",
                    "updated_at": updated_at,
                }
            )

        # 稳定排序：优先按 updated_at（字符串 ISO），再按 package_id
        results.sort(
            key=lambda item: (str(item.get("updated_at", "")), str(item.get("package_id", ""))),
            reverse=True,
        )
        return results

    @staticmethod
    def _resolve_instance_dir(package_root_dir: Path) -> Path:
        """返回“实体摆放”目录路径。

        约定：
        - 目录名以 `ResourceType.INSTANCE.value` 为唯一真源（当前为 `实体摆放`）。
        - 不再兼容旧目录名 `实例`；若检测到旧目录将直接抛错，避免静默漏扫/串包。
        """
        preferred = package_root_dir / ResourceType.INSTANCE.value
        legacy_dir = package_root_dir / "实例"
        if legacy_dir.exists() and legacy_dir.is_dir():
            raise ValueError(
                f"检测到旧目录名 '实例'：{legacy_dir}。请将其改名为 '{ResourceType.INSTANCE.value}' 后重试。"
            )
        return preferred

    @classmethod
    def _infer_package_display_name(cls, package_dir: Path, package_id: str) -> str:
        instances_dir = cls._resolve_instance_dir(package_dir)
        if instances_dir.exists() and instances_dir.is_dir():
            candidates = sorted(instances_dir.glob("*_关卡实体.json"), key=lambda path: path.name.casefold())
            if candidates:
                stem = candidates[0].stem
                if stem.endswith("_关卡实体"):
                    display = stem[: -len("_关卡实体")].strip()
                    if display:
                        return display
        return package_id

    @staticmethod
    def _get_latest_mtime_under_dir(root_dir: Path) -> float:
        """返回目录的最新修改时间（轻量近似）。

        注意：
        - 旧实现曾通过 `rglob("*")` 递归扫描整棵目录树计算“最新文件 mtime”，在资源库体量增大后会显著拖慢 UI；
        - 目录模式下 `updated_at` 仅用于 UI 展示/排序，不应成为性能热点，因此这里使用 **目录自身 mtime** 作为近似。
        """
        if not root_dir.exists():
            return 0.0
        return float(root_dir.stat().st_mtime)


