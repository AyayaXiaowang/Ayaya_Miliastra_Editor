from __future__ import annotations

import sys
from pathlib import Path

from app.common.private_extension_registry import register_main_window_hook


def _ensure_ugc_file_tools_importable() -> None:
    """
    私有扩展按文件路径加载，不会自动把 `private_extensions/` 加到 sys.path。
    为了能 `import ugc_file_tools.*`，这里显式注入其父目录（private_extensions）。
    """
    private_extensions_root = Path(__file__).resolve().parent.parent
    root_text = str(private_extensions_root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)


def install(workspace_root: Path) -> None:
    _ = workspace_root
    _ensure_ugc_file_tools_importable()


@register_main_window_hook
def _install_ugc_file_tools_buttons(main_window: object) -> None:
    _ensure_ugc_file_tools_importable()

    from ugc_file_tools.ui_integration.package_toolbar import install_ugc_file_tools_buttons

    install_ugc_file_tools_buttons(main_window)


