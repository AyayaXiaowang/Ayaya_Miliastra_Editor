from __future__ import annotations

from pathlib import Path


def test_ui_workbench_bridge_can_start_http_server_without_notimplemented() -> None:
    """回归：内置 UiWorkbenchBridge 能启动静态服务器（不依赖私有扩展）。"""
    from tests._helpers.project_paths import get_repo_root

    repo_root = get_repo_root()
    from app.ui.ui_workbench_bridge import UiWorkbenchBridge

    workbench_dir = (Path(repo_root) / "assets" / "ui_workbench").resolve()
    assert workbench_dir.is_dir(), f"missing assets/ui_workbench: {workbench_dir}"

    bridge = UiWorkbenchBridge(workspace_root=Path(repo_root), workbench_dir=workbench_dir)
    bridge.ensure_server_running()
    server = bridge._server
    assert server is not None
    assert int(getattr(server, "port", 0) or 0) > 0
    httpd = getattr(server, "_httpd", None)
    assert httpd is not None
    httpd.shutdown()

