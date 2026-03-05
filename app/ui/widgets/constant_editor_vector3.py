"""常量编辑器：三维向量输入控件（ConstantVector3Edit）。"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING, cast

from PyQt6 import QtCore, QtGui, QtWidgets

from app.ui.foundation import fonts as ui_fonts
from app.ui.graph import graph_component_styles as graph_styles

from app.ui.widgets.constant_editors_helpers import (
    _is_inline_constant_virtualization_active_for_node_item,
    _safe_strip_text,
)

if TYPE_CHECKING:
    from app.ui.graph.items.node_item import NodeGraphicsItem


class ConstantVector3Edit(QtWidgets.QGraphicsProxyWidget):
    """向量3输入框（X, Y, Z三个输入框）"""

    def __init__(self, node_item: "NodeGraphicsItem", port_name: str, parent=None):
        super().__init__(parent)
        self.node_item = node_item
        self.port_name = port_name

        # 创建容器widget
        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(graph_styles.GRAPH_INLINE_VECTOR3_CONTAINER_LAYOUT_SPACING_PX)
        container.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)

        # 解析当前值：兼容 None / list / tuple / 字符串字面量，避免旧数据触发 .strip() 崩溃。
        raw_value = node_item.node.input_constants.get(port_name, "0, 0, 0")
        if isinstance(raw_value, (list, tuple)) and len(raw_value) == 3:
            values = [_safe_strip_text(v) for v in raw_value]
            current_value = f"{values[0]}, {values[1]}, {values[2]}"
        else:
            current_value = _safe_strip_text(raw_value) or "0, 0, 0"
            # 兼容以 Python 元组/列表字面量形式存储的三维向量，如 "(0, 0, 0)" 或 "[0, 0, 0]"
            if (len(current_value) >= 2) and (
                (current_value[0] == "(" and current_value[-1] == ")")
                or (current_value[0] == "[" and current_value[-1] == "]")
            ):
                current_value = current_value[1:-1].strip()
            values = [v.strip() for v in current_value.split(",")]

        # 如果没有保存过值，立即保存默认值
        if port_name not in node_item.node.input_constants:
            node_item.node.input_constants[port_name] = current_value

        if len(values) != 3:
            values = ["0", "0", "0"]

        # 创建三个输入框
        self.x_edit = self._create_axis_edit("X:", values[0])
        self.y_edit = self._create_axis_edit("Y:", values[1])
        self.z_edit = self._create_axis_edit("Z:", values[2])

        layout.addWidget(self.x_edit)
        layout.addWidget(self.y_edit)
        layout.addWidget(self.z_edit)

        # 高度缩小30%：通过 max-height 限制控件高度
        container.setFixedHeight(graph_styles.GRAPH_INLINE_VECTOR3_CONTAINER_HEIGHT_PX)
        # 固定宽度避免容器默认尺寸过大时，内部 QLabel 被拉伸把数值输入框挤到右侧（看起来像“靠近下一个轴”）。
        container.setFixedWidth(graph_styles.GRAPH_INLINE_VECTOR3_CONTAINER_WIDTH_PX)
        container.setStyleSheet(graph_styles.graph_inline_vector3_container_style())

        self.setWidget(container)
        self.setZValue(25)

    def _create_axis_edit(self, label: str, value: str):
        """创建单个轴的输入框"""
        widget = QtWidgets.QWidget()
        widget.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        layout = QtWidgets.QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(graph_styles.GRAPH_INLINE_VECTOR3_AXIS_LAYOUT_SPACING_PX)

        # 标签（不可编辑）
        label_widget = QtWidgets.QLabel(label)
        label_widget.setFont(ui_fonts.monospace_font(7))
        label_widget.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        layout.addWidget(label_widget)

        # 输入框（只能输入数字和小数点）
        edit = QtWidgets.QLineEdit(value)
        edit.setFont(ui_fonts.monospace_font(8))
        edit.setFixedWidth(graph_styles.GRAPH_INLINE_VECTOR3_LINE_EDIT_WIDTH_PX)
        edit.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        edit.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        # 使用正则表达式验证器，只允许数字、小数点和负号
        validator = QtGui.QRegularExpressionValidator(QtCore.QRegularExpression(r"^-?\d*\.?\d*$"))
        edit.setValidator(validator)
        edit.textChanged.connect(self._on_value_changed)
        edit.editingFinished.connect(self._on_any_axis_editing_finished)
        layout.addWidget(edit)

        widget.setFixedWidth(widget.sizeHint().width())
        return widget

    def _on_any_axis_editing_finished(self) -> None:
        """任意轴输入框结束编辑（失焦）时：若整个向量控件已不再聚焦则释放。"""
        if not _is_inline_constant_virtualization_active_for_node_item(self.node_item):
            return
        QtCore.QTimer.singleShot(0, self._maybe_release_after_focus_check)

    def _maybe_release_after_focus_check(self) -> None:
        # 若焦点仍在该控件的任意轴输入框内，则不释放（支持 X→Y→Z 连续编辑）
        for axis_container in (getattr(self, "x_edit", None), getattr(self, "y_edit", None), getattr(self, "z_edit", None)):
            if not isinstance(axis_container, QtWidgets.QWidget):
                continue
            axis_line = axis_container.findChild(QtWidgets.QLineEdit)
            if isinstance(axis_line, QtWidgets.QLineEdit) and axis_line.hasFocus():
                return
        release_fn = getattr(self.node_item, "release_inline_constant_editor", None)
        if callable(release_fn):
            release_fn(self.port_name)

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
        scene = self.scene()
        if scene is not None:
            scene_any = cast(Any, scene)
            on_data_changed = getattr(scene_any, "on_data_changed", None)
            if on_data_changed:
                on_data_changed()
        self.node_item.update()

    def focusOutEvent(self, event: QtGui.QFocusEvent | None) -> None:  # type: ignore[override]
        super().focusOutEvent(event)
        if _is_inline_constant_virtualization_active_for_node_item(self.node_item):
            QtCore.QTimer.singleShot(0, self._maybe_release_after_focus_check)

