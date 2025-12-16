"""主窗口 wiring 层：集中放置信号绑定与导航请求转发。"""

from .graph_library_binder import bind_graph_library_page
from .management_binder import bind_management_page
from .package_library_binder import bind_package_library_page
from .right_panel_binder import (
    bind_combat_panels,
    bind_composite_panels,
    bind_graph_property_panel,
    bind_management_panels,
    bind_template_instance_panel,
    bind_validation_detail_panel,
)
from .todo_binder import bind_todo_page
from .validation_binder import bind_validation_page

__all__ = [
    "bind_graph_library_page",
    "bind_management_page",
    "bind_package_library_page",
    "bind_combat_panels",
    "bind_composite_panels",
    "bind_graph_property_panel",
    "bind_management_panels",
    "bind_template_instance_panel",
    "bind_validation_detail_panel",
    "bind_todo_page",
    "bind_validation_page",
]


