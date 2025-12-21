"""
代码结构规范规则（M2）：if 布尔条件、可变参数节点最小入参、节点图变量声明、类型名合法性等。

该文件是**稳定入口**：为了避免外部 import 路径随内部拆分变化，具体实现已拆到
`engine.validate.rules.code_structure` 子包中，此处仅 re-export 规则类。
"""

from __future__ import annotations

from .code_structure.boolean_conditions import (
    IfBooleanRule,
    IfBoolEqualityToConstRule,
    NoDirectLogicNotCallInIfRule,
)
from .code_structure.event_handler_name import EventHandlerNameRule
from .code_structure.event_name import EventNameRule
from .code_structure.graph_vars_declaration import GraphVarsDeclarationRule
from .code_structure.literal_assignment import NoLiteralAssignmentRule
from .code_structure.local_var_initial_value import LocalVarInitialValueRule
from .code_structure.local_var_usage import LocalVarUsageRule
from .code_structure.node_call_game_required import NodeCallGameRequiredRule
from .code_structure.on_method_name import OnMethodNameRule
from .code_structure.unknown_node_call import UnknownNodeCallRule
from .code_structure.required_inputs import RequiredInputsRule
from .code_structure.signal_param_names import SignalParamNamesRule
from .code_structure.struct_name_required import StructNameRequiredRule
from .code_structure.type_name import TypeNameRule
from .code_structure.variadic_min_args import VariadicMinArgsRule

__all__ = [
    "IfBooleanRule",
    "NoDirectLogicNotCallInIfRule",
    "IfBoolEqualityToConstRule",
    "VariadicMinArgsRule",
    "GraphVarsDeclarationRule",
    "NoLiteralAssignmentRule",
    "UnknownNodeCallRule",
    "EventHandlerNameRule",
    "EventNameRule",
    "OnMethodNameRule",
    "TypeNameRule",
    "SignalParamNamesRule",
    "RequiredInputsRule",
    "StructNameRequiredRule",
    "LocalVarInitialValueRule",
    "LocalVarUsageRule",
    "NodeCallGameRequiredRule",
]

