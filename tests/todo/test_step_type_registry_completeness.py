from __future__ import annotations

import ast
from pathlib import Path

from app.ui.todo.todo_config import StepTypeRules, TodoStyles
from app.ui.todo import todo_detail_builder_registry
from tests._helpers.project_paths import get_repo_root


def _workspace_root() -> Path:
    return get_repo_root()


def _collect_preview_controller_detail_types() -> set[str]:
    """从源码中提取 TodoPreviewController 注册的 detail_type 常量集合。

    目的：避免执行/实例化 GraphView 等 UI 对象，直接通过 AST 静态提取。
    """

    file_path = (
        _workspace_root() / "app" / "ui" / "todo" / "todo_preview_controller.py"
    )
    source_text = file_path.read_text(encoding="utf-8")
    module = ast.parse(source_text)

    registered_types: set[str] = set()

    class _Visitor(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> None:
            # self.register_handler("graph_xxx", ...)
            if isinstance(node.func, ast.Attribute) and node.func.attr == "register_handler":
                if node.args and isinstance(node.args[0], ast.Constant):
                    value = node.args[0].value
                    if isinstance(value, str):
                        registered_types.add(value)
            self.generic_visit(node)

    _Visitor().visit(module)

    # dynamic_port_types = ("graph_add_variadic_inputs", ...)
    for node in ast.walk(module):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "dynamic_port_types" for target in node.targets):
            continue
        value_node = node.value
        if not isinstance(value_node, (ast.Tuple, ast.List)):
            continue
        for element in value_node.elts:
            if isinstance(element, ast.Constant) and isinstance(element.value, str):
                registered_types.add(element.value)

    return registered_types


def _collect_detail_builder_registered_types() -> set[str]:
    return set(todo_detail_builder_registry.list_registered_detail_types())


def test_graph_detail_types_are_declared_in_step_type_rules() -> None:
    preview_controller_types = _collect_preview_controller_detail_types()
    detail_builder_types = _collect_detail_builder_registered_types()

    referenced_graph_types = {
        detail_type
        for detail_type in (preview_controller_types | detail_builder_types)
        if StepTypeRules.is_graph_step(detail_type)
    }

    declared_graph_types = (
        set(TodoStyles.GRAPH_TASK_TYPES)
        | set(TodoStyles.GRAPH_DETAIL_TYPES_WITHOUT_PREVIEW)
        | set(StepTypeRules.AUTO_CHECK_GRAPH_STEP_TYPES)
        | set(StepTypeRules.RICH_TEXT_GRAPH_STEP_TYPES)
        | set(StepTypeRules.CONTEXT_MENU_EXECUTABLE_STEP_TYPES)
    )

    missing_types = sorted(referenced_graph_types - declared_graph_types)
    assert not missing_types, (
        "发现未在 StepTypeRules/TodoStyles 声明集合中覆盖的图步骤类型，"
        "请补齐对应常量集合以固定新增类型的改动点：\n"
        + "\n".join(missing_types)
    )


