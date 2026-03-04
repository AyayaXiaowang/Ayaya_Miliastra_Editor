from __future__ import annotations

import shutil
from pathlib import Path

from engine.validate.api import validate_files
from tests._helpers.project_paths import get_repo_root

import pytest


def _workspace_root() -> Path:
    return get_repo_root()

_TMP_PACKAGE_IDS = (
    "__tmp_validate_ui_registry__",
    "__tmp_validate_ui_registry_missing_key__",
    "__tmp_validate_ui_registry_missing_registry__",
)


@pytest.fixture(autouse=True)
def _cleanup_tmp_validate_ui_registry_packages() -> None:
    """防污染护栏：测试创建的临时项目存档目录必须在用前/用后清理干净。"""
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


def _make_temp_graph_code(tmp_dir: Path, code: str) -> Path:
    target = tmp_dir / "temp_guid_ui_key_placeholder_graph.py"
    target.write_text(code, encoding="utf-8")
    return target


def test_guid_ui_key_placeholder_is_allowed_in_graph_code_validation(tmp_path: Path) -> None:
    """工程化：允许 GUID 端口使用 ui_key 占位符，避免作者手填 GUID。"""
    graph_code = '''
"""
graph_id: test_guid_ui_key_placeholder
graph_name: GUID ui_key 占位符校验
graph_type: server
"""

from __future__ import annotations

from _prelude import *

GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="配置_UI测试控件索引",
        variable_type="整数",
        default_value="ui_key:HUD_HP_BAR",
        description="工程化：整数类型节点图变量允许用 ui_key 占位符，写回阶段替换为真实索引。",
    ),
]

class GUID_UIKey_占位符校验:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        # 变量注解为 GUID：允许占位符（写回阶段解析为真实 GUID）
        某控件: "GUID" = "ui_key:HUD_HP_BAR"

        # 节点入参期望 GUID：允许占位符
        创建实体(
            self.game,
            目标GUID="ui:HUD_HP_BAR",
            单位标签索引列表=[],
        )

        # 节点入参期望 整数：允许占位符（写回阶段解析为真实整数 ID）
        获取随机整数(
            self.game,
            下限="ui:HUD_HP_BAR",
            上限=10,
        )
'''
    workspace = _workspace_root()
    graph_path = _make_temp_graph_code(tmp_path, graph_code)
    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)

    unexpected = [
        issue
        for issue in report.issues
        if issue.code
        in {
            "CODE_ID_LITERAL_DIGITS_1_TO_10_REQUIRED",
            "PORT_TYPE_MISMATCH",
        }
    ]
    assert not unexpected, f"不应因 ui_key 占位符触发 ID/类型报错，实际：{[i.code for i in unexpected]}"


def test_writeback_can_resolve_ui_key_guid_placeholder(monkeypatch) -> None:
    """写回侧：GUID 端口常量应可解析 ui_key 占位符为真实 guid。"""
    repo_root = _workspace_root()
    private_extensions_root = repo_root / "private_extensions"
    monkeypatch.syspath_prepend(str(private_extensions_root))

    from ugc_file_tools.node_graph_semantics.var_base import (
        coerce_constant_value_for_port_type,
        coerce_constant_value_for_var_type,
        set_ui_key_guid_registry,
    )

    set_ui_key_guid_registry({"HUD_HP_BAR": 1234567890})
    assert coerce_constant_value_for_port_type(port_type="GUID", raw_value="ui:HUD_HP_BAR") == 1234567890
    assert coerce_constant_value_for_port_type(port_type="GUID", raw_value="ui_key:HUD_HP_BAR") == 1234567890
    # 工程化：UI 控件索引（整数）也允许用 ui_key 占位符（写回阶段替换为真实整数 ID）
    assert coerce_constant_value_for_port_type(port_type="整数", raw_value="ui:HUD_HP_BAR") == 1234567890
    assert coerce_constant_value_for_port_type(port_type="整数", raw_value="ui_key:HUD_HP_BAR") == 1234567890
    # 工程化：GraphVariables(default_value, VarType=整数=3) 同样允许 ui_key 占位符
    assert coerce_constant_value_for_var_type(var_type_int=3, raw_value="ui:HUD_HP_BAR") == 1234567890
    set_ui_key_guid_registry(None)


