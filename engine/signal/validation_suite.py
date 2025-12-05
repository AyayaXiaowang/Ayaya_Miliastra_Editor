from __future__ import annotations

from typing import List, Type

from engine.validate.pipeline import ValidationRule
from engine.validate.issue import EngineIssue
from engine.validate.rules.code_structure_rules import SignalParamNamesRule
from engine.validate.comprehensive_rules.signal_rule import SignalUsageRule


class SignalValidationSuite:
    """信号系统相关验证规则集合。

    封装代码级规则与存档级综合规则的装配，便于上层在需要时一次性启用/禁用
    与信号系统相关的检查，而不必关心具体规则类名与注册顺序。
    """

    @staticmethod
    def build_code_rules() -> List[ValidationRule[EngineIssue]]:
        """构建与信号相关的代码级（M2/M3）规则列表。"""
        return [SignalParamNamesRule()]

    @staticmethod
    def get_code_rule_types() -> List[Type[ValidationRule[EngineIssue]]]:
        """返回代码级规则类型列表，便于外部按类型比较或去重。"""
        return [SignalParamNamesRule]

    @staticmethod
    def build_comprehensive_rules() -> List[SignalUsageRule]:
        """构建与信号相关的综合规则列表。"""
        return [SignalUsageRule()]


