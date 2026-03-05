"""通用 JSON 资源存储服务。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from engine.configs.resource_types import ResourceType
from engine.utils.logging.logger import log_info
from engine.utils.resource_library_layout import (
    find_containing_resource_root,
    get_default_unclassified_package_root_dir,
)
from .resource_cache_service import ResourceCacheService
from .resource_file_ops import ResourceFileOps
from .resource_state import ResourceIndexState
from .atomic_json import atomic_write_json


class JsonResourceStore:
    """负责 JSON 资源的物理存储、索引同步与缓存集成。"""

    def __init__(
        self,
        file_ops: ResourceFileOps,
        cache_service: ResourceCacheService,
        index_state: ResourceIndexState,
    ) -> None:
        self._file_ops = file_ops
        self._cache_service = cache_service
        self._state = index_state

    def save(
        self,
        resource_type: ResourceType,
        resource_id: str,
        data: dict,
        *,
        resource_root_dir: Path | None = None,
    ) -> Path:
        """保存资源文件并同步索引。

        Args:
            resource_root_dir: 可选的资源根目录写入落点；用于“目录即存档”模式下把新建资源写入当前项目存档目录。
        """
        resource_name = data.get("name")
        existing_file = self._state.get_file_path(resource_type, resource_id)

        # 若该资源已存在于某个 root（共享/项目存档），则保存时保持其 root 不变；
        # 若资源落在 legacy 根目录下，则会在保存时迁入默认未归属项目存档，避免目录漂移。
        resolved_root_dir = resource_root_dir
        if resolved_root_dir is None:
            if existing_file is not None and existing_file.exists():
                resolved_root_dir = find_containing_resource_root(
                    self._file_ops.resource_library_dir,
                    existing_file,
                )
        if resolved_root_dir is None:
            resolved_root_dir = get_default_unclassified_package_root_dir(self._file_ops.resource_library_dir)

        resource_file = self._file_ops.get_resource_file_path(
            resource_type,
            resource_id,
            self._state.filename_cache,
            extension=".json",
            resource_name=resource_name,
            resource_root_dir=resolved_root_dir,
        )

        if existing_file and existing_file.exists() and existing_file != resource_file:
            existing_file.unlink()
            log_info("  [重命名] 已删除旧文件: {}", existing_file.name)

        resource_file.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(resource_file, data, ensure_ascii=False, indent=2)

        self._state.set_file_path(resource_type, resource_id, resource_file)
        self._state.set_filename(resource_type, resource_id, resource_file.stem)
        return resource_file

    def load(
        self,
        resource_type: ResourceType,
        resource_id: str,
        *,
        copy_mode: ResourceCacheService.CopyMode = "deep",
    ) -> Optional[dict]:
        """加载资源（带缓存），不存在时返回 None。

        Args:
            copy_mode:
                - "deep"：缓存命中时返回 deep copy（默认，防止调用方意外修改缓存对象）
                - "shallow"：缓存命中时仅做浅拷贝（更快，但嵌套结构仍共享）
                - "none"：缓存命中时直接返回缓存对象（最快，仅适用于严格只读调用方）
        """
        resource_file = self._state.get_file_path(resource_type, resource_id)
        if resource_file is None:
            resource_file = self._file_ops.get_resource_file_path(
                resource_type,
                resource_id,
                self._state.filename_cache,
            )

        if not resource_file.exists():
            return None

        cache_key = (resource_type, resource_id)
        current_mtime = resource_file.stat().st_mtime
        cached = self._cache_service.get(cache_key, current_mtime, copy_mode=copy_mode)
        if cached is not None:
            return cached

        with open(resource_file, "r", encoding="utf-8") as file:
            data = json.load(file)

        self._state.set_file_path(resource_type, resource_id, resource_file)
        self._cache_service.add(cache_key, data, current_mtime)
        return data

    def delete(self, resource_type: ResourceType, resource_id: str) -> bool:
        """删除资源文件与索引。"""
        resource_file = self._state.get_file_path(resource_type, resource_id)
        if resource_file is None:
            resource_file = self._file_ops.get_resource_file_path(
                resource_type,
                resource_id,
                self._state.filename_cache,
            )

        if not resource_file.exists():
            return False

        resource_file.unlink()
        self._state.remove_file_path(resource_type, resource_id)
        self._state.remove_filename(resource_type, resource_id)
        return True

    def exists(self, resource_type: ResourceType, resource_id: str) -> bool:
        """资源文件是否存在。"""
        resource_file = self._state.get_file_path(resource_type, resource_id)
        if resource_file is None:
            resource_file = self._file_ops.get_resource_file_path(
                resource_type,
                resource_id,
                self._state.filename_cache,
            )
        return resource_file.exists()


