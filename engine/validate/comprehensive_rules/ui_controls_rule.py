from __future__ import annotations

from typing import List

from ..comprehensive_types import ValidationIssue
from .base import BaseComprehensiveRule


class UiControlsRule(BaseComprehensiveRule):
    rule_id = "package.ui_controls"
    category = "UI控件"
    default_level = "error"

    def run(self, ctx) -> List[ValidationIssue]:
        return validate_ui_controls(self.validator)


def validate_ui_controls(validator) -> List[ValidationIssue]:
    management = getattr(validator.package, "management", None)
    if not management or not management.ui_layouts:
        return []
    issues: List[ValidationIssue] = []
    for layout_id, layout_data in management.ui_layouts.items():
        if not isinstance(layout_data, dict):
            continue
        layout_name = layout_data.get("name", layout_id)
        widgets = layout_data.get("widgets", [])
        for widget in widgets:
            if not isinstance(widget, dict):
                continue
            if "graphs" in widget and widget["graphs"]:
                widget_name = widget.get("name", "未命名控件")
                issues.append(
                    ValidationIssue(
                        level="error",
                        category="UI控件",
                        location=f"界面布局 '{layout_name}' > 控件 '{widget_name}'",
                        message="UI控件不能挂载节点图",
                        suggestion="UI控件使用界面控件组的专门配置，不使用节点图系统。",
                        detail={
                            "type": "ui_layout",
                            "layout_id": layout_id,
                            "widget": widget,
                        },
                    )
                )
    return issues


__all__ = ["UiControlsRule"]

