from __future__ import annotations

from typing import Dict, Sequence, Tuple


# ============================================================================
# 类型映射与工具函数（中文展示名 <-> JSON param_type）
# ============================================================================

# UI 中使用的“规范中文类型名”到 JSON 里的 param_type 英文名映射。
_CANONICAL_TO_PARAM_TYPE: Dict[str, str] = {
    "整数": "Int32",
    "浮点数": "Float",
    "字符串": "String",
    "布尔值": "Bool",
    "GUID": "Guid",
    "实体": "Entity",
    "阵营": "Camp",
    "三维向量": "Vector3",
    "元件ID": "ComponentId",
    "配置ID": "ConfigId",
    # 列表类型
    "整数列表": "Int32List",
    "浮点数列表": "FloatList",
    "字符串列表": "StringList",
    "布尔值列表": "BoolList",
    "GUID列表": "GuidList",
    "实体列表": "EntityList",
    "阵营列表": "CampList",
    "三维向量列表": "Vector3List",
    "元件ID列表": "ComponentIdList",
    "配置ID列表": "ConfigIdList",
    # 结构体与字典
    "结构体": "Struct",
    "结构体列表": "StructList",
    "字典": "Dict",
}

_PARAM_TYPE_TO_CANONICAL: Dict[str, str] = {
    value: key for key, value in _CANONICAL_TO_PARAM_TYPE.items()
}

# NodeGraph 配置里的中文类型名别名，统一收敛为规范展示名。
_TYPE_NAME_ALIASES: Dict[str, str] = {
    "结构体": "结构体",
    "结构体列表": "结构体列表",
}


def normalize_canonical_type_name(raw_name: str) -> str:
    """将外部传入的类型名规约为页面内部使用的“规范中文类型名”。"""
    name = raw_name.strip()
    if not name:
        return name
    return _TYPE_NAME_ALIASES.get(name, name)


def canonical_to_param_type(type_name: str) -> str:
    """规范中文类型名 -> JSON param_type 英文名。

    若不在映射表中，则直接返回原始字符串，便于兼容 Army/ArmyList 等暂未内建类型。
    """
    normalized = normalize_canonical_type_name(type_name)
    return _CANONICAL_TO_PARAM_TYPE.get(normalized, normalized)


def param_type_to_canonical(param_type: str) -> str:
    """JSON param_type 英文名 -> 规范中文类型名（找不到则原样返回）。"""
    canonical = _PARAM_TYPE_TO_CANONICAL.get(param_type)
    return canonical if canonical is not None else param_type


def is_struct_type(type_name: str) -> bool:
    """判断是否为“结构体”或“结构体列表”类型（展示名语义层）。"""
    normalized = normalize_canonical_type_name(type_name)
    return normalized in ("结构体", "结构体列表")


def is_dict_type(type_name: str) -> bool:
    """判断是否为“字典”类型（展示名语义层）。"""
    normalized = normalize_canonical_type_name(type_name)
    return normalized == "字典"


def is_list_type(type_name: str) -> bool:
    """判断是否为列表类型（不含“结构体列表”这种特殊列表）。"""
    normalized = normalize_canonical_type_name(type_name)
    if is_struct_type(normalized) or is_dict_type(normalized):
        return False
    return normalized.endswith("列表") or normalized.endswith("List")


def format_field_pairs_summary(pairs: Sequence[Tuple[str, str]]) -> str:
    """将 (字段名, 类型名) 序列格式化为“字段名: 类型A，字段名2: 类型B”摘要。"""
    if not pairs:
        return ""
    parts = [f"{field_name}: {field_type}" for field_name, field_type in pairs]
    summary = "，".join(parts)
    if len(summary) > 80:
        return summary[:77] + "..."
    return summary


__all__ = [
    "normalize_canonical_type_name",
    "canonical_to_param_type",
    "param_type_to_canonical",
    "is_struct_type",
    "is_dict_type",
    "is_list_type",
    "format_field_pairs_summary",
]


