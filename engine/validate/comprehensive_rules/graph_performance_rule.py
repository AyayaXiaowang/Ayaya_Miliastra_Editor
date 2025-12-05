from __future__ import annotations

from typing import Dict, List

from engine.configs.rules.entity_rules import can_entity_have_node_graphs
from engine.utils.graph.graph_utils import is_reasonable_constant

from ..comprehensive_types import ValidationIssue
from .base import BaseComprehensiveRule
from .helpers import get_graph_snapshot, iter_all_package_graphs


class GraphPerformanceRule(BaseComprehensiveRule):
    rule_id = "package.graph_performance"
    category = "节点图复用性"
    default_level = "info"

    def run(self, ctx) -> List[ValidationIssue]:
        return validate_graph_performance(self.validator)


def validate_graph_performance(validator) -> List[ValidationIssue]:
    resource_manager = validator.resource_manager
    if not resource_manager:
        return []
    # 当前关闭节点图硬编码常量的提示，不再返回任何与复用性相关的 Issue。
    return []


def check_graph_hardcoded_values(
    graph_data: Dict,
    location: str,
    detail: Dict,
) -> List[ValidationIssue]:
    if not graph_data or "nodes" not in graph_data:
        return []
    snapshot = get_graph_snapshot(graph_data, detail.get("graph_id"))
    nodes = snapshot.nodes
    node_violations: Dict[str, List[str]] = {}
    node_titles: Dict[str, str] = {}
    for node in nodes:
        node_id = node.get("id", "")
        node_title = node.get("title", node_id)
        node_titles[node_id] = node_title
        input_constants = node.get("input_constants", {})
        invalid_ports: List[str] = []
        for param_name, param_value in input_constants.items():
            if is_reasonable_constant(param_name, param_value):
                continue
            invalid_ports.append(param_name)
        if invalid_ports:
            node_violations[node_id] = invalid_ports
    if not node_violations:
        return []
    issues: List[ValidationIssue] = []
    for node_id, ports in node_violations.items():
        node_detail = dict(detail)
        node_detail["node_id"] = node_id
        node_detail["ports"] = sorted(ports)
        issues.append(
            ValidationIssue(
                level="info",
                category="节点图复用性",
                location=f"{location} > 节点 '{node_titles.get(node_id, node_id)}'",
                message=(
                    "节点图中检测到硬编码的数据参数："
                    f"{', '.join(sorted(ports))}"
                ),
                suggestion=(
                    "建议将硬编码的配置参数改为节点图变量或自定义变量，"
                    "以提升复用性与可维护性。"
                ),
                reference="节点图最佳实践.md:性能与复用性",
                detail=node_detail,
            )
        )
    return issues


__all__ = ["GraphPerformanceRule"]

