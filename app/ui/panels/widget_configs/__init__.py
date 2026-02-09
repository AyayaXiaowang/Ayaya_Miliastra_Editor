"""UI 控件配置面板子模块。"""

from .base import BaseWidgetConfigPanel, WidgetConfigForm, VariableSelector  # noqa: F401
from .interaction_controls import (  # noqa: F401
    InteractionButtonConfigPanel,
    ItemDisplayConfigPanel,
)
from .container_panel import ContainerConfigPanel  # noqa: F401
from .selection_panel import CardSelectorConfigPanel  # noqa: F401
from .status_panels import (  # noqa: F401
    ProgressBarConfigPanel,
    ScoreboardConfigPanel,
    TimerConfigPanel,
)
from .textual_panels import (  # noqa: F401
    PopupConfigPanel,
    TextBoxConfigPanel,
)
from .registry import PANEL_REGISTRY, create_config_panel  # noqa: F401

__all__ = [
    "BaseWidgetConfigPanel",
    "WidgetConfigForm",
    "VariableSelector",
    "InteractionButtonConfigPanel",
    "ItemDisplayConfigPanel",
    "ContainerConfigPanel",
    "TextBoxConfigPanel",
    "PopupConfigPanel",
    "ProgressBarConfigPanel",
    "TimerConfigPanel",
    "ScoreboardConfigPanel",
    "CardSelectorConfigPanel",
    "PANEL_REGISTRY",
    "create_config_panel",
]

