from __future__ import annotations

"""
struct_definitions_importer.py

对外稳定入口（薄门面）：
- 保持 `ugc_file_tools.project_archive_importer.struct_definitions_importer` 导入路径不变
- 实现拆分到 `struct_definitions_importer_parts/`，避免单文件过长
"""

from ugc_file_tools.project_archive_importer.struct_definitions_importer_parts.importer import (
    import_struct_definitions_from_project_archive_to_gil,
)
from ugc_file_tools.project_archive_importer.struct_definitions_importer_parts.node_defs import (
    choose_template_struct_id_for_node_defs,
    ensure_struct_node_defs,
)
from ugc_file_tools.project_archive_importer.struct_definitions_importer_parts.paths import (
    collect_basic_struct_py_files_in_scope,
    iter_struct_decoded_files,
    resolve_project_archive_path,
)
from ugc_file_tools.project_archive_importer.struct_definitions_importer_parts.types import StructImportOptions

__all__ = [
    "StructImportOptions",
    "resolve_project_archive_path",
    "iter_struct_decoded_files",
    "collect_basic_struct_py_files_in_scope",
    "choose_template_struct_id_for_node_defs",
    "ensure_struct_node_defs",
    "import_struct_definitions_from_project_archive_to_gil",
]

