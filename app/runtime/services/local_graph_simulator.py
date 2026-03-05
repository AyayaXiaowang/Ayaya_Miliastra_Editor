from __future__ import annotations

"""
本地节点图模拟器（public facade）。

说明：
- 该模块对外保持稳定导入路径：`app.runtime.services.local_graph_simulator`
- 具体实现已按职责拆分到同目录下的 `local_graph_simulator_*.py`，以降低单文件复杂度。
"""

from .local_graph_sim_mount_catalog import LocalGraphSimResourceMountSpec
from .local_graph_simulator_loader import (
    GraphCompileResult,
    GraphSourceResult,
    compile_graph_to_executable,
    load_compiled_graph_class,
    load_source_graph_module_and_class,
)
from .local_graph_simulator_session import (
    GraphMountSpec,
    LocalGraphSimSession,
    MountedGraph,
    build_local_graph_sim_session,
)
from .local_graph_simulator_ui_keys import (
    UiKeyIndexRegistry,
    build_ui_key_registry_from_graph,
    build_ui_key_registry_from_graph_variables,
    extract_html_stem_from_layout_index_description,
    populate_runtime_graph_variables,
    populate_runtime_graph_variables_from_graph_variables,
    populate_runtime_graph_variables_from_ui_constants,
    resolve_ui_key_placeholders_in_graph_module,
    stable_layout_index_from_html_stem,
)

__all__ = [
    "GraphCompileResult",
    "GraphSourceResult",
    "GraphMountSpec",
    "MountedGraph",
    "LocalGraphSimResourceMountSpec",
    "UiKeyIndexRegistry",
    "LocalGraphSimSession",
    "extract_html_stem_from_layout_index_description",
    "stable_layout_index_from_html_stem",
    "build_local_graph_sim_session",
]

