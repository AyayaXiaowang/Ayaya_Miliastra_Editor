"""Todo 树结构辅助函数。

集中放置对 `TodoItem.children` 的常用操作，避免在多个模块中重复实现。"""

from __future__ import annotations

from app.models import TodoItem


def ensure_child_reference(parent: TodoItem, child_id: str) -> None:
    """将子节点 ID 附加到父节点，若已存在则跳过。"""
    if child_id in parent.children:
        return
    parent.children.append(child_id)


