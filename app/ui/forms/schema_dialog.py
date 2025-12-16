from __future__ import annotations

from typing import Optional, Sequence, Tuple

from PyQt6 import QtGui, QtWidgets

from app.ui.foundation.base_widgets import FormDialog
from app.ui.foundation.theme_manager import Colors, ThemeManager


class FormDialogBuilder:
    """标准表单对话框构建器，封装常见输入控件与按钮布局。

    设计目标：
    - 统一复用 `FormDialog` 的样式与按钮区；
    - 通过一组 `add_*` 方法快速拼装表单字段；
    - 将具体业务逻辑与校验留在调用方（通过 `dialog.validate` 或返回结果自行处理）。
    """

    def __init__(
        self,
        parent: QtWidgets.QWidget,
        title: str,
        fixed_size: Optional[Tuple[int, int]] = None,
    ) -> None:
        width, height = fixed_size if fixed_size else (420, 320)
        self.dialog = FormDialog(title=title, width=width, height=height, parent=parent)
        self._form_layout = self.dialog.form_layout

    def add_line_edit(
        self,
        label: str,
        text: str = "",
        placeholder: Optional[str] = None,
        read_only: bool = False,
    ) -> QtWidgets.QLineEdit:
        line_edit = QtWidgets.QLineEdit(text)
        if placeholder:
            line_edit.setPlaceholderText(placeholder)
        line_edit.setReadOnly(read_only)
        line_edit.setStyleSheet(ThemeManager.input_style())
        self._form_layout.addRow(label, line_edit)
        return line_edit

    def add_combo_box(
        self,
        label: str,
        items: Sequence[str],
        current_text: Optional[str] = None,
    ) -> QtWidgets.QComboBox:
        combo_box = QtWidgets.QComboBox()
        combo_box.setStyleSheet(ThemeManager.combo_box_style())
        combo_box.addItems(list(items))
        if current_text:
            combo_box.setCurrentText(current_text)
        self._form_layout.addRow(label, combo_box)
        return combo_box

    def add_spin_box(
        self,
        label: str,
        minimum: int,
        maximum: int,
        value: int,
        single_step: int = 1,
    ) -> QtWidgets.QSpinBox:
        spin_box = QtWidgets.QSpinBox()
        spin_box.setStyleSheet(ThemeManager.spin_box_style())
        spin_box.setRange(minimum, maximum)
        spin_box.setSingleStep(single_step)
        spin_box.setValue(value)
        self._form_layout.addRow(label, spin_box)
        return spin_box

    def add_double_spin_box(
        self,
        label: str,
        minimum: float,
        maximum: float,
        value: float,
        decimals: int = 2,
        single_step: float = 0.1,
        suffix: Optional[str] = None,
    ) -> QtWidgets.QDoubleSpinBox:
        spin_box = QtWidgets.QDoubleSpinBox()
        spin_box.setStyleSheet(ThemeManager.spin_box_style())
        spin_box.setRange(minimum, maximum)
        spin_box.setDecimals(decimals)
        spin_box.setSingleStep(single_step)
        if suffix:
            spin_box.setSuffix(suffix)
        spin_box.setValue(value)
        self._form_layout.addRow(label, spin_box)
        return spin_box

    def add_check_box(self, label: str, checked: bool = False) -> QtWidgets.QCheckBox:
        check_box = QtWidgets.QCheckBox()
        check_box.setChecked(checked)
        self._form_layout.addRow(label, check_box)
        return check_box

    def add_plain_text_edit(
        self,
        label: str,
        text: str = "",
        min_height: Optional[int] = None,
        max_height: Optional[int] = None,
    ) -> QtWidgets.QTextEdit:
        text_edit = QtWidgets.QTextEdit()
        text_edit.setPlainText(text)
        if min_height:
            text_edit.setMinimumHeight(min_height)
        if max_height:
            text_edit.setMaximumHeight(max_height)
        text_edit.setStyleSheet(ThemeManager.input_style())
        self._form_layout.addRow(label, text_edit)
        return text_edit

    def add_color_picker(
        self,
        label: str,
        color: str = Colors.BG_CARD,
        button_text: str = "选择颜色",
    ) -> QtWidgets.QLineEdit:
        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        color_edit = QtWidgets.QLineEdit(color)
        color_edit.setStyleSheet(ThemeManager.input_style())
        pick_button = QtWidgets.QPushButton(button_text)
        pick_button.setStyleSheet(ThemeManager.button_style())

        def choose_color() -> None:
            initial = QtGui.QColor(color_edit.text() or Colors.BG_CARD)
            selected = QtWidgets.QColorDialog.getColor(initial, self.dialog)
            if selected.isValid():
                color_edit.setText(selected.name())

        pick_button.clicked.connect(choose_color)
        layout.addWidget(color_edit, 1)
        layout.addWidget(pick_button)
        self._form_layout.addRow(label, container)
        return color_edit

    def add_vector3_editor(
        self,
        label: str,
        values: Sequence[float],
        minimum: float = -9999.0,
        maximum: float = 9999.0,
        decimals: int = 2,
    ) -> tuple[
        QtWidgets.QDoubleSpinBox,
        QtWidgets.QDoubleSpinBox,
        QtWidgets.QDoubleSpinBox,
    ]:
        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        components: list[QtWidgets.QDoubleSpinBox] = []
        labels = ("X:", "Y:", "Z:")
        defaults = list(values) if len(values) == 3 else [0.0, 0.0, 0.0]

        for axis, default in zip(labels, defaults):
            layout.addWidget(QtWidgets.QLabel(axis))
            spin = QtWidgets.QDoubleSpinBox()
            spin.setStyleSheet(ThemeManager.spin_box_style())
            spin.setRange(minimum, maximum)
            spin.setDecimals(decimals)
            spin.setValue(default)
            layout.addWidget(spin)
            components.append(spin)

        self._form_layout.addRow(label, container)
        return components[0], components[1], components[2]

    def add_custom_row(self, label: str, widget: QtWidgets.QWidget) -> None:
        """在表单中追加一行自定义控件。"""
        self._form_layout.addRow(label, widget)

    def add_buttons(self) -> QtWidgets.QDialogButtonBox:
        """返回底层对话框的按钮区，便于自定义按钮行为。"""
        return self.dialog.button_box

    def exec(self) -> bool:
        """显示对话框并返回是否被接受。"""
        return self.dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted


