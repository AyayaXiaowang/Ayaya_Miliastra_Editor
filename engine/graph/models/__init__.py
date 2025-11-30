"""
图模型与相关数据结构/序列化/哈希/配置的稳定对外导出点。
"""

from .graph_model import GraphModel, NodeModel, EdgeModel, PortModel, BasicBlock
from .graph_serialization import serialize_graph, deserialize_graph
from .graph_hash import get_content_hash
from .graph_config import GraphConfig
from .package_model import (
    VariableConfig,
    GraphVariableConfig,
    SignalParameterConfig,
    SignalConfig,
    ComponentConfig,
    TemplateConfig,
    InstanceConfig,
    CombatPresets,
    ManagementData,
)
from .entity_templates import (
    ENTITY_UI_INFO,
    VARIABLE_TYPES,
    COMPONENT_TYPES,
    get_entity_type_info,
    get_all_entity_types,
    get_template_library_entity_types,
    get_template_library_category_types,
    get_combat_preset_entity_types,
    get_all_entity_types_including_special,
    get_all_variable_types,
    get_all_component_types,
)

__all__ = [
    # graph_model
    "GraphModel",
    "NodeModel",
    "EdgeModel",
    "PortModel",
    "BasicBlock",
    # graph_serialization
    "serialize_graph",
    "deserialize_graph",
    # graph_hash
    "get_content_hash",
    # graph_config
    "GraphConfig",
    # package_model（存档相关配置类型，不再暴露聚合 PackageModel）
    "VariableConfig",
    "GraphVariableConfig",
    "SignalParameterConfig",
    "SignalConfig",
    "ComponentConfig",
    "TemplateConfig",
    "InstanceConfig",
    "CombatPresets",
    "ManagementData",
    # entity_templates
    "ENTITY_UI_INFO",
    "VARIABLE_TYPES",
    "COMPONENT_TYPES",
    "get_entity_type_info",
    "get_all_entity_types",
    "get_template_library_entity_types",
    "get_template_library_category_types",
    "get_combat_preset_entity_types",
    "get_all_entity_types_including_special",
    "get_all_variable_types",
    "get_all_component_types",
]



