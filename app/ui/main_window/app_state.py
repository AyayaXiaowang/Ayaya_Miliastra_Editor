"""主窗口的共享状态对象（AppState）。

目标：
- 将启动期的稳定依赖（workspace / 节点库 / ResourceManager / PackageIndexManager / GraphView）集中到明确对象中；
- 避免在主窗口上保留 `self.*` 的兼容别名，减少跨域逻辑对隐式约定的依赖。

约定：
- **动态的** GraphModel/GraphScene 由 `GraphEditorController` 管理（加载图时会重建模型与场景），
  因此 AppState 不持有 `graph_model/graph_scene`，以避免出现“陈旧副本”。

- settings 的 workspace_root 注入与用户设置加载由应用入口（`app.cli.run_app`）负责；
  本模块只读取 settings，不在此处重复 `settings.load()`，避免启动链路分叉与隐性覆盖。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time

from engine.configs.settings import settings
from engine.graph.models.graph_model import GraphModel
from engine.nodes.node_registry import get_node_registry
from engine.resources import (
    PackageIndexManager,
    ResourceManager,
    build_resource_index_context,
)
from engine.utils.logging.logger import log_debug, log_info, log_warn
from engine.utils.workspace import get_injected_workspace_root_or_none, init_settings_for_workspace
from app.codegen import ExecutableCodeGenerator
from app.ui.graph.graph_scene import GraphScene
from app.ui.graph.graph_view import GraphView
from app.ui.foundation.keymap_store import KeymapStore


@dataclass(slots=True)
class MainWindowAppState:
    """主窗口启动期装配得到的稳定依赖集合（单一真源）。"""

    workspace_path: Path
    node_library: dict
    resource_manager: ResourceManager
    package_index_manager: PackageIndexManager
    graph_view: GraphView
    keymap_store: KeymapStore


def build_main_window_app_state(workspace_path: Path) -> MainWindowAppState:
    """构建主窗口 AppState：集中完成 settings / 节点库 / 资源索引 / 图编辑器基础对象装配。"""
    started_monotonic = float(time.monotonic())
    log_debug("[BOOT][AppState] 开始构建 MainWindowAppState，workspace={}", workspace_path)

    # 1) settings 由入口负责注入与加载；这里只做一致性保障，不重复 load（避免覆盖入口侧的启动期开关）。
    expected_workspace_root = Path(workspace_path).resolve()
    injected_workspace_root = get_injected_workspace_root_or_none()
    if injected_workspace_root is None:
        init_settings_for_workspace(workspace_root=expected_workspace_root, load_user_settings=False)
    else:
        injected_workspace_root_resolved = injected_workspace_root.resolve()
        if injected_workspace_root_resolved != expected_workspace_root:
            init_settings_for_workspace(workspace_root=expected_workspace_root, load_user_settings=False)

    log_debug(
        "[BOOT][AppState] settings 已就绪（UI_THEME_MODE={}）",
        getattr(settings, "UI_THEME_MODE", "unknown"),
    )

    # 2) 加载节点定义（集中式注册表）
    node_library_started = float(time.monotonic())
    registry = get_node_registry(workspace_path, include_composite=True)
    node_library = registry.get_library()
    node_library_elapsed = float(time.monotonic()) - node_library_started

    # 3) 资源管理器与存档索引管理器
    resource_context_started = float(time.monotonic())
    graph_code_generator = ExecutableCodeGenerator(workspace_path, node_library)
    resource_manager, package_index_manager = build_resource_index_context(
        workspace_path,
        init_settings_first=False,
        graph_code_generator=graph_code_generator,
    )
    resource_context_elapsed = float(time.monotonic()) - resource_context_started

    # 4) 节点图编辑器基础对象（空图）
    graph_model = GraphModel()
    graph_scene = GraphScene(graph_model, node_library=node_library)
    graph_view = GraphView(graph_scene)
    graph_view.node_library = node_library
    log_debug("[BOOT][AppState] GraphModel/GraphScene/GraphView 初始化完成")

    # 5) 快捷键配置（默认值 + runtime cache 覆盖）
    keymap_store = KeymapStore(workspace_path)
    log_debug("[BOOT][AppState] KeymapStore 初始化完成")

    log_warn(
        "[BOOT] AppState 就绪：nodes={} (elapsed={:.2f}s), resources_ctx={:.2f}s, total={:.2f}s",
        int(len(node_library)),
        float(node_library_elapsed),
        float(resource_context_elapsed),
        float(time.monotonic()) - started_monotonic,
    )

    return MainWindowAppState(
        workspace_path=workspace_path,
        node_library=node_library,
        resource_manager=resource_manager,
        package_index_manager=package_index_manager,
        graph_view=graph_view,
        keymap_store=keymap_store,
    )


