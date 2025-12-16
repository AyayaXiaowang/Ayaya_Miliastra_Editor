from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from PyQt6 import QtWidgets

from app.models import TodoItem
from app.models.todo_generator import TodoGenerator
from engine.graph.models.graph_config import GraphConfig
from engine.resources.resource_manager import ResourceType
from app.ui.todo.todo_config import StepTypeRules


@dataclass
class GraphExpandContext:
    """懒加载模板图步骤时所需的上下文。"""

    parent_id: str
    graph_id: str
    graph_config: GraphConfig
    preview_template_id: str
    package: Any
    resource_manager: Any
    package_index_manager: Optional[Any] = None


def expand_graph_on_demand(tree_manager: Any, graph_root: TodoItem) -> None:
    """在首次展开模板图根时，按需生成其子步骤并补充到树与 todo 列表中。"""
    if graph_root.children:
        return

    context = _resolve_graph_expand_context(tree_manager, graph_root)
    if context is None:
        return

    new_todos = _expand_graph_tasks_for_root(tree_manager, graph_root, context)
    if not new_todos:
        return

    refresh_gate = getattr(tree_manager, "_refresh_gate", None)
    tree = getattr(tree_manager, "tree", None)
    if refresh_gate is None or tree is None:
        return

    refresh_gate.set_refreshing(True)
    tree.setUpdatesEnabled(False)
    _attach_expanded_graph_to_tree(tree_manager, graph_root, context, new_todos)
    tree.setUpdatesEnabled(True)
    refresh_gate.set_refreshing(False)


def _resolve_graph_expand_context(
    tree_manager: Any,
    graph_root: TodoItem,
) -> Optional[GraphExpandContext]:
    """解析模板图根懒加载所需的上下文。"""
    detail_info = graph_root.detail_info or {}
    parent_id = str(graph_root.parent_id or "")
    graph_id = str(detail_info.get("graph_id", "") or "")
    if not parent_id or not graph_id:
        return None

    dependency_getter = getattr(tree_manager, "_graph_expand_dependency_getter", None)
    if dependency_getter is None:
        return None

    dependencies = dependency_getter()
    if not isinstance(dependencies, tuple) or len(dependencies) not in (2, 3):
        return None
    package = dependencies[0]
    resource_manager = dependencies[1]
    package_index_manager = dependencies[2] if len(dependencies) == 3 else None
    if not package or resource_manager is None:
        return None

    data = resource_manager.load_resource(ResourceType.GRAPH, graph_id)
    if not data:
        return None
    graph_config = GraphConfig.deserialize(data)

    preview_template_id = str(detail_info.get("template_id", "") or "")

    return GraphExpandContext(
        parent_id=parent_id,
        graph_id=graph_id,
        graph_config=graph_config,
        preview_template_id=preview_template_id,
        package=package,
        resource_manager=resource_manager,
        package_index_manager=package_index_manager,
    )


def _expand_graph_tasks_for_root(
    tree_manager: Any,
    graph_root: TodoItem,
    context: GraphExpandContext,
) -> List[TodoItem]:
    """调用生成器生成图步骤，并同步回填 todo 列表与父子关系。"""
    new_todos = TodoGenerator.expand_graph_tasks(
        package=context.package,
        resource_manager=context.resource_manager,
        package_index_manager=context.package_index_manager,
        parent_id=context.parent_id,
        graph_id=context.graph_id,
        graph_name=context.graph_config.name,
        graph_data=context.graph_config.data,
        preview_template_id=context.preview_template_id,
        suppress_auto_jump=False,
        graph_root=graph_root,
        attach_graph_root=False,
    )

    todo_map: Dict[str, TodoItem] = getattr(tree_manager, "todo_map", {})
    todos: List[TodoItem] = getattr(tree_manager, "todos", [])
    for expanded_todo in new_todos:
        if expanded_todo.todo_id not in todo_map:
            todo_map[expanded_todo.todo_id] = expanded_todo
            todos.append(expanded_todo)

    parent_todo = todo_map.get(context.parent_id)
    if parent_todo is not None:
        for expanded_todo in new_todos:
            if (
                expanded_todo.parent_id == context.parent_id
                and expanded_todo.todo_id not in parent_todo.children
            ):
                parent_todo.children.append(expanded_todo.todo_id)

    return new_todos


def _attach_expanded_graph_to_tree(
    tree_manager: Any,
    graph_root: TodoItem,
    context: GraphExpandContext,
    new_todos: List[TodoItem],
) -> None:
    """基于最新 todo 结构，将懒加载得到的节点挂载到树上。"""
    item_map: Dict[str, QtWidgets.QTreeWidgetItem] = getattr(tree_manager, "_item_map", {})
    todo_map: Dict[str, TodoItem] = getattr(tree_manager, "todo_map", {})

    root_item = item_map.get(graph_root.todo_id)
    build_tree_recursive = getattr(tree_manager, "_build_tree_recursive", None)
    if root_item is not None and callable(build_tree_recursive):
        build_tree_recursive(graph_root, root_item)
        root_item.setExpanded(True)

    parent_item = item_map.get(context.parent_id)
    parent_todo = todo_map.get(context.parent_id)
    if parent_item is None or parent_todo is None:
        return

    create_tree_item = getattr(tree_manager, "_create_tree_item", None)
    if not callable(create_tree_item):
        return

    for child_id in parent_todo.children:
        if child_id in item_map:
            continue
        child_todo = todo_map.get(child_id)
        if not child_todo:
            continue
        child_item = create_tree_item(child_todo)
        parent_item.addChild(child_item)
        if child_todo.children and callable(build_tree_recursive):
            build_tree_recursive(child_todo, child_item)
        detail_type = (child_todo.detail_info or {}).get("type", "")
        should_expand = not StepTypeRules.is_event_flow_root(detail_type)
        child_item.setExpanded(should_expand)


