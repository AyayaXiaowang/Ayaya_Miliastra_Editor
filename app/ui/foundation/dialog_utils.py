"""标准化对话框与提示入口，集中封装 Qt MessageBox 行为。

约定：所有弹窗中的文本必须可选中/可复制（便于用户复制报错信息）。
"""

from PyQt6 import QtCore, QtWidgets
from app.ui.foundation.theme_manager import ThemeManager, Sizes


_MESSAGE_BOX_TEXT_INTERACTION_FLAGS = QtCore.Qt.TextInteractionFlag.TextBrowserInteraction

_MESSAGE_BOX_ICON_MAP: dict[str, QtWidgets.QMessageBox.Icon] = {
    "information": QtWidgets.QMessageBox.Icon.Information,
    "warning": QtWidgets.QMessageBox.Icon.Warning,
    "critical": QtWidgets.QMessageBox.Icon.Critical,
    "question": QtWidgets.QMessageBox.Icon.Question,
}

_MESSAGE_BOX_ROLE_MAP: dict[str, QtWidgets.QMessageBox.ButtonRole] = {
    "accept": QtWidgets.QMessageBox.ButtonRole.AcceptRole,
    "reject": QtWidgets.QMessageBox.ButtonRole.RejectRole,
    "destructive": QtWidgets.QMessageBox.ButtonRole.DestructiveRole,
    "action": QtWidgets.QMessageBox.ButtonRole.ActionRole,
    "yes": QtWidgets.QMessageBox.ButtonRole.YesRole,
    "no": QtWidgets.QMessageBox.ButtonRole.NoRole,
}

_DIALOG_BUTTON_ROLE_MAP: dict[str, QtWidgets.QDialogButtonBox.ButtonRole] = {
    "accept": QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole,
    "reject": QtWidgets.QDialogButtonBox.ButtonRole.RejectRole,
    "destructive": QtWidgets.QDialogButtonBox.ButtonRole.DestructiveRole,
    "action": QtWidgets.QDialogButtonBox.ButtonRole.ActionRole,
    "yes": QtWidgets.QDialogButtonBox.ButtonRole.YesRole,
    "no": QtWidgets.QDialogButtonBox.ButtonRole.NoRole,
}


def _enable_copyable_text_for_message_box(message_box: QtWidgets.QMessageBox) -> None:
    """让 QMessageBox 内的文本可选中/可复制。

    说明：
    - 仅启用“可复制文本”，不改变按钮逻辑。
    - 同时对内部 QLabel 做兜底处理，避免不同 Qt 版本/样式导致某些文本区域仍不可选中。
    """
    message_box.setTextInteractionFlags(_MESSAGE_BOX_TEXT_INTERACTION_FLAGS)

    for label_widget in message_box.findChildren(QtWidgets.QLabel):
        label_text = str(label_widget.text() or "").strip()
        if label_text == "":
            continue
        label_widget.setTextInteractionFlags(_MESSAGE_BOX_TEXT_INTERACTION_FLAGS)
        label_widget.setCursor(QtCore.Qt.CursorShape.IBeamCursor)


def show_warning_dialog(parent: QtWidgets.QWidget | None, title: str, message: str) -> None:
    """显示统一的警告对话框（文本可复制）。"""
    message_box = QtWidgets.QMessageBox(parent)
    message_box.setIcon(QtWidgets.QMessageBox.Icon.Warning)
    message_box.setWindowTitle(title)
    message_box.setText(message)
    message_box.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Ok)
    ok_button = message_box.button(QtWidgets.QMessageBox.StandardButton.Ok)
    if ok_button is not None:
        ok_button.setText("确定")
    _enable_copyable_text_for_message_box(message_box)
    message_box.exec()


def show_info_dialog(parent: QtWidgets.QWidget | None, title: str, message: str) -> None:
    """显示统一的信息对话框（文本可复制）。"""
    message_box = QtWidgets.QMessageBox(parent)
    message_box.setIcon(QtWidgets.QMessageBox.Icon.Information)
    message_box.setWindowTitle(title)
    message_box.setText(message)
    message_box.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Ok)
    ok_button = message_box.button(QtWidgets.QMessageBox.StandardButton.Ok)
    if ok_button is not None:
        ok_button.setText("确定")
    _enable_copyable_text_for_message_box(message_box)
    message_box.exec()


