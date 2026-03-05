from __future__ import annotations

from typing import Any


def get_detail_type(todo_or_detail_info: object) -> str:
    """统一读取 detail_type。

    - 支持传入 TodoItem（duck-typing: 有 detail_info 属性即可）
    - 支持传入 detail_info dict
    - 缺失时返回空字符串（保持与历史 `.get("type","")` 行为一致）
    """

    detail_info: object = todo_or_detail_info
    if hasattr(todo_or_detail_info, "detail_info"):
        detail_info = getattr(todo_or_detail_info, "detail_info", None)
    if not isinstance(detail_info, dict):
        return ""
    return str(detail_info.get("type") or "")


def get_graph_id(todo_or_detail_info: object) -> str:
    detail_info: object = todo_or_detail_info
    if hasattr(todo_or_detail_info, "detail_info"):
        detail_info = getattr(todo_or_detail_info, "detail_info", None)
    if not isinstance(detail_info, dict):
        return ""
    return str(detail_info.get("graph_id") or "")


def get_node_id(todo_or_detail_info: object) -> str:
    detail_info: object = todo_or_detail_info
    if hasattr(todo_or_detail_info, "detail_info"):
        detail_info = getattr(todo_or_detail_info, "detail_info", None)
    if not isinstance(detail_info, dict):
        return ""
    return str(detail_info.get("node_id") or "")


def require_field(detail_info: object, field_name: str) -> Any:
    """强约束读取字段：缺失/空值直接抛错，利于暴露数据问题。"""

    if not isinstance(detail_info, dict):
        raise RuntimeError(f"detail_info 必须为 dict，无法读取字段: {field_name}")
    normalized_name = str(field_name or "")
    if not normalized_name:
        raise RuntimeError("field_name 不能为空")
    if normalized_name not in detail_info:
        raise RuntimeError(f"detail_info 缺少必填字段: {normalized_name}")
    value = detail_info.get(normalized_name)
    if value is None or value == "":
        raise RuntimeError(f"detail_info 必填字段为空: {normalized_name}")
    return value


