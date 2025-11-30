from __future__ import annotations

from typing import List

from engine.validate.context import ValidationContext

from ..comprehensive_types import ValidationIssue


class BaseComprehensiveRule:
    """存档级验证规则基类。"""

    rule_id: str = ""
    category: str = "package"
    default_level: str = "info"

    def __init__(self, validator) -> None:
        self.validator = validator

    def apply(self, ctx: ValidationContext) -> List[ValidationIssue]:
        issues = self.run(ctx)
        if issues:
            existing = getattr(self.validator, "issues", [])
            for issue in issues:
                if issue not in existing:
                    self.validator.report_issue(issue)
        return issues

    def run(self, ctx: ValidationContext) -> List[ValidationIssue]:
        raise NotImplementedError


__all__ = ["BaseComprehensiveRule"]