def show_error_dialog(
    parent: QtWidgets.QWidget | None,
    title: str,
    message: str,
    *,
    details: str | None = None,
    copy_text: str | None = None,
) -> None:
    """显示统一的错误对话框。

    约定：错误对话框必须提供“复制报错”按钮，方便用户将报错信息直接复制给开发者。
    """
    message_box = QtWidgets.QMessageBox(parent)
    message_box.setIcon(QtWidgets.QMessageBox.Icon.Critical)
    message_box.setWindowTitle(title)
    message_box.setText(message)
    if details:
        message_box.setDetailedText(details)

    _enable_copyable_text_for_message_box(message_box)

    copy_button = message_box.addButton("复制报错", QtWidgets.QMessageBox.ButtonRole.ActionRole)
    ok_button = message_box.addButton("确定", QtWidgets.QMessageBox.ButtonRole.AcceptRole)
    message_box.setDefaultButton(ok_button)

    message_box.exec()
    if message_box.clickedButton() is copy_button:
        resolved_copy_text = copy_text
        if resolved_copy_text is None:
            resolved_copy_text = f"{message}\n\n{details}" if details else message
        QtWidgets.QApplication.clipboard().setText(resolved_copy_text)


def ask_yes_no_dialog(
    parent: QtWidgets.QWidget | None,
    title: str,
    message: str,
    *,
    default_yes: bool = False,
) -> bool:
    """显示“是/否”确认框并返回用户是否选择“是”。

    注意：为了避免业务模块直接引用 `QMessageBox.StandardButton`，这里使用布尔参数控制默认按钮。
    """
    message_box = QtWidgets.QMessageBox(parent)
    message_box.setIcon(QtWidgets.QMessageBox.Icon.Question)
    message_box.setWindowTitle(title)
    message_box.setText(message)
    message_box.setStandardButtons(
        QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
    )

    yes_button = message_box.button(QtWidgets.QMessageBox.StandardButton.Yes)
    if yes_button is not None:
        yes_button.setText("是")
    no_button = message_box.button(QtWidgets.QMessageBox.StandardButton.No)
    if no_button is not None:
        no_button.setText("否")

    default_button = (
        QtWidgets.QMessageBox.StandardButton.Yes
        if default_yes
        else QtWidgets.QMessageBox.StandardButton.No
    )
    message_box.setDefaultButton(default_button)

    _enable_copyable_text_for_message_box(message_box)

    reply = message_box.exec()
    return reply == QtWidgets.QMessageBox.StandardButton.Yes