def test_ui_key_placeholder_must_exist_in_ui_html_for_project_graph(tmp_path: Path) -> None:
    """工程化：当节点图位于资源库项目存档下时，占位符 key 必须存在于 UI源码(HTML) 的 data-ui-key 中。"""
    workspace = _workspace_root()
    package_root = workspace / "assets" / "资源库" / "项目存档" / "__tmp_validate_ui_registry__"
    ui_source_dir = package_root / "管理配置" / "UI源码"
    ui_source_dir.mkdir(parents=True, exist_ok=True)
    (ui_source_dir / "test.html").write_text(
        '<div data-ui-key="HUD_HP_BAR"></div>\n',
        encoding="utf-8",
    )

    graph_dir = package_root / "节点图" / "server" / "实体节点图"
    graph_dir.mkdir(parents=True, exist_ok=True)
    graph_path = graph_dir / "temp_ui_key_registry_exists_check.py"
    graph_path.write_text(
        '''
"""
graph_id: test_ui_key_registry_exists_check
graph_name: UIKey registry exists check
graph_type: server
"""

from __future__ import annotations

from _prelude import *

GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="配置_UI索引_单值",
        variable_type="整数",
        default_value="ui_key:HUD_HP_BAR",
    ),
    GraphVariableConfig(
        name="配置_UI索引_列表",
        variable_type="整数列表",
        default_value=["ui:HUD_HP_BAR", 1, "2"],
    ),
    GraphVariableConfig(
        name="配置_UI控件_GUID列表",
        variable_type="GUID列表",
        default_value=["ui_key:HUD_HP_BAR"],
    ),
]

class UIKeyRegistry_Exists_Check:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        # 整数端口允许占位符（需命中 registry）
        获取随机整数(
            self.game,
            下限="ui:HUD_HP_BAR",
            上限=10,
        )
''',
        encoding="utf-8",
    )

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    unexpected = [i for i in report.issues if i.code in {"CODE_UI_HTML_SOURCES_NOT_FOUND", "CODE_UI_KEY_NOT_FOUND_IN_UI_HTML"}]
    assert not unexpected, f"占位符已在 UI源码(HTML) 中声明，不应报错，实际：{[(i.code, i.message) for i in unexpected]}"


def test_ui_key_placeholder_missing_key_should_error(tmp_path: Path) -> None:
    """工程化：节点图位于项目存档下时，UI源码(HTML) 存在但缺 key 应报错。"""
    workspace = _workspace_root()
    package_root = workspace / "assets" / "资源库" / "项目存档" / "__tmp_validate_ui_registry_missing_key__"
    ui_source_dir = package_root / "管理配置" / "UI源码"
    ui_source_dir.mkdir(parents=True, exist_ok=True)
    (ui_source_dir / "test.html").write_text(
        '<div data-ui-key="SOME_OTHER_KEY"></div>\n',
        encoding="utf-8",
    )

    graph_dir = package_root / "节点图" / "server" / "实体节点图"
    graph_dir.mkdir(parents=True, exist_ok=True)
    graph_path = graph_dir / "temp_ui_key_registry_missing_key.py"
    graph_path.write_text(
        '''
"""
graph_id: test_ui_key_registry_missing_key
graph_name: UIKey registry missing key
graph_type: server
"""

from __future__ import annotations

from _prelude import *

GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="配置_UI索引_单值",
        variable_type="整数",
        default_value="ui_key:HUD_HP_BAR",
    ),
]

class UIKeyRegistry_Missing_Key:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        获取随机整数(
            self.game,
            下限="ui:HUD_HP_BAR",
            上限=10,
        )
''',
        encoding="utf-8",
    )

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    assert any(i.code == "CODE_UI_KEY_NOT_FOUND_IN_UI_HTML" for i in report.issues), (
        "UI源码(HTML) 缺 key 时应报 CODE_UI_KEY_NOT_FOUND_IN_UI_HTML，实际："
        + repr([(i.code, i.message) for i in report.issues])
    )


def test_ui_key_placeholder_missing_ui_html_should_error(tmp_path: Path) -> None:
    """工程化：节点图位于项目存档下时，UI源码(HTML) 缺失应报错（无法校验存在性）。"""
    workspace = _workspace_root()
    package_root = workspace / "assets" / "资源库" / "项目存档" / "__tmp_validate_ui_registry_missing_registry__"
    graph_dir = package_root / "节点图" / "server" / "实体节点图"
    graph_dir.mkdir(parents=True, exist_ok=True)
    graph_path = graph_dir / "temp_ui_key_registry_missing_registry.py"
    graph_path.write_text(
        '''
"""
graph_id: test_ui_key_registry_missing_registry
graph_name: UIKey registry missing registry
graph_type: server
"""

from __future__ import annotations

from _prelude import *

GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="配置_UI索引_单值",
        variable_type="整数",
        default_value="ui_key:HUD_HP_BAR",
    ),
]

class UIKeyRegistry_Missing_Registry:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        获取随机整数(
            self.game,
            下限="ui:HUD_HP_BAR",
            上限=10,
        )
''',
        encoding="utf-8",
    )

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    assert any(i.code == "CODE_UI_HTML_SOURCES_NOT_FOUND" for i in report.issues), (
        "UI源码(HTML) 缺失时应报 CODE_UI_HTML_SOURCES_NOT_FOUND，实际："
        + repr([(i.code, i.message) for i in report.issues])
    )

