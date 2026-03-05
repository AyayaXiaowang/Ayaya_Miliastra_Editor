from __future__ import annotations

"""内置 UI Workbench（Web 工作台）薄门面。

对外保持稳定导入路径：
    from app.ui.ui_workbench_bridge import UiWorkbenchBridge

具体实现位于：
    app.ui.workbench.bridge
"""

from app.ui.workbench.bridge import UiWorkbenchBridge

__all__ = [
    "UiWorkbenchBridge",
]

