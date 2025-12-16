from __future__ import annotations

from typing import Any

from app.models import UiNavigationRequest


def bind_management_page(*, management_widget: Any, nav_coordinator: Any) -> None:
    """绑定管理页面的额外跨页面请求信号。

    目前仅处理“界面控件组”触发的打开玩家编辑器请求。
    """

    ui_control_group_manager = getattr(management_widget, "ui_control_group_manager", None)
    if ui_control_group_manager is None:
        return

    def _on_open_player_editor_requested() -> None:
        request = UiNavigationRequest.for_open_player_editor(origin="ui_control_groups")
        nav_coordinator.handle_request(request)

    ui_control_group_manager.open_player_editor_requested.connect(_on_open_player_editor_requested)


