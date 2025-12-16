from __future__ import annotations

import sys
from pathlib import Path


def get_workspace_root() -> Path:
    """
    返回仓库根目录（与 README.md 同级）。

    - tools/_bootstrap.py 位于 <workspace>/tools/_bootstrap.py
    - workspace root 为 tools 目录的父目录
    """
    tools_dir = Path(__file__).resolve().parent
    workspace_root = tools_dir.parent
    return workspace_root


def ensure_workspace_root_on_sys_path() -> Path:
    """
    确保 workspace root 在 sys.path 中（用于 `python tools/<script>.py` 直接执行脚本的场景）。

    注意：不注入 `app/` 到 sys.path；UI 统一通过 `app.ui.*` 导入。
    """
    workspace_root = get_workspace_root()
    workspace_root_text = str(workspace_root)
    if workspace_root_text not in sys.path:
        sys.path.insert(0, workspace_root_text)
    return workspace_root


