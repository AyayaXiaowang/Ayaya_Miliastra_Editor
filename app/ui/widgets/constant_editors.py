"""常量编辑控件模块

包含用于节点输入端口的常量值编辑控件（文本、布尔值、向量3）。
"""
from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets
from typing import TYPE_CHECKING, Optional, Union

from app.ui.graph.graph_palette import GraphPalette

if TYPE_CHECKING:
    from app.ui.graph.items.node_item import NodeGraphicsItem


class ConstantTextEdit(QtWidgets.QGraphicsTextItem):
    """可编辑的常量值文本框（默认泛型类型）"""
    def __init__(self, node_item: 'NodeGraphicsItem', port_name: str, port_type: str = "泛型", parent=None):
        super().__init__(parent)
        self.node_item = node_item
        self.port_name = port_name
        self.port_type = port_type
        self._layout_timer = None  # 兼容保留（将使用 Debouncer）
        self._layout_debouncer = None
        self.setDefaultTextColor(QtGui.QColor(GraphPalette.TEXT_LABEL))  # 使用更亮的颜色，与端口标签一致
        self.setFont(QtGui.QFont('Consolas', 8))
        self.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextEditorInteraction)

        # 初始化显示文本：将值为字符串 "None" 的常量视为“未填写”，在编辑器中显示为空。
        raw_value = node_item.node.input_constants.get(port_name, "")
        if isinstance(raw_value, str):
            text_value = raw_value.strip()
            if text_value.lower() == "none":
                initial_text = ""
            else:
                initial_text = raw_value
        else:
            initial_text = str(raw_value) if raw_value is not None else ""
        self.setPlainText(initial_text)
        
        # 设置文本框样式和交互
        # Z-order: 必须高于端口(20)，才能接收鼠标事件
        self.setZValue(25)
        # 设置可聚焦，允许用户点击进行编辑
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)
        # 不要设置为可选中，避免与文本选择冲突
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
    
    def keyPressEvent(self, event):
        """处理按键事件，阻止换行并根据类型限制输入"""
        if event.key() in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
            # 回车时失去焦点，触发保存
            self.clearFocus()
            event.accept()
            return
        
        # 根据端口类型限制输入
        if self.port_type == "整数":
            # 只允许数字和负号
            text = event.text()
            if text and not (text.isdigit() or text == '-'):
                event.accept()
                return
        elif self.port_type == "浮点数":
            # 只允许数字、小数点和负号
            text = event.text()
            if text and not (text.isdigit() or text in '.-'):
                event.accept()
                return
        
        super().keyPressEvent(event)
        # 不要在输入时重新布局，会导致失去焦点，只在失去焦点时布局
        
    def focusOutEvent(self, event):
        """失去焦点时保存"""
        # 清除任何残留的文本选择并恢复默认前景色，避免选区导致的永久变白
        cursor = self.textCursor()
        if cursor.hasSelection():
            cursor.clearSelection()
            self.setTextCursor(cursor)
        doc_cursor = self.textCursor()
        doc_cursor.select(QtGui.QTextCursor.SelectionType.Document)
        fmt = QtGui.QTextCharFormat()
        fmt.setForeground(QtGui.QBrush(QtGui.QColor(GraphPalette.TEXT_LABEL)))
        doc_cursor.mergeCharFormat(fmt)
        doc_cursor.clearSelection()
        self.setTextCursor(doc_cursor)
        text = self.toPlainText().strip()
        # 移除换行符
        text = text.replace('\n', '').replace('\r', '')
        old_value = self.node_item.node.input_constants.get(self.port_name, "")
        new_value = text
        
        # 检查值是否改变
        value_changed = False
        if text:
            if old_value != new_value:
                self.node_item.node.input_constants[self.port_name] = text
                value_changed = True
        else:
            if self.port_name in self.node_item.node.input_constants:
                del self.node_item.node.input_constants[self.port_name]
                value_changed = True
        
        # 延迟布局操作，让焦点切换先完成，避免界面跳转
        if value_changed:
            from app.ui.foundation.debounce import Debouncer
            if self._layout_debouncer is None:
                self._layout_debouncer = Debouncer(self)
            self._layout_debouncer.debounce(50, self._delayed_layout_and_save)
        
        super().focusOutEvent(event)
    
    def _delayed_layout_and_save(self):
        """延迟执行的布局和保存操作"""
        # 重新布局以确保节点宽度正确
        self.node_item._layout_ports()
        self.node_item.update()
        
        # 触发自动保存
        if self.scene():
            scene = self.scene()
            if hasattr(scene, 'on_data_changed') and scene.on_data_changed:
                scene.on_data_changed()
        
        # 清理兼容字段
        self._layout_timer = None


