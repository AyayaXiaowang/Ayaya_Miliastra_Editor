from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from app.models.todo_graph_tasks.dynamic_port_steps import DynamicPortStepPlanner
from app.models.todo_node_type_helper import NodeTypeHelper


@dataclass
class _DummyNode:
    title: str
    input_constants: Dict[str, Any]


def _build_planner() -> DynamicPortStepPlanner:
    def add_todo(todo_item) -> None:
        _ = todo_item
        return

    return DynamicPortStepPlanner(
        type_helper=NodeTypeHelper(),
        add_todo=add_todo,
        todo_map={},
    )


def test_collect_constant_params_skips_signal_internal_id_and_signal_name() -> None:
    planner = _build_planner()
    node = _DummyNode(
        title="发送信号",
        input_constants={
            "信号名": "踏板开关状态",
            "__signal_id": "signal_example_pedal_switch_state",
            "_signal_id": "signal_example_pedal_switch_state",
            "目标": "some_target",
        },
    )
    params = planner.collect_constant_params(node)
    assert {entry.get("param_name") for entry in params} == {"目标"}


def test_collect_constant_params_skips_listen_signal_internal_id_and_signal_name() -> None:
    planner = _build_planner()
    node = _DummyNode(
        title="监听信号",
        input_constants={
            "信号名": "踏板开关状态",
            "__signal_id": "signal_example_pedal_switch_state",
            "_signal_id": "signal_example_pedal_switch_state",
            "目标": "some_target",
        },
    )
    params = planner.collect_constant_params(node)
    assert {entry.get("param_name") for entry in params} == {"目标"}


def test_collect_constant_params_skips_struct_internal_id_and_struct_name() -> None:
    planner = _build_planner()
    node = _DummyNode(
        title="拆分结构体",
        input_constants={
            "结构体名": "示例结构体",
            "__struct_id": "struct_example",
            "_struct_id": "struct_example",
            "结构体": "some_instance",
        },
    )
    params = planner.collect_constant_params(node)
    assert {entry.get("param_name") for entry in params} == {"结构体"}


