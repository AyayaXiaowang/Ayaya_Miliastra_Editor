# -*- coding: utf-8 -*-
"""
执行策略类：执行相关的各类策略与辅助工具。

模块职责分离：
    - anchor_selector: 锚点选择策略
    - step_summary_builder: 步骤摘要文案生成
    - execution_coordinator: 执行前协调（校准、快速映射、单步验证）
    - step_skip_checker: 步骤跳过检查
    - retry_handler: 失败重试处理
"""

from .anchor_selector import AnchorSelector, AnchorInfo
from .step_summary_builder import StepSummaryBuilder
from .execution_coordinator import ExecutionCoordinator, CalibrationResult
from .step_skip_checker import StepSkipChecker, SkipDecision
from .retry_handler import RetryHandler, RetryResult

__all__ = [
    "AnchorSelector",
    "AnchorInfo",
    "StepSummaryBuilder",
    "ExecutionCoordinator",
    "CalibrationResult",
    "StepSkipChecker",
    "SkipDecision",
    "RetryHandler",
    "RetryResult",
]

