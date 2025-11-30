from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Set

from app.models import TodoItem


@dataclass(frozen=True)
class RecognitionFlowProgress:
    """识别回填规划结果：命中的事件流根与最新可见创建步骤。"""

    flow_todo: TodoItem
    step_todo: TodoItem
    step_index_in_flow: int


_CREATED_NODE_ID_FIELDS: Dict[str, str] = {
    "graph_create_node": "node_id",
    "graph_create_and_connect": "node_id",
    "graph_create_and_connect_reverse": "node_id",
    "graph_create_and_connect_data": "data_node_id",
    "graph_create_branch_node": "branch_node_id",
}


def _get_created_node_id_from_detail(detail_info: object) -> str:
    """根据 detail_info 提取“新创建节点”的 node_id，集中维护映射规则。"""
    if not isinstance(detail_info, dict):
        return ""
    detail_type = detail_info.get("type", "")
    field_name = _CREATED_NODE_ID_FIELDS.get(detail_type, "")
    if not field_name:
        return ""
    node_identifier = detail_info.get(field_name)
    return str(node_identifier) if node_identifier is not None else ""


def _scan_flows_for_latest_visible_step(
    visible_node_ids: Set[str],
    flows: Sequence[TodoItem],
    todo_map: Dict[str, TodoItem],
) -> Optional[RecognitionFlowProgress]:
    """在给定事件流集合中查找“索引最大且创建节点仍可见”的叶子步骤。"""
    best_progress: Optional[RecognitionFlowProgress] = None
    best_index = -1

    for flow_todo in flows:
        for child_index, child_identifier in enumerate(flow_todo.children):
            step_todo = todo_map.get(child_identifier)
            if not step_todo or step_todo.children:
                continue
            created_node_identifier = _get_created_node_id_from_detail(
                step_todo.detail_info
            )
            if not created_node_identifier or created_node_identifier not in visible_node_ids:
                continue
            if child_index > best_index:
                best_index = child_index
                best_progress = RecognitionFlowProgress(
                    flow_todo=flow_todo,
                    step_todo=step_todo,
                    step_index_in_flow=child_index,
                )

    return best_progress


def plan_recognition_backfill(
    visible_node_identifiers: Set[str],
    candidate_flows: Sequence[TodoItem],
    selected_flow: Optional[TodoItem],
    todo_map: Dict[str, TodoItem],
) -> Optional[RecognitionFlowProgress]:
    """根据识别到的可见节点以及候选事件流，规划“回填到哪一个步骤”。

    优先级：
    1. 若存在当前选中的事件流根，则优先在该事件流中查找；
    2. 若未选中或选中流中没有命中的创建步骤，则依次检查其它事件流。
    """
    if not visible_node_identifiers or not candidate_flows:
        return None

    primary_flows: List[TodoItem] = []
    secondary_flows: List[TodoItem] = []

    if selected_flow is not None:
        primary_flows.append(selected_flow)
        for flow in candidate_flows:
            if flow is not selected_flow:
                secondary_flows.append(flow)
    else:
        primary_flows = list(candidate_flows)

    best_progress = _scan_flows_for_latest_visible_step(
        visible_node_identifiers,
        primary_flows,
        todo_map,
    )
    if best_progress is not None:
        return best_progress
    if not secondary_flows:
        return None
    return _scan_flows_for_latest_visible_step(
        visible_node_identifiers,
        secondary_flows,
        todo_map,
    )


