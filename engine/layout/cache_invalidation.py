from __future__ import annotations

from typing import Iterable

from engine.graph.models import GraphModel


_DEFAULT_LAYOUT_CACHE_ATTRS: tuple[str, ...] = (
    "_layout_context_cache",
    "_layout_blocks_cache",
    "_layout_block_relationships",
    "_layout_cache_signature",
    "_layout_y_debug_info",
    "_layout_registry_context_cache",
)


def invalidate_layout_caches(model: GraphModel, *, extra_attrs: Iterable[str] = ()) -> None:
    """
    清理挂载在 GraphModel 上的布局相关私有缓存。

    说明：
    - 布局层为了避免重复 O(N+E) 构建索引，会把 LayoutContext、块关系快照等缓存挂到模型上；
    - 当资源库/节点库刷新、或模型结构被外部重建时，旧缓存可能与当前模型不一致；
    - 该函数提供一个集中、可复用的失效入口，用于缩短“需要手动清一串缓存”的链路。
    """
    if model is None:
        raise ValueError("model is required")

    attrs = list(_DEFAULT_LAYOUT_CACHE_ATTRS) + [str(a) for a in (extra_attrs or [])]
    for attr_name in attrs:
        if hasattr(model, attr_name):
            delattr(model, attr_name)


