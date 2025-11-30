from __future__ import annotations

from pathlib import Path


def get_runtime_cache_root(workspace_path: Path) -> Path:
    """获取统一的运行时缓存根目录：app/runtime/cache。

    所有基于工作区的缓存（图缓存、资源索引缓存、节点库缓存等）都应从此处派生子目录，
    避免在各个模块中重复硬编码路径片段。
    """
    return workspace_path / "app" / "runtime" / "cache"


def get_graph_cache_dir(workspace_path: Path) -> Path:
    """返回节点图持久化缓存目录：app/runtime/cache/graph_cache。"""
    return get_runtime_cache_root(workspace_path) / "graph_cache"


def get_node_cache_dir(workspace_path: Path) -> Path:
    """返回节点库持久化缓存目录：app/runtime/cache/node_cache。"""
    return get_runtime_cache_root(workspace_path) / "node_cache"


def get_resource_cache_dir(workspace_path: Path) -> Path:
    """返回资源索引持久化缓存目录：app/runtime/cache/resource_cache。"""
    return get_runtime_cache_root(workspace_path) / "resource_cache"


def get_resource_index_cache_file(workspace_path: Path) -> Path:
    """返回资源索引持久化缓存文件路径：app/runtime/cache/resource_cache/resource_index.json。"""
    return get_resource_cache_dir(workspace_path) / "resource_index.json"


def get_name_sync_state_file(workspace_path: Path) -> Path:
    """返回资源名称同步状态文件路径：app/runtime/cache/name_sync_state.json。"""
    return get_runtime_cache_root(workspace_path) / "name_sync_state.json"


def get_validation_cache_file(workspace_path: Path) -> Path:
    """返回验证结果缓存文件路径：app/runtime/cache/validation_cache/results.json。"""
    return get_runtime_cache_root(workspace_path) / "validation_cache" / "results.json"



