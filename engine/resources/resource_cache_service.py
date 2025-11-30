"""资源缓存服务 - 提供统一的内存缓存（LRU 风格）实现。"""

from __future__ import annotations

from typing import Dict, Optional

from engine.configs.resource_types import ResourceType


class ResourceCacheService:
    """资源数据的内存缓存服务（LRU 样式，负责命中统计与失效策略）。"""

    def __init__(self, max_cache_size: int = 500) -> None:
        # 缓存已加载的资源数据：{(resource_type, resource_id): (data, mtime)}
        # mtime 用于检测文件是否被外部修改
        self._resource_cache: Dict[tuple[ResourceType, str], tuple[dict, float]] = {}
        self._cache_hits = 0
        self._cache_misses = 0
        self._max_cache_size = max_cache_size

    def get(self, key: tuple[ResourceType, str], current_mtime: float) -> Optional[dict]:
        """按 key 读取缓存，如果 mtime 匹配则返回深拷贝后的数据。"""
        if key not in self._resource_cache:
            self._cache_misses += 1
            return None

        cached_data, cached_mtime = self._resource_cache[key]
        if abs(current_mtime - cached_mtime) >= 0.001:
            # 文件已变化，视为未命中
            self._cache_misses += 1
            return None

        self._cache_hits += 1

        import copy

        return copy.deepcopy(cached_data)

    def add(self, key: tuple[ResourceType, str], data: dict, mtime: float) -> None:
        """向缓存写入一条记录，必要时进行淘汰。"""
        # 简单的 FIFO 淘汰：Python 3.7+ 字典保持插入顺序
        if len(self._resource_cache) >= self._max_cache_size:
            first_key = next(iter(self._resource_cache))
            del self._resource_cache[first_key]

        import copy

        self._resource_cache[key] = (copy.deepcopy(data), mtime)

    def clear(self, resource_type: Optional[ResourceType] = None, resource_id: Optional[str] = None) -> None:
        """根据条件清理缓存。

        - 未提供参数：清空所有缓存并重置统计；
        - 仅提供 resource_type：清理该类型所有资源；
        - 同时提供 resource_type 与 resource_id：清理单个资源。
        """
        if resource_type is not None and resource_id is not None:
            cache_key = (resource_type, resource_id)
            if cache_key in self._resource_cache:
                del self._resource_cache[cache_key]
            return

        if resource_type is not None:
            keys_to_remove = [key for key in self._resource_cache.keys() if key[0] == resource_type]
            for key in keys_to_remove:
                del self._resource_cache[key]
            return

        self._resource_cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0

    def invalidate_by_file_change(self, resource_type: ResourceType, resource_id: str) -> None:
        """文件被修改时显式失效单条缓存。"""
        self.clear(resource_type, resource_id)

    def get_stats(self) -> dict:
        """获取缓存统计数据。"""
        total_requests = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total_requests * 100) if total_requests > 0 else 0.0
        return {
            "cache_size": len(self._resource_cache),
            "max_cache_size": self._max_cache_size,
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate": round(hit_rate, 2),
        }


