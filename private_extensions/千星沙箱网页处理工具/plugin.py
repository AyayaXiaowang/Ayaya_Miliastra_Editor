from __future__ import annotations

"""
私有扩展：千星沙箱网页处理工具（UI 工作台）插件化接入（入口文件）

约束：
- 私有扩展会在 QApplication 创建前被 import，因此模块顶层禁止导入 PyQt6。
- 不使用 try/except 吞错：失败直接抛出，便于暴露问题。

说明：
- 由于私有扩展加载器会按“文件路径”执行本文件（而不是把本目录当作 package 导入），
  因此后端实现拆分到同目录下的独立包 `ui_workbench_backend/`，并在这里做 sys.path 注入后再 import。
"""

import sys
from pathlib import Path

from app.common.private_extension_registry import (
    register_main_window_hook,
    register_ui_tools_plugin_enabled,
)


def _ensure_backend_importable() -> None:
    """
    让插件可在多种加载方式下稳定 import：
    - 插件目录：import `ui_workbench_backend`
    - private_extensions 根：import `ugc_file_tools`
    - workspace 根：import `app` / `engine`
    """
    plugin_dir = Path(__file__).resolve().parent
    private_extensions_root = plugin_dir.parent
    workspace_root = private_extensions_root.parent

    # 插入顺序：先插 plugin_dir，再插 private_extensions_root，再插 workspace_root，
    # 使得 workspace_root 最终位于 sys.path[0]（优先解析主程序代码，如 engine/app）。
    for import_root in (plugin_dir, private_extensions_root, workspace_root):
        root_text = str(import_root)
        if root_text not in sys.path:
            sys.path.insert(0, root_text)


_ensure_backend_importable()

from ui_workbench_backend.bridge import _UiWorkbenchBridge  # noqa: E402
from ui_workbench_backend.bridge_base import (  # noqa: E402
    _ExportGiaResult,
    _ExportGilResult,
    _ImportBundleResult,
    _ImportResult,
)

__all__ = [
    "install",
    "_BRIDGE",
    "_UiWorkbenchBridge",
    "_ImportResult",
    "_ImportBundleResult",
    "_ExportGilResult",
    "_ExportGiaResult",
]


_BRIDGE: "_UiWorkbenchBridge | None" = None


def install(workspace_root: Path) -> None:
    # 标记：UI Web 工具插件已启用（用于 UI 侧门禁；与自动转换器注册解耦）。
    register_ui_tools_plugin_enabled()

    # 仅注册 hook：实际 Qt 注入与服务启动在主窗口创建后执行
    @register_main_window_hook
    def _on_main_window_created(main_window: object) -> None:
        global _BRIDGE
        if _BRIDGE is None:
            _BRIDGE = _UiWorkbenchBridge(
                workspace_root=workspace_root,
                workbench_dir=Path(__file__).resolve().parent,
            )
        _BRIDGE.attach_main_window(main_window)
        _BRIDGE.install_entrypoints()

