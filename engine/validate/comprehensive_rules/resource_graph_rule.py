from __future__ import annotations

from typing import List

from engine.graph.models.graph_config import GraphConfig
from engine.resources.resource_manager import ResourceManager, ResourceType

from ..comprehensive_types import ValidationIssue
from .base import BaseComprehensiveRule


class ResourceLibraryGraphsRule(BaseComprehensiveRule):
    rule_id = "package.resource_graphs"
    category = "资源库节点图"
    default_level = "error"

    def run(self, ctx) -> List[ValidationIssue]:
        return validate_resource_library_graphs(self.validator)


def validate_resource_library_graphs(validator) -> List[ValidationIssue]:
    resource_manager: ResourceManager | None = validator.resource_manager
    if not resource_manager:
        return []
    graph_ids = resource_manager.list_resources(ResourceType.GRAPH)
    if not graph_ids:
        return []
    issues: List[ValidationIssue] = []
    for graph_id in graph_ids:
        graph_data = resource_manager.load_resource(ResourceType.GRAPH, graph_id)
        if not graph_data:
            continue
        graph_config = GraphConfig.deserialize(graph_data)
        location = f"资源库节点图 '{graph_config.name}' ({graph_id})"
        detail = {
            "type": "resource_graph",
            "graph_id": graph_id,
            "graph_name": graph_config.name,
        }
        issues.extend(
            validator.validate_graph_structure_only_checks(graph_config.data, location, detail)
        )
    return issues


__all__ = ["ResourceLibraryGraphsRule"]

