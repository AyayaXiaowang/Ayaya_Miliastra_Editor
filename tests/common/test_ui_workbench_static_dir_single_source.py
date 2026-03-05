from __future__ import annotations

import importlib
from pathlib import Path

from tests._helpers.project_paths import get_repo_root


def test_ui_workbench_static_dir_is_assets_ui_workbench() -> None:
    repo_root = get_repo_root()
    assert isinstance(repo_root, Path)

    assets_workbench_dir = (repo_root / "assets" / "ui_workbench").resolve()
    assert assets_workbench_dir.is_dir()
    assert (assets_workbench_dir / "ui_app_ui_preview.html").is_file()

    plugin_dir = (repo_root / "private_extensions" / "千星沙箱网页处理工具").resolve()
    assert plugin_dir.is_dir()

    plugin_mod = importlib.import_module("private_extensions.千星沙箱网页处理工具.plugin")
    Bridge = getattr(plugin_mod, "_UiWorkbenchBridge")

    bridge = Bridge(workspace_root=repo_root, workbench_dir=plugin_dir)
    assert bridge.get_workbench_static_dir() == assets_workbench_dir
    assert bridge.get_workbench_backend_dir() == plugin_dir

