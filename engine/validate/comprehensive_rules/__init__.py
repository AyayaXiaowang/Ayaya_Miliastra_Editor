from __future__ import annotations

from typing import List

from ..comprehensive_types import ValidationIssue
from .base import BaseComprehensiveRule
from .composite_rule import CompositeNodesRule
from .frontend_variable_rule import FrontendVariableRule
from .graph_performance_rule import GraphPerformanceRule
from .instance_rule import InstanceRule
from .level_entity_rule import LevelEntityRule
from .management_rule import ManagementConfigRule
from .package_graph_mount_rule import PackageGraphMountRule
from .resource_graph_rule import ResourceLibraryGraphsRule
from .signal_rule import SignalUsageRule
from .struct_rule import StructUsageRule
from .template_rule import TemplateRule
from .ui_controls_rule import UiControlsRule


def build_rules(validator) -> List[BaseComprehensiveRule]:
    return [
        LevelEntityRule(validator),
        TemplateRule(validator),
        InstanceRule(validator),
        PackageGraphMountRule(validator),
        UiControlsRule(validator),
        ManagementConfigRule(validator),
        FrontendVariableRule(validator),
        GraphPerformanceRule(validator),
        SignalUsageRule(validator),
        StructUsageRule(validator),
        ResourceLibraryGraphsRule(validator),
        CompositeNodesRule(validator),
    ]


__all__ = ["build_rules", "BaseComprehensiveRule"]

