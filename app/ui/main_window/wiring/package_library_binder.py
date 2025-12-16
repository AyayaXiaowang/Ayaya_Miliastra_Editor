from __future__ import annotations

from typing import Any

from app.models import UiNavigationRequest


def bind_package_library_page(*, package_library_widget: Any, nav_coordinator: Any) -> None:
    """绑定存档库页面对外信号（跳转到资源对应的属性面板）。"""

    def _on_package_library_jump(entity_type: str, entity_id: str, package_id: str) -> None:
        request = UiNavigationRequest.for_property_panel_entity(
            entity_type=entity_type,
            entity_id=entity_id,
            package_id=package_id,
            origin="package_library",
        )
        nav_coordinator.handle_request(request)

    package_library_widget.jump_to_entity_requested.connect(_on_package_library_jump)


