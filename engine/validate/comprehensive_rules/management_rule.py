from __future__ import annotations

from typing import List

from ..comprehensive_types import ValidationIssue
from .base import BaseComprehensiveRule


class ManagementConfigRule(BaseComprehensiveRule):
    rule_id = "package.management"
    category = "管理配置"
    default_level = "warning"

    def run(self, ctx) -> List[ValidationIssue]:
        return validate_management_configs(self.validator)


def validate_management_configs(validator) -> List[ValidationIssue]:
    management = getattr(validator.package, "management", None)
    if not management:
        return []
    issues: List[ValidationIssue] = []
    issues.extend(_validate_layout_widget_templates(management))
    issues.extend(_validate_level_variables(management))
    return issues


def _validate_layout_widget_templates(management) -> List[ValidationIssue]:
    layouts = getattr(management, "ui_layouts", {}) or {}
    templates = getattr(management, "ui_widget_templates", {}) or {}
    if not layouts:
        return []
    issues: List[ValidationIssue] = []
    for layout_id, layout_data in layouts.items():
        if not isinstance(layout_data, dict):
            continue
        widgets = layout_data.get("widgets", []) or []
        if not widgets:
            continue
        layout_name = layout_data.get("name", layout_id)
        for widget in widgets:
            if not isinstance(widget, dict):
                continue
            template_id = widget.get("template_id")
            if not template_id:
                continue
            if template_id in templates:
                continue
            widget_name = widget.get("name", widget.get("id", "未命名控件"))
            detail = {
                "type": "management_ui_layout",
                "layout_id": layout_id,
                "widget_name": widget_name,
                "template_id": template_id,
            }
            issues.append(
                ValidationIssue(
                    level="error",
                    category="管理配置",
                    location=f"界面布局 '{layout_name}' > 控件 '{widget_name}'",
                    message=f"控件引用的模板 '{template_id}' 未在 UI 控件模板库中定义",
                    suggestion="请先在管理配置中创建对应的 UI 控件模板，或移除该引用。",
                    detail=detail,
                )
            )
    return issues


def _validate_level_variables(management) -> List[ValidationIssue]:
    level_variables = getattr(management, "level_variables", {}) or {}
    if not level_variables:
        return []
    issues: List[ValidationIssue] = []
    for variable_id, payload in level_variables.items():
        if not isinstance(payload, dict):
            continue
        variable_type = payload.get("variable_type")
        if variable_type:
            continue
        variable_name = payload.get("name", variable_id)
        detail = {
            "type": "management_level_variable",
            "variable_id": variable_id,
            "variable_name": variable_name,
        }
        issues.append(
            ValidationIssue(
                level="warning",
                category="管理配置",
                location=f"关卡变量 '{variable_name}'",
                message="关卡变量缺少 `variable_type` 定义，节点图无法推断其数据类型。",
                suggestion="请在管理配置中为该变量补充变量类型以保证节点引用安全。",
                detail=detail,
            )
        )
    return issues


__all__ = ["ManagementConfigRule"]

