from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional
from weakref import WeakKeyDictionary

from engine.graph.models.graph_config import GraphConfig
from engine.graph.models.package_model import InstanceConfig, TemplateConfig
from engine.resources.resource_manager import ResourceManager, ResourceType
from engine.validate.component_validator import ComponentValidator
from engine.utils.graph.graph_utils import normalize_graph_edges, normalize_graph_nodes

from ..comprehensive_types import ValidationIssue


@dataclass(frozen=True)
class GraphAttachment:
    owner_kind: str  # template | instance | level
    owner_name: str
    owner_id: str
    entity_type: str
    graph_id: str
    graph_config: GraphConfig
    detail: Dict[str, object]
    location_full: str
    location_compact: str


@dataclass(frozen=True)
class GraphDataSnapshot:
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    connections: List[Dict[str, Any]]


_GRAPH_CONFIG_CACHE: "WeakKeyDictionary[ResourceManager, Dict[str, GraphConfig]]" = (
    WeakKeyDictionary()
)
_GRAPH_SNAPSHOT_CACHE: Dict[str, GraphDataSnapshot] = {}


def _load_graph_config(resource_manager: ResourceManager, graph_id: str) -> Optional[GraphConfig]:
    manager_cache = _GRAPH_CONFIG_CACHE.setdefault(resource_manager, {})
    cached = manager_cache.get(graph_id)
    if cached is not None:
        return cached
    graph_data = resource_manager.load_resource(ResourceType.GRAPH, graph_id)
    if not graph_data:
        return None
    graph_config = GraphConfig.deserialize(graph_data)
    manager_cache[graph_id] = graph_config
    return graph_config


def get_graph_snapshot(graph_data: Dict[str, Any], cache_key: Optional[str] = None) -> GraphDataSnapshot:
    if cache_key:
        cached = _GRAPH_SNAPSHOT_CACHE.get(cache_key)
        if cached:
            return cached
    nodes = normalize_graph_nodes(graph_data.get("nodes", []))
    edges = normalize_graph_edges(graph_data.get("edges", []))
    connections = normalize_graph_edges(graph_data.get("connections", []))
    snapshot = GraphDataSnapshot(nodes=nodes, edges=edges, connections=connections)
    if cache_key:
        _GRAPH_SNAPSHOT_CACHE[cache_key] = snapshot
    return snapshot


def clear_graph_snapshot_cache() -> None:
    _GRAPH_SNAPSHOT_CACHE.clear()


def convert_engine_issues_to_validation(
    engine_issues,
    *,
    fallback_location: str,
    detail: Dict[str, object],
    category_override: Optional[str] = None,
) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    base_detail = dict(detail)
    for issue in engine_issues or []:
        merged_detail = {**base_detail, **(issue.detail or {})}
        issues.append(
            ValidationIssue(
                level=issue.level,
                category=category_override or issue.category,
                location=issue.location or fallback_location,
                message=issue.message,
                suggestion="",
                reference=issue.reference or "",
                detail=merged_detail,
            )
        )
    return issues


def validate_components_for_entity(
    components,
    entity_type: str,
    *,
    location: str,
    detail: Dict[str, object],
) -> List[ValidationIssue]:
    if not components:
        return []
    component_names = ComponentValidator.collect_component_names(components)
    engine_issues = ComponentValidator.validate_components(component_names, entity_type)
    return convert_engine_issues_to_validation(
        engine_issues,
        fallback_location=location,
        detail=detail,
        category_override="组件",
    )


