"""代码结构（M2）规则子包。

该子包按“单一规则域/单一主题”拆分实现，`engine.validate.rules.code_structure_rules`
作为稳定入口负责对外 re-export，避免外部 import 路径随内部拆分变化。
"""

from .boolean_conditions import (
    IfBooleanRule,
    IfBoolEqualityToConstRule,
    NoDirectLogicNotCallInIfRule,
)
from .event_handler_name import EventHandlerNameRule
from .event_name import EventNameRule
from .graph_vars_declaration import GraphVarsDeclarationRule
from .literal_assignment import NoLiteralAssignmentRule
from .local_var_initial_value import LocalVarInitialValueRule
from .local_var_usage import LocalVarUsageRule
from .node_call_game_required import NodeCallGameRequiredRule
from .on_method_name import OnMethodNameRule
from .unknown_node_call import UnknownNodeCallRule
from .required_inputs import RequiredInputsRule
from .signal_param_names import SignalParamNamesRule
from .struct_name_required import StructNameRequiredRule
from .type_name import TypeNameRule
from .variadic_min_args import VariadicMinArgsRule

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


