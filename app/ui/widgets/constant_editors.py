"""常量编辑控件模块（对外导入门面）。

包含用于节点输入端口的常量值编辑控件（文本、布尔值、向量3）。

实现按职责拆分到：
- `constant_editors_helpers.py`：文本清洗、变量 ID/名称映射、虚拟化判定
- `constant_editors_display.py`：将常量解析为“画布展示文本”（虚拟化占位绘制）
- `constant_editor_text_edit.py`：`ConstantTextEdit`
- `constant_editor_bool_combo.py`：`ConstantBoolComboBox`
- `constant_editor_vector3.py`：`ConstantVector3Edit`
- `constant_editors_factory.py`：`create_constant_editor_for_port`

外部代码应继续从本模块导入，保持 API 稳定。
"""

from __future__ import annotations

from app.ui.widgets.constant_editor_bool_combo import ConstantBoolComboBox
from app.ui.widgets.constant_editor_text_edit import ConstantTextEdit
from app.ui.widgets.constant_editor_vector3 import ConstantVector3Edit
from app.ui.widgets.constant_editors_display import resolve_constant_display_for_port
from app.ui.widgets.constant_editors_factory import create_constant_editor_for_port

__all__ = [
    "ConstantTextEdit",
    "ConstantBoolComboBox",
    "ConstantVector3Edit",
    "create_constant_editor_for_port",
    "resolve_constant_display_for_port",
]

