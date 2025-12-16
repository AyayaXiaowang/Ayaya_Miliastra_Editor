from __future__ import annotations

from pathlib import Path


def get_runtime_cache_root(workspace_path: Path) -> Path:
    """获取统一的运行时缓存根目录。

    所有基于工作区的缓存（图缓存、资源索引缓存、节点库缓存等）都应从此处派生子目录，
    避免在各个模块中重复硬编码路径片段。
    """
    from engine.configs.settings import Settings, settings

    configured = str(getattr(settings, "RUNTIME_CACHE_ROOT", "") or "").strip()
    if not configured:
        configured = "app/runtime/cache"

    configured_path = Path(configured)
    if configured_path.is_absolute():
        return configured_path

    # 单一真源：若 settings 已通过 set_config_path(workspace_root) 初始化，
    # 则优先使用 Settings._workspace_root，避免调用方误传 workspace_path
    #（例如传成 <workspace>/engine）导致缓存跑偏。
    workspace_root = workspace_path
    injected_root = getattr(Settings, "_workspace_root", None)
    if isinstance(injected_root, Path):
        workspace_root = injected_root

    return workspace_root / configured_path


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



