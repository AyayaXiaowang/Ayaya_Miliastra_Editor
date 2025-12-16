from __future__ import annotations

"""
资源上下文构建（引擎侧统一入口）

目的：
- 收敛 CLI / 工具脚本 / UI 的“资源管理上下文构建”逻辑，避免各处各自拼装导致行为分叉；
- 统一 settings.workspace_root 初始化时机，避免未初始化导致的缓存路径漂移等问题。
"""

from pathlib import Path
from typing import List, Optional, Tuple

from engine.configs.settings import settings

from .package_index_manager import PackageIndexManager
from .package_view import PackageView
from .resource_manager import ResourceManager


def init_workspace_settings(workspace_path: Path) -> None:
    """统一初始化 settings 的 workspace_root（CLI/工具入口应在构建资源上下文前调用）。"""
    settings.set_config_path(workspace_path)


def build_resource_manager(
    workspace_path: Path,
    *,
    init_settings_first: bool = True,
    graph_code_generator: Optional[object] = None,
) -> ResourceManager:
    """构建 ResourceManager（可选择是否先初始化 settings）。"""
    if init_settings_first:
        init_workspace_settings(workspace_path)
    return ResourceManager(workspace_path, graph_code_generator=graph_code_generator)


def build_resource_index_context(
    workspace_path: Path,
    *,
    init_settings_first: bool = True,
    graph_code_generator: Optional[object] = None,
) -> Tuple[ResourceManager, PackageIndexManager]:
    """构建 ResourceManager + PackageIndexManager（不创建 PackageView）。"""
    if init_settings_first:
        init_workspace_settings(workspace_path)
    resource_manager = ResourceManager(workspace_path, graph_code_generator=graph_code_generator)
    package_index_manager = PackageIndexManager(workspace_path, resource_manager)
    return resource_manager, package_index_manager


def build_resource_context(
    workspace_path: Path,
    *,
    init_settings_first: bool = True,
    graph_code_generator: Optional[object] = None,
) -> Tuple[ResourceManager, PackageIndexManager, List[PackageView]]:
    """构建 ResourceManager + PackageIndexManager + 当前工作区下的全部 PackageView。"""
    resource_manager, package_index_manager = build_resource_index_context(
        workspace_path,
        init_settings_first=init_settings_first,
        graph_code_generator=graph_code_generator,
    )
    package_views: List[PackageView] = []
    for info in package_index_manager.list_packages():
        if not isinstance(info, dict):
            continue
        package_id_value = info.get("package_id")
        if not isinstance(package_id_value, str) or not package_id_value:
            continue
        package_index = package_index_manager.load_package_index(package_id_value)
        if package_index is None:
            continue
        package_views.append(PackageView(package_index, resource_manager))
    return resource_manager, package_index_manager, package_views


