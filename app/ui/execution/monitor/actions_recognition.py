# -*- coding: utf-8 -*-
"""
识别测试动作（兼容导入入口）。

权威实现位于：`app.ui.execution.monitor.recognition_actions.actions_recognition`。
本模块仅保留旧导入路径，供 `ExecutionMonitorPanel` 等调用方保持稳定引用。
"""

from .recognition_actions import RecognitionActions

__all__ = ["RecognitionActions"]



