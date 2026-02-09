from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.models import TodoItem
from app.ui.todo.todo_tree_source_tooltip import TodoTreeSourceTooltipProvider


class _DummyResourceManager:
    def get_graph_file_path(self, graph_id: str) -> Optional[object]:
        return None


@dataclass
class _DummyNode:
    id: str
    title: str
    category: str
    source_lineno: int
    source_end_lineno: int


class _DummyGraphModel:
    def __init__(self, nodes: Dict[str, _DummyNode]) -> None:
        self.nodes = nodes


def test_todo_tree_source_tooltip_uses_todo_detail_info_and_does_not_raise() -> None:
    """回归：tooltip 构建必须从 todo.detail_info 读取关联节点信息，不能引用未定义变量。"""

    dummy_resource_manager = _DummyResourceManager()

    def dependency_getter() -> tuple[object, object, object]:
        return (object(), dummy_resource_manager, None)

    provider = TodoTreeSourceTooltipProvider(dependency_getter)

    graph_id = "graph_1"
    provider._graph_payload_cache[graph_id] = ({}, "dummy_graph_file.py")
    provider._graph_model_cache[graph_id] = _DummyGraphModel(
        nodes={
            "n1": _DummyNode(
                id="n1",
                title="创建节点",
                category="graph_create_node",
                source_lineno=123,
                source_end_lineno=130,
            )
        }
    )

    todo = TodoItem(
        todo_id="todo_1",
        title="t",
        description="",
        level=0,
        parent_id=None,
        children=[],
        task_type="graph",
        target_id="",
        detail_info={
            "type": "graph_create_node",
            "graph_id": graph_id,
            "node_id": "n1",
        },
    )

    tooltip_text = provider.get_tooltip_for_todo(todo)
    assert isinstance(tooltip_text, str)
    assert "dummy_graph_file.py" in tooltip_text
    assert "关联节点" in tooltip_text
    assert "第 123 行" in tooltip_text


