from __future__ import annotations

from typing import List

from engine.graph.models.package_model import InstanceConfig

from ..comprehensive_types import ValidationIssue
from .base import BaseComprehensiveRule
from .helpers import iter_instance_graphs, validate_components_for_entity


class InstanceRule(BaseComprehensiveRule):
    rule_id = "package.instances"
    category = "实例"
    default_level = "error"

    def run(self, ctx) -> List[ValidationIssue]:
        return validate_instances(self.validator)


def validate_instances(validator) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    for instance in validator.package.instances.values():
        issues.extend(validate_single_instance(validator, instance))
    return issues


def validate_single_instance(validator, instance: InstanceConfig) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    location_prefix = f"实例 '{instance.name}' ({instance.instance_id})"
    is_level_entity = instance.metadata.get("is_level_entity", False)
    if not is_level_entity and instance.template_id not in validator.package.templates:
        issues.append(
            ValidationIssue(
                level="error",
                category="实例",
                location=location_prefix,
                message=f"实例引用的模板'{instance.template_id}'不存在",
                suggestion="请确保模板已创建，或修正实例的 template_id。",
                detail={"type": "instance", "instance_id": instance.instance_id},
            )
        )
        return issues
    if is_level_entity:
        entity_type = instance.metadata.get("entity_type", "关卡")
        issues.extend(
            _validate_instance_components(
                validator,
                instance.additional_components,
                entity_type,
                location_prefix,
                instance.instance_id,
            )
        )
        issues.extend(
            _validate_instance_graphs(
                validator,
                instance,
                entity_type,
                location_prefix,
            )
        )
        return issues

    template = validator.package.templates[instance.template_id]
    issues.extend(
        _validate_instance_components(
            validator,
            instance.additional_components,
            template.entity_type,
            location_prefix,
            instance.instance_id,
        )
    )
    issues.extend(
        _validate_instance_graphs(
            validator,
            instance,
            template.entity_type,
            location_prefix,
        )
    )
    return issues


def _validate_instance_components(
    validator, components, entity_type, location_prefix, instance_id
):
    detail = {"type": "instance", "instance_id": instance_id}
    return validate_components_for_entity(
        components,
        entity_type,
        location=f"{location_prefix} > 附加组件",
        detail=detail,
    )


def _validate_instance_graphs(
    validator,
    instance: InstanceConfig,
    entity_type: str,
    location_prefix: str,
):
    issues: List[ValidationIssue] = []
    if not instance.additional_graphs:
        return issues
    attachments = iter_instance_graphs(
        validator.resource_manager,
        {instance.instance_id: instance},
        validator.package.templates,
    )
    for attachment in attachments:
        issues.extend(
            validator.validate_graph_data(
                attachment.graph_config.data,
                entity_type,
                attachment.location_full,
                attachment.detail,
            )
        )
    return issues


__all__ = ["InstanceRule"]

