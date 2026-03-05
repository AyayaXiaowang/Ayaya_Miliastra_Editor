from __future__ import annotations

"""
兼容门面：web_ui_import_variables

历史上该模块是一个超大单体，混杂了：
- 变量引用解析（lv/ps/{1:lv.xxx}）
- variable_defaults 归一化（含字典字段路径收敛）
- 类型推断 / 显式类型标注
- 自定义变量 value/type message 构造
- root4/5/1 实体自定义变量补齐（含字典 key 去重与 lossless dump 兼容）

为降低耦合并形成单一真源，上述规则已迁移到：
- `ugc_file_tools.custom_variables/*`

本文件仅保留稳定导入路径，对外 re-export 公开 API。
"""

from ugc_file_tools.custom_variables.apply import (
    ensure_config_id_custom_variable_in_asset_entry,
    ensure_custom_variables_from_variable_defaults,
    ensure_dict_custom_variable_in_asset_entry,
    ensure_float_custom_variable_in_asset_entry,
    ensure_int_custom_variable_in_asset_entry,
    ensure_override_variables_group1_container,
    ensure_string_custom_variable_in_asset_entry,
    ensure_text_placeholder_referenced_custom_variables,
    extract_instance_entry_name_from_root4_5_1_entry,
    find_root4_5_1_entry_by_name,
)
from ugc_file_tools.custom_variables.coerce import (
    coerce_default_float,
    coerce_default_int,
    coerce_default_string,
    is_blank_or_dot_text,
    normalize_custom_variable_name_field2,
)
from ugc_file_tools.custom_variables.defaults import normalize_variable_defaults_map
from ugc_file_tools.custom_variables.refs import (
    extract_variable_refs_from_text_placeholders,
    is_number_like_text,
    parse_variable_ref_text,
    require_scalar_variable_name,
)
from ugc_file_tools.custom_variables.web_ui_apply import (
    ensure_item_display_referenced_custom_variables,
    ensure_progressbar_referenced_custom_variables,
    normalize_progressbar_binding_text,
)

__all__ = [
    # --- names / defaults ---
    "normalize_custom_variable_name_field2",
    "coerce_default_int",
    "coerce_default_float",
    "coerce_default_string",
    "is_blank_or_dot_text",
    "normalize_variable_defaults_map",
    # --- refs ---
    "is_number_like_text",
    "parse_variable_ref_text",
    "require_scalar_variable_name",
    "extract_variable_refs_from_text_placeholders",
    # --- root4/5/1 helpers ---
    "extract_instance_entry_name_from_root4_5_1_entry",
    "find_root4_5_1_entry_by_name",
    "ensure_override_variables_group1_container",
    # --- writeback ensure_* ---
    "ensure_int_custom_variable_in_asset_entry",
    "ensure_float_custom_variable_in_asset_entry",
    "ensure_config_id_custom_variable_in_asset_entry",
    "ensure_string_custom_variable_in_asset_entry",
    "ensure_dict_custom_variable_in_asset_entry",
    "ensure_custom_variables_from_variable_defaults",
    "ensure_text_placeholder_referenced_custom_variables",
    "ensure_item_display_referenced_custom_variables",
    "ensure_progressbar_referenced_custom_variables",
    # --- web ui ---
    "normalize_progressbar_binding_text",
]

