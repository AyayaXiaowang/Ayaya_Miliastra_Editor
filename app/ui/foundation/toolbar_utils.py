"""工具栏辅助方法 - 统一'新建'工具栏行的布局与间距

约定：
- 统一左对齐
- 统一边距为 0，间距为 Sizes.SPACING_SMALL

使用：
    toolbar = QtWidgets.QHBoxLayout()
    apply_standard_toolbar(toolbar)
    # 左侧按钮 ...
    toolbar.addStretch()  # 可选：将搜索/筛选控件放到右侧
    # 右侧控件 ...
"""

from PyQt6 import QtWidgets, QtCore
from typing import List

from ui.foundation.theme_manager import Sizes


def apply_standard_toolbar(toolbar: QtWidgets.QHBoxLayout) -> None:
    """对传入的水平工具栏应用统一规范。"""
    toolbar.setContentsMargins(0, 0, 0, 0)
    toolbar.setSpacing(Sizes.SPACING_SMALL)
    toolbar.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)


def move_trailing_widgets_to_right(toolbar: QtWidgets.QHBoxLayout, widgets: List[QtWidgets.QWidget]) -> None:
    """将给定的若干控件移动到工具栏右侧。

    该函数会先将这些控件从布局中移除，然后插入一个弹性伸展，再依次追加控件，达到右侧排布的效果。
    """
    for widget in widgets:
        toolbar.removeWidget(widget)
    toolbar.addStretch()
    for widget in widgets:
        toolbar.addWidget(widget)


