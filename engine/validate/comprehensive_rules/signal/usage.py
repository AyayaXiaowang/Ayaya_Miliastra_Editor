from __future__ import annotations

from typing import Dict, List

from engine.nodes.advanced_node_features import SignalDefinition, build_signal_definitions_from_package
from engine.nodes.node_definition_loader import NodeDef

from ...comprehensive_types import ValidationIssue
from ..base import BaseComprehensiveRule
from ..helpers import iter_all_package_graphs
from .definition_bounds import validate_signal_definition_bounds
from .graph_validation import validate_signals_in_single_graph


class SignalUsageRule(BaseComprehensiveRule):
    """基于包级 `signals` 字段的信号使用一致性校验（存在性 / 参数覆盖 / 常量类型 / 连线类型）。"""

    rule_id = "package.signal_usage"
    category = "信号系统"
    default_level = "error"

    def run(self, ctx) -> List[ValidationIssue]:
        return validate_package_signal_usage(self.validator)


def validate_package_signal_usage(validator) -> List[ValidationIssue]:
    """在整个存档包范围内校验信号定义与节点图用法的一致性。"""
    package = getattr(validator, "package", None)
    resource_manager = getattr(validator, "resource_manager", None)
    if package is None or resource_manager is None:
        return []

    signal_definitions: Dict[str, SignalDefinition] = build_signal_definitions_from_package(
        package
    )
    # 预构建 signal_id -> {param_name: param_type} 映射，便于后续快速查询
    signal_param_types: Dict[str, Dict[str, str]] = {}
    for signal_id, signal_def in signal_definitions.items():
        type_map: Dict[str, str] = {}
        for param in signal_def.parameters:
            type_map[param.param_name] = param.param_type
        signal_param_types[signal_id] = type_map

    issues: List[ValidationIssue] = []
    issues.extend(validate_signal_definition_bounds(signal_definitions))

    attachments = iter_all_package_graphs(
        resource_manager,
        package.templates,
        package.instances,
        package.level_entity,
    )

    node_library: Dict[str, NodeDef] = getattr(validator, "node_library", {}) or {}

    for attachment in attachments:
        # 仅对服务器节点图执行信号校验
        if attachment.graph_config.graph_type != "server":
            continue
        issues.extend(
            validate_signals_in_single_graph(
                attachment,
                signal_definitions,
                signal_param_types,
                node_library,
            )
        )
    return issues


__all__ = ["SignalUsageRule"]


