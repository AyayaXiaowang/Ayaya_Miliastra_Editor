from __future__ import annotations

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
