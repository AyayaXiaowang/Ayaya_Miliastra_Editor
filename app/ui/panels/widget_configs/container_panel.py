from __future__ import annotations

from PyQt6 import QtWidgets

from .base import BaseWidgetConfigPanel

__all__ = ["ContainerConfigPanel"]


class ContainerConfigPanel(BaseWidgetConfigPanel):
    """面板/容器配置面板（无额外字段）。

    该类型只依赖 UIWidgetConfig 的通用字段（位置/大小/初始可见/层级）。
    """

    def _setup_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        label = QtWidgets.QLabel(
            "该控件类型没有额外配置项。\n"
            "请在上方“基础信息”中调整初始可见性、位置、大小与层级。"
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addStretch()


