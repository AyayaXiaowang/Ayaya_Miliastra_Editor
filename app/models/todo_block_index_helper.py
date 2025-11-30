from __future__ import annotations

from typing import Dict, List, Optional

from app.models import TodoItem
from engine.graph.models import GraphModel


def build_node_block_index(model: Optional[GraphModel]) -> Dict[str, int]:
    """构建 node_id -> basic_block 索引。

    仅依赖 GraphModel.basic_blocks，避免引入 UI 依赖。
    """
    node_block_index: Dict[str, int] = {}
    if model is None:
        return node_block_index

    basic_blocks = getattr(model, "basic_blocks", None) or []
    for block_index, basic_block in enumerate(basic_blocks):
        block_nodes = getattr(basic_block, "nodes", None) or []
        for node_id in block_nodes:
            node_key = str(node_id)
            if node_key not in node_block_index:
                node_block_index[node_key] = block_index
    return node_block_index


def resolve_block_index_for_todo(
    todo: TodoItem,
    node_block_index: Dict[str, int],
) -> Optional[int]:
    """根据 Todo 关联的节点 ID 推导其所属 BasicBlock 索引。

    规则：
    - 若步骤只关联单个节点，则直接返回该节点所在块；
    - 若步骤跨多个块（例如连接块1与块3），则归入“后面的块”，
      即所有相关节点块索引中的最大值，保证不会在后续再次出现前面块的分组头。
    - 非图相关步骤返回 None。
    """
    info = todo.detail_info or {}
    detail_type = info.get("type", "")
    if not isinstance(detail_type, str):
        return None
    if not (detail_type.startswith("graph") or detail_type in {"template_graph_root", "event_flow_root"}):
        return None

    candidate_ids: List[object] = [
        info.get("node_id"),
        info.get("dst_node"),
        info.get("src_node"),
        info.get("target_node_id"),
        info.get("data_node_id"),
        info.get("prev_node_id"),
        info.get("node1_id"),
        info.get("node2_id"),
        info.get("branch_node_id"),
    ]

    indices: List[int] = []
    for raw_id in candidate_ids:
        if not raw_id:
            continue
        node_key = str(raw_id)
        block_idx = node_block_index.get(node_key)
        if isinstance(block_idx, int):
            indices.append(block_idx)

    if not indices:
        return None
    return max(indices)


