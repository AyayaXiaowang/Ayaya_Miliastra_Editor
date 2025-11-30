"""资源索引与引用状态容器。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from engine.configs.resource_types import ResourceType


@dataclass
class ResourceIndexState:
    """封装资源索引、名称映射与文件名缓存，避免在各处手动管理裸字典。"""

    resource_paths: Dict[ResourceType, Dict[str, Path]] = field(default_factory=dict)
    name_to_id_map: Dict[ResourceType, Dict[str, str]] = field(default_factory=dict)
    filename_cache: Dict[ResourceType, Dict[str, str]] = field(default_factory=dict)

    def get_file_path(self, resource_type: ResourceType, resource_id: str) -> Optional[Path]:
        """返回资源对应的物理文件路径。"""
        resource_bucket = self.resource_paths.get(resource_type)
        if not resource_bucket:
            return None
        return resource_bucket.get(resource_id)

    def set_file_path(self, resource_type: ResourceType, resource_id: str, file_path: Path) -> None:
        """记录资源的物理文件路径。"""
        resource_bucket = self.resource_paths.setdefault(resource_type, {})
        resource_bucket[resource_id] = file_path

    def remove_file_path(self, resource_type: ResourceType, resource_id: str) -> None:
        """从索引中移除资源路径记录。"""
        resource_bucket = self.resource_paths.get(resource_type)
        if not resource_bucket:
            return
        if resource_id in resource_bucket:
            del resource_bucket[resource_id]
        if not resource_bucket:
            del self.resource_paths[resource_type]

    def list_resource_ids(self, resource_type: ResourceType) -> List[str]:
        """列出指定资源类型下的所有资源ID。"""
        resource_bucket = self.resource_paths.get(resource_type)
        if not resource_bucket:
            return []
        return list(resource_bucket.keys())

    def set_filename(self, resource_type: ResourceType, resource_id: str, filename_without_ext: str) -> None:
        """记录资源ID对应的文件名缓存。"""
        filename_bucket = self.filename_cache.setdefault(resource_type, {})
        filename_bucket[resource_id] = filename_without_ext

    def remove_filename(self, resource_type: ResourceType, resource_id: str) -> None:
        """移除资源ID对应的文件名缓存。"""
        filename_bucket = self.filename_cache.get(resource_type)
        if not filename_bucket:
            return
        if resource_id in filename_bucket:
            del filename_bucket[resource_id]
        if not filename_bucket:
            del self.filename_cache[resource_type]


@dataclass
class ResourceReferenceIndex:
    """存档 -> 资源引用索引（用于引用检查）。"""

    references: Dict[str, List[str]] = field(default_factory=dict)

    def add_reference(self, resource_id: str, package_id: str) -> None:
        """添加资源引用。"""
        packages = self.references.setdefault(resource_id, [])
        if package_id not in packages:
            packages.append(package_id)

    def remove_reference(self, resource_id: str, package_id: str) -> None:
        """移除资源引用记录。"""
        packages = self.references.get(resource_id)
        if not packages:
            return
        if package_id in packages:
            packages.remove(package_id)
        if not packages:
            del self.references[resource_id]

    def clear_resource(self, resource_id: str) -> None:
        """删除资源的所有引用记录。"""
        if resource_id in self.references:
            del self.references[resource_id]

    def get_references(self, resource_id: str) -> List[str]:
        """返回引用该资源的存档ID列表。"""
        packages = self.references.get(resource_id)
        if not packages:
            return []
        return list(packages)

    def is_referenced(self, resource_id: str) -> bool:
        """判断资源是否仍被存档引用。"""
        packages = self.references.get(resource_id)
        return bool(packages)


