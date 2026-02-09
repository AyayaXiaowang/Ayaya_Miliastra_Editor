from __future__ import annotations

from typing import Dict, List, Optional, Set

from app.models import TodoItem
from app.ui.todo.current_todo_resolver import (
    CurrentTodoContext,
    resolve_current_todo_for_leaf,
    resolve_current_todo_for_root,
)
from app.ui.todo.todo_execution_service import (
    plan_execute_from_this_step,
    plan_single_step_execution,
    plan_template_root_execution,
    plan_event_flow_root_execution,
)
from app.ui.todo.graph_data_resolver import resolve_graph_data_for_execution
from app.ui.todo.recognition_backfill_planner import (
    RecognitionFlowProgress,
    plan_recognition_backfill,
)
from app.runtime.services.graph_data_service import get_shared_graph_data_service


def _make_todo(
    todo_identifier: str,
    *,
    level: int = 0,
    parent_identifier: str = "",
    detail_type: str = "",
    graph_identifier: str = "",
) -> TodoItem:
    detail_information: Dict[str, object] = {}
    if detail_type:
        detail_information["type"] = detail_type
    if graph_identifier:
        detail_information["graph_id"] = graph_identifier
    return TodoItem(
        todo_id=todo_identifier,
        parent_id=parent_identifier,
        children=[],
        level=level,
        task_type="template",
        title=todo_identifier,
        description="",
        target_id=graph_identifier or "",
        detail_info=detail_information,
    )


def _build_simple_context(
    selected_identifier: str,
    current_identifier: str,
    detail_information: Optional[dict],
    todos: List[TodoItem],
) -> CurrentTodoContext:
    todo_mapping: Dict[str, TodoItem] = {t.todo_id: t for t in todos}
    return CurrentTodoContext(
        selected_todo_id=selected_identifier,
        current_todo_id=current_identifier,
        current_detail_info=detail_information,
        todo_map=todo_mapping,
        todos=todos,
        find_first_todo_for_graph=None,
        get_item_by_id=None,
    )


def test_current_todo_resolver_leaf_priority_order() -> None:
    base_todo = _make_todo("base", level=0, detail_type="graph_create_node")
    fallback_todo = _make_todo("fallback", level=0, detail_type="graph_create_node")
    todos = [base_todo, fallback_todo]
    context = _build_simple_context(
        selected_identifier="base",
        current_identifier="fallback",
        detail_information=None,
        todos=todos,
    )
    resolved = resolve_current_todo_for_leaf(context)
    assert resolved is not None
    assert resolved.todo_id == "base"


def test_current_todo_resolver_root_template_and_flow() -> None:
    template_root = _make_todo("template_root", level=0, detail_type="template_graph_root")
    event_root = _make_todo(
        "event_root",
        level=1,
        parent_identifier="template_root",
        detail_type="event_flow_root",
    )
    leaf_step = _make_todo(
        "leaf",
        level=2,
        parent_identifier="event_root",
        detail_type="graph_create_node",
    )
    template_root.children = ["event_root"]
    event_root.children = ["leaf"]
    todos = [template_root, event_root, leaf_step]
    todo_mapping: Dict[str, TodoItem] = {t.todo_id: t for t in todos}
    context = _build_simple_context(
        selected_identifier="leaf",
        current_identifier="",
        detail_information=None,
        todos=todos,
    )
    template_plan = plan_template_root_execution(
        context,
        todo_mapping,
        find_template_root_for_item=None,
    )
    assert template_plan is not None
    assert template_plan.root_todo.todo_id == "template_root"
    flow_plan = plan_event_flow_root_execution(
        context,
        todo_mapping,
        find_template_root_for_item=None,
        find_event_flow_root_for_todo=lambda identifier: event_root if identifier == "leaf" else None,
    )
    assert flow_plan is not None
    assert flow_plan.root_todo.todo_id == "event_root"


def test_execution_service_execute_from_this_step_sequence() -> None:
    root = _make_todo("root", level=0, detail_type="template_graph_root")
    step_one = _make_todo("s1", level=1, parent_identifier="root", detail_type="graph_create_node")
    step_two = _make_todo("s2", level=1, parent_identifier="root", detail_type="graph_create_node")
    root.children = ["s1", "s2"]
    todos = [root, step_one, step_two]
    todo_mapping: Dict[str, TodoItem] = {t.todo_id: t for t in todos}
    plan = plan_execute_from_this_step(
        step_two,
        todo_mapping,
        find_event_flow_root_for_todo=None,
        find_template_root_for_todo=lambda identifier: root if identifier in {"s1", "s2"} else None,
    )
    identifiers = [t.todo_id for t in plan.step_list]
    assert identifiers == ["s2"]


def test_execution_service_single_step_unsupported_type_error() -> None:
    step = _make_todo("s1", level=1, parent_identifier="", detail_type="custom_unsupported_type")
    todos = [step]
    todo_mapping: Dict[str, TodoItem] = {step.todo_id: step}
    plan, error = plan_single_step_execution(
        step,
        todo_mapping,
        find_event_flow_root_for_todo=None,
        find_template_root_for_todo=None,
    )
    assert plan is None
    assert error is not None
    assert error.reason == "unsupported_type"
    assert error.detail_type == "custom_unsupported_type"
    assert isinstance(error.user_message, str) and len(error.user_message) > 0


def test_graph_data_resolver_prefers_preview_panel_cache() -> None:
    focus_todo = _make_todo("focus", level=0, detail_type="template_graph_root")
    root_todo = focus_todo
    class DummyPreview:
        def __init__(self) -> None:
            self.current_graph_data: Dict[str, object] = {"nodes": [], "edges": []}
            self.current_graph_id: str = ""
    preview = DummyPreview()
    graph_data_service = get_shared_graph_data_service(None, None)
    result = resolve_graph_data_for_execution(
        focus_todo,
        root_todo,
        preview_panel=preview,
        tree_manager=None,
        graph_data_service=graph_data_service,
        current_package=None,
    )
    assert isinstance(result, dict)
    assert "nodes" in result


def test_recognition_backfill_planner_picks_latest_visible_step() -> None:
    flow = _make_todo("flow", level=1, detail_type="event_flow_root")
    step_one = _make_todo("a", level=2, parent_identifier="flow", detail_type="graph_create_node")
    step_two = _make_todo("b", level=2, parent_identifier="flow", detail_type="graph_create_node")
    step_one.detail_info["node_id"] = "n1"
    step_two.detail_info["node_id"] = "n2"
    flow.children = ["a", "b"]
    todo_mapping: Dict[str, TodoItem] = {
        "flow": flow,
        "a": step_one,
        "b": step_two,
    }
    visible_identifiers: Set[str] = {"n1", "n2"}
    result = plan_recognition_backfill(
        visible_identifiers,
        candidate_flows=[flow],
        selected_flow=None,
        todo_map=todo_mapping,
    )
    assert isinstance(result, RecognitionFlowProgress)
    assert result.flow_todo.todo_id == "flow"
    assert result.step_todo.todo_id == "b"
    assert result.step_index_in_flow == 1


