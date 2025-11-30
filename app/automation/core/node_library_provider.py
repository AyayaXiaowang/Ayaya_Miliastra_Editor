from __future__ import annotations

"""
共享的节点定义库提供器。

目的：避免在多个模块中重复加载 / 缓存节点库，统一以 workspace 路径为粒度维护缓存。
"""

from pathlib import Path
from typing import Dict, Optional, Tuple

from engine.nodes import NodeDef
from engine.nodes.node_registry import get_node_registry

_LIB_CACHE: Dict[Tuple[Path, bool], Dict[str, NodeDef]] = {}
_DEFAULT_WORKSPACE: Optional[Path] = None


def set_default_workspace_path(workspace_path: Path | str) -> None:
    """设置默认 workspace 路径（供无法显式传参的调用方复用）。"""
    global _DEFAULT_WORKSPACE
    _DEFAULT_WORKSPACE = Path(workspace_path).resolve()


def clear_node_library_cache(workspace_path: Path | str | None = None) -> None:
    """按需清理缓存；若未指定路径则清空所有缓存与默认路径。"""
    global _LIB_CACHE, _DEFAULT_WORKSPACE
    if workspace_path is None:
        _LIB_CACHE.clear()
        _DEFAULT_WORKSPACE = None
        return
    resolved = Path(workspace_path).resolve()
    for key in list(_LIB_CACHE.keys()):
        if key[0] == resolved:
            _LIB_CACHE.pop(key)
    if _DEFAULT_WORKSPACE == resolved:
        _DEFAULT_WORKSPACE = None


def _resolve_workspace(workspace_path: Path | str | None) -> Path:
    if workspace_path is None:
        if _DEFAULT_WORKSPACE is None:
            raise ValueError("workspace_path 未设置，且不存在默认 workspace，可调用 set_default_workspace_path")
        return _DEFAULT_WORKSPACE
    return Path(workspace_path).resolve()


def get_workspace_root(workspace_path: Path | str | None = None) -> Path:
    """返回规范化后的 workspace 根路径，复用内部的解析逻辑。"""
    return _resolve_workspace(workspace_path)


def get_node_library(
    workspace_path: Path | str | None = None,
    *,
    include_composite: bool = True,
) -> Dict[str, NodeDef]:
    """返回指定 workspace 下的节点定义库，按 (workspace, include_composite) 维度缓存。"""
    resolved = _resolve_workspace(workspace_path)
    cache_key = (resolved, bool(include_composite))
    cached = _LIB_CACHE.get(cache_key)
    if cached is not None:
        return cached
    registry = get_node_registry(resolved, include_composite=include_composite)
    library = registry.get_library()
    _LIB_CACHE[cache_key] = library
    return library


