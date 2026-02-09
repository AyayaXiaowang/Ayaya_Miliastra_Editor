from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional, Set, TYPE_CHECKING

from engine.graph.models import GraphModel

from ..graph_query_utils import is_jump_out_edge

if TYPE_CHECKING:
    from engine.layout.internal.layout_models import LayoutBlock


def _build_block_children_map(*, model: GraphModel, layout_blocks: List["LayoutBlock"]) -> Dict[str, List[str]]:
    """基于 LayoutBlock.last_node_branches 构建块级有向关系（按端口顺序稳定输出）。"""
    flow_node_to_block_id: Dict[str, str] = {}
    for layout_block in layout_blocks:
        block_id = f"block_{int(getattr(layout_block, 'order_index', 0) or 0)}"
        for flow_node_id in list(getattr(layout_block, "flow_nodes", None) or []):
            flow_node_to_block_id[str(flow_node_id)] = block_id

    children_by_block_id: Dict[str, List[str]] = {
        f"block_{int(getattr(layout_block, 'order_index', 0) or 0)}": [] for layout_block in layout_blocks
    }

    for layout_block in layout_blocks:
        src_block_id = f"block_{int(getattr(layout_block, 'order_index', 0) or 0)}"
        src_last_flow_id = ""
        flow_nodes = list(getattr(layout_block, "flow_nodes", None) or [])
        if flow_nodes:
            src_last_flow_id = str(flow_nodes[-1])

        seen_targets: Set[str] = set()
        for _, next_flow_node_id in list(getattr(layout_block, "last_node_branches", None) or []):
            next_flow_node_id_text = str(next_flow_node_id or "")
            if not next_flow_node_id_text:
                continue
            if src_last_flow_id and is_jump_out_edge(model, src_last_flow_id, next_flow_node_id_text):
                continue
            dst_block_id = flow_node_to_block_id.get(next_flow_node_id_text)
            if not dst_block_id or dst_block_id == src_block_id:
                continue
            if dst_block_id in seen_targets:
                continue
            seen_targets.add(dst_block_id)
            children_by_block_id.setdefault(src_block_id, []).append(dst_block_id)

    return children_by_block_id


def _find_shortest_block_path(*, children_by_block_id: Dict[str, List[str]], src_block_id: str, dst_block_id: str) -> List[str]:
    """按块关系图（有向）找一条最短路径（BFS，按 children 顺序保证确定性）。"""
    if src_block_id == dst_block_id:
        return [src_block_id]
    if not src_block_id or not dst_block_id:
        return []

    queue = deque([src_block_id])
    previous_by_node: Dict[str, Optional[str]] = {src_block_id: None}

    while queue:
        current = queue.popleft()
        for child in children_by_block_id.get(current, []) or []:
            if child in previous_by_node:
                continue
            previous_by_node[child] = current
            if child == dst_block_id:
                queue.clear()
                break
            queue.append(child)

    if dst_block_id not in previous_by_node:
        return []

    path_reversed: List[str] = []
    cursor: Optional[str] = dst_block_id
    while cursor is not None:
        path_reversed.append(cursor)
        cursor = previous_by_node.get(cursor)
    path_reversed.reverse()
    return path_reversed


__all__ = [
    "_build_block_children_map",
    "_find_shortest_block_path",
]



