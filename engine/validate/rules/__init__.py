"""UGC编辑器规则系统

基于内部规则文档整理的规则定义与验证体系
"""

from engine.configs.rules.entity_rules import ENTITY_TYPES, get_entity_allowed_components
from engine.configs.components.component_registry import COMPONENT_DEFINITIONS
from engine.configs.rules.component_rules import is_component_compatible
from .node_mount_rules import NODE_ENTITY_RESTRICTIONS, can_node_mount_on_entity
from .datatype_rules import BASE_TYPES, LIST_TYPES, TYPE_CONVERSIONS

__all__ = [
    "ENTITY_TYPES",
    "get_entity_allowed_components",
    "NODE_ENTITY_RESTRICTIONS",
    "can_node_mount_on_entity",
    "COMPONENT_DEFINITIONS",
    "is_component_compatible",
    "BASE_TYPES",
    "LIST_TYPES",
    "TYPE_CONVERSIONS",
]

