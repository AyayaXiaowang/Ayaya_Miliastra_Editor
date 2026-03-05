from __future__ import annotations

import sys
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, Dict

from ugc_file_tools.graph.port_types import load_node_library_maps_from_registry
from ugc_file_tools.repo_paths import try_find_graph_generater_root


@dataclass(frozen=True, slots=True)
class _GGContext:
    gg_root: Path
    workspace_root: Path
    package_id: str
    ResourceType: Any
    resource_manager: Any
    cache_manager: Any
    GraphModel: Any
    load_graph_metadata_from_file: Any
    node_defs_by_scope: Dict[str, Dict[str, Any]]
    node_defs_by_key_by_scope: Dict[str, Dict[str, Any]]
    composite_node_def_by_id_by_scope: Dict[str, Dict[str, Any]]


def _resolve_graph_generater_root(project_archive_path: Path) -> Path:
    project_path = Path(project_archive_path).resolve()
    found = try_find_graph_generater_root(start_path=project_path)
    if found is not None:
        return found
    default = try_find_graph_generater_root()
    if default is not None:
        return default
    raise FileNotFoundError(
        "无法定位 Graph_Generater 根目录（需要包含 engine/assets；通常包含 app/plugins）："
        f"project_archive={str(project_path)!r}"
    )


def resolve_graph_generater_root(project_archive_path: Path) -> Path:
    return _resolve_graph_generater_root(Path(project_archive_path))


def _prepare_graph_generater_context(*, gg_root: Path, package_id: str) -> _GGContext:
    root = Path(gg_root).resolve()
    if not (root / "engine").is_dir():
        raise FileNotFoundError(f"invalid Graph_Generater root (missing engine/): {str(root)!r}")
    if not (root / "app").is_dir():
        raise FileNotFoundError(f"invalid Graph_Generater root (missing app/): {str(root)!r}")

    # 让 ugc_file_tools 侧可直接 import Graph_Generater 的 engine/app（只加 root 与 assets）
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    if str(root / "assets") not in sys.path:
        sys.path.insert(1, str(root / "assets"))

    ensure_settings_workspace_root = getattr(import_module("engine.utils.workspace"), "ensure_settings_workspace_root")
    workspace_root = Path(
        ensure_settings_workspace_root(
            explicit_root=root,
            start_paths=[root],
            load_user_settings=True,
        )
    ).resolve()

    ResourceType = getattr(import_module("engine.configs.resource_types"), "ResourceType")
    ResourceManager = getattr(import_module("engine.resources.resource_manager"), "ResourceManager")
    PersistentGraphCacheManager = getattr(
        import_module("engine.resources.persistent_graph_cache_manager"), "PersistentGraphCacheManager"
    )
    GraphModel = getattr(import_module("engine.graph.models.graph_model"), "GraphModel")
    load_graph_metadata_from_file = getattr(
        import_module("engine.graph.utils.metadata_extractor"), "load_graph_metadata_from_file"
    )

    resource_manager = ResourceManager(Path(workspace_root))
    resource_manager.set_active_package_id(str(package_id) or None)
    # 仅构建一次索引，避免每个图都触发 resource_index.json 的落盘与潜在锁冲突
    resource_manager.rebuild_index()

    cache_manager = PersistentGraphCacheManager(Path(workspace_root))

    server_name, server_key, server_comp = load_node_library_maps_from_registry(
        workspace_root=Path(workspace_root),
        scope="server",
        include_composite=True,
    )
    client_name, client_key, client_comp = load_node_library_maps_from_registry(
        workspace_root=Path(workspace_root),
        scope="client",
        include_composite=True,
    )
    node_defs_by_scope = {"server": dict(server_name), "client": dict(client_name)}
    node_defs_by_key_by_scope = {"server": dict(server_key), "client": dict(client_key)}
    composite_node_def_by_id_by_scope = {"server": dict(server_comp), "client": dict(client_comp)}

    return _GGContext(
        gg_root=Path(root),
        workspace_root=Path(workspace_root),
        package_id=str(package_id),
        ResourceType=ResourceType,
        resource_manager=resource_manager,
        cache_manager=cache_manager,
        GraphModel=GraphModel,
        load_graph_metadata_from_file=load_graph_metadata_from_file,
        node_defs_by_scope=node_defs_by_scope,
        node_defs_by_key_by_scope=node_defs_by_key_by_scope,
        composite_node_def_by_id_by_scope=composite_node_def_by_id_by_scope,
    )


def prepare_graph_generater_context(*, gg_root: Path, package_id: str) -> _GGContext:
    return _prepare_graph_generater_context(gg_root=gg_root, package_id=package_id)

