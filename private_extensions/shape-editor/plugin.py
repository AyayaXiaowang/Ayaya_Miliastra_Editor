from __future__ import annotations

"""
内置扩展：拼贴画（shape-editor）插件接入（入口文件；随仓库分发）

目标：
- 在主程序左侧导航栏底部注入“拼贴画”入口按钮；
- 点击后打开本地静态服务中的 shape-editor 页面；
- 提供后端 API，用于将画布导出为“装饰物组挂空实体”的 .gia。

约束：
- 扩展会在 QApplication 创建前被 import，因此模块顶层禁止导入 PyQt6。
- 不使用 try/except 吞错：失败直接抛出，便于暴露问题。
"""

import sys
from pathlib import Path

from app.common.private_extension_registry import register_main_window_hook


def _ensure_backend_importable() -> None:
    plugin_dir = Path(__file__).resolve().parent
    # 允许扩展之间复用代码：`private_extensions/ugc_file_tools` 等目录
    # 以顶层包名 `ugc_file_tools` 被导入（无需写 `private_extensions.ugc_file_tools`）。
    private_ext_root = plugin_dir.parent
    plugin_dir_text = str(plugin_dir)
    if plugin_dir_text not in sys.path:
        sys.path.insert(0, plugin_dir_text)
    private_ext_root_text = str(private_ext_root)
    if private_ext_root_text not in sys.path:
        sys.path.insert(0, private_ext_root_text)


_ensure_backend_importable()

from shape_editor_backend.bridge import _ShapeEditorBridge  # noqa: E402

__all__ = [
    "install",
    "_BRIDGE",
    "_ShapeEditorBridge",
]


_BRIDGE: "_ShapeEditorBridge | None" = None


def install(workspace_root: Path) -> None:
    # 插件安装期无需执行任何 Qt 逻辑；真正注入在主窗口创建后执行。
    @register_main_window_hook
    def _on_main_window_created(main_window: object) -> None:
        global _BRIDGE
        if _BRIDGE is None:
            _BRIDGE = _ShapeEditorBridge(
                workspace_root=workspace_root,
                tool_dir=Path(__file__).resolve().parent,
            )
        _BRIDGE.attach_main_window(main_window)
        _BRIDGE.install_entrypoints()

