"""标准化对话框与提示入口，集中封装 Qt MessageBox 行为。"""

from PyQt6 import QtWidgets


def show_warning_dialog(parent: QtWidgets.QWidget | None, title: str, message: str) -> None:
    """显示统一的警告对话框。"""
    QtWidgets.QMessageBox.warning(parent, title, message)


def show_info_dialog(parent: QtWidgets.QWidget | None, title: str, message: str) -> None:
    """显示统一的信息对话框。"""
    QtWidgets.QMessageBox.information(parent, title, message)


def show_error_dialog(parent: QtWidgets.QWidget | None, title: str, message: str) -> None:
    """显示统一的错误对话框。"""
    QtWidgets.QMessageBox.critical(parent, title, message)


def ask_yes_no_dialog(
    parent: QtWidgets.QWidget | None,
    title: str,
    message: str,
    *,
    default: QtWidgets.QMessageBox.StandardButton = QtWidgets.QMessageBox.StandardButton.No,
) -> bool:
    """显示“是/否”确认框并返回用户是否选择“是”。"""
    reply = QtWidgets.QMessageBox.question(
        parent,
        title,
        message,
        QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        default,
    )
    return reply == QtWidgets.QMessageBox.StandardButton.Yes


def ask_acknowledge_or_suppress_dialog(
    parent: QtWidgets.QWidget | None,
    title: str,
    message: str,
    *,
    acknowledge_label: str = "确定",
    suppress_label: str = "不再提示",
) -> bool:
    """显示"确认 + 不再提示"型对话框，返回是否选择"不再提示"。"""
    message_box = QtWidgets.QMessageBox(parent)
    message_box.setIcon(QtWidgets.QMessageBox.Icon.Warning)
    message_box.setWindowTitle(title)
    message_box.setText(message)
    acknowledge_button = message_box.addButton(
        acknowledge_label,
        QtWidgets.QMessageBox.ButtonRole.DestructiveRole,
    )
    suppress_button = message_box.addButton(
        suppress_label,
        QtWidgets.QMessageBox.ButtonRole.AcceptRole,
    )
    message_box.setDefaultButton(acknowledge_button)
    message_box.exec()
    return message_box.clickedButton() is suppress_button


def prompt_text(
    parent: QtWidgets.QWidget | None,
    title: str,
    label: str,
    *,
    placeholder: str = "",
    text: str = "",
) -> str | None:
    """统一的单文本输入对话框辅助函数（兼容旧入口，实际委托给 `input_dialogs.prompt_text`）。

    为了避免在多个模块中复制 FormDialog 构建逻辑，这里仅作为薄封装：
    - 样式与行为由 `ui.foundation.input_dialogs.prompt_text` 决定；
    - 推荐新代码从 `ui.foundation` 顶层导入 `prompt_text` / `prompt_item` / `prompt_int`。
    """
    from app.ui.foundation.input_dialogs import prompt_text as _prompt_text

    return _prompt_text(
        parent,
        title,
        label,
        placeholder=placeholder,
        text=text,
    )


def apply_standard_button_box_labels(button_box: QtWidgets.QDialogButtonBox) -> None:
    """统一将标准 Ok/Cancel 按钮的文本替换为中文文案。

    Qt 默认会根据系统或翻译文件选择按钮文本，但在未加载翻译或跨平台时可能出现英文“OK/Cancel”。
    该辅助函数在创建 `QDialogButtonBox` 之后调用，确保所有标准确定/取消按钮都显示为“确定/取消”。
    """
    ok_button = button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
    if ok_button is not None:
        ok_button.setText("确定")

    cancel_button = button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Cancel)
    if cancel_button is not None:
        cancel_button.setText("取消")


__all__ = [
    "apply_standard_button_box_labels",
    "ask_acknowledge_or_suppress_dialog",
    "ask_yes_no_dialog",
    "prompt_text",
    "show_error_dialog",
    "show_info_dialog",
    "show_warning_dialog",
]

