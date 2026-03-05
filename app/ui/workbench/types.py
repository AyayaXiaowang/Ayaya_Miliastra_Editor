from __future__ import annotations
"""
内置 UI Workbench（Web 工作台）导入结果数据结构。

注意：实现已下沉到 `app.runtime.services.ui_workbench.types`，
本模块仅作为稳定导入路径的薄封装。
"""

from app.runtime.services.ui_workbench.types import ImportBundleResult, ImportResult


__all__ = [
    "ImportBundleResult",
    "ImportResult",
]

