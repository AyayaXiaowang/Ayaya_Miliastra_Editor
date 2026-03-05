"""导航切换、窗口状态与验证相关的事件处理 Mixin。

注意：本文件仅作为**对外稳定入口**与聚合继承点。
具体实现已按职责拆分到 `ui/main_window/window_navigation_events/` 子包中，避免单文件过大。
"""

from __future__ import annotations

from .window_navigation_events.close_event_mixin import CloseEventMixin
from .window_navigation_events.command_palette_mixin import CommandPaletteMixin
from .window_navigation_events.navigation_helpers_mixin import NavigationHelpersMixin
from .window_navigation_events.navigation_history_mixin import NavigationHistoryMixin
from .window_navigation_events.save_status_mixin import SaveStatusMixin
from .window_navigation_events.toast_mixin import ToastMixin
from .window_navigation_events.ui_session_state_mixin import UiSessionStateMixin
from .window_navigation_events.validation_and_settings_mixin import ValidationAndSettingsMixin


class WindowAndNavigationEventsMixin(  # noqa: D101
    SaveStatusMixin,
    NavigationHistoryMixin,
    UiSessionStateMixin,
    ToastMixin,
    NavigationHelpersMixin,
    ValidationAndSettingsMixin,
    CommandPaletteMixin,
    CloseEventMixin,
):
    """负责导航切换、窗口标题/保存状态、验证与设置等通用事件处理逻辑。"""

    ...


