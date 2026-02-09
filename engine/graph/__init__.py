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
    LevelVariableDefinition,
    LevelVariableOverride,
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
    "LevelVariableDefinition",
    "LevelVariableOverride",
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

from .graph_code_parser import GraphCodeParser, GraphParseError, validate_graph_model
from .composite_code_parser import CompositeCodeParser
from .graph_code_reverse_generator import (
    ReverseGraphCodeError,
    ReverseGraphCodeOptions,
    build_semantic_signature,
    diff_semantic_signature,
    generate_graph_code_from_model,
)

__all__ += [
    "GraphCodeParser",
    "GraphParseError",
    "CompositeCodeParser",
    "validate_graph_model",
    "ReverseGraphCodeError",
    "ReverseGraphCodeOptions",
    "generate_graph_code_from_model",
    "build_semantic_signature",
    "diff_semantic_signature",
]


