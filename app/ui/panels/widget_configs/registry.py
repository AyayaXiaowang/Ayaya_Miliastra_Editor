from __future__ import annotations

from typing import Dict, Optional, Type

from PyQt6 import QtWidgets

from .interaction_controls import InteractionButtonConfigPanel, ItemDisplayConfigPanel
from .selection_panel import CardSelectorConfigPanel
from .status_panels import ProgressBarConfigPanel, ScoreboardConfigPanel, TimerConfigPanel
from .textual_panels import PopupConfigPanel, TextBoxConfigPanel

PanelType = Type[QtWidgets.QWidget]

PANEL_REGISTRY: Dict[str, PanelType] = {
    "交互按钮": InteractionButtonConfigPanel,
    "道具展示": ItemDisplayConfigPanel,
    "文本框": TextBoxConfigPanel,
    "弹窗": PopupConfigPanel,
    "进度条": ProgressBarConfigPanel,
    "计时器": TimerConfigPanel,
    "计分板": ScoreboardConfigPanel,
    "卡牌选择器": CardSelectorConfigPanel,
}


def create_config_panel(widget_type: str, parent: Optional[QtWidgets.QWidget] = None) -> Optional[QtWidgets.QWidget]:
    """根据控件类型创建配置面板"""
    panel_class = PANEL_REGISTRY.get(widget_type)
    if panel_class:
        return panel_class(parent)
    return None

