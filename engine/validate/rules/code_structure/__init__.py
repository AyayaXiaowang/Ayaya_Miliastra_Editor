"""代码结构（M2）规则子包。

该子包按“单一规则域/单一主题”拆分实现，`engine.validate.rules.code_structure_rules`
作为稳定入口负责对外 re-export，避免外部 import 路径随内部拆分变化。
"""

from .boolean_conditions import (
    IfBooleanRule,
    IfBoolEqualityToConstRule,
    NoDirectLogicNotCallInIfRule,
)
from .dict_annotation_requires_key_value import DictAnnotationRequiresKeyValueRule
from .event_handler_name import EventHandlerNameRule
from .event_handler_signature import EventHandlerSignatureRule
from .event_name import EventNameRule
from .graph_vars_declaration import GraphVarsDeclarationRule
from .graph_var_redundant_init_on_entity_created import (
    GraphVarRedundantInitOnEntityCreatedRule,
)
from .graph_vars_struct_name_required import GraphVarsStructNameRequiredRule
from .custom_var_redundant_init_on_entity_created import (
    CustomVarRedundantInitOnEntityCreatedRule,
)
from .id_literal_10_digits import IdLiteralTenDigitsRule
from .literal_assignment import NoLiteralAssignmentRule
from .local_var_initial_value import LocalVarInitialValueRule
from .local_var_usage import LocalVarUsageRule
from .node_call_game_required import NodeCallGameRequiredRule
from .on_method_name import OnMethodNameRule
from .unknown_node_call import UnknownNodeCallRule
from .ui_level_custom_var_target_entity import UiLevelCustomVarTargetEntityRule
from .required_inputs import RequiredInputsRule
from .signal_param_names import SignalParamNamesRule
from .shared_signal_definitions_forbidden import SharedSignalsForbiddenRule
from .client_skill_graph_single_start_event import ClientSkillGraphSingleStartEventRule
from .client_filter_graph_single_return import ClientFilterGraphSingleReturnRule
from .struct_name_required import StructNameRequiredRule
from .type_name import TypeNameRule
from .variadic_min_args import VariadicMinArgsRule

__all__ = [
    "IfBooleanRule",
    "NoDirectLogicNotCallInIfRule",
    "IfBoolEqualityToConstRule",
    "DictAnnotationRequiresKeyValueRule",
    "VariadicMinArgsRule",
    "GraphVarsDeclarationRule",
    "GraphVarsStructNameRequiredRule",
    "GraphVarRedundantInitOnEntityCreatedRule",
    "CustomVarRedundantInitOnEntityCreatedRule",
    "IdLiteralTenDigitsRule",
    "NoLiteralAssignmentRule",
    "UnknownNodeCallRule",
    "UiLevelCustomVarTargetEntityRule",
    "EventHandlerNameRule",
    "EventHandlerSignatureRule",
    "EventNameRule",
    "OnMethodNameRule",
    "TypeNameRule",
    "SignalParamNamesRule",
    "SharedSignalsForbiddenRule",
    "RequiredInputsRule",
    "StructNameRequiredRule",
    "LocalVarInitialValueRule",
    "LocalVarUsageRule",
    "NodeCallGameRequiredRule",
    "ClientSkillGraphSingleStartEventRule",
    "ClientFilterGraphSingleReturnRule",
]


