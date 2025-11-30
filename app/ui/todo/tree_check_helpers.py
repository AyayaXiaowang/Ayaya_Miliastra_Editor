# -*- coding: utf-8 -*-
"""
树三态与增量刷新辅助工具：集中封装父子联动与进度文本的计算与应用。
"""

from PyQt6 import QtCore
from PyQt6.QtCore import Qt


def set_all_children_state(todo_map, todo_states, todo, is_checked: bool, emit_checked) -> None:
    """递归设置所有叶子子任务的勾选状态，并通过回调发出变更信号。

    Args:
        todo_map: dict[todo_id, TodoItem]
        todo_states: dict[todo_id, bool]
        todo: 当前父 TodoItem
        is_checked: 目标状态
        emit_checked: 回调函数 (todo_id: str, checked: bool) -> None
    """
    for child_id in todo.children:
        child_todo = todo_map.get(child_id)
        if not child_todo:
            continue
        if child_todo.children:
            set_all_children_state(todo_map, todo_states, child_todo, is_checked, emit_checked)
        else:
            old_state = todo_states.get(child_id, False)
            if old_state != is_checked:
                todo_states[child_id] = is_checked
                emit_checked(child_id, is_checked)


def apply_parent_progress(item, todo, todo_states, get_icon) -> None:
    """根据子任务完成情况应用父节点三态与进度文本。"""
    icon = get_icon(todo)
    completed, total = todo.get_progress(todo_states)
    if completed == 0:
        item.setCheckState(0, Qt.CheckState.Unchecked)
    elif completed == total:
        item.setCheckState(0, Qt.CheckState.Checked)
    else:
        item.setCheckState(0, Qt.CheckState.PartiallyChecked)
    item.setText(0, f"{icon} {todo.title} ({completed}/{total})")


def apply_leaf_state(item, todo, todo_states, get_icon, apply_style) -> None:
    """统一应用叶子节点的复选框、文本与样式。"""
    is_checked = todo_states.get(todo.todo_id, False)
    item.setCheckState(0, Qt.CheckState.Checked if is_checked else Qt.CheckState.Unchecked)
    item.setText(0, f"{get_icon(todo)} {todo.title}")
    apply_style(item, todo, is_checked)


