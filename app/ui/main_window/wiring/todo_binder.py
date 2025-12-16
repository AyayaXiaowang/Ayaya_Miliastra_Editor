from __future__ import annotations

from typing import Any, Callable, Dict

from app.models import UiNavigationRequest


def bind_todo_page(
    *,
    todo_widget: Any,
    nav_coordinator: Any,
    on_todo_checked: Callable[[str, bool], None],
) -> None:
    """绑定任务清单页面对外信号。

    约定：
    - todo_widget 提供 `todo_checked`, `jump_to_task`, `preview_view.jump_to_graph_element` 信号
    - nav_coordinator 提供 `handle_request(UiNavigationRequest)` 方法
    """

    todo_widget.todo_checked.connect(on_todo_checked)

    def _on_todo_jump_to_task(detail_info: Dict[str, object]) -> None:
        request = UiNavigationRequest.for_todo_task(detail_info, origin="todo")
        nav_coordinator.handle_request(request)

    def _on_todo_preview_jump(jump_info: Dict[str, object]) -> None:
        request = UiNavigationRequest.for_todo_preview_jump(jump_info, origin="todo_preview")
        if request is None:
            return
        nav_coordinator.handle_request(request)

    todo_widget.jump_to_task.connect(_on_todo_jump_to_task)
    todo_widget.preview_view.jump_to_graph_element.connect(_on_todo_preview_jump)


