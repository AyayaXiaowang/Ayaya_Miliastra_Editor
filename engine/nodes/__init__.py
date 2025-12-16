"""节点系统 - 节点定义、端口类型、复合节点等

注意：为避免导入时的循环依赖，`CompositeNodeManager` 采取延迟导入策略，
仅在访问该属性时才从 `composite_node_manager` 加载。
"""

from .node_definition_loader import load_all_nodes, NodeDef
from .port_type_system import can_connect_ports
from .node_registry import NodeRegistry, get_node_registry
from .port_index_mapper import map_port_index_to_name, get_and_clear_last_mappings
from .node_spec import node_spec, NodeSpec
from .port_name_rules import (
    parse_range_definition,
    map_index_to_range_instance,
    match_range_port_type,
    get_dynamic_port_type,
)
from .constants import NODE_CATEGORY_VALUES, ALLOWED_SCOPES, NodeCategory
from .port_type_system import (
    FLOW_PORT_TYPE,
    ANY_PORT_TYPE,
    GENERIC_PORT_TYPE,
    BOOLEAN_TYPE_KEYWORDS,
    is_flow_port_with_context,
    get_port_type_color,
)
from .advanced_node_features import (
    MappedPort,
    VirtualPinConfig,
    CompositeNodeConfig,
    convert_composite_to_node_def,
)

__all__ = [
    # 节点定义加载
    'load_all_nodes',
    'NodeDef',
    # 端口类型系统
    'can_connect_ports',
    'is_flow_port_with_context',
    'get_port_type_color',
    'FLOW_PORT_TYPE',
    'ANY_PORT_TYPE',
    'GENERIC_PORT_TYPE',
    'BOOLEAN_TYPE_KEYWORDS',
    # 节点注册表
    'NodeRegistry',
    'get_node_registry',
    # 端口映射
    'map_port_index_to_name',
    'get_and_clear_last_mappings',
    # 节点规格
    'node_spec',
    'NodeSpec',
    # 端口名称规则
    'parse_range_definition',
    'map_index_to_range_instance',
    'match_range_port_type',
    'get_dynamic_port_type',
    # 常量
    'NODE_CATEGORY_VALUES',
    'ALLOWED_SCOPES',
    'NodeCategory',
    # 高级特性
    'MappedPort',
    'VirtualPinConfig',
    'CompositeNodeConfig',
    'convert_composite_to_node_def',
    # 延迟加载
    'CompositeNodeManager',
    'clear_global_composite_node_manager_for_tests',
]


def __getattr__(name: str):
    if name == 'CompositeNodeManager':
        from .composite_node_manager import CompositeNodeManager  # 延迟导入以避免循环依赖
        return CompositeNodeManager
    if name == 'clear_global_composite_node_manager_for_tests':
        from .composite_node_manager import clear_global_composite_node_manager_for_tests  # 延迟导入以避免循环依赖
        return clear_global_composite_node_manager_for_tests
    raise AttributeError(name)
