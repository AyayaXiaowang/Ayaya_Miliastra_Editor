"""
引擎核心公共 API 导出点（稳定入口）。

仅暴露对外使用的接口；子模块默认内部。
"""

# Graph（模型/序列化/哈希/配置）
from .graph.models import (
    GraphModel,
    NodeModel,
    EdgeModel,
    PortModel,
    BasicBlock,
    serialize_graph,
    deserialize_graph,
    get_content_hash,
    GraphConfig,
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

# Nodes（节点注册表与规格）
from .nodes import (
    NodeRegistry,
    get_node_registry,
)

# Graph Code（图代码解析与生成）
from engine.graph import (  # type: ignore
    GraphCodeParser,
    CompositeCodeParser,
    GraphParseError,
    validate_graph,
)

# Validators（验证引擎）
from engine.validate.api import validate_files  # type: ignore

# Utilities（工具函数）
from engine.utils.graph.graph_utils import is_flow_port_name  # type: ignore
from engine.utils.logging.logger import log_info, log_error, log_warn  # type: ignore

# Configs（配置与设置）
from engine.configs.settings import settings, Settings  # type: ignore

__all__ = [
    # graph models
    "GraphModel",
    "NodeModel",
    "EdgeModel",
    "PortModel",
    "BasicBlock",
    # serialization/hash
    "serialize_graph",
    "deserialize_graph",
    "get_content_hash",
    # graph config
    "GraphConfig",
    # package model (transition)
    "VariableConfig",
    "GraphVariableConfig",
    "SignalParameterConfig",
    "SignalConfig",
    "ComponentConfig",
    "TemplateConfig",
    "InstanceConfig",
    "CombatPresets",
    "ManagementData",
    # nodes
    "NodeRegistry",
    "get_node_registry",
    # graph code
    "GraphCodeParser",
    "CompositeCodeParser",
    "GraphParseError",
    "validate_graph",
    # validators
    "validate_files",
    # utilities
    "is_flow_port_name",
    "log_info",
    "log_error",
    "log_warn",
    # configs
    "settings",
    "Settings",
]

