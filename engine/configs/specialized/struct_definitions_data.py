from __future__ import annotations

from typing import Any, Dict

from engine.configs.resource_types import ResourceType
from engine.resources.definition_schema_view import get_default_definition_schema_view
from engine.resources.resource_manager import ResourceManager


def _get_all_struct_definitions(
    resource_manager: ResourceManager | None = None,
) -> Dict[str, Dict[str, Any]]:
    """获取结构体定义副本。

    设计约定：
    - UI/编辑器侧应优先传入当前上下文的 `ResourceManager`，以 **“共享根 + 当前存档根”**
      作用域列出可见结构体，避免混入其它项目存档的结构体定义；
    - 若未提供 `ResourceManager`，则回退为“全库 Schema 聚合视图”（用于校验/诊断等全局场景）。
    """
    if isinstance(resource_manager, ResourceManager):
        struct_ids = resource_manager.list_resources(ResourceType.STRUCT_DEFINITION)
        normalized_ids = [
            str(value).strip()
            for value in struct_ids
            if isinstance(value, str) and str(value).strip()
        ]
        normalized_ids.sort(key=lambda text: text.casefold())

        results: Dict[str, Dict[str, Any]] = {}
        for struct_id in normalized_ids:
            payload = resource_manager.load_resource(ResourceType.STRUCT_DEFINITION, struct_id)
            if not isinstance(payload, dict):
                continue
            results[str(struct_id)] = dict(payload)
        return results

    schema_view = get_default_definition_schema_view()
    raw_definitions = schema_view.get_all_struct_definitions()

    results: Dict[str, Dict[str, Any]] = {}
    for raw_struct_id, raw_payload in raw_definitions.items():
        if not isinstance(raw_payload, dict):
            continue
        struct_id_text = str(raw_struct_id)
        results[struct_id_text] = dict(raw_payload)
    return results


def list_struct_ids(resource_manager: ResourceManager | None = None) -> list[str]:
    """返回可用的结构体 ID 列表（排序后）。

    建议：UI 调用方传入当前上下文 `ResourceManager`，以便按视图作用域过滤。
    """
    all_definitions = _get_all_struct_definitions(resource_manager)
    return sorted(all_definitions.keys())


def get_struct_payload(
    struct_id: str,
    resource_manager: ResourceManager | None = None,
) -> Dict[str, Any] | None:
    """按 ID 获取单个结构体定义载荷的浅拷贝，未找到时返回 None。"""
    key = str(struct_id)
    all_definitions = _get_all_struct_definitions(resource_manager)
    payload = all_definitions.get(key)
    if payload is None:
        return None
    return dict(payload)


