"""
启动装配（bootstrap）子包。

该包用于承载 UI/CLI 启动阶段的“装配管线”，例如：
- workspace_root 推导与注入后的二次装配
- OCR 预热与 PyQt6 导入顺序约束
- 启动诊断、看门狗、异常钩子等“启动期基础设施”

注意：本包不提供稳定的库级 API；仅供 `app.cli.*` 等入口调用。
"""

from __future__ import annotations

__all__ = []


