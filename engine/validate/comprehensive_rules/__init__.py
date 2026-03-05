from __future__ import annotations

from typing import List

from ..comprehensive_types import ValidationIssue
from .base import BaseComprehensiveRule
from .auto_custom_variable_registry_rule import AutoCustomVariableRegistryRule
from .composite_rule import CompositeNodesRule
from .frontend_variable_rule import FrontendVariableRule
from .graph_performance_rule import GraphPerformanceRule
from .instance_rule import InstanceRule
from .guid_rule import PackageGuidUniquenessRule
from .graph_level_variable_usage_rule import GraphLevelVariableUsageRule
from .level_variable_reference_rule import LevelVariableReferenceRule
from .level_entity_rule import LevelEntityRule
from .management_rule import ManagementConfigRule
from .package_graph_mount_rule import PackageGraphMountRule
from .resource_graph_rule import ResourceLibraryGraphsRule
from .resource_id_uniqueness_rule import ResourceIdUniquenessRule
from .signal_rule import SignalUsageRule
from .signal_definition_rule import SignalDefinitionRule
from .struct_rule import StructUsageRule
from .struct_definition_rule import StructDefinitionRule
from .template_rule import TemplateRule
from .ui_controls_rule import UiControlsRule


def build_rules(validator) -> List[BaseComprehensiveRule]:
    return [
        LevelEntityRule(validator),
        TemplateRule(validator),
        InstanceRule(validator),
        PackageGuidUniquenessRule(validator),
        ResourceIdUniquenessRule(validator),
        PackageGraphMountRule(validator),
        UiControlsRule(validator),
        ManagementConfigRule(validator),
        AutoCustomVariableRegistryRule(validator),
        LevelVariableReferenceRule(validator),
        GraphLevelVariableUsageRule(validator),
        FrontendVariableRule(validator),
        GraphPerformanceRule(validator),
        SignalDefinitionRule(validator),
        SignalUsageRule(validator),
        StructDefinitionRule(validator),
        StructUsageRule(validator),
        ResourceLibraryGraphsRule(validator),
        CompositeNodesRule(validator),
    ]


__all__ = ["build_rules", "BaseComprehensiveRule"]

