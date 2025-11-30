"""UGC编辑器规则系统

基于内部规则文档整理的规则定义与验证体系
"""

from .entity_rules import (
    ENTITY_TYPES,
    get_entity_allowed_components,
    validate_entity_transform,
)
from .node_mount_rules import NODE_ENTITY_RESTRICTIONS, can_node_mount_on_entity
from .component_rules import COMPONENT_DEFINITIONS, is_component_compatible
from .datatype_rules import BASE_TYPES, LIST_TYPES, TYPE_CONVERSIONS

__all__ = [
    'ENTITY_TYPES',
    'get_entity_allowed_components',
    'validate_entity_transform',
    'NODE_ENTITY_RESTRICTIONS',
    'can_node_mount_on_entity',
    'COMPONENT_DEFINITIONS',
    'is_component_compatible',
    'BASE_TYPES',
    'LIST_TYPES',
    'TYPE_CONVERSIONS',
]

