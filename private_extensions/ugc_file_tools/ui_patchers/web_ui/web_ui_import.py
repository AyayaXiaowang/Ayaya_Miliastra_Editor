from __future__ import annotations

"""
Web Workbench 导出的 JSON → `.gil` 写回入口（薄门面层）。

实现已按职责拆分到同目录下的 `web_ui_import_*.py` 模块中，避免单文件过大。
"""

from .web_ui_import_main import import_web_ui_control_group_template_to_gil_layout
from .web_ui_import_item_display import (
    find_item_display_blob,
    patch_item_display_blob_bytes,
    write_item_display_blob_back_to_record,
)
from .web_ui_import_types import ImportedWebItemDisplay, ImportedWebProgressbar, ImportedWebTextbox

__all__ = [
    "ImportedWebItemDisplay",
    "ImportedWebProgressbar",
    "ImportedWebTextbox",
    "import_web_ui_control_group_template_to_gil_layout",
    "find_item_display_blob",
    "patch_item_display_blob_bytes",
    "write_item_display_blob_back_to_record",
]

