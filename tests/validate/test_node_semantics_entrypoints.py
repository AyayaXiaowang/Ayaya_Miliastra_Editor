from __future__ import annotations

from pathlib import Path

from engine.nodes.node_definition_loader import NodeDef
from engine.validate.node_semantics import SEMANTIC_SIGNAL_SEND, is_semantic_graph_node


def test_is_semantic_graph_node_uses_node_def_semantic_id_first() -> None:
    node_def = NodeDef(
        name="发送信号",
        category="执行节点",
        semantic_id="signal.send",
    )
    node_library = {"执行节点/发送信号": node_def}
    assert (
        is_semantic_graph_node(
            workspace_path=Path("."),
            node_library=node_library,
            node_category="执行节点",
            node_title="发送信号",
            scope_text="server",
            semantic_id=SEMANTIC_SIGNAL_SEND,
        )
        is True
    )


