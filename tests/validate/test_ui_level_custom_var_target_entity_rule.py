from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from engine.validate.api import validate_files
from tests._helpers.project_paths import get_repo_root


def _workspace_root() -> Path:
    return get_repo_root()


_TMP_PACKAGE_IDS = (
    "__tmp_validate_ui_lv_custom_var_target__",
    "__tmp_validate_ui_lv_custom_var_target_ok__",
)


@pytest.fixture(autouse=True)
def _cleanup_tmp_packages() -> None:
    workspace = _workspace_root()
    packages_root = workspace / "assets" / "资源库" / "项目存档"
    for package_id in _TMP_PACKAGE_IDS:
        target = (packages_root / package_id).resolve()
        if target.exists():
            shutil.rmtree(target)
    yield
    for package_id in _TMP_PACKAGE_IDS:
        target = (packages_root / package_id).resolve()
        if target.exists():
            shutil.rmtree(target)


def test_lv_ui_custom_var_must_not_write_to_owner_entity(tmp_path: Path) -> None:
    """回归：UI源码使用 lv/ls 作用域时，ui_* 自定义变量写到 self.owner_entity 需显式声明归属。"""
    workspace = _workspace_root()
    package_root = workspace / "assets" / "资源库" / "项目存档" / "__tmp_validate_ui_lv_custom_var_target__"
    ui_source_dir = package_root / "管理配置" / "UI源码"
    ui_source_dir.mkdir(parents=True, exist_ok=True)
    (ui_source_dir / "test.html").write_text(
        '<div class="x">{1:lv.ui_test_var.some_key}</div>\n',
        encoding="utf-8",
    )

    graph_dir = package_root / "节点图" / "server" / "实体节点图"
    graph_dir.mkdir(parents=True, exist_ok=True)
    graph_path = graph_dir / "temp_ui_lv_custom_var_target_error.py"
    graph_path.write_text(
        '''
"""
graph_id: test_ui_lv_custom_var_target_error
graph_name: UI关卡变量写错目标实体_应报错
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class UI关卡变量写错目标实体_应报错:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_界面控件组触发时(self, 事件源实体, 事件源GUID, 界面控件组组合索引, 界面控件组索引):
        # 错误：lv/ui_* 变量不应写到 self.owner_entity（除非声明 mount_entity_type: 关卡）
        v: "字符串-字符串字典" = 获取自定义变量(self.game, 目标实体=self.owner_entity, 变量名="ui_test_var")
        设置自定义变量(self.game, 目标实体=self.owner_entity, 变量名="ui_test_var", 变量值=v, 是否触发事件=False)
''',
        encoding="utf-8",
    )

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    assert any(i.code == "CODE_UI_LEVEL_CUSTOM_VAR_TARGET_ENTITY_REQUIRED" for i in report.issues), (
        "应报 CODE_UI_LEVEL_CUSTOM_VAR_TARGET_ENTITY_REQUIRED，实际："
        + repr([(i.code, i.message) for i in report.issues])
    )


def test_lv_ui_custom_var_ok_when_mount_entity_type_is_level(tmp_path: Path) -> None:
    """允许：作者显式声明挂载在关卡实体上，则 self.owner_entity 作为关卡实体合法。"""
    workspace = _workspace_root()
    package_root = workspace / "assets" / "资源库" / "项目存档" / "__tmp_validate_ui_lv_custom_var_target_ok__"
    ui_source_dir = package_root / "管理配置" / "UI源码"
    ui_source_dir.mkdir(parents=True, exist_ok=True)
    (ui_source_dir / "test.html").write_text(
        '<div class="x">{1:lv.ui_test_var.some_key}</div>\n',
        encoding="utf-8",
    )

    graph_dir = package_root / "节点图" / "server" / "实体节点图"
    graph_dir.mkdir(parents=True, exist_ok=True)
    graph_path = graph_dir / "temp_ui_lv_custom_var_target_ok.py"
    graph_path.write_text(
        '''
"""
graph_id: test_ui_lv_custom_var_target_ok
graph_name: UI关卡变量_挂载关卡实体_允许owner_entity
graph_type: server
mount_entity_type: 关卡
"""

from __future__ import annotations

from _prelude import *


class UI关卡变量_挂载关卡实体_允许owner_entity:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_界面控件组触发时(self, 事件源实体, 事件源GUID, 界面控件组组合索引, 界面控件组索引):
        v: "字符串-字符串字典" = 获取自定义变量(self.game, 目标实体=self.owner_entity, 变量名="ui_test_var")
        设置自定义变量(self.game, 目标实体=self.owner_entity, 变量名="ui_test_var", 变量值=v, 是否触发事件=False)
''',
        encoding="utf-8",
    )

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    unexpected = [i for i in report.issues if i.code == "CODE_UI_LEVEL_CUSTOM_VAR_TARGET_ENTITY_REQUIRED"]
    assert not unexpected, f"显式声明 mount_entity_type: 关卡 时不应报错，实际：{[(i.code, i.message) for i in unexpected]}"


