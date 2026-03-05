"""常量编辑器：工厂方法（按端口类型选择控件）。"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from PyQt6 import QtWidgets

from app.ui.widgets.constant_editor_bool_combo import ConstantBoolComboBox
from app.ui.widgets.constant_editor_text_edit import ConstantTextEdit
from app.ui.widgets.constant_editor_vector3 import ConstantVector3Edit

if TYPE_CHECKING:
    from app.ui.graph.items.node_item import NodeGraphicsItem


def create_constant_editor_for_port(
    node_item: "NodeGraphicsItem",
    port_name: str,
    port_type: str,
    parent: Optional[QtWidgets.QGraphicsItem] = None,
) -> Optional[QtWidgets.QGraphicsItem]:
    """根据端口类型创建对应的常量编辑控件。

    约定：
    - 实体类型（"实体"）不在节点内联显示常量编辑控件，返回 None；
    - "布尔值" 使用下拉框；
    - "三维向量" 使用三轴输入控件；
    - 其他类型统一使用文本编辑框，并将 `port_type` 透传给文本框用于输入约束。
    """
    port_type_text = str(port_type or "")
    # “实体/结构体”属于引用/复合数据：只允许连线，不提供行内常量编辑（避免误把结构体当作字符串填值）。
    if port_type_text == "实体" or port_type_text.startswith("结构体"):
        return None
    if port_type_text == "布尔值":
        return ConstantBoolComboBox(node_item, port_name, parent)
    if port_type_text == "三维向量":
        return ConstantVector3Edit(node_item, port_name, parent)
    return ConstantTextEdit(node_item, port_name, port_type_text, parent)

