"""
图模型、图变换与解析（不含具体节点实现）。

说明：本子包包含 Graph 模型与解析/生成的核心逻辑；
复合节点解析、IR 管线与工具位于 `engine/graph/*`。
"""

from .models import (
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

__all__ = [
    "GraphModel",
    "NodeModel",
    "EdgeModel",
    "PortModel",
    "BasicBlock",
    "serialize_graph",
    "deserialize_graph",
    "get_content_hash",
    "GraphConfig",
    "VariableConfig",
    "GraphVariableConfig",
    "SignalParameterConfig",
    "SignalConfig",
    "ComponentConfig",
    "TemplateConfig",
    "InstanceConfig",
    "CombatPresets",
    "ManagementData",
]

"""
图代码解析与生成
"""

from .graph_code_parser import GraphCodeParser, GraphParseError, validate_graph
from .composite_code_parser import CompositeCodeParser

__all__ += [
    "GraphCodeParser",
    "GraphParseError",
    "CompositeCodeParser",
    "validate_graph",
]


