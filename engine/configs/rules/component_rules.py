"""组件规则定义

基于内部组件设计文档整理的组件定义和兼容性规则。

注意：组件元数据（名称、说明、适用实体）由
`engine.configs.components.component_registry` 统一维护，
本模块只负责基于这些定义进行校验与工具方法。
"""

from .entity_rules import normalize_entity_type
from ..components.component_registry import (
    COMPONENT_DEFINITIONS,
    get_all_component_names as _registry_get_all_component_names,
)


def is_component_compatible(component_name: str, entity_type: str) -> tuple[bool, str]:
    """检查组件是否与实体类型兼容
    
    Args:
        component_name: 组件名称
        entity_type: 实体类型
        
    Returns:
        (是否兼容, 错误信息)
    """
    if component_name not in COMPONENT_DEFINITIONS:
        return False, f"未知的组件类型: {component_name}"
    
    component = COMPONENT_DEFINITIONS[component_name]
    applicable_value = component["applicable_entities"]
    if isinstance(applicable_value, list):
        applicable: list[str] = [str(name) for name in applicable_value]
    else:
        applicable = [str(applicable_value)]
    
    # 使用统一的实体类型规范化函数
    normalized_entity_type = normalize_entity_type(entity_type)
    
    # 检查规范化后的类型或原始类型是否在允许列表中
    if normalized_entity_type in applicable or entity_type in applicable:
        return True, ""
    
    error_msg = (
        f"组件'{component_name}'不能添加到实体类型'{entity_type}'上\n"
        f"允许的实体类型：{', '.join(applicable)}\n"
        f"参考：{component.get('reference', '')}"
    )
    return False, error_msg


def get_all_component_names() -> list:
    """获取所有组件名称列表（直接来自组件注册表的权威入口）。"""
    return _registry_get_all_component_names()

