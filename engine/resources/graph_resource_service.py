"""节点图资源服务 - 编排层（加载/保存/缓存/轻量元数据）。

说明：
- 该模块对外保持原有 API（ResourceManager 依赖），内部实现拆分为多个明确职责的类；
- GraphResourceService 仅负责编排与依赖注入，不再承载具体解析/布局/统计/保存细节。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from engine.resources.persistent_graph_cache_manager import PersistentGraphCacheManager

from .graph_cache_facade import GraphCacheFacade
from .graph_fingerprints_service import GraphFingerprintsService
from .graph_loader import GraphLoader
from .graph_metadata_reader import GraphMetadataReader
from .graph_saver import GraphSaver, GraphCodeGenerator
from .resource_cache_service import ResourceCacheService
from .resource_file_ops import ResourceFileOps
from .resource_state import ResourceIndexState


class GraphResourceService:
    """节点图专用服务：负责 .py 解析、自动布局、代码生成与往返校验及缓存。"""

    def __init__(
        self,
        workspace_path: Path,
        file_ops: ResourceFileOps,
        cache_service: ResourceCacheService,
        persistent_graph_cache_manager: PersistentGraphCacheManager,
        index_state: ResourceIndexState,
        graph_code_generator: Optional[GraphCodeGenerator] = None,
    ) -> None:
        self.workspace_path = workspace_path
        self._file_ops = file_ops
        self._cache_service = cache_service
        self._persistent_graph_cache_manager = persistent_graph_cache_manager
        self._index_state = index_state

        self._fingerprints_service = GraphFingerprintsService()
        self._cache_facade = GraphCacheFacade(
            workspace_path,
            cache_service=cache_service,
            persistent_graph_cache_manager=persistent_graph_cache_manager,
            fingerprints_service=self._fingerprints_service,
        )
        self._loader = GraphLoader(
            workspace_path,
            file_ops=file_ops,
            index_state=index_state,
            cache_facade=self._cache_facade,
            fingerprints_service=self._fingerprints_service,
        )
        self._metadata_reader = GraphMetadataReader(
            workspace_path,
            file_ops=file_ops,
            index_state=index_state,
            cache_service=cache_service,
            cache_facade=self._cache_facade,
        )
        self._saver = GraphSaver(
            workspace_path,
            file_ops=file_ops,
            cache_service=cache_service,
            index_state=index_state,
            graph_code_generator=graph_code_generator,
        )

    def save_graph(self, graph_id: str, data: dict) -> tuple[bool, Optional[Path]]:
        """保存节点图资源，返回 (是否成功, 最终文件路径)。"""
        return self._saver.save_graph(graph_id, data)

    def load_graph(self, graph_id: str) -> Optional[dict]:
        """加载节点图，带持久化与内存缓存。"""
        return self._loader.load_graph(graph_id)

    def load_graph_metadata(self, graph_id: str) -> Optional[dict]:
        """加载节点图的轻量级元数据（不执行节点图代码）。"""
        return self._metadata_reader.load_graph_metadata(graph_id)

    def update_persistent_graph_cache(
        self,
        graph_id: str,
        file_path: Path,
        result_data: dict,
        delta: Optional[dict] = None,
        layout_changed: Optional[bool] = None,
    ) -> dict:
        """更新图的持久化缓存并同步内存缓存，返回最终写入的数据。"""
        return self._cache_facade.update_persistent_graph_cache(
            graph_id,
            file_path,
            result_data,
            delta=delta,
            layout_changed=layout_changed,
        )


