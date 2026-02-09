from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _load_ui_workbench_plugin_module(repo_root: Path):
    plugin_path = repo_root / "private_extensions" / "千星沙箱网页处理工具" / "plugin.py"
    if not plugin_path.is_file():
        pytest.skip("千星沙箱网页处理工具 私有扩展不在当前工作区中，跳过变量清单用例。")

    spec = importlib.util.spec_from_file_location("ui_workbench_plugin", plugin_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[str(spec.name)] = module
    spec.loader.exec_module(module)
    return module, plugin_path


def test_ui_workbench_variable_catalog_payload_smoke() -> None:
    """回归：Workbench 变量浏览器能给出当前项目可用的 lv/ps 变量清单（含解析链路信息）。"""

    from tests._helpers.project_paths import get_repo_root

    repo_root = get_repo_root()
    module, plugin_path = _load_ui_workbench_plugin_module(repo_root)

    Bridge = getattr(module, "_UiWorkbenchBridge")

    from engine.resources.package_index_manager import PackageIndexManager
    from engine.resources.resource_manager import ResourceManager

    workspace_root = repo_root
    package_id = "测试基础内容"

    resource_manager = ResourceManager(workspace_root)
    resource_manager.rebuild_index(active_package_id=package_id)
    package_index_manager = PackageIndexManager(workspace_root, resource_manager)
    package_index = package_index_manager.load_package_index(package_id)
    assert package_index is not None

    class _DummyPackageController:
        def __init__(self) -> None:
            self.current_package_id = package_id
            self.current_package_index = package_index
            self.resource_manager = resource_manager
            self.package_index_manager = package_index_manager

    class _DummyMainWindow:
        def __init__(self) -> None:
            self.package_controller = _DummyPackageController()

    bridge = Bridge(workspace_root=workspace_root, workbench_dir=plugin_path.parent)
    bridge.attach_main_window(_DummyMainWindow())

    payload = bridge.get_variable_catalog_payload()
    assert payload["ok"] is True
    assert payload["current_package_id"] == package_id

    lv = payload["lv"]
    ps = payload["ps"]
    assert isinstance(lv, list) and isinstance(ps, list)
    assert len(lv) > 0
    assert len(ps) > 0

    chain = payload["debug_chain"]
    assert isinstance(chain, dict)
    assert "player_template_ids" in chain
    assert "referenced_level_variable_file_ids" in chain

