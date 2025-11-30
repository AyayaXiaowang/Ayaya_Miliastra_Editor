from __future__ import annotations

from typing import List

from ..comprehensive_types import ValidationIssue
from .base import BaseComprehensiveRule
from .helpers import iter_level_entity_graphs


class LevelEntityRule(BaseComprehensiveRule):
    rule_id = "package.level_entity"
    category = "关卡实体"
    default_level = "error"

    def run(self, ctx) -> List[ValidationIssue]:
        return validate_level_entity(self.validator)


def validate_level_entity(validator) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    package = validator.package
    if not package.level_entity:
        issues.append(
            ValidationIssue(
                level="error",
                category="关卡实体",
                location="存档根节点",
                message="存档缺少关卡实体",
                suggestion="每个存档必须配置一个关卡实体，用于承载关卡逻辑。",
                detail={"type": "level_entity", "action": "create"},
            )
        )
        return issues

    level_entity = package.level_entity
    entity_type = level_entity.metadata.get("entity_type")
    if entity_type != "关卡":
        issues.append(
            ValidationIssue(
                level="error",
                category="关卡实体",
                location=f"关卡实体 '{level_entity.name}'",
                message=f"关卡实体的类型不正确：{entity_type}，应为'关卡'",
                suggestion="请将 metadata.entity_type 设置为 '关卡'。",
                detail={
                    "type": "level_entity",
                    "entity_id": level_entity.instance_id,
                },
            )
        )

    component_names = [c.component_type for c in level_entity.additional_components]
    valid_components = {"自定义变量", "全局计时器"}
    for component in component_names:
        if component in valid_components:
            continue
        issues.append(
            ValidationIssue(
                level="warning",
                category="关卡实体",
                location=f"关卡实体 '{level_entity.name}' > 组件 '{component}'",
                message=f"关卡实体包含组件'{component}'，可能不受支持",
                suggestion=f"关卡实体的可用组件：{', '.join(valid_components)}",
                reference="关卡.md:15-17",
                detail={
                    "type": "level_entity",
                    "instance_id": level_entity.instance_id,
                    "component": component,
                },
            )
        )

    attachments = iter_level_entity_graphs(validator.resource_manager, level_entity) or []
    for attachment in attachments:
        issues.extend(
            validator.validate_graph_data(
                attachment.graph_config.data,
                "关卡",
                attachment.location_full,
                attachment.detail,
            )
        )

    return issues


__all__ = ["LevelEntityRule"]

