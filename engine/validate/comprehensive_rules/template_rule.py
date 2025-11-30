from __future__ import annotations

from typing import List, Optional

from engine.configs.rules.entity_rules import can_entity_have_node_graphs
from engine.graph.models.package_model import TemplateConfig
from engine.validate.entity_config_validator import EntityConfigValidator
from engine.validate.entity_validator import EntityValidator

from ..comprehensive_types import ValidationIssue
from .base import BaseComprehensiveRule
from .helpers import (
    convert_engine_issues_to_validation,
    iter_template_graphs,
    validate_components_for_entity,
)


class TemplateRule(BaseComprehensiveRule):
    rule_id = "package.templates"
    category = "模板"
    default_level = "error"

    def run(self, ctx) -> List[ValidationIssue]:
        return validate_templates(self.validator)


def validate_templates(validator) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    templates = validator.package.templates
    for template in templates.values():
        issues.extend(validate_single_template(validator, template))
    return issues


def validate_single_template(validator, template: TemplateConfig) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    location_prefix = f"模板 '{template.name}' ({template.template_id})"
    type_issue = _build_template_type_issue(template, location_prefix)
    if type_issue is not None:
        issues.append(type_issue)
    base_detail = {"type": "template", "template_id": template.template_id}
    entity_issues = EntityValidator.validate_entity_type(template.entity_type)
    issues.extend(
        convert_engine_issues_to_validation(
            entity_issues,
            fallback_location=location_prefix,
            detail=base_detail,
            category_override="模板",
        )
    )
    issues.extend(
        validate_components_for_entity(
            template.default_components,
            template.entity_type,
            location=f"{location_prefix} > 组件",
            detail=base_detail,
        )
    )
    if template.entity_config:
        config_issues = EntityConfigValidator.validate_entity_config_by_type(
            template.entity_type, template.entity_config
        )
        issues.extend(
            convert_engine_issues_to_validation(
                config_issues,
                fallback_location=f"{location_prefix} > 实体配置",
                detail=base_detail,
                category_override="实体配置",
            )
        )
    graph_support_issues = EntityValidator.validate_node_graphs(
        template.entity_type, bool(template.default_graphs)
    )
    if graph_support_issues:
        issues.extend(
            convert_engine_issues_to_validation(
                graph_support_issues,
                fallback_location=f"{location_prefix} > 节点图",
                detail=base_detail,
                category_override="节点图",
            )
        )
        return issues
    if template.default_graphs:
        attachments = iter_template_graphs(
            validator.resource_manager,
            {template.template_id: template},
        )
        for attachment in attachments:
            issues.extend(
                validator.validate_graph_data(
                    attachment.graph_config.data,
                    template.entity_type,
                    attachment.location_full,
                    attachment.detail,
                )
            )

    return issues


def _build_template_type_issue(
    template: TemplateConfig, location_prefix: str
) -> Optional[ValidationIssue]:
    detail = {"type": "template", "template_id": template.template_id}
    if template.entity_type == "关卡":
        return ValidationIssue(
            level="error",
            category="模板",
            location=location_prefix,
            message="元件库中不应包含关卡类型的模板",
            suggestion="关卡实体应存储在 level_entity 字段中，请移除此模板。",
            detail=detail,
        )
    if template.entity_type == "UI控件":
        return ValidationIssue(
            level="error",
            category="模板",
            location=location_prefix,
            message="元件库中不应包含UI控件类型的模板",
            suggestion="UI控件属于资产类型，应移至界面控件组管理区域。",
            detail=detail,
        )
    valid_types = {"角色", "物件", "物件-动态", "物件-静态", "造物", "本地投射物", "玩家"}
    if template.entity_type not in valid_types:
        return ValidationIssue(
            level="warning",
            category="模板",
            location=location_prefix,
            message=f"模板类型'{template.entity_type}'可能不适合放在元件库中",
            suggestion=f"元件库应只包含可摆放的实体类型：{', '.join(valid_types)}",
            detail=detail,
        )
    return None


__all__ = ["TemplateRule"]

