from __future__ import annotations

from typing import Dict, Optional

from app.models import TodoItem
from app.ui.todo.current_todo_resolver import CurrentTodoContext, resolve_current_todo_for_leaf


def _make_todo(todo_id: str, *, detail_info: Optional[Dict] = None) -> TodoItem:
    return TodoItem(
        todo_id=todo_id,
        title=todo_id,
        description="",
        level=0,
        parent_id=None,
        children=[],
        task_type="graph",
        target_id="",
        detail_info=detail_info or {},
    )


def test_restore_prefers_selected_id_over_current_id() -> None:
    selected = _make_todo("selected")
    current = _make_todo("current")
    context = CurrentTodoContext(
        selected_todo_id="selected",
        current_todo_id="current",
        current_detail_info={"graph_id": "g1"},
        todo_map={"selected": selected, "current": current},
        todos=[selected, current],
    )
    resolved = resolve_current_todo_for_leaf(context)
    assert resolved is selected


def test_restore_falls_back_to_current_id_when_selected_missing() -> None:
    current = _make_todo("current")
    context = CurrentTodoContext(
        selected_todo_id="selected_missing",
        current_todo_id="current",
        current_detail_info={"graph_id": "g1"},
        todo_map={"current": current},
        todos=[current],
    )
    resolved = resolve_current_todo_for_leaf(context)
    assert resolved is current


def test_restore_falls_back_to_detail_info_full_match() -> None:
    detail = {"type": "graph_create_node", "graph_id": "g1", "node_id": "n1"}
    matched = _make_todo("by_detail", detail_info=detail)
    context = CurrentTodoContext(
        selected_todo_id="selected_missing",
        current_todo_id="current_missing",
        current_detail_info=dict(detail),
        todo_map={"by_detail": matched},
        todos=[matched],
    )
    resolved = resolve_current_todo_for_leaf(context)
    assert resolved is matched


def test_restore_falls_back_to_graph_id_via_find_first_callback() -> None:
    fallback = _make_todo("fallback", detail_info={"type": "graph_step", "graph_id": "g1"})

    def _find_first_todo_for_graph(graph_id: str) -> Optional[TodoItem]:
        assert graph_id == "g1"
        return fallback

    context = CurrentTodoContext(
        selected_todo_id="",
        current_todo_id="",
        current_detail_info={"graph_id": "g1"},
        todo_map={"fallback": fallback},
        todos=[fallback],
        find_first_todo_for_graph=_find_first_todo_for_graph,
    )
    resolved = resolve_current_todo_for_leaf(context)
    assert resolved is fallback