def iter_template_graphs(
    resource_manager: Optional[ResourceManager],
    templates: Dict[str, TemplateConfig],
) -> Iterator[GraphAttachment]:
    if not resource_manager:
        return
    for template_id, template in templates.items():
        if not template.default_graphs:
            continue
        for graph_id in template.default_graphs:
            graph_config = _load_graph_config(resource_manager, graph_id)
            if not graph_config:
                continue
            location_prefix = f"模板 '{template.name}' ({template_id})"
            detail = {
                "type": "template",
                "template_id": template_id,
                "graph_name": graph_config.name,
                "graph_id": graph_id,
            }
            yield GraphAttachment(
                owner_kind="template",
                owner_name=template.name,
                owner_id=template_id,
                entity_type=template.entity_type,
                graph_id=graph_id,
                graph_config=graph_config,
                detail=detail,
                location_full=f"{location_prefix} > 节点图 '{graph_config.name}' ({graph_id})",
                location_compact=f"{location_prefix} > 节点图 '{graph_config.name}'",
            )


def iter_instance_graphs(
    resource_manager: Optional[ResourceManager],
    instances: Dict[str, InstanceConfig],
    templates: Optional[Dict[str, TemplateConfig]] = None,
) -> Iterator[GraphAttachment]:
    if not resource_manager:
        return
    for instance_id, instance in instances.items():
        if not instance.additional_graphs:
            continue
        template = templates.get(instance.template_id) if templates else None
        resolved_entity_type = (
            template.entity_type
            if template
            else instance.metadata.get("entity_type") or ""
        )
        for graph_id in instance.additional_graphs:
            graph_config = _load_graph_config(resource_manager, graph_id)
            if not graph_config:
                continue
            location_prefix = f"实例 '{instance.name}' ({instance_id})"
            detail = {
                "type": "instance",
                "instance_id": instance.instance_id,
                "graph_name": graph_config.name,
                "graph_id": graph_id,
            }
            yield GraphAttachment(
                owner_kind="instance",
                owner_name=instance.name,
                owner_id=instance_id,
                entity_type=resolved_entity_type,
                graph_id=graph_id,
                graph_config=graph_config,
                detail=detail,
                location_full=f"{location_prefix} > 节点图 '{graph_config.name}' ({graph_id})",
                location_compact=f"{location_prefix} > 节点图 '{graph_config.name}'",
            )


def iter_level_entity_graphs(
    resource_manager: Optional[ResourceManager],
    level_entity,
) -> Iterator[GraphAttachment]:
    if not resource_manager or not level_entity or not level_entity.additional_graphs:
        return
    entity_type = level_entity.metadata.get("entity_type", "关卡")
    for graph_id in level_entity.additional_graphs:
        graph_config = _load_graph_config(resource_manager, graph_id)
        if not graph_config:
            continue
        location_prefix = f"关卡实体 '{level_entity.name}'"
        detail = {
            "type": "level_entity",
            "instance_id": level_entity.instance_id,
            "graph_name": graph_config.name,
            "graph_id": graph_id,
            "entity_type": entity_type,
        }
        yield GraphAttachment(
            owner_kind="level",
            owner_name=level_entity.name,
            owner_id=level_entity.instance_id,
            entity_type=entity_type,
            graph_id=graph_id,
            graph_config=graph_config,
            detail=detail,
            location_full=f"{location_prefix} > 节点图 '{graph_config.name}' ({graph_id})",
            location_compact=f"{location_prefix} > 节点图 '{graph_config.name}'",
        )


def iter_all_package_graphs(
    resource_manager: Optional[ResourceManager],
    templates: Dict[str, TemplateConfig],
    instances: Dict[str, InstanceConfig],
    level_entity,
) -> Iterator[GraphAttachment]:
    yield from iter_template_graphs(resource_manager, templates)
    yield from iter_instance_graphs(resource_manager, instances, templates)
    yield from iter_level_entity_graphs(resource_manager, level_entity)


__all__ = [
    "GraphAttachment",
    "GraphDataSnapshot",
    "iter_all_package_graphs",
    "iter_template_graphs",
    "iter_instance_graphs",
    "iter_level_entity_graphs",
    "get_graph_snapshot",
    "clear_graph_snapshot_cache",
    "convert_engine_issues_to_validation",
    "validate_components_for_entity",
]


