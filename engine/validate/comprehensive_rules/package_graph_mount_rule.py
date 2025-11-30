from __future__ import annotations

from typing import Dict, List, Set

from engine.validate.context import ValidationContext

from ..comprehensive_types import ValidationIssue
from .base import BaseComprehensiveRule
from .helpers import GraphAttachment, iter_all_package_graphs


class PackageGraphMountRule(BaseComprehensiveRule):
    """检查存档索引中的节点图与实体挂载关系是否一致。

    目标：
    - 提醒：存档索引 `resources.graphs` 中声明但未挂载到任何实体/模板的节点图；
    - 提醒：模板/实例/关卡实体上挂载的节点图未在存档索引中声明。
    """

    rule_id = "package.graph_mount"
    category = "节点图挂载"
    default_level = "warning"

    def run(self, ctx: ValidationContext) -> List[ValidationIssue]:
        return validate_package_graph_mount(self.validator, ctx)


def validate_package_graph_mount(
    validator,
    ctx: ValidationContext,
) -> List[ValidationIssue]:
    package = ctx.package
    resource_manager = ctx.resource_manager
    if not package or not resource_manager:
        return []

    package_id = getattr(package, "package_id", "")
    if not isinstance(package_id, str) or not package_id:
        return []
    if package_id in ("global_view", "unclassified_view"):
        return []

    package_index = getattr(package, "package_index", None)
    if package_index is None or not hasattr(package_index, "resources"):
        return []

    declared_graph_ids: List[str] = list(getattr(package_index.resources, "graphs", []) or [])
    templates = getattr(package, "templates", {}) or {}
    instances = getattr(package, "instances", {}) or {}
    level_entity = getattr(package, "level_entity", None)

    attachments: List[GraphAttachment] = list(
        iter_all_package_graphs(resource_manager, templates, instances, level_entity)
    )
    if not declared_graph_ids and not attachments:
        return []

    attached_graph_ids: Set[str] = set()
    attachment_by_graph: Dict[str, GraphAttachment] = {}
    for attachment in attachments:
        attached_graph_ids.add(attachment.graph_id)
        if attachment.graph_id not in attachment_by_graph:
            attachment_by_graph[attachment.graph_id] = attachment

    issues: List[ValidationIssue] = []
    declared_graph_set: Set[str] = set(declared_graph_ids)

    for graph_id in declared_graph_ids:
        if graph_id in attached_graph_ids:
            continue
        location = f"存档 '{package.name}' ({package_id}) > 节点图索引"
        detail = {
            "type": "package_graph_index",
            "package_id": package_id,
            "graph_id": graph_id,
        }
        issues.append(
            ValidationIssue(
                level="warning",
                category="节点图挂载",
                location=location,
                message=(
                    f"节点图 '{graph_id}' 在存档索引的 resources.graphs 中声明，"
                    f"但当前存档内没有任何模板或实体挂载该节点图。"
                ),
                suggestion=(
                    "如果该节点图已不再使用，可以从存档索引中移除；"
                    "如果仍需使用，请在对应的模板 default_graphs 或实体 additional_graphs 中挂载。"
                ),
                detail=detail,
            )
        )

    for graph_id, attachment in attachment_by_graph.items():
        if graph_id in declared_graph_set:
            continue
        location = attachment.location_full
        detail = {
            "type": "attached_graph",
            "package_id": package_id,
            "graph_id": graph_id,
            "owner_kind": attachment.owner_kind,
            "owner_id": attachment.owner_id,
            "owner_name": attachment.owner_name,
        }
        issues.append(
            ValidationIssue(
                level="warning",
                category="节点图挂载",
                location=location,
                message=(
                    f"实体挂载的节点图 '{attachment.graph_config.name}' ({graph_id}) "
                    f"未在当前存档索引的 resources.graphs 中声明。"
                ),
                suggestion=(
                    "建议将该节点图 ID 加入当前存档索引的 resources.graphs 列表，"
                    "以保证存档包内资源引用闭合且便于后续维护。"
                ),
                detail=detail,
            )
        )

    return issues


__all__ = ["PackageGraphMountRule", "validate_package_graph_mount"]