class ConstantBoolComboBox(QtWidgets.QGraphicsProxyWidget):
    """布尔值下拉选择框"""
    def __init__(self, node_item: 'NodeGraphicsItem', port_name: str, parent=None):
        super().__init__(parent)
        self.node_item = node_item
        self.port_name = port_name
        
        # 创建QComboBox
        self.combo = QtWidgets.QComboBox()
        self.combo.addItems(["否", "是"])
        self.combo.setFont(QtGui.QFont('Microsoft YaHei UI', 8))
        self.combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {GraphPalette.INPUT_BG};
                color: {GraphPalette.TEXT_LABEL};
                border: 1px solid {GraphPalette.INPUT_BORDER};
                border-radius: 3px;
                padding: 2px 5px;
            }}
            QComboBox:hover {{
                border: 1px solid {GraphPalette.INPUT_BORDER_HOVER};
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid {GraphPalette.TEXT_LABEL};
                margin-right: 5px;
            }}
        """)
        
        # 设置初始值
        current_value = node_item.node.input_constants.get(port_name, "否")
        
        # 如果没有保存过值，立即保存默认值
        if port_name not in node_item.node.input_constants:
            node_item.node.input_constants[port_name] = current_value
        
        if current_value.lower() in ["true", "是", "1", "yes"]:
            self.combo.setCurrentIndex(1)
        else:
            self.combo.setCurrentIndex(0)
        
        # 连接信号
        self.combo.currentIndexChanged.connect(self._on_value_changed)
        
        self.setWidget(self.combo)
        self.setZValue(25)
    
    def _on_value_changed(self, index):
        """值改变时保存"""
        value = "是" if index == 1 else "否"
        self.node_item.node.input_constants[self.port_name] = value
        # 只更新显示，不重新布局（布尔值控件大小固定，不需要重新布局）
        self.node_item.update()
        
        # 触发自动保存
        if self.scene():
            scene = self.scene()
            if hasattr(scene, 'on_data_changed') and scene.on_data_changed:
                scene.on_data_changed()


class ConstantVector3Edit(QtWidgets.QGraphicsProxyWidget):
    """向量3输入框（X, Y, Z三个输入框）"""
    def __init__(self, node_item: 'NodeGraphicsItem', port_name: str, parent=None):
        super().__init__(parent)
        self.node_item = node_item
        self.port_name = port_name
        
        # 创建容器widget
        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        
        # 解析当前值
        current_value = node_item.node.input_constants.get(port_name, "0, 0, 0")
        # 兼容以 Python 元组/列表字面量形式存储的三维向量，如 "(0, 0, 0)" 或 "[0, 0, 0]"
        text = current_value.strip()
        if (len(text) >= 2) and ((text[0] == '(' and text[-1] == ')') or (text[0] == '[' and text[-1] == ']')):
            current_value = text[1:-1].strip()
        
        # 如果没有保存过值，立即保存默认值
        if port_name not in node_item.node.input_constants:
            node_item.node.input_constants[port_name] = current_value
        
        values = [v.strip() for v in current_value.split(',')]
        if len(values) != 3:
            values = ["0", "0", "0"]
        
        # 创建三个输入框
        self.x_edit = self._create_axis_edit("X:", values[0])
        self.y_edit = self._create_axis_edit("Y:", values[1])
        self.z_edit = self._create_axis_edit("Z:", values[2])
        
        layout.addWidget(self.x_edit)
        layout.addWidget(self.y_edit)
        layout.addWidget(self.z_edit)
        
        container.setStyleSheet(f"""
            QWidget {{
                background-color: transparent;
            }}
            QLabel {{
                color: {GraphPalette.TEXT_SECONDARY};
                font-size: 8px;
            }}
            QLineEdit {{
                background-color: {GraphPalette.INPUT_BG};
                color: {GraphPalette.TEXT_LABEL};
                border: 1px solid {GraphPalette.INPUT_BORDER};
                border-radius: 2px;
                padding: 1px 3px;
                font-size: 8px;
            }}
            QLineEdit:focus {{
                border: 1px solid {GraphPalette.INPUT_BORDER_HOVER};
            }}
        """)
        
        self.setWidget(container)
        self.setZValue(25)
    
    def _create_axis_edit(self, label: str, value: str):
        """创建单个轴的输入框"""
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)
        
        # 标签（不可编辑）
        label_widget = QtWidgets.QLabel(label)
        label_widget.setFont(QtGui.QFont('Consolas', 7))
        layout.addWidget(label_widget)
        
        # 输入框（只能输入数字和小数点）
        edit = QtWidgets.QLineEdit(value)
        edit.setFont(QtGui.QFont('Consolas', 8))
        edit.setFixedWidth(30)
        # 使用正则表达式验证器，只允许数字、小数点和负号
        validator = QtGui.QRegularExpressionValidator(QtCore.QRegularExpression(r"^-?\d*\.?\d*$"))
        edit.setValidator(validator)
        edit.textChanged.connect(self._on_value_changed)
        layout.addWidget(edit)
        
        return widget
    
    def _on_value_changed(self):
        """任意输入框值改变时保存"""
        # 获取X、Y、Z输入框
        x_edit = self.x_edit.findChild(QtWidgets.QLineEdit)
        y_edit = self.y_edit.findChild(QtWidgets.QLineEdit)
        z_edit = self.z_edit.findChild(QtWidgets.QLineEdit)
        
        x_val = x_edit.text() or "0"
        y_val = y_edit.text() or "0"
        z_val = z_edit.text() or "0"
        
        # 保存为逗号分隔的字符串
        value = f"{x_val}, {y_val}, {z_val}"
        self.node_item.node.input_constants[self.port_name] = value
        # 只更新显示，不重新布局（向量控件大小固定，不需要重新布局）
        
        # 触发自动保存
        if self.scene():
            scene = self.scene()
            if hasattr(scene, 'on_data_changed') and scene.on_data_changed:
                scene.on_data_changed()
        self.node_item.update()


def create_constant_editor_for_port(
    node_item: "NodeGraphicsItem",
    port_name: str,
    port_type: str,
    parent: Optional[QtWidgets.QGraphicsItem] = None,
) -> Optional[QtWidgets.QGraphicsItem]:
    """根据端口类型创建对应的常量编辑控件。

    约定：
    - 实体类型（\"实体\"）不在节点内联显示常量编辑控件，返回 None；
    - \"布尔值\" 使用下拉框；
    - \"三维向量\" 使用三轴输入控件；
    - 其他类型统一使用文本编辑框，并将 `port_type` 透传给文本框用于输入约束。
    """
    if port_type == "实体":
        return None
    if port_type == "布尔值":
        return ConstantBoolComboBox(node_item, port_name, parent)
    if port_type == "三维向量":
        return ConstantVector3Edit(node_item, port_name, parent)
    return ConstantTextEdit(node_item, port_name, port_type, parent)

