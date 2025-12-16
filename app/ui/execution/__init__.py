# -*- coding: utf-8 -*-
"""
执行子系统：统一管理所有执行相关的模块。

目录结构：
    - runner.py: 执行驱动器（主入口）
    - thread.py: 执行线程
    - planner.py: 执行计划器
    - guides.py: 执行指引
    - strategies/: 策略类子模块（锚点选择、跳过检查、重试等）
    - monitor/: 执行监控面板子模块

推荐导入方式：
    from app.ui.execution import ExecutionRunner, ExecutionPlanner
    from app.ui.execution.strategies import AnchorSelector, RetryHandler
    from app.ui.execution.monitor import ExecutionMonitorPanel
"""

# 主要执行类
from .runner import ExecutionRunner
from .thread import ExecutionThread
from .planner import ExecutionPlanner
from .guides import ExecutionGuides

# 策略类（为兼容性重新导出）
from .strategies import (
    AnchorSelector,
    AnchorInfo,
    StepSummaryBuilder,
    ExecutionCoordinator,
    CalibrationResult,
    StepSkipChecker,
    SkipDecision,
    RetryHandler,
    RetryResult,
)

# 监控面板（为兼容性重新导出）
from .monitor.panel import ExecutionMonitorPanel

__all__ = [
    # 主要执行类
    "ExecutionRunner",
    "ExecutionThread",
    "ExecutionPlanner",
    "ExecutionGuides",
    # 策略类
    "AnchorSelector",
    "AnchorInfo",
    "StepSummaryBuilder",
    "ExecutionCoordinator",
    "CalibrationResult",
    "StepSkipChecker",
    "SkipDecision",
    "RetryHandler",
    "RetryResult",
    # 监控面板
    "ExecutionMonitorPanel",
]

