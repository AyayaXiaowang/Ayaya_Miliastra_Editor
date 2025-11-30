from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Generic, List, Protocol, TypeVar
from time import perf_counter

from .context import ValidationContext
from .issue import EngineIssue


# 说明：
# - ValidationRule / ValidationPipeline 现在对“问题类型”做泛型抽象，既可以产出 EngineIssue，
#   也可以在 UI 侧复用为 ValidationIssue 等其他结构。
# - 现有基于 EngineIssue 的规则无需修改：类型推断会自动推导出 IssueT = EngineIssue。
IssueT = TypeVar("IssueT")


# ========== 规则级性能采样（可选） ==========

_profiling_enabled: bool = False
_profiling_time_by_rule: Dict[str, float] = {}
_profiling_calls_by_rule: Dict[str, int] = {}


def enable_validation_profiling(enabled: bool = True) -> None:
    """开启或关闭验证规则级别的耗时统计。

    说明：
        - 仅在调试/基准测试场景使用，默认关闭以避免在日常开发中产生多余开销。
        - 统计结果按 rule_id 聚合：同一规则在不同文件上的多次调用会被累计。
    """
    global _profiling_enabled
    _profiling_enabled = bool(enabled)


def reset_validation_profiling_stats() -> None:
    """清空当前的规则级性能统计数据。"""
    _profiling_time_by_rule.clear()
    _profiling_calls_by_rule.clear()


def get_validation_profiling_stats() -> Dict[str, Dict[str, float]]:
    """返回当前规则级性能统计快照。

    返回值示例：
        {
            "engine_code_port_types_match": {"time": 0.123, "calls": 24},
            "engine_code_if_boolean": {"time": 0.045, "calls": 24},
        }
    """
    snapshot: Dict[str, Dict[str, float]] = {}
    for rule_id, total_time in _profiling_time_by_rule.items():
        calls = float(_profiling_calls_by_rule.get(rule_id, 0))
        snapshot[rule_id] = {
            "time": float(total_time),
            "calls": calls,
        }
    return snapshot


class ValidationRule(Protocol[IssueT]):
    """规则协议：实现 apply(ctx) -> List[IssueT] 即可"""

    rule_id: str
    category: str
    default_level: str

    def apply(self, ctx: ValidationContext) -> List[IssueT]:
        ...


@dataclass
class ValidationPipeline(Generic[IssueT]):
    """按顺序执行的规则管线"""

    rules: List[ValidationRule[IssueT]]

    def run(self, ctx: ValidationContext) -> List[IssueT]:
        all_issues: List[IssueT] = []
        for rule in self.rules:
            if _profiling_enabled:
                start = perf_counter()
                issues = rule.apply(ctx)
                elapsed = perf_counter() - start
                rule_id = getattr(rule, "rule_id", rule.__class__.__name__)
                previous_time = _profiling_time_by_rule.get(rule_id, 0.0)
                previous_calls = _profiling_calls_by_rule.get(rule_id, 0)
                _profiling_time_by_rule[rule_id] = previous_time + elapsed
                _profiling_calls_by_rule[rule_id] = previous_calls + 1
            else:
                issues = rule.apply(ctx)
            all_issues.extend(issues)
        return all_issues


# 兼容别名：在大多数引擎内部用例中仍然以 EngineIssue 作为问题类型
EngineValidationRule = ValidationRule[EngineIssue]
EngineValidationPipeline = ValidationPipeline[EngineIssue]
