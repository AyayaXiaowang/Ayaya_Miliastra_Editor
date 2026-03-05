from __future__ import annotations
"""
内置 UI Workbench（Web 工作台）变量默认值处理。

注意：实现已下沉到 `app.runtime.services.ui_workbench.variable_defaults`，
本模块仅作为稳定导入路径的薄封装。
"""

from app.runtime.services.ui_workbench.variable_defaults import (  # noqa: F401
    ImportedVariable,
    discover_player_templates,
    extract_import_items,
    get_player_custom_variable_file_ids_from_template,
    infer_variable_type_and_default,
    set_player_custom_variable_file_ids,
    try_attach_ps_variable_file_to_player_templates,
    variable_id_for,
    write_level_variable_file,
)


__all__ = [
    "ImportedVariable",
    "discover_player_templates",
    "extract_import_items",
    "get_player_custom_variable_file_ids_from_template",
    "infer_variable_type_and_default",
    "set_player_custom_variable_file_ids",
    "try_attach_ps_variable_file_to_player_templates",
    "variable_id_for",
    "write_level_variable_file",
]