def test_ps_ui_custom_var_must_declare_owner_entity_kind(tmp_path: Path) -> None:
    """回归：UI源码使用 ps/p1.. 作用域时，ui_* 自定义变量写到 self.owner_entity 需显式声明归属。"""
    workspace = _workspace_root()
    package_root = workspace / "assets" / "资源库" / "项目存档" / "__tmp_validate_ui_lv_custom_var_target__"
    ui_source_dir = package_root / "管理配置" / "UI源码"
    ui_source_dir.mkdir(parents=True, exist_ok=True)
    (ui_source_dir / "test.html").write_text(
        "<div>{{ps.ui_test_var}}</div>\n",
        encoding="utf-8",
    )

    graph_dir = package_root / "节点图" / "server" / "实体节点图"
    graph_dir.mkdir(parents=True, exist_ok=True)
    graph_path = graph_dir / "temp_ui_ps_custom_var_target_error.py"
    graph_path.write_text(
        '''
"""
graph_id: test_ui_ps_custom_var_target_error
graph_name: UI玩家变量写到owner_entity但未声明_应报错
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class UI玩家变量写到owner_entity但未声明_应报错:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_界面控件组触发时(self, 事件源实体, 事件源GUID, 界面控件组组合索引, 界面控件组索引):
        v: "字符串" = 获取自定义变量(self.game, 目标实体=self.owner_entity, 变量名="ui_test_var")
        设置自定义变量(self.game, 目标实体=self.owner_entity, 变量名="ui_test_var", 变量值=v, 是否触发事件=False)
''',
        encoding="utf-8",
    )

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    assert any(i.code == "CODE_UI_LEVEL_CUSTOM_VAR_TARGET_ENTITY_REQUIRED" for i in report.issues), (
        "应报 CODE_UI_LEVEL_CUSTOM_VAR_TARGET_ENTITY_REQUIRED，实际："
        + repr([(i.code, i.message) for i in report.issues])
    )


def test_ps_ui_custom_var_ok_when_mount_entity_type_is_player(tmp_path: Path) -> None:
    """允许：作者显式声明挂载在玩家实体上，则 self.owner_entity 作为玩家实体合法。"""
    workspace = _workspace_root()
    package_root = workspace / "assets" / "资源库" / "项目存档" / "__tmp_validate_ui_lv_custom_var_target_ok__"
    ui_source_dir = package_root / "管理配置" / "UI源码"
    ui_source_dir.mkdir(parents=True, exist_ok=True)
    (ui_source_dir / "test.html").write_text(
        "<div>{{ps.ui_test_var}}</div>\n",
        encoding="utf-8",
    )

    graph_dir = package_root / "节点图" / "server" / "实体节点图"
    graph_dir.mkdir(parents=True, exist_ok=True)
    graph_path = graph_dir / "temp_ui_ps_custom_var_target_ok.py"
    graph_path.write_text(
        '''
"""
graph_id: test_ui_ps_custom_var_target_ok
graph_name: UI玩家变量_挂载玩家实体_允许owner_entity
graph_type: server
mount_entity_type: 玩家
"""

from __future__ import annotations

from _prelude import *


class UI玩家变量_挂载玩家实体_允许owner_entity:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_界面控件组触发时(self, 事件源实体, 事件源GUID, 界面控件组组合索引, 界面控件组索引):
        v: "字符串" = 获取自定义变量(self.game, 目标实体=self.owner_entity, 变量名="ui_test_var")
        设置自定义变量(self.game, 目标实体=self.owner_entity, 变量名="ui_test_var", 变量值=v, 是否触发事件=False)
''',
        encoding="utf-8",
    )

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    unexpected = [i for i in report.issues if i.code == "CODE_UI_LEVEL_CUSTOM_VAR_TARGET_ENTITY_REQUIRED"]
    assert not unexpected, f"显式声明 mount_entity_type: 玩家 时不应报错，实际：{[(i.code, i.message) for i in unexpected]}"

