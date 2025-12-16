from __future__ import annotations

from typing import Callable, Optional

from PyQt6 import QtWidgets

from app.ui.todo.todo_config import TodoStyles


def create_execute_button(
    parent: Optional[QtWidgets.QWidget],
    clicked_handler: Callable[[], None],
    *,
    minimum_height: Optional[int] = None,
) -> QtWidgets.QPushButton:
    """创建统一风格的“执行”按钮（默认文案为“执行当前步骤”）。

    约定：
    - 默认文案为“执行当前步骤”，后续可由上层根据步骤类型动态覆盖
    - 使用 TodoStyles.execute_button_qss() 作为样式（颜色来源于 ThemeManager.Colors）
    - 默认不可见，由调用方通过 setVisible / set_execute_visible 控制显示
    - 点击行为统一委托给传入的回调
    """
    button = QtWidgets.QPushButton("执行当前步骤", parent)
    if minimum_height is not None:
        button.setMinimumHeight(int(minimum_height))
    button.setStyleSheet(TodoStyles.execute_button_qss())
    button.setVisible(False)
    button.clicked.connect(clicked_handler)
    return button


