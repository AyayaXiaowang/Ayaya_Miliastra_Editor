"""界面控件配置面板入口，负责暴露面板类与工厂函数。"""

from ui.panels.widget_configs import (
    BaseWidgetConfigPanel,
    CardSelectorConfigPanel,
    InteractionButtonConfigPanel,
    ItemDisplayConfigPanel,
    PANEL_REGISTRY,
    PopupConfigPanel,
    ProgressBarConfigPanel,
    ScoreboardConfigPanel,
    TextBoxConfigPanel,
    TimerConfigPanel,
    create_config_panel,
)

__all__ = [
    "BaseWidgetConfigPanel",
    "InteractionButtonConfigPanel",
    "ItemDisplayConfigPanel",
    "TextBoxConfigPanel",
    "PopupConfigPanel",
    "ProgressBarConfigPanel",
    "TimerConfigPanel",
    "ScoreboardConfigPanel",
    "CardSelectorConfigPanel",
    "PANEL_REGISTRY",
    "create_config_panel",
]

