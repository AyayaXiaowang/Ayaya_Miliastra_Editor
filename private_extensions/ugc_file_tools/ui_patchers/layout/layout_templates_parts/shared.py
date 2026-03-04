from __future__ import annotations

"""
shared.py

对外稳定入口（薄门面）：
- 保持 `ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared` 导入路径不变
- 实现拆分到 `shared_parts/`，避免单文件过长
"""

# 兼容：历史上该模块既暴露“公开别名”（无下划线），也允许同目录内部通过相对导入使用 `_private` 实现。
# 这里保持两者都可用，并继续在文件末尾集中给出“公开别名”映射（对齐旧语义）。

from .shared_parts.dump_and_writeback import *  # noqa: F401,F403
from .shared_parts.guid_and_find import *  # noqa: F401,F403
from .shared_parts.layout_registry import *  # noqa: F401,F403
from .shared_parts.meta_blob13 import *  # noqa: F401,F403
from .shared_parts.models import *  # noqa: F401,F403
from .shared_parts.rect_transform import *  # noqa: F401,F403
from .shared_parts.varint_stream import *  # noqa: F401,F403
from .shared_parts.widget_ops import *  # noqa: F401,F403


# === Public API re-exports (import-policy friendly) ===
#
# Import policy (tests/arch/test_ugc_file_tools_import_policy.py):
# - cross-module imports must not import underscored private names from `ugc_file_tools.*`.
# - keep underscored implementations for internal use; expose public aliases for reuse.
write_back_modified_gil_by_reencoding_payload = _write_back_modified_gil_by_reencoding_payload
append_layout_root_guid_to_layout_registry = _append_layout_root_guid_to_layout_registry
prepend_layout_root_guid_to_layout_registry = _prepend_layout_root_guid_to_layout_registry

collect_all_widget_guids = _collect_all_widget_guids
allocate_next_guid = _allocate_next_guid
find_record_by_guid = _find_record_by_guid
infer_base_layout_guid = _infer_base_layout_guid

has_meta_blob13 = _has_meta_blob13
collect_existing_meta_blob13_field501_values = _collect_existing_meta_blob13_field501_values
try_extract_meta_blob13_field501_value = _try_extract_meta_blob13_field501_value
set_meta_blob13_field501_value = _set_meta_blob13_field501_value

set_widget_guid = _set_widget_guid
set_widget_parent_guid_field504 = _set_widget_parent_guid_field504
set_widget_name = _set_widget_name
force_record_to_group_container_shape = _force_record_to_group_container_shape

set_children_guids_to_parent_record = _set_children_guids_to_parent_record
append_children_guids_to_parent_record = _append_children_guids_to_parent_record
get_children_guids_from_parent_record = _get_children_guids_from_parent_record

encode_varint_stream = _encode_varint_stream
decode_varint_stream = _decode_varint_stream

set_rect_state_canvas_position_and_size = _set_rect_state_canvas_position_and_size
set_rect_transform_layer = _set_rect_transform_layer
try_extract_rect_transform_layer = _try_extract_rect_transform_layer

