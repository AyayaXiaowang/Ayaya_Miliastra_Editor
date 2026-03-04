from __future__ import annotations

"""
layout_templates.py

对外兼容入口：
- 仍提供 `ugc_file_tools.ui_patchers.layout_templates` 这个模块路径
- 实现已拆分到 `layout_templates_parts/`，避免单文件过长
"""

from ugc_file_tools.ui_patchers.layout.layout_templates_parts.control_groups import (
    create_control_group_in_library,
    create_control_group_in_library_from_component_groups,
    place_control_group_template_in_layout,
    save_control_group_as_template,
    save_component_groups_as_custom_templates,
    set_control_rect_transform_layers,
)
from ugc_file_tools.ui_patchers.layout.layout_templates_parts.layout_create import create_layout_in_gil
from ugc_file_tools.ui_patchers.layout.layout_templates_parts.progressbar_templates import (
    create_progressbar_template_and_place_in_layout,
    create_progressbar_template_and_place_many_in_layout,
)
from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import (
    DEFAULT_CANVAS_SIZE_BY_STATE_INDEX,
    DEFAULT_LIBRARY_ROOT_GUID,
    CreatedControlGroup,
    CreatedControlGroupTemplate,
    CreatedLayout,
    CreatedProgressbarTemplate,
    PlacedProgressbarInstance,
)

__all__ = [
    "DEFAULT_LIBRARY_ROOT_GUID",
    "DEFAULT_CANVAS_SIZE_BY_STATE_INDEX",
    "CreatedLayout",
    "CreatedProgressbarTemplate",
    "PlacedProgressbarInstance",
    "CreatedControlGroup",
    "CreatedControlGroupTemplate",
    "create_layout_in_gil",
    "create_progressbar_template_and_place_in_layout",
    "create_progressbar_template_and_place_many_in_layout",
    "create_control_group_in_library",
    "create_control_group_in_library_from_component_groups",
    "save_control_group_as_template",
    "save_component_groups_as_custom_templates",
    "place_control_group_template_in_layout",
    "set_control_rect_transform_layers",
]



