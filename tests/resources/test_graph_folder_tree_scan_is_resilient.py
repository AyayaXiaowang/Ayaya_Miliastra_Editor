from __future__ import annotations

from pathlib import Path

import pytest

from engine.resources.resource_manager import ResourceManager


def test_get_all_graph_folders_does_not_depend_on_path_rglob_after_init(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """回归测试：

    - ResourceManager 在初始化阶段仍会使用 rglob 扫描节点图文件；
    - 但 get_all_graph_folders 的“空文件夹扫描”不应依赖 Path.rglob，
      否则在 Windows 的异常目录项场景下可能抛错并导致 UI 文件夹树被清空。
    """

    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir(parents=True, exist_ok=True)

    # 手工创建资源目录结构（与 ResourceManager 内部约定对齐）
    server_dir = workspace_path / "assets" / "资源库" / "共享" / "节点图" / "server"
    client_dir = workspace_path / "assets" / "资源库" / "共享" / "节点图" / "client"
    (server_dir / "示例A").mkdir(parents=True, exist_ok=True)
    (server_dir / "示例A" / "子目录").mkdir(parents=True, exist_ok=True)
    (client_dir / "示例B").mkdir(parents=True, exist_ok=True)

    # 初始化：允许 ResourceManager 内部使用 rglob（索引构建需要）
    resource_manager = ResourceManager(workspace_path)

    # 初始化完成后：强制要求 get_all_graph_folders 不再调用 Path.rglob
    original_rglob = Path.rglob

    def _rglob_should_not_be_called(self: Path, pattern: str):  # type: ignore[no-untyped-def]
        raise AssertionError(f"Path.rglob() should not be called by get_all_graph_folders (pattern={pattern})")

    monkeypatch.setattr(Path, "rglob", _rglob_should_not_be_called)

    folders = resource_manager.get_all_graph_folders()

    # 还原，避免影响其它测试（monkeypatch fixture 也会自动回滚，这里显式更清晰）
    monkeypatch.setattr(Path, "rglob", original_rglob)

    assert "server" in folders
    assert "client" in folders
    assert "示例A" in folders["server"]
    assert "示例A/子目录" in folders["server"]
    assert "示例B" in folders["client"]


