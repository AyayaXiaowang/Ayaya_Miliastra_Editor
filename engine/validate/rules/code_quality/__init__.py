"""代码质量（M2/M3）规则子包。

该子包按“单一规则域/单一主题”拆分实现，对外稳定入口为 `engine.validate.rules.code_quality`。
"""

from .basic import LongWireRule, EventMultipleFlowOutputsRule, UnreachableCodeRule
from .dict_hazards import DictComputeMultiUseHazardRule, DictMutationRequiresGraphVarRule
from .entity_destroy_event_mount import EntityDestroyEventMountRule
from .graph_errors import IrModelingErrorsRule, GraphStructuralErrorsRule
from .pull_eval_reevaluation_hazard import PullEvalReevaluationHazardRule
from .unused_query_output import UnusedQueryOutputRule

__all__ = [
    "IrModelingErrorsRule",
    "GraphStructuralErrorsRule",
    "LongWireRule",
    "EventMultipleFlowOutputsRule",
    "EntityDestroyEventMountRule",
    "PullEvalReevaluationHazardRule",
    "DictComputeMultiUseHazardRule",
    "DictMutationRequiresGraphVarRule",
    "UnusedQueryOutputRule",
    "UnreachableCodeRule",
]


