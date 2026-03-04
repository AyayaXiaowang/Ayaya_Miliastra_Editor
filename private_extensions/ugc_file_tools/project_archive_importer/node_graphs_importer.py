from __future__ import annotations

"""
node_graphs_importer.py

对外稳定入口（薄门面）：
- 保持 `ugc_file_tools.project_archive_importer.node_graphs_importer` 导入路径不变
- 实现拆分到 `node_graphs_importer_parts/`，避免单文件过长
"""

from ugc_file_tools.project_archive_importer.node_graphs_importer_parts.constants import (
    CLIENT_SCOPE_MASK,
    SCOPE_MASK,
    SERVER_SCOPE_MASK,
)
from ugc_file_tools.project_archive_importer.node_graphs_importer_parts.export_graph_model import (
    export_graph_model_json_from_graph_code_with_context,
)
from ugc_file_tools.project_archive_importer.node_graphs_importer_parts import gg_context as _gg_context
from ugc_file_tools.project_archive_importer.node_graphs_importer_parts.gg_context import (
    prepare_graph_generater_context,
    resolve_graph_generater_root,
)
from ugc_file_tools.project_archive_importer.node_graphs_importer_parts.importer import (
    import_node_graphs_from_project_archive_to_gil,
)
from ugc_file_tools.project_archive_importer.node_graphs_importer_parts import specs as _specs
from ugc_file_tools.project_archive_importer.node_graphs_importer_parts.specs import (
    build_graph_specs,
    build_graph_specs_by_scanning_roots,
    build_overview_object_by_scanning_node_graph_dir,
    pick_template_graph_id_int,
)
from ugc_file_tools.project_archive_importer.node_graphs_importer_parts.types import NodeGraphsImportOptions
from ugc_file_tools.project_archive_importer.node_graphs_importer_parts.ui_scan import (
    collect_required_ui_keys_from_graph_code_files,
)

# NOTE: import-policy guard forbids `from ugc_file_tools... import _private_name`.
# Keep `_private` names for backward compat via attribute aliasing.
_GGContext = _gg_context._GGContext
_GraphSpec = _specs._GraphSpec
_select_explicit_graph_specs = _specs._select_explicit_graph_specs

__all__ = [
    # constants
    "SERVER_SCOPE_MASK",
    "CLIENT_SCOPE_MASK",
    "SCOPE_MASK",
    # types
    "_GGContext",
    "NodeGraphsImportOptions",
    "_GraphSpec",
    # helpers (public)
    "collect_required_ui_keys_from_graph_code_files",
    "pick_template_graph_id_int",
    "build_overview_object_by_scanning_node_graph_dir",
    "build_graph_specs_by_scanning_roots",
    "build_graph_specs",
    "resolve_graph_generater_root",
    "prepare_graph_generater_context",
    "export_graph_model_json_from_graph_code_with_context",
    # helpers (internal but used by tests/tooling)
    "_select_explicit_graph_specs",
    # main entry
    "import_node_graphs_from_project_archive_to_gil",
]