def ask_choice_dialog(
    parent: QtWidgets.QWidget | None,
    title: str,
    message: str,
    *,
    icon: str = "information",
    choices: list[tuple[str, str, str]],
    default_choice_key: str | None = None,
    escape_choice_key: str | None = None,
    details_title: str | None = None,
    details_lines: list[str] | None = None,
) -> str:
    """显示“多选项”对话框并返回被点击按钮的 key。

    用于少量需要“多个自定义按钮”的场景（例如：检查更新后提供“下载/打开页面/取消”）。

    Args:
        choices: [(key, label, role), ...]。key 必须唯一且非空。
        details_title: 可选的“清单标题”。提供 details_lines 时会展示带滚动区的清单对话框。
        details_lines: 可选的清单行（可复制，支持滚动）。用于“退出前保存/切换存档”等需要展示变更概览的场景。
    """
    if not choices:
        raise ValueError("choices 不能为空")

    normalized_icon = str(icon or "").strip().lower()
    resolved_icon = _MESSAGE_BOX_ICON_MAP.get(normalized_icon)
    if resolved_icon is None:
        raise ValueError(f"不支持的 icon: {normalized_icon}")

    normalized_details_lines: list[str] = []
    if details_lines is not None:
        normalized_details_lines = [str(line) for line in details_lines if str(line).strip()]

    if normalized_details_lines:
        # 使用自定义 QDialog 以支持“可滚动清单”，避免长文本导致 QMessageBox 撑大窗口。
        if not choices:
            raise ValueError("choices 不能为空")

        # 先做与 QMessageBox 同口径的 choices 校验与归一化
        key_to_label_and_role: dict[str, tuple[str, str]] = {}
        for choice_key, choice_label, choice_role in choices:
            normalized_key = str(choice_key or "").strip()
            if normalized_key == "":
                raise ValueError("choices 中存在空 key")
            if normalized_key in key_to_label_and_role:
                raise ValueError(f"choices 中存在重复 key: {normalized_key}")
            key_to_label_and_role[normalized_key] = (str(choice_label), str(choice_role))

        dialog = QtWidgets.QDialog(parent)
        dialog.setWindowTitle(title)
        dialog.setModal(True)
        dialog.setStyleSheet(ThemeManager.dialog_surface_style(include_tables=False))

        # 统一限制窗口最大尺寸，避免在小屏幕下超出可见范围
        screen = parent.screen() if isinstance(parent, QtWidgets.QWidget) else None
        if screen is None:
            screen = QtWidgets.QApplication.primaryScreen()
        available = screen.availableGeometry() if screen is not None else QtCore.QRect(0, 0, 1280, 720)
        max_width = max(520, int(available.width() * 0.85))
        max_height = max(360, int(available.height() * 0.85))
        dialog.setMaximumSize(max_width, max_height)
        dialog.resize(min(860, max_width), min(560, max_height))

        outer_layout = QtWidgets.QVBoxLayout(dialog)
        outer_layout.setContentsMargins(
            Sizes.PADDING_LARGE,
            Sizes.PADDING_LARGE,
            Sizes.PADDING_LARGE,
            Sizes.PADDING_LARGE,
        )
        outer_layout.setSpacing(Sizes.SPACING_LARGE)

        # 顶部：图标 + 文本
        header_layout = QtWidgets.QHBoxLayout()
        header_layout.setSpacing(Sizes.SPACING_LARGE)

        icon_label = QtWidgets.QLabel(dialog)
        icon_pixmap = QtWidgets.QMessageBox.standardIcon(resolved_icon)
        if not icon_pixmap.isNull():
            icon_label.setPixmap(
                icon_pixmap.scaled(
                    32,
                    32,
                    QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                    QtCore.Qt.TransformationMode.SmoothTransformation,
                )
            )
        icon_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        header_layout.addWidget(icon_label, 0)

        text_layout = QtWidgets.QVBoxLayout()
        text_layout.setSpacing(Sizes.SPACING_MEDIUM)

        message_label = QtWidgets.QLabel(str(message))
        message_label.setWordWrap(True)
        message_label.setTextInteractionFlags(_MESSAGE_BOX_TEXT_INTERACTION_FLAGS)
        message_label.setCursor(QtCore.Qt.CursorShape.IBeamCursor)
        text_layout.addWidget(message_label, 0)

        resolved_details_title = str(details_title or "").strip() or "修改清单（未保存）"
        details_title_label = QtWidgets.QLabel(resolved_details_title)
        details_title_label.setTextInteractionFlags(_MESSAGE_BOX_TEXT_INTERACTION_FLAGS)
        details_title_label.setCursor(QtCore.Qt.CursorShape.IBeamCursor)
        details_title_label.setStyleSheet(ThemeManager.heading(level=4))
        text_layout.addWidget(details_title_label, 0)

        details_edit = QtWidgets.QPlainTextEdit(dialog)
        details_edit.setReadOnly(True)
        details_edit.setUndoRedoEnabled(False)
        details_edit.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.WidgetWidth)
        details_edit.setPlainText("\n".join(normalized_details_lines))

        line_height = max(16, int(details_edit.fontMetrics().lineSpacing()))
        visible_lines = max(4, min(len(normalized_details_lines), 10))
        desired_height = int(line_height * (visible_lines + 1) + 18)
        max_details_height = min(int(max_height * 0.45), int(line_height * 14 + 24))
        details_edit.setFixedHeight(max(140, min(desired_height, max_details_height)))
        text_layout.addWidget(details_edit, 1)

        header_layout.addLayout(text_layout, 1)
        outer_layout.addLayout(header_layout, 1)

        # 底部：按钮
        button_box = QtWidgets.QDialogButtonBox(dialog)
        key_to_button: dict[str, QtWidgets.QAbstractButton] = {}
        for normalized_key, (choice_label, choice_role) in key_to_label_and_role.items():
            normalized_role = str(choice_role or "").strip().lower()
            resolved_role = _DIALOG_BUTTON_ROLE_MAP.get(normalized_role)
            if resolved_role is None:
                raise ValueError(f"不支持的 button role: {normalized_role}")
            button_widget = button_box.addButton(str(choice_label), resolved_role)
            key_to_button[normalized_key] = button_widget

        selected_key: str | None = None

        def on_clicked(clicked_button: QtWidgets.QAbstractButton) -> None:
            nonlocal selected_key
            for key, button_widget in key_to_button.items():
                if clicked_button is button_widget:
                    selected_key = key
                    dialog.accept()
                    return

        button_box.clicked.connect(on_clicked)

        # 默认按钮
        if default_choice_key is not None:
            normalized_default = str(default_choice_key or "").strip()
            default_button = key_to_button.get(normalized_default)
            if default_button is not None and isinstance(default_button, QtWidgets.QPushButton):
                default_button.setDefault(True)
                default_button.setFocus()

        outer_layout.addWidget(button_box, 0)

        dialog.exec()

        if selected_key is not None:
            return selected_key
        if escape_choice_key is not None:
            normalized_escape = str(escape_choice_key or "").strip()
            if normalized_escape in key_to_button:
                return normalized_escape
        first_key = next(iter(key_to_button))
        return first_key

    message_box = QtWidgets.QMessageBox(parent)
    message_box.setIcon(resolved_icon)
    message_box.setWindowTitle(title)
    message_box.setText(message)

    key_to_button: dict[str, QtWidgets.QAbstractButton] = {}
    for choice_key, choice_label, choice_role in choices:
        normalized_key = str(choice_key or "").strip()
        if normalized_key == "":
            raise ValueError("choices 中存在空 key")
        if normalized_key in key_to_button:
            raise ValueError(f"choices 中存在重复 key: {normalized_key}")

        normalized_role = str(choice_role or "").strip().lower()
        resolved_role = _MESSAGE_BOX_ROLE_MAP.get(normalized_role)
        if resolved_role is None:
            raise ValueError(f"不支持的 button role: {normalized_role}")

        button_widget = message_box.addButton(str(choice_label), resolved_role)
        key_to_button[normalized_key] = button_widget

    if default_choice_key is not None:
        normalized_default = str(default_choice_key or "").strip()
        default_button = key_to_button.get(normalized_default)
        if default_button is not None:
            message_box.setDefaultButton(default_button)

    if escape_choice_key is not None:
        normalized_escape = str(escape_choice_key or "").strip()
        escape_button = key_to_button.get(normalized_escape)
        if escape_button is not None:
            message_box.setEscapeButton(escape_button)

    _enable_copyable_text_for_message_box(message_box)

    message_box.exec()
    clicked_button = message_box.clickedButton()
    if clicked_button is None:
        if escape_choice_key is not None and str(escape_choice_key or "").strip() in key_to_button:
            return str(escape_choice_key or "").strip()
        first_key = next(iter(key_to_button))
        return first_key

    for key, button_widget in key_to_button.items():
        if clicked_button is button_widget:
            return key

    # 兜底：理论上不会发生，但避免返回空字符串导致上层误判。
    first_key = next(iter(key_to_button))
    return first_key


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
    _enable_copyable_text_for_message_box(message_box)
    message_box.exec()
    return message_box.clickedButton() is suppress_button


