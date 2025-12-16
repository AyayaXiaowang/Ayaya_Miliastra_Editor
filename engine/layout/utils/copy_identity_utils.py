from __future__ import annotations

from typing import Any, Optional, Tuple


COPY_BLOCK_MARKER = "_copy_block_"
COPY_MARKER = "_copy_"
ORDER_MAX_FALLBACK = 10**6


def strip_copy_suffix(node_id: str) -> str:
    """去除节点ID中的副本后缀（截断到第一个 `_copy_` 之前）。"""
    if not node_id:
        return ""
    index = node_id.find(COPY_MARKER)
    return node_id[:index] if index != -1 else node_id


def parse_block_index(block_id: str) -> int:
    """解析块ID中的序号（block_2 -> 2），失败返回哨兵值。"""
    if isinstance(block_id, str) and block_id.startswith("block_"):
        suffix = block_id.split("_", 1)[-1]
        if suffix.isdigit():
            return int(suffix)
    return ORDER_MAX_FALLBACK


def parse_copy_counter(node_id: str) -> int:
    """解析副本计数器（*_copy_block_2_5 / *_copy_block_2_1 -> 5/1），失败返回哨兵值。"""
    if not node_id or COPY_MARKER not in node_id:
        return ORDER_MAX_FALLBACK
    suffix = node_id.rsplit(COPY_MARKER, 1)[-1]
    parts = suffix.split("_")
    for part in reversed(parts):
        if part.isdigit():
            return int(part)
    return ORDER_MAX_FALLBACK


def infer_copy_block_id_from_node_id(node_id: str) -> str:
    """从副本节点ID推断 copy_block_id（兼容 *_copy_block_2_1 约定）。"""
    if not node_id or COPY_MARKER not in node_id:
        return ""
    suffix = node_id.rsplit(COPY_MARKER, 1)[-1]
    parts = suffix.split("_")
    if len(parts) >= 2 and parts[0] == "block" and parts[1].isdigit():
        return f"block_{parts[1]}"
    return ""


def is_data_node_copy(node_obj: Any) -> bool:
    """判断对象是否为数据节点副本（兼容标记字段与命名约定）。"""
    if node_obj is None:
        return False
    if bool(getattr(node_obj, "is_data_node_copy", False)):
        return True
    node_id = getattr(node_obj, "id", "")
    return isinstance(node_id, str) and COPY_BLOCK_MARKER in node_id


def resolve_copy_block_id(node_obj: Any) -> str:
    """解析副本节点所属块ID（优先 copy_block_id 字段，其次从 node_id 推断）。"""
    if node_obj is None:
        return ""
    block_id_value = getattr(node_obj, "copy_block_id", "") or ""
    if block_id_value:
        return str(block_id_value)
    node_id = getattr(node_obj, "id", "") or ""
    return infer_copy_block_id_from_node_id(str(node_id))


def resolve_copy_block_index(node_obj: Any) -> int:
    """解析副本节点所属块序号（block_2 -> 2）；失败返回哨兵值。"""
    block_id = resolve_copy_block_id(node_obj)
    if block_id:
        parsed = parse_block_index(str(block_id))
        if parsed < ORDER_MAX_FALLBACK:
            return parsed

    node_id = getattr(node_obj, "id", "") or ""
    if isinstance(node_id, str) and COPY_BLOCK_MARKER in node_id:
        suffix = node_id.rsplit(COPY_BLOCK_MARKER, 1)[-1]
        parts = suffix.split("_")
        if parts and parts[0].isdigit():
            return int(parts[0])
    return ORDER_MAX_FALLBACK


def resolve_copy_target_id(node_obj: Any) -> Optional[str]:
    """若 node_obj 是副本节点，则返回其对应的原始节点ID（去除副本后缀）。"""
    if not is_data_node_copy(node_obj):
        return None
    original_id = getattr(node_obj, "original_node_id", "") or getattr(node_obj, "id", "")
    target_id = strip_copy_suffix(str(original_id))
    return target_id or None


def resolve_canonical_original_id(node_id: str, *, model: Any = None) -> str:
    """将任意数据节点（含副本）归一到其 canonical original id。"""
    if not node_id:
        return ""
    if model is not None:
        nodes = getattr(model, "nodes", None)
        if isinstance(nodes, dict) and node_id in nodes:
            original_id = getattr(nodes[node_id], "original_node_id", "") or ""
            if original_id:
                return str(original_id)
    return strip_copy_suffix(str(node_id))


def compute_copy_rank(node_obj: Any) -> Tuple[int, int]:
    """副本排序规则：按 copy_block_id 的块序号，再按 copy_counter 排序。"""
    return (resolve_copy_block_index(node_obj), parse_copy_counter(str(getattr(node_obj, "id", "") or "")))


