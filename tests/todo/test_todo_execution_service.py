from __future__ import annotations

"""TodoExecutionService 最小单元测试。

该测试仅依赖 TodoItem 与纯逻辑服务，不创建 QApplication。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.models import TodoItem
from app.ui.todo.current_todo_resolver import CurrentTodoContext
from app.ui.todo.todo_execution_service import (
    plan_template_root_execution,
    plan_remaining_event_flows_execution,
    plan_execute_from_this_step,
    plan_single_step_execution,
)


def _make_todo(
    todo_id: str,
    *,
    detail_type: str,
    parent_id: str = "",
    children: Optional[List[str]] = None,
) -> TodoItem:
    """构造最小 TodoItem（仅关心 id/父子关系/detail_type）。"""
    return TodoItem(
        todo_id=todo_id,
        parent_id=parent_id,
        title=f"todo-{todo_id}",
        description="",
        level=0,
        task_type="graph",
        target_id="",
        detail_info={"type": detail_type},
        children=list(children or []),
    )


def test_plan_template_root_execution_simple_tree() -> None:
    """选中叶子步骤时，应回溯到模板图根并在其上规划步骤。"""
    # 构造：root -> step1 -> step2
    root = _make_todo("root", detail_type="template_graph_root", children=["step1"])
    step1 = _make_todo("step1", detail_type="graph_create_node", parent_id="root", children=["step2"])
    step2 = _make_todo("step2", detail_type="graph_connect", parent_id="step1")

    todo_map: Dict[str, TodoItem] = {t.todo_id: t for t in [root, step1, step2]}
    todos = [root, step1, step2]

    # 当前上下文：选中 step2
    context = CurrentTodoContext(
        selected_todo_id="step2",
        current_todo_id="",
        current_detail_info=None,
        todo_map=todo_map,
        todos=todos,
    )

    # 通过 parent_id 简单回溯模板图根
    def _find_template_root_for_item(_item: object) -> Optional[TodoItem]:
        return root

    plan = plan_template_root_execution(context, todo_map, find_template_root_for_item=_find_template_root_for_item)
    assert plan is not None
    assert plan.root_todo.todo_id == "root"
    planned_ids = [t.todo_id for t in plan.step_list]
    # 规划结果至少应包含 step1/step2（具体顺序由 planner 决定，这里只做弱校验）
    assert "step1" in planned_ids or "step2" in planned_ids


def test_plan_execute_from_this_step_truncates_before_start() -> None:
    """从中间步骤起执行时，应只返回从该步骤开始的后续序列。"""
    # flow_root -> a -> b -> c
    flow_root = _make_todo("flow", detail_type="event_flow_root", children=["a", "b", "c"])
    a = _make_todo("a", detail_type="graph_create_node", parent_id="flow")
    b = _make_todo("b", detail_type="graph_connect", parent_id="flow")
    c = _make_todo("c", detail_type="graph_connect", parent_id="flow")

    todo_map: Dict[str, TodoItem] = {t.todo_id: t for t in [flow_root, a, b, c]}

    def _find_flow_root(todo_id: str) -> Optional[TodoItem]:
        # 所有子步骤都归属同一事件流根
        if todo_id in {"a", "b", "c"}:
            return flow_root
        return None

    step_plan = plan_execute_from_this_step(
        start_todo=b,
        todo_map=todo_map,
        find_event_flow_root_for_todo=_find_flow_root,
        find_template_root_for_todo=None,
    )
    planned_ids = [t.todo_id for t in step_plan.step_list]
    # 期望从 b 开始，至少包含 b 和后续步骤
    assert planned_ids[0] == "b"
    assert "c" in planned_ids


def test_plan_single_step_unsupported_type_returns_error() -> None:
    """不在 SUPPORTED_STEP_TYPES 集合内的步骤类型应返回错误。"""
    root = _make_todo("root", detail_type="template_graph_root")
    unsupported = _make_todo("meta", detail_type="template_graph_root", parent_id="root")
    todo_map: Dict[str, TodoItem] = {t.todo_id: t for t in [root, unsupported]}

    def _find_template_root(todo_id: str) -> Optional[TodoItem]:
        if todo_id == "meta":
            return root
        return None

    plan, error = plan_single_step_execution(
        unsupported,
        todo_map,
        find_event_flow_root_for_todo=None,
        find_template_root_for_todo=_find_template_root,
    )
    assert plan is None
    assert error is not None
    assert error.reason == "unsupported_type"


def test_plan_remaining_event_flows_execution_starts_from_selected_flow() -> None:
    """选择事件流根后，应只规划当前及后续事件流的步骤序列。"""
    graph_root = _make_todo("graph", detail_type="template_graph_root", children=["flow1", "flow2"])

    flow1 = _make_todo("flow1", detail_type="event_flow_root", parent_id="graph", children=["a1", "a2"])
    a1 = _make_todo("a1", detail_type="graph_create_node", parent_id="flow1")
    a2 = _make_todo("a2", detail_type="graph_connect", parent_id="flow1")

    flow2 = _make_todo("flow2", detail_type="event_flow_root", parent_id="graph", children=["b1"])
    b1 = _make_todo("b1", detail_type="graph_connect", parent_id="flow2")

    todo_map: Dict[str, TodoItem] = {t.todo_id: t for t in [graph_root, flow1, a1, a2, flow2, b1]}
    todos = [graph_root, flow1, a1, a2, flow2, b1]

    # 选中 flow2：应只包含 flow2 的步骤，不应包含 flow1 的步骤
    context = CurrentTodoContext(
        selected_todo_id="flow2",
        current_todo_id="",
        current_detail_info=None,
        todo_map=todo_map,
        todos=todos,
    )
    plan, error = plan_remaining_event_flows_execution(context, todo_map)
    assert error is None
    assert plan is not None
    planned_ids = [t.todo_id for t in plan.step_list]
    assert "b1" in planned_ids
    assert "a1" not in planned_ids


def test_plan_remaining_event_flows_execution_includes_following_flows() -> None:
    """选择第一个事件流根后，应串联本图下后续事件流的步骤。"""
    graph_root = _make_todo("graph", detail_type="template_graph_root", children=["flow1", "flow2"])

    flow1 = _make_todo("flow1", detail_type="event_flow_root", parent_id="graph", children=["a1"])
    a1 = _make_todo("a1", detail_type="graph_create_node", parent_id="flow1")

    flow2 = _make_todo("flow2", detail_type="event_flow_root", parent_id="graph", children=["b1"])
    b1 = _make_todo("b1", detail_type="graph_connect", parent_id="flow2")

    todo_map: Dict[str, TodoItem] = {t.todo_id: t for t in [graph_root, flow1, a1, flow2, b1]}
    todos = [graph_root, flow1, a1, flow2, b1]

    context = CurrentTodoContext(
        selected_todo_id="flow1",
        current_todo_id="",
        current_detail_info=None,
        todo_map=todo_map,
        todos=todos,
    )
    plan, error = plan_remaining_event_flows_execution(context, todo_map)
    assert error is None
    assert plan is not None
    planned_ids = [t.todo_id for t in plan.step_list]
    assert "a1" in planned_ids
    assert "b1" in planned_ids


def test_plan_remaining_event_flows_execution_no_event_flows_returns_error() -> None:
    """图根 children 为空时，应返回明确错误。"""
    graph_root = _make_todo("graph", detail_type="template_graph_root", children=[])
    flow = _make_todo("flow", detail_type="event_flow_root", parent_id="graph", children=["a1"])
    a1 = _make_todo("a1", detail_type="graph_create_node", parent_id="flow")

    todo_map: Dict[str, TodoItem] = {t.todo_id: t for t in [graph_root, flow, a1]}
    todos = [graph_root, flow, a1]

    context = CurrentTodoContext(
        selected_todo_id="flow",
        current_todo_id="",
        current_detail_info=None,
        todo_map=todo_map,
        todos=todos,
    )
    plan, error = plan_remaining_event_flows_execution(context, todo_map)
    assert plan is None
    assert error is not None
    assert error.reason == "no_event_flows"


