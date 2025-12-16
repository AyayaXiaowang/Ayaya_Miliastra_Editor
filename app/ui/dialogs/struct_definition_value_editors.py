from __future__ import annotations

"""结构体定义相关值编辑组件与通用输入控件的聚合入口。

本模块仅负责统一导出以下类，保持既有导入路径不变：
- ScrollSafeComboBox / ClickToEditLineEdit：用于表格行内编辑的通用输入控件
- ListValueEditor / ListEditDialog：列表字段的内联编辑器与弹窗
- DictValueEditor / DictEditDialog：字典字段的内联编辑器与弹窗

具体实现拆分在：
- ui.dialogs.value_editor_common_widgets
- ui.dialogs.list_value_editors
- ui.dialogs.dict_value_editors
"""

from app.ui.dialogs.value_editor_common_widgets import (
    ClickToEditLineEdit,
    ScrollSafeComboBox,
)
from app.ui.dialogs.list_value_editors import ListEditDialog, ListValueEditor
from app.ui.dialogs.dict_value_editors import DictEditDialog, DictValueEditor


__all__ = [
    "ScrollSafeComboBox",
    "ClickToEditLineEdit",
    "ListValueEditor",
    "ListEditDialog",
    "DictValueEditor",
    "DictEditDialog",
]


