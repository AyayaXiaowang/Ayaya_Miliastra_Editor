from __future__ import annotations

"""
control_groups.py

对外稳定入口（薄门面）：
- 保持 `ugc_file_tools.ui_patchers.layout.layout_templates_parts.control_groups` 导入路径不变
- 实现拆分到 `control_groups_parts/`，避免单文件过长
"""

from .control_groups_parts.create_in_library import (
    create_control_group_in_library,
    create_control_group_in_library_from_component_groups,
)
from .control_groups_parts.layers import set_control_rect_transform_layers
from .control_groups_parts.place import place_control_group_template_in_layout
from .control_groups_parts.templates import (
    save_component_groups_as_custom_templates,
    save_control_group_as_template,
)

__all__ = [
    "create_control_group_in_library_from_component_groups",
    "save_component_groups_as_custom_templates",
    "create_control_group_in_library",
    "save_control_group_as_template",
    "place_control_group_template_in_layout",
    "set_control_rect_transform_layers",
]

