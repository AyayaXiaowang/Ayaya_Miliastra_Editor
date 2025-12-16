from __future__ import annotations

from typing import Dict, List

from engine.nodes.advanced_node_features import SignalDefinition
from engine.signal import get_default_signal_repository

from ...comprehensive_types import ValidationIssue


MAX_SIGNAL_PARAMS = 10
MAX_SIGNAL_PARAM_NAME_LENGTH = 30


def validate_signal_definition_bounds(
    signal_definitions: Dict[str, SignalDefinition],
) -> List[ValidationIssue]:
    """检查信号定义本身的参数数量与参数名长度边界。

    约束规则：
    - 单个信号的参数数量不得超过 MAX_SIGNAL_PARAMS；
    - 每个参数名的字符长度不得超过 MAX_SIGNAL_PARAM_NAME_LENGTH。
    """
    issues: List[ValidationIssue] = []

    if not signal_definitions:
        return issues

    repo = get_default_signal_repository()
    allowed_params_by_id = repo.get_allowed_param_names_by_id()
    all_payloads = repo.get_all_payloads()

    for signal_id in signal_definitions.keys():
        payload = all_payloads.get(signal_id) or {}
        parameters = list(allowed_params_by_id.get(signal_id, set()))
        param_count = len(parameters)
        signal_name_text = payload.get("signal_name")
        signal_name = str(signal_name_text or signal_id)
        location = f"信号定义 '{signal_name}' (ID: {signal_id})"

        if param_count > MAX_SIGNAL_PARAMS:
            detail = {
                "type": "signal_definition",
                "signal_id": signal_id,
                "signal_name": signal_name,
                "param_count": param_count,
            }
            issues.append(
                ValidationIssue(
                    level="error",
                    category="信号系统",
                    location=location,
                    message=(
                        f"信号定义包含 {param_count} 个参数，超过允许的最大数量 "
                        f"{MAX_SIGNAL_PARAMS}。"
                    ),
                    suggestion=(
                        "请精简该信号的参数（例如拆分为多个信号或改为使用结构体参数），"
                        f"确保单个信号的参数数量不超过 {MAX_SIGNAL_PARAMS} 个。"
                    ),
                    reference="信号系统设计.md:5.1 信号参数数量与命名边界",
                    detail=detail,
                )
            )

        for param_name in parameters:
            name_text = str(param_name or "")
            if not name_text:
                continue
            name_length = len(name_text)
            if name_length > MAX_SIGNAL_PARAM_NAME_LENGTH:
                detail = {
                    "type": "signal_definition",
                    "signal_id": signal_id,
                    "signal_name": signal_name,
                    "param_name": name_text,
                    "param_name_length": name_length,
                }
                issues.append(
                    ValidationIssue(
                        level="error",
                        category="信号系统",
                        location=location,
                        message=(
                            f"信号参数名 '{param_name}' 长度为 {name_length}，"
                            f"超过允许的最大长度 {MAX_SIGNAL_PARAM_NAME_LENGTH} 字符。"
                        ),
                        suggestion=(
                            "请缩短参数名，使其在节点端口与信号管理界面中更易阅读，"
                            f"并满足不超过 {MAX_SIGNAL_PARAM_NAME_LENGTH} 个字符的要求。"
                        ),
                        reference="信号系统设计.md:5.1 信号参数数量与命名边界",
                        detail=detail,
                    )
                )

    return issues


__all__ = [
    "MAX_SIGNAL_PARAMS",
    "MAX_SIGNAL_PARAM_NAME_LENGTH",
    "validate_signal_definition_bounds",
]