def ask_warning_action_dialog(
    parent: QtWidgets.QWidget | None,
    title: str,
    message: str,
    *,
    action_label: str,
    continue_label: str = "继续执行",
) -> bool:
    """显示“警告 + 一个操作按钮 + 继续按钮”的对话框。

    Returns:
        True：用户点击了 action_label 对应的按钮；False：用户点击了 continue_label。
    """
    message_box = QtWidgets.QMessageBox(parent)
    message_box.setIcon(QtWidgets.QMessageBox.Icon.Warning)
    message_box.setWindowTitle(title)
    message_box.setText(message)

    action_button = message_box.addButton(
        str(action_label or "执行操作"),
        QtWidgets.QMessageBox.ButtonRole.ActionRole,
    )
    continue_button = message_box.addButton(
        str(continue_label or "继续"),
        QtWidgets.QMessageBox.ButtonRole.AcceptRole,
    )
    message_box.setDefaultButton(continue_button)
    _enable_copyable_text_for_message_box(message_box)

    message_box.exec()
    return message_box.clickedButton() is action_button


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
    "ask_choice_dialog",
    "apply_standard_button_box_labels",
    "ask_acknowledge_or_suppress_dialog",
    "ask_warning_action_dialog",
    "ask_yes_no_dialog",
    "show_error_dialog",
    "show_info_dialog",
    "show_warning_dialog",
]

