from __future__ import annotations

from typing import Any, Dict

from app.models import UiNavigationRequest


def bind_validation_page(*, validation_panel: Any, nav_coordinator: Any) -> None:
    """绑定验证页面对外信号。"""

    def _on_validation_jump_to_issue(detail: Dict[str, object]) -> None:
        request = UiNavigationRequest.for_validation_issue(detail)
        nav_coordinator.handle_request(request)

    validation_panel.jump_to_issue.connect(_on_validation_jump_to_issue)


