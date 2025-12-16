from __future__ import annotations

"""
进程内的临时节点图 payload 缓存（in-memory）。

用途：
- UI/任务清单等场景为了避免在 detail_info 中塞入整张图，会将 graph_data 放入进程内缓存，
  并在 detail_info 中仅保存 cache_key（graph_data_key）。

注意：
- 本模块仅用于“进程内临时缓存”，不是磁盘持久化缓存；
- 磁盘持久化的节点图缓存由 `engine.resources.persistent_graph_cache_manager` 管理。
"""

from threading import RLock
from typing import Any, Dict, Optional

_CACHE_LOCK = RLock()
_GRAPH_DATA_CACHE: Dict[str, Dict[str, Any]] = {}


def build_cache_key(graph_root_id: str, graph_id: str) -> str:
    if not graph_root_id:
        raise ValueError("graph_root_id is required")
    if not graph_id:
        raise ValueError("graph_id is required")
    return f"{graph_root_id}::{graph_id}"


def store_graph_data(graph_root_id: str, graph_id: str, graph_data: Dict[str, Any]) -> str:
    cache_key = build_cache_key(graph_root_id, graph_id)
    with _CACHE_LOCK:
        _GRAPH_DATA_CACHE[cache_key] = graph_data
    return cache_key


def fetch_graph_data(cache_key: str) -> Optional[Dict[str, Any]]:
    if not cache_key:
        return None
    with _CACHE_LOCK:
        return _GRAPH_DATA_CACHE.get(cache_key)


def resolve_graph_data(detail_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(detail_info, dict):
        return None
    direct_payload = detail_info.get("graph_data")
    if isinstance(direct_payload, dict):
        return direct_payload
    cache_key = detail_info.get("graph_data_key")
    if isinstance(cache_key, str):
        return fetch_graph_data(cache_key)
    return None


def drop_graph_data_for_root(graph_root_id: str) -> None:
    if not graph_root_id:
        return
    prefix = f"{graph_root_id}::"
    with _CACHE_LOCK:
        keys_to_remove = [key for key in _GRAPH_DATA_CACHE if key.startswith(prefix)]
        for cache_key in keys_to_remove:
            _GRAPH_DATA_CACHE.pop(cache_key, None)


def drop_graph_data_for_graph(graph_id: str) -> None:
    """
    按图 ID 失效所有缓存的 graph_data。

    说明：
    - 用于在节点图布局或结构发生变化后，统一让任务清单/预览/执行等上下文在下一次访问时
      强制从 ResourceManager 重新加载最新的图数据；
    - 不依赖具体的 graph_root_id，避免逐个图根清理的遗漏。
    """
    if not graph_id:
        return
    suffix = f"::{graph_id}"
    with _CACHE_LOCK:
        keys_to_remove = [key for key in _GRAPH_DATA_CACHE if key.endswith(suffix)]
        for cache_key in keys_to_remove:
            _GRAPH_DATA_CACHE.pop(cache_key, None)


def clear_all_graph_data() -> int:
    """清空进程内的所有 graph_data 缓存条目。

    用途：
    - 资源库刷新、节点库刷新等全局操作后，统一使任务清单/预览/执行等上下文在下一次访问时
      强制从 ResourceManager 重新加载最新的图数据；
    - 作为集中失效入口，避免 UI 侧“需要手动清一串缓存”的链条过长。
    """
    with _CACHE_LOCK:
        removed = len(_GRAPH_DATA_CACHE)
        _GRAPH_DATA_CACHE.clear()
    return removed


