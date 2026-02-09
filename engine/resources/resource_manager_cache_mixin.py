from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from engine.configs.resource_types import ResourceType
from engine.utils.cache.cache_paths import get_node_cache_dir

if TYPE_CHECKING:
    from engine.graph.models.graph_model import GraphModel


class ResourceManagerCacheMixin:
    """ResourceManager 的缓存相关方法（内存缓存 + 磁盘持久化缓存）。"""

    def clear_cache(self, resource_type: Optional[ResourceType] = None, resource_id: Optional[str] = None) -> None:
        """清除缓存

        Args:
            resource_type: 如果指定，只清除该类型的缓存；否则清除所有
            resource_id: 如果指定，只清除该资源的缓存
        """
        self._cache_service.clear(resource_type, resource_id)

    def get_cache_stats(self) -> dict:
        """获取缓存统计信息

        Returns:
            缓存统计字典，包含：
            - cache_size: 当前缓存条目数
            - max_cache_size: 最大缓存条目数
            - cache_hits: 缓存命中次数
            - cache_misses: 缓存未命中次数
            - hit_rate: 缓存命中率（百分比）
        """
        return self._cache_service.get_stats()

    # ===== 缓存清理（公开API） =====
    def clear_persistent_graph_cache(self) -> int:
        """清空磁盘上的节点图持久化缓存（app/runtime/cache/graph_cache）。

        Returns:
            被删除的缓存文件数量
        """
        return self._persistent_graph_cache_manager.clear_all_persistent_graph_cache()

    def clear_persistent_resource_index_cache(self) -> int:
        """清空磁盘上的资源索引缓存（app/runtime/cache/resource_cache/resource_index*.json）。"""
        return self._index_service.clear_persistent_cache()

    def clear_persistent_graph_cache_for(self, graph_id: str) -> int:
        """按图ID清除节点图的持久化缓存文件（app/runtime/cache/graph_cache/<graph_id>.json）。

        Returns:
            被删除的缓存文件数量（0或1）
        """
        return self._persistent_graph_cache_manager.clear_persistent_graph_cache_for(graph_id)

    def invalidate_graph_for_reparse(self, graph_id: str) -> None:
        """为“重新解析 .py”场景集中失效该图的缓存（内存 + 磁盘持久化）。

        适用场景：
        - 布局语义开关发生变化（例如跨块复制 True→False）后，需要强制从源 .py 重新解析，
          清除历史副本或旧布局结果；
        - 其它明确需要绕过持久化 graph_cache 的场景。

        说明：
        - 该方法只负责失效“资源层缓存”（ResourceCacheService + app/runtime/cache/graph_cache）。
        - UI/任务清单使用的进程内 graph_data payload 缓存由应用层服务统一失效。
        """
        if not graph_id:
            raise ValueError("graph_id is required")
        self.clear_cache(ResourceType.GRAPH, graph_id)
        self.clear_persistent_graph_cache_for(graph_id)

    def clear_persistent_node_cache(self) -> int:
        """清空磁盘上的节点库持久化缓存（app/runtime/cache/node_cache）。"""
        cache_dir = get_node_cache_dir(self.workspace_path)
        if not cache_dir.exists():
            return 0
        removed_files = 0
        for json_file in cache_dir.glob("*.json"):
            json_file.unlink()
            removed_files += 1
        if not any(cache_dir.iterdir()):
            cache_dir.rmdir()
        return removed_files

    def clear_all_caches(self) -> dict:
        """清除所有缓存（内存+磁盘节点图缓存）。

        - 内存缓存：资源数据LRU缓存、元数据缓存
        - 磁盘缓存：app/runtime/cache/graph_cache 下的持久化缓存

        Returns:
            {"removed_persistent_files": int, "memory_cache_cleared": bool}
        """
        removed_persistent_files = 0
        removed_persistent_files += self.clear_persistent_graph_cache()
        removed_persistent_files += self.clear_persistent_resource_index_cache()
        removed_persistent_files += self.clear_persistent_node_cache()
        self.clear_cache()
        return {"removed_persistent_files": removed_persistent_files, "memory_cache_cleared": True}

    def invalidate_cache_by_file_change(self, resource_type: ResourceType, resource_id: str) -> None:
        """文件修改时使缓存失效

        Args:
            resource_type: 资源类型
            resource_id: 资源ID
        """
        self._cache_service.invalidate_by_file_change(resource_type, resource_id)

    # ===== 对外: 更新图的持久化缓存 =====
    def update_persistent_graph_cache(
        self,
        graph_id: str,
        result_data: dict,
        delta: Optional[dict] = None,
        layout_changed: Optional[bool] = None,
    ) -> None:
        """将当前内存中的图结果写入持久化缓存（app/runtime/cache/graph_cache）。

        用途：在不改动 .py 源文件的情况下（例如自动排版仅改变位置），
        也能刷新下一次加载所使用的持久化缓存内容。

        Args:
            graph_id: 节点图ID
            result_data: 按 `load_resource(ResourceType.GRAPH, ...)` 产出的结构组织的数据：
                {
                  "graph_id": str,
                  "name": str,
                  "graph_type": str,
                  "folder_path": str,
                  "description": str,
                  "data": dict,
                  "metadata": dict
                }
            delta: 可选的增量更新字典；若提供，将基于现有缓存进行合并，仅更新变更部分
            layout_changed: 布局是否发生变化；为 False 时将尽量复用旧的 fingerprints
        """
        file_path = self.get_graph_file_path(graph_id)
        if not file_path:
            raise ValueError(f"找不到节点图文件路径: {graph_id}")
        self._graph_service.update_persistent_graph_cache(
            graph_id,
            file_path,
            result_data,
            delta=delta,
            layout_changed=layout_changed,
        )

    def update_persistent_graph_cache_from_model(
        self,
        graph_id: str,
        model: "GraphModel",
        *,
        delta: Optional[dict] = None,
        layout_changed: Optional[bool] = None,
    ) -> dict:
        """从 GraphModel 构建标准 result_data 并写入持久化缓存（同时同步内存缓存）。"""
        file_path = self.get_graph_file_path(graph_id)
        if not file_path:
            raise ValueError(f"找不到节点图文件路径: {graph_id}")
        return self._graph_service.update_persistent_graph_cache_from_model(
            graph_id,
            file_path,
            model,
            delta=delta,
            layout_changed=layout_changed,
        )



