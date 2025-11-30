from __future__ import annotations

# -*- coding: utf-8 -*-
"""
结构体字段 → 规范类型名 映射缓存。

职责：
- 扫描“结构体定义”目录中的 JSON 配置，建立字段名到规范中文类型名的映射；
- 当同名字段在不同结构体中类型不一致时，映射为空字符串，表示类型不确定；
- 作为端口类型推断阶段的公共数据源，供以键查询字典值等节点复用。

说明：
- 规范类型名统一复用 `app.ui.dialogs.struct_definition_types.param_type_to_canonical`，
  避免在自动化模块中维护平行的 param_type → 类型名 映射表。
"""

from typing import Dict

from app.ui.dialogs.struct_definition_types import param_type_to_canonical
from engine.resources.definition_schema_view import (
    get_default_definition_schema_view,
)


_STRUCT_FIELD_TYPE_CACHE: Dict[str, str] = {}
_STRUCT_FIELD_CACHE_BUILT: bool = False


def _build_struct_field_type_cache() -> None:
    """基于代码级结构体定义 Schema，为字段名建立到规范类型名的映射。"""
    global _STRUCT_FIELD_TYPE_CACHE
    global _STRUCT_FIELD_CACHE_BUILT

    mapping: Dict[str, str] = {}

    schema_view = get_default_definition_schema_view()
    all_structs = schema_view.get_all_struct_definitions()

    for struct_data in all_structs.values():
        value_items = struct_data.get("value") or []
        if not isinstance(value_items, list):
            continue

        for item in value_items:
            if not isinstance(item, dict):
                continue
            field_name_raw = item.get("key")
            param_type_raw = item.get("param_type")
            field_name = str(field_name_raw) if field_name_raw is not None else ""
            param_type = str(param_type_raw) if param_type_raw is not None else ""
            if not field_name or not param_type:
                continue

            canonical_type = param_type_to_canonical(param_type)
            if not canonical_type:
                continue

            previous_type = mapping.get(field_name)
            if previous_type is None:
                mapping[field_name] = canonical_type
            elif previous_type != canonical_type:
                # 同名字段类型冲突：标记为空字符串，后续调用方视为“不确定类型”
                mapping[field_name] = ""

    _STRUCT_FIELD_TYPE_CACHE = mapping
    _STRUCT_FIELD_CACHE_BUILT = True


def lookup_struct_field_type_by_name(field_name: str) -> str:
    """根据字段名查找在结构体定义中的规范类型名。

    返回：
        - 规范中文类型名字符串；
        - 空字符串表示未找到或存在类型冲突。
    """
    global _STRUCT_FIELD_CACHE_BUILT

    if not isinstance(field_name, str) or field_name == "":
        return ""

    if not _STRUCT_FIELD_CACHE_BUILT:
        _build_struct_field_type_cache()

    type_name = _STRUCT_FIELD_TYPE_CACHE.get(field_name, "")
    if not isinstance(type_name, str):
        return ""
    if type_name.strip() == "":
        return ""
    return type_name


__all__ = ["lookup_struct_field_type_by_name"]


