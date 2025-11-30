"""节点判定辅助函数，避免在各处散落硬编码字符串。"""

from __future__ import annotations

from typing import Any

_EVENT_CATEGORY_TOKENS = {"event", "events", "事件节点"}


def _normalize(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def is_event_node(node_obj: Any) -> bool:
    """根据节点的 category / category_id 来判断是否为事件节点。"""
    if node_obj is None:
        return False
    candidates = (
        getattr(node_obj, "category_id", None),
        getattr(node_obj, "category", None),
        getattr(node_obj, "node_category", None),
    )
    for candidate in candidates:
        normalized = _normalize(candidate)
        if normalized and normalized in _EVENT_CATEGORY_TOKENS:
            return True
    return False


