from __future__ import annotations

from app.models import TodoItem
from app.ui.todo.runtime.execution_preflight_warning import inspect_graph_execution_preflight


def _make_todo_for_graph(
    *,
    todo_id: str,
    detail_type: str,
    graph_id: str,
) -> TodoItem:
    return TodoItem(
        todo_id=todo_id,
        title="test",
        description="",
        level=0,
        parent_id=None,
        children=[],
        task_type="template",
        target_id=graph_id,
        detail_info={"type": detail_type, "graph_id": graph_id},
    )


def test_inspect_graph_execution_preflight_no_warning_when_graph_has_no_special_items() -> None:
    graph_id = "graph_alpha"
    todo_map = {
        "1": _make_todo_for_graph(todo_id="1", detail_type="graph_create_node", graph_id=graph_id),
        "2": _make_todo_for_graph(todo_id="2", detail_type="graph_connect", graph_id=graph_id),
    }
    summary = inspect_graph_execution_preflight(todo_map, graph_id)
    assert summary.graph_id == graph_id
    assert summary.should_warn is False


def test_inspect_graph_execution_preflight_detects_signals_by_overview_or_bind_step() -> None:
    graph_id = "graph_beta"
    todo_map = {
        "signals": _make_todo_for_graph(
            todo_id="signals",
            detail_type="graph_signals_overview",
            graph_id=graph_id,
        ),
        "bind": _make_todo_for_graph(
            todo_id="bind",
            detail_type="graph_bind_signal",
            graph_id=graph_id,
        ),
    }
    summary = inspect_graph_execution_preflight(todo_map, graph_id)
    assert summary.includes_signal is True
    assert summary.includes_struct is False
    assert summary.includes_composite is False
    assert summary.should_warn is True
    message = summary.build_dialog_message()
    assert "信号" in message
    assert "结构体" not in message
    assert "复合节点" not in message


def test_inspect_graph_execution_preflight_detects_struct_by_bind_struct_step() -> None:
    graph_id = "graph_gamma"
    todo_map = {
        "struct": _make_todo_for_graph(
            todo_id="struct",
            detail_type="graph_bind_struct",
            graph_id=graph_id,
        )
    }
    summary = inspect_graph_execution_preflight(todo_map, graph_id)
    assert summary.includes_signal is False
    assert summary.includes_struct is True
    assert summary.includes_composite is False
    assert summary.should_warn is True
    message = summary.build_dialog_message()
    assert "结构体" in message
    assert "信号" not in message


def test_inspect_graph_execution_preflight_detects_composite_by_composite_root() -> None:
    graph_id = "graph_delta"
    todo_map = {
        "composite_root": _make_todo_for_graph(
            todo_id="composite_root",
            detail_type="composite_root",
            graph_id=graph_id,
        )
    }
    summary = inspect_graph_execution_preflight(todo_map, graph_id)
    assert summary.includes_signal is False
    assert summary.includes_struct is False
    assert summary.includes_composite is True
    assert summary.should_warn is True
    message = summary.build_dialog_message()
    assert "复合节点" in message
    assert "信号" not in message


def test_inspect_graph_execution_preflight_filters_by_graph_id() -> None:
    graph_id = "graph_epsilon"
    other_graph_id = "graph_zeta"
    todo_map = {
        "other_signals": _make_todo_for_graph(
            todo_id="other_signals",
            detail_type="graph_signals_overview",
            graph_id=other_graph_id,
        ),
        "other_struct": _make_todo_for_graph(
            todo_id="other_struct",
            detail_type="graph_bind_struct",
            graph_id=other_graph_id,
        ),
        "self_node": _make_todo_for_graph(
            todo_id="self_node",
            detail_type="graph_create_node",
            graph_id=graph_id,
        ),
    }
    summary = inspect_graph_execution_preflight(todo_map, graph_id)
    assert summary.graph_id == graph_id
    assert summary.should_warn is False


