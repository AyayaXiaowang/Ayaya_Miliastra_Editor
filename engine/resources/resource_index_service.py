"""资源索引服务 - 扫描资源库并维护索引与名称映射。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from engine.configs.resource_types import ResourceType
from engine.graph.utils.metadata_extractor import load_graph_metadata_from_file
from engine.resources.resource_index_builder import ResourceIndexBuilder
from engine.utils.logging.logger import log_info
from engine.utils.cache.cache_paths import get_name_sync_state_file
from .resource_file_ops import ResourceFileOps
from .resource_state import ResourceIndexState
from .atomic_json import atomic_write_json


class ResourceIndexService:
    """资源索引与名称映射服务：负责索引构建、持久化与 name/id 映射维护。"""

    def __init__(
        self,
        workspace_path: Path,
        index_builder: ResourceIndexBuilder,
        file_ops: ResourceFileOps,
        index_state: ResourceIndexState,
    ) -> None:
        self.workspace_path = workspace_path
        self._index_builder = index_builder
        self._file_ops = file_ops
        self._state = index_state
        self.resource_index = self._state.resource_paths
        self.name_to_id_index = self._state.name_to_id_map
        self.id_to_filename_cache = self._state.filename_cache

        self._name_sync_state_file: Path = get_name_sync_state_file(self.workspace_path)
        self._name_sync_state: Dict[str, float] = {}

    def load_name_sync_state(self) -> None:
        """加载文件名同步提示的去重状态。"""
        state_file = self._name_sync_state_file
        if state_file.exists():
            with open(state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._name_sync_state = {str(k): float(v) for k, v in data.items()}
        else:
            self._name_sync_state = {}

    def _save_name_sync_state(self) -> None:
        """保存文件名同步提示的去重状态。"""
        state_file = self._name_sync_state_file
        atomic_write_json(state_file, self._name_sync_state, ensure_ascii=False, indent=2)

    def _check_and_sync_name(
        self,
        file_path: Path,
        resource_type: ResourceType,
        resource_id: str,
        filename_without_ext: str,
        preloaded_data: Optional[dict] = None,
    ) -> bool:
        """检查文件名与内部 name 字段是否一致，如需要则执行同步。"""
        data_payload: Optional[dict] = preloaded_data

        if resource_type == ResourceType.INSTANCE:
            if data_payload is None:
                with open(file_path, "r", encoding="utf-8") as f:
                    data_payload = json.load(f)
            if data_payload.get("metadata", {}).get("is_level_entity", False):
                return False

        if resource_type == ResourceType.GRAPH:
            metadata = load_graph_metadata_from_file(file_path)
            internal_name = metadata.graph_name
            if internal_name:
                sanitized = self._file_ops.sanitize_filename(internal_name)
                if sanitized != filename_without_ext:
                    current_mtime = file_path.stat().st_mtime
                    key = str(file_path.resolve())
                    last_logged_mtime = self._name_sync_state.get(key)
                    if (
                        last_logged_mtime is None
                        or abs(current_mtime - last_logged_mtime) >= 0.001
                    ):
                        log_info(
                            "  [文件名同步] {}: '{}' -> '{}'",
                            file_path.name,
                            internal_name,
                            filename_without_ext,
                        )
                        self._name_sync_state[key] = current_mtime
                        self._save_name_sync_state()
                    return False
            return False

        if data_payload is None:
            with open(file_path, "r", encoding="utf-8") as f:
                data_payload = json.load(f)

        internal_name = data_payload.get("name", "")
        if not internal_name:
            return False

        sanitized_internal_name = self._file_ops.sanitize_filename(internal_name)
        if sanitized_internal_name != filename_without_ext:
            data_payload["name"] = filename_without_ext
            data_payload["updated_at"] = datetime.now().isoformat()

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data_payload, f, ensure_ascii=False, indent=2)

            log_info(
                "  [文件名同步] {}: name字段 '{}' -> '{}'",
                file_path.name,
                internal_name,
                filename_without_ext,
            )
            return True

        return False

    def build_index(self) -> None:
        """扫描资源库目录，构建资源索引和名称映射。"""
        cached = self._index_builder.try_load_from_cache()
        if cached is not None:
            self.resource_index.clear()
            self.resource_index.update(cached.resource_index)
            self.name_to_id_index.clear()
            self.name_to_id_index.update(cached.name_to_id_index)
            self.id_to_filename_cache.clear()
            self.id_to_filename_cache.update(cached.id_to_filename_cache)
            return

        index_data = self._index_builder.build_index(self._check_and_sync_name)
        self.resource_index.clear()
        self.resource_index.update(index_data.resource_index)
        self.name_to_id_index.clear()
        self.name_to_id_index.update(index_data.name_to_id_index)
        self.id_to_filename_cache.clear()
        self.id_to_filename_cache.update(index_data.id_to_filename_cache)

        total_resources = sum(len(resources) for resources in self.resource_index.values())
        log_info("[OK] 资源索引构建完成，共加载 {} 个资源", total_resources)
        if index_data.synced_file_count > 0:
            log_info(
                "[同步] 自动同步了 {} 个文件的name字段（文件名已被手动修改）",
                index_data.synced_file_count,
            )

    def rebuild_index(self) -> None:
        """强制重建资源索引。"""
        self.resource_index.clear()
        self.build_index()

    def compute_resources_fingerprint(self) -> str:
        """计算当前资源库指纹（文件数 + 最新修改时间）。"""
        return self._index_builder.compute_resources_fingerprint()

    def save_persistent_index(self) -> None:
        """将当前内存中的资源索引写入磁盘缓存。"""
        self._index_builder._save_persistent_resource_index(  # type: ignore[attr-defined]
            self.resource_index,
            self.name_to_id_index,
            self.id_to_filename_cache,
        )

    def clear_persistent_cache(self) -> int:
        """清空磁盘上的资源索引缓存文件。"""
        return self._index_builder.clear_persistent_cache()


