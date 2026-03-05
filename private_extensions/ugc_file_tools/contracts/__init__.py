"""
ugc_file_tools.contracts

面向 `.gia` 导出 与 `.gil` 写回的“口径对齐/契约层”（single source of truth）。

该包只放“跨域共享的规则与解析器”，避免把同一规则散落在：
- gia_export.*
- node_graph_writeback.*
- var_type_map / registries / patchers
从而降低“只改了一半”的风险。
"""

from .node_graph_type_mappings import (  # noqa: F401
    resolve_concrete_id_from_node_data_type_mappings,
    try_resolve_dict_kv_concrete_mapping,
    try_resolve_t_concrete_mapping,
    try_resolve_t_dict_concrete_mapping,
)
from .signal_meta_binding import (  # noqa: F401
    resolve_signal_meta_binding_param_pin_indices,
)

__all__ = [
    "resolve_concrete_id_from_node_data_type_mappings",
    "try_resolve_dict_kv_concrete_mapping",
    "try_resolve_t_concrete_mapping",
    "try_resolve_t_dict_concrete_mapping",
    "resolve_signal_meta_binding_param_pin_indices",
]

