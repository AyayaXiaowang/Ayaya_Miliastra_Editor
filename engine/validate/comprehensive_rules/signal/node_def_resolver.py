from __future__ import annotations

from typing import Any, Dict, List

from engine.nodes.node_definition_loader import NodeDef
from engine.utils.graph.graph_utils import get_node_display_info


def build_node_defs_for_nodes(
    nodes: List[Dict[str, Any]],
    node_library: Dict[str, NodeDef],
) -> Dict[str, NodeDef]:
    """为图中的每个节点解析对应的 NodeDef，供类型检查使用。"""
    result: Dict[str, NodeDef] = {}
    if not node_library:
        return result
    for node in nodes:
        node_id, node_title, node_category = get_node_display_info(node)
        if not node_id:
            continue
        category_text = str(node_category or "")
        category_standard = (
            category_text if category_text.endswith("节点") else f"{category_text}节点"
        )
        candidate_key = f"{category_standard}/{node_title}"
        node_def = node_library.get(candidate_key)
        if node_def is None:
            for scope_suffix in ("#client", "#server"):
                scoped_key = f"{candidate_key}{scope_suffix}"
                scoped_def = node_library.get(scoped_key)
                if scoped_def is not None:
                    node_def = scoped_def
                    break
        if node_def is not None:
            result[node_id] = node_def
    return result


__all__ = ["build_node_defs_for_nodes"]


