from __future__ import annotations

from pathlib import Path
from typing import List

from engine.resources.definition_schema_view import get_default_definition_schema_view
from engine.signal import get_default_signal_repository

from ..comprehensive_types import ValidationIssue
from .base import BaseComprehensiveRule


class SignalDefinitionRule(BaseComprehensiveRule):
    """信号定义本身的有效性校验（不依赖节点图是否使用）。"""

    rule_id = "package.signal_definitions"
    category = "信号系统"
    default_level = "error"

    def run(self, ctx) -> List[ValidationIssue]:
        return validate_signal_definitions(self.validator)


def validate_signal_definitions(validator) -> List[ValidationIssue]:
    repo = get_default_signal_repository()
    errors = repo.get_errors()
    if not errors:
        return []

    schema_view = get_default_definition_schema_view()
    sources = schema_view.get_all_signal_definition_sources()

    issues: List[ValidationIssue] = []
    for signal_id in sorted(errors.keys()):
        message = str(errors.get(signal_id) or "").strip() or "信号定义无效"
        source_path = sources.get(signal_id)
        source_text = str(source_path.as_posix()) if isinstance(source_path, Path) else ""
        location = f"信号定义 SIGNAL_ID={signal_id}"
        if source_text:
            location = f"{location} @ {source_text}"

        issues.append(
            ValidationIssue(
                level="error",
                category="信号系统",
                code="SIGNAL_DEFINITION_INVALID",
                location=location,
                message=message,
                suggestion=(
                    "请修正该信号定义文件中的 SIGNAL_PAYLOAD：\n"
                    "- signal_id/signal_name/parameters 结构必须完整；\n"
                    "- 参数名必须唯一；\n"
                    "- parameter_type 必须为受支持的中文类型名，且**严禁使用字典类型**（含别名字典/泛型字典）。\n"
                    "  若需要传递复杂数据，请优先改为结构体参数或拆分为多个信号。"
                ),
                reference="信号系统设计.md: 信号定义格式与参数约束",
                detail={
                    "type": "signal_definition_invalid",
                    "signal_id": signal_id,
                    "source_path": source_text or None,
                },
            )
        )

    return issues


__all__ = ["SignalDefinitionRule", "validate_signal_definitions"]


