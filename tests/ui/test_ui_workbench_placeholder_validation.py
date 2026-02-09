from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _load_ui_workbench_plugin_module(repo_root: Path):
    plugin_path = repo_root / "private_extensions" / "千星沙箱网页处理工具" / "plugin.py"
    if not plugin_path.is_file():
        pytest.skip("千星沙箱网页处理工具 私有扩展不在当前工作区中，跳过占位符校验用例。")

    spec = importlib.util.spec_from_file_location("ui_workbench_plugin", plugin_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # 重要：dataclasses + from __future__ import annotations 会在处理字符串注解时查询 sys.modules。
    # 若不提前注册，`cls.__module__` 对应的条目不存在，会导致 dataclasses 内部崩溃。
    sys.modules[str(spec.name)] = module
    spec.loader.exec_module(module)
    return module, plugin_path


def test_ui_workbench_placeholder_validation_scopes_and_ingame_save_forbidden() -> None:
    """回归：Workbench 导入/导出前的 UI 文本占位符必须可解析且来源合法。

    覆盖：
    - `ps.`：仅允许玩家模板 metadata.custom_variable_file；禁止局内存档变量
    - `lv.`：允许包内关卡变量文件（PackageIndex.resources.management.level_variables）与共享变量文件
    - 无前缀 `{{变量名}}`：若同时命中 lv + ps 则要求显式前缀
    """

    from tests._helpers.project_paths import get_repo_root

    repo_root = get_repo_root()
    module, plugin_path = _load_ui_workbench_plugin_module(repo_root)

    Bridge = getattr(module, "_UiWorkbenchBridge")

    from engine.resources.resource_manager import ResourceManager
    from engine.resources.package_index_manager import PackageIndexManager
    from engine.resources.level_variable_schema_view import get_default_level_variable_schema_view

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

    schema_view = get_default_level_variable_schema_view()
    schema_view.set_active_package_id(package_id)

    # 玩家模板（普通自定义变量文件）
    player_custom_file_id = "sample_custom_variables_all_types__测试基础内容"
    player_custom_vars = schema_view.get_variables_by_file_id(player_custom_file_id)
    assert player_custom_vars
    player_custom_name = str(player_custom_vars[0].get("variable_name") or "").strip()
    assert player_custom_name

    # 局内存档变量文件（UI 禁止）
    ingame_save_file_id = "sample_ingame_save_variables_all_types__测试基础内容"
    ingame_save_vars = schema_view.get_variables_by_file_id(ingame_save_file_id)
    assert ingame_save_vars
    ingame_save_name = str(ingame_save_vars[0].get("variable_name") or "").strip()
    assert ingame_save_name

    # 关卡进度变量文件（仅 lv，玩家模板未引用）
    progress_file_id = "sample_level_progress_variables__测试基础内容"
    progress_vars = schema_view.get_variables_by_file_id(progress_file_id)
    assert progress_vars
    progress_name = str(progress_vars[0].get("variable_name") or "").strip()
    assert progress_name

    # ps + 普通自定义变量：允许
    ok, error = bridge.try_validate_text_placeholders_in_ui_payload({"text": f"X{{{{ps.{player_custom_name}}}}}Y"})
    assert ok is True
    assert error == ""

    # ps + 局内存档变量：禁止
    ok, error = bridge.try_validate_text_placeholders_in_ui_payload({"text": f"X{{{{ps.{ingame_save_name}}}}}Y"})
    assert ok is False
    assert "局内存档" in error

    # lv + 包内关卡变量：允许
    ok, error = bridge.try_validate_text_placeholders_in_ui_payload({"text": f"X{{{{lv.{progress_name}}}}}Y"})
    assert ok is True
    assert error == ""

    # 无前缀：若变量同时可解析为 lv + ps，则要求显式前缀
    ok, error = bridge.try_validate_text_placeholders_in_ui_payload({"text": f"X{{{{{player_custom_name}}}}}Y"})
    assert ok is False
    assert "来源不明确" in error or "请显式写成" in error


