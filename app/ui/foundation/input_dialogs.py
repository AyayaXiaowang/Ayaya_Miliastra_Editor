from __future__ import annotations

"""统一的输入对话框封装。

本模块基于 `FormDialog` 提供文本/枚举/整数输入的标准弹窗，
用于替代分散的 `QInputDialog.get*` 调用，保证样式与按钮文案一致。
"""

from typing import Optional, Sequence

from PyQt6 import QtWidgets

from app.ui.foundation.base_widgets import FormDialog
from app.ui.foundation.theme_manager import ThemeManager


def prompt_text(
    parent: QtWidgets.QWidget | None,
    title: str,
    label: str,
    *,
    placeholder: str = "",
    text: str = "",
) -> Optional[str]:
    """显示单行文本输入对话框并返回用户输入（去除首尾空白）。

    返回：
        - 非空字符串：用户点击“确定”且最终文本非空
        - None：用户取消或文本为空
    """
    dialog = FormDialog(title=title, width=420, height=200, parent=parent)

    line_edit = QtWidgets.QLineEdit()
    line_edit.setStyleSheet(ThemeManager.input_style())
    if placeholder:
        line_edit.setPlaceholderText(placeholder)
    if text:
        line_edit.setText(text)

    dialog.add_form_field(label, line_edit, field_name="value")

    if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
        return None

    value = line_edit.text().strip()
    if not value:
        return None
    return value


def prompt_item(
    parent: QtWidgets.QWidget | None,
    title: str,
    label: str,
    items: Sequence[str],
    *,
    current_index: int = 0,
    editable: bool = False,
) -> Optional[str]:
    """显示下拉枚举选择对话框并返回选中的条目文本。

    返回：
        - 字符串：用户点击“确定”后当前下拉框文本（可编辑模式下为用户输入）
        - None：用户取消或列表为空
    """
    choices = list(items)
    if not choices:
        return None

    dialog = FormDialog(title=title, width=420, height=200, parent=parent)

    combo = QtWidgets.QComboBox()
    combo.setStyleSheet(ThemeManager.combo_box_style())
    combo.addItems(choices)
    combo.setEditable(editable)

    if 0 <= current_index < len(choices):
        combo.setCurrentIndex(current_index)

    dialog.add_form_field(label, combo, field_name="value")

    if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
        return None

    value = combo.currentText().strip()
    if not value:
        return None
    return value


def prompt_int(
    parent: QtWidgets.QWidget | None,
    title: str,
    label: str,
    *,
    value: int = 0,
    minimum: int = 0,
    maximum: int = 999_999,
    step: int = 1,
) -> Optional[int]:
    """显示整数输入对话框并返回用户选择的整数值。

    返回：
        - int：用户点击“确定”后的数值
        - None：用户取消
    """
    dialog = FormDialog(title=title, width=420, height=200, parent=parent)

    spin_box = QtWidgets.QSpinBox()
    spin_box.setStyleSheet(ThemeManager.spin_box_style())
    spin_box.setRange(minimum, maximum)
    spin_box.setSingleStep(step)
    spin_box.setValue(value)

    dialog.add_form_field(label, spin_box, field_name="value")

    if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
        return None

    return int(spin_box.value())


__all__ = ["prompt_text", "prompt_item", "prompt_int"]


