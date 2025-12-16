from __future__ import annotations

from typing import Any

from app.models import UiNavigationRequest


def bind_graph_library_page(*, graph_library_widget: Any, nav_coordinator: Any) -> None:
    """绑定节点图库页面对外信号。"""

    def _on_graph_library_jump(entity_type: str, entity_id: str, package_id: str) -> None:
        request = UiNavigationRequest.for_property_panel_entity(
            entity_type=entity_type,
            entity_id=entity_id,
            package_id=package_id,
            origin="graph_library",
        )
        nav_coordinator.handle_request(request)

    graph_library_widget.jump_to_entity_requested.connect(_on_graph_library_jump)


