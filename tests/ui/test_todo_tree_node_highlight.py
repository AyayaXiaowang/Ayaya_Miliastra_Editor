from __future__ import annotations

from typing import Dict, List, Any

from PyQt6 import QtCore, QtWidgets

from app.models import TodoItem
from app.ui.todo.todo_tree import TodoTreeManager
from app.ui.todo.todo_runtime_state import TodoRuntimeState
from app.ui.todo.todo_list_widget import TodoListWidget
from app.ui.foundation.theme_manager import Colors as ThemeColors


_app = QtWidgets.QApplication.instance()
if _app is None:
    _app = QtWidgets.QApplication([])


def _make_graph_todo(
    todo_identifier: str,
    *,
    level: int,
    parent_identifier: str = "",
    detail_type: str,
    node_identifier: str = "",
) -> TodoItem:
    detail_information: Dict[str, object] = {"type": detail_type}
    if node_identifier:
        detail_information["node_id"] = node_identifier
    return TodoItem(
        todo_id=todo_identifier,
        parent_id=parent_identifier,
        children=[],
        level=level,
        task_type="graph",
        title=todo_identifier,
        description="",
        target_id="",
        detail_info=detail_information,
    )


def test_highlight_steps_for_node_dims_unrelated_qtree_items() -> None:
    """在直接调用 TreeManager API 时，树中与该节点无关的步骤应被统一置灰。"""
    tree = QtWidgets.QTreeWidget()
    runtime_state = TodoRuntimeState(tree)
    rich_role = int(QtCore.Qt.ItemDataRole.UserRole) + 10
    manager = TodoTreeManager(tree, runtime_state, rich_role)

    related = _make_graph_todo(
        "related",
        level=0,
        parent_identifier="",
        detail_type="graph_create_node",
        node_identifier="n1",
    )
    unrelated = _make_graph_todo(
        "unrelated",
        level=0,
        parent_identifier="",
        detail_type="graph_create_node",
        node_identifier="n2",
    )

    todos = [related, unrelated]
    todo_states: Dict[str, bool] = {}

    manager.set_data(todos, todo_states)

    related_item = manager.get_item_by_id("related")
    unrelated_item = manager.get_item_by_id("unrelated")
    assert related_item is not None
    assert unrelated_item is not None

    manager.highlight_steps_for_node("n1", anchor_todo_id="related")

    # 确认内部高亮/过滤状态已开启
    assert manager._current_node_highlight_ids == {"related"}
    assert manager._node_filter_active is True

    # 富文本委托的置灰标记应被设置在无关步骤上
    assert unrelated_item.data(0, manager.DIMMED_ROLE)

    manager.clear_node_highlight()


def test_preview_node_click_triggers_tree_highlight_and_dim() -> None:
    """在预览中点击节点时，应高亮关联步骤并置灰无关步骤。"""
    widget = TodoListWidget()

    related = _make_graph_todo(
        "related",
        level=0,
        parent_identifier="",
        detail_type="graph_create_node",
        node_identifier="n1",
    )
    unrelated = _make_graph_todo(
        "unrelated",
        level=0,
        parent_identifier="",
        detail_type="graph_create_node",
        node_identifier="n2",
    )

    todos = [related, unrelated]
    todo_states: Dict[str, bool] = {}

    widget.load_todos(todos, todo_states)

    tree_manager = widget.tree_manager
    unrelated_item = tree_manager.get_item_by_id("unrelated")
    assert unrelated_item is not None

    # 模拟在预览中点击节点 n1（通过预览面板信号联动）
    widget.preview_panel.node_clicked.emit("n1")

    # 预览点击后 TreeManager 内部应记录当前节点高亮状态
    assert widget.tree_manager._current_node_highlight_ids == {"related"}
    assert widget.tree_manager._node_filter_active is True

    # 富文本委托的置灰标记也应被设置
    assert unrelated_item.data(0, tree_manager.DIMMED_ROLE)


def test_select_unrelated_step_clears_node_highlight() -> None:
    """当处于节点置灰模式时，点击树中与该节点无关的步骤应自动取消置灰。"""
    widget = TodoListWidget()

    related = _make_graph_todo(
        "related",
        level=0,
        parent_identifier="",
        detail_type="graph_create_node",
        node_identifier="n1",
    )
    unrelated = _make_graph_todo(
        "unrelated",
        level=0,
        parent_identifier="",
        detail_type="graph_create_node",
        node_identifier="n2",
    )

    todos = [related, unrelated]
    todo_states: Dict[str, bool] = {}

    widget.load_todos(todos, todo_states)

    tree_manager = widget.tree_manager
    related_item = tree_manager.get_item_by_id("related")
    unrelated_item = tree_manager.get_item_by_id("unrelated")
    assert related_item is not None
    assert unrelated_item is not None

    # 先通过预览点击进入节点高亮/置灰模式
    widget.preview_panel.node_clicked.emit("n1")

    assert tree_manager._current_node_highlight_ids == {"related"}
    assert tree_manager._node_filter_active is True
    assert unrelated_item.data(0, tree_manager.DIMMED_ROLE)

    # 模拟用户点击与该节点无关的步骤（unrelated），应自动清除节点高亮与置灰
    widget.tree.setCurrentItem(unrelated_item)

    assert not tree_manager._node_filter_active
    assert tree_manager._current_node_highlight_ids == set()
    assert not unrelated_item.data(0, tree_manager.DIMMED_ROLE)
