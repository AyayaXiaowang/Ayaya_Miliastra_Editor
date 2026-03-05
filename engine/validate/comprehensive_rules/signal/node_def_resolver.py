from __future__ import annotations

from typing import Any, Dict, List

from engine.nodes.node_definition_loader import NodeDef
from engine.utils.graph.graph_utils import get_node_display_info

from engine.validate.node_def_resolver import resolve_node_def_from_library


def build_node_defs_for_nodes(
    nodes: List[Dict[str, Any]],
    node_library: Dict[str, NodeDef],
    *,
    scope_text: str | None = None,
) -> Dict[str, NodeDef]:
    """为图中的每个节点解析对应的 NodeDef，供类型检查使用。"""
    result: Dict[str, NodeDef] = {}
    if not node_library:
        return result
    for node in nodes:
        node_id, node_title, node_category = get_node_display_info(node)
        if not node_id:
            continue
        resolved = resolve_node_def_from_library(
            node_library,
            node_category=str(node_category or ""),
            node_title=str(node_title or ""),
            scope_text=str(scope_text or "").strip().lower() or None,
        )
        if resolved is not None:
            result[node_id] = resolved.node_def
    return result


__all__ = ["build_node_defs_for_nodes"]


