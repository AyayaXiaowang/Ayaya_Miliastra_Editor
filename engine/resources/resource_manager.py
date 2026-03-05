"""资源管理器 - 统一管理所有离散化资源的增删改查"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from engine.configs.resource_types import ResourceType
from engine.resources.persistent_graph_cache_manager import PersistentGraphCacheManager
from engine.resources.resource_index_builder import ResourceIndexBuilder
from .graph_resource_service import GraphResourceService
from .resource_cache_service import ResourceCacheService
from .resource_file_ops import ResourceFileOps
from .resource_index_service import ResourceIndexService
from .resource_manager_cache_mixin import ResourceManagerCacheMixin
from .resource_manager_fingerprint_mixin import ResourceManagerFingerprintMixin
from .resource_manager_graph_mixin import ResourceManagerGraphMixin
from .resource_manager_index_mixin import ResourceManagerIndexMixin
from .resource_manager_io_mixin import ResourceManagerIoMixin
from .resource_manager_metadata_mixin import ResourceManagerMetadataMixin
from .resource_manager_reference_mixin import ResourceManagerReferenceMixin
from .resource_manager_scope_mixin import ResourceManagerScopeMixin
from .resource_metadata_service import ResourceMetadataService
from .resource_state import ResourceIndexState, ResourceReferenceIndex
from .resource_store import JsonResourceStore

__all__ = ["ResourceManager", "ResourceType"]


class ResourceManager(
    ResourceManagerScopeMixin,
    ResourceManagerIndexMixin,
    ResourceManagerFingerprintMixin,
    ResourceManagerCacheMixin,
    ResourceManagerIoMixin,
    ResourceManagerReferenceMixin,
    ResourceManagerMetadataMixin,
    ResourceManagerGraphMixin,
):
    """资源管理器 - 管理所有离散化存储的资源"""

    def __init__(
        self,
        workspace_path: Path,
        *,
        index_state: Optional[ResourceIndexState] = None,
        reference_state: Optional[ResourceReferenceIndex] = None,
        cache_service: Optional[ResourceCacheService] = None,
        file_ops: Optional[ResourceFileOps] = None,
        index_builder: Optional[ResourceIndexBuilder] = None,
        persistent_graph_cache_manager: Optional[PersistentGraphCacheManager] = None,
        resource_store: Optional[JsonResourceStore] = None,
        index_service: Optional[ResourceIndexService] = None,
        graph_service: Optional[GraphResourceService] = None,
        graph_code_generator: Optional[object] = None,
        max_cache_size: int = 500,
    ):
        """初始化资源管理器。

        Args:
            workspace_path: 工作区根目录（workspace_root）
            index_state: 可注入的索引状态，实现内存/Mock 替换
            reference_state: 可注入的引用索引实现
            cache_service: 自定义缓存服务（便于测试或注入空实现）
            file_ops: 自定义文件操作实现
            index_builder: 自定义索引构建器
            persistent_graph_cache_manager: 自定义节点图持久化缓存管理器（磁盘）
            resource_store: JSON资源存储实现
            index_service: 自定义索引服务
            graph_service: 自定义图资源服务
            graph_code_generator: 可注入的“节点图源码生成器”（应用层实现），仅 GraphResourceService.save_graph 使用
            max_cache_size: 资源缓存最大尺寸
        """
        self.workspace_path = workspace_path
        self.resource_library_dir = workspace_path / "assets" / "资源库"

        self._state = index_state or ResourceIndexState()
        self.resource_index: Dict[ResourceType, Dict[str, Path]] = self._state.resource_paths
        self.name_to_id_index: Dict[ResourceType, Dict[str, str]] = self._state.name_to_id_map
        self.id_to_filename_cache: Dict[ResourceType, Dict[str, str]] = self._state.filename_cache

        self._references = reference_state or ResourceReferenceIndex()
        self.reference_index: Dict[str, list[str]] = self._references.references

        self._max_cache_size = max_cache_size

        self._resource_index_builder = index_builder or ResourceIndexBuilder(self.workspace_path, self.resource_library_dir)
        # 当前资源索引的“项目存档”作用域（None 表示仅共享根）。
        # 重要：当允许跨项目存档出现重复资源 ID 时，必须显式限定作用域，
        # 否则按 (ResourceType, resource_id) 的全局索引会产生歧义。
        self._active_package_id: str | None = None
        self._resource_index_builder.set_active_package_id(None)
        self._persistent_graph_cache_manager = (
            persistent_graph_cache_manager or PersistentGraphCacheManager(self.workspace_path)
        )

        self._cache_service = cache_service or ResourceCacheService(max_cache_size=self._max_cache_size)
        self._file_ops = file_ops or ResourceFileOps(self.resource_library_dir)
        self._resource_store = resource_store or JsonResourceStore(
            self._file_ops,
            self._cache_service,
            self._state,
        )
        self._index_service = index_service or ResourceIndexService(
            self.workspace_path,
            self._resource_index_builder,
            self._file_ops,
            self._state,
        )
        self._graph_service = graph_service or GraphResourceService(
            self.workspace_path,
            self._file_ops,
            self._cache_service,
            self._persistent_graph_cache_manager,
            self._state,
            graph_code_generator=graph_code_generator,
        )
        self._metadata_service = ResourceMetadataService()
        self._resource_library_fingerprint: str = ""
        # 指纹脏标记：当资源被保存时设为 True，延迟到下次需要时再重新计算
        self._fingerprint_invalidated: bool = False

        # 确保目录结构存在
        self._ensure_directories()

        # 加载“文件名同步提示”的去重状态并构建索引（委托索引服务）
        self._index_service.load_name_sync_state()
        self._index_service.build_index()
        self.refresh_resource_library_fingerprint()



