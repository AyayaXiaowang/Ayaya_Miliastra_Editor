from __future__ import annotations

from typing import Any, Dict

from engine.resources.definition_schema_view import get_default_definition_schema_view


def _get_all_struct_definitions() -> Dict[str, Dict[str, Any]]:
    """从代码级 Schema 视图获取所有结构体定义副本。"""
    schema_view = get_default_definition_schema_view()
    raw_definitions = schema_view.get_all_struct_definitions()

    results: Dict[str, Dict[str, Any]] = {}
    for raw_struct_id, raw_payload in raw_definitions.items():
        if not isinstance(raw_payload, dict):
            continue
        struct_id_text = str(raw_struct_id)
        results[struct_id_text] = dict(raw_payload)
    return results


def list_struct_ids() -> list[str]:
    """返回所有可用的结构体 ID 列表（排序后）。"""
    all_definitions = _get_all_struct_definitions()
    return sorted(all_definitions.keys())


def get_struct_payload(struct_id: str) -> Dict[str, Any] | None:
    """按 ID 获取单个结构体定义载荷的浅拷贝，未找到时返回 None。"""
    key = str(struct_id)
    all_definitions = _get_all_struct_definitions()
    payload = all_definitions.get(key)
    if payload is None:
        return None
    return dict(payload)


