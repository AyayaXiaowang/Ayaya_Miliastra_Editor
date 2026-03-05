from __future__ import annotations

from pathlib import Path

from engine.validate.api import validate_files
from tests._helpers.project_paths import get_repo_root


def _workspace_root() -> Path:
    return get_repo_root()


def _write_graph_code(tmp_dir: Path, filename: str, source: str) -> Path:
    target = tmp_dir / filename
    target.write_text(source, encoding="utf-8")
    return target


def test_graph_var_redundant_init_on_entity_created_reports_warning(tmp_path: Path) -> None:
    """on_实体创建时 中把图变量设回默认值（False/0/空列表）应给出 warning。"""
    graph_code = '''
"""
graph_id: graph_var_redundant_init_on_entity_created_01
graph_name: 图变量冗余初始化提示_示例
graph_type: server
"""

from __future__ import annotations

from engine.graph.models.package_model import GraphVariableConfig
from _prelude import *


GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="门是否已打开",
        variable_type="布尔值",
        default_value=False,
        description="用于测试：默认 False",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="当前激活数量",
        variable_type="整数",
        default_value=0,
        description="用于测试：默认 0",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="当前激活踏板GUID列表",
        variable_type="GUID列表",
        default_value=[],
        description="用于测试：默认空列表",
        is_exposed=False,
    ),
]


class 图变量冗余初始化提示_示例:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        设置节点图变量(self.game, 变量名="门是否已打开", 变量值=False, 是否触发事件=False)
        设置节点图变量(self.game, 变量名="当前激活数量", 变量值=0, 是否触发事件=False)

        临时列表: "GUID列表" = [事件源GUID]
        临时列表.clear()
        设置节点图变量(self.game, 变量名="当前激活踏板GUID列表", 变量值=临时列表, 是否触发事件=False)
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(
        tmp_path,
        "graph_var_redundant_init_on_entity_created_01.py",
        graph_code,
    )
    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)

    hits = [issue for issue in report.issues if issue.code == "CODE_GRAPH_VAR_REDUNDANT_INIT_DEFAULT"]
    assert hits, "应产生 CODE_GRAPH_VAR_REDUNDANT_INIT_DEFAULT warning，用于提示 on_实体创建时 冗余设置默认值"
    assert any(issue.level == "warning" for issue in hits)
    assert any("门是否已打开" in issue.message for issue in hits)
    assert any("当前激活数量" in issue.message for issue in hits)
    assert any("当前激活踏板GUID列表" in issue.message for issue in hits)


def test_graph_var_redundant_init_on_entity_created_not_reported_when_value_not_default(
    tmp_path: Path,
) -> None:
    """当设置值与默认值不相等时，不应提示。"""
    graph_code = '''
"""
graph_id: graph_var_redundant_init_on_entity_created_02
graph_name: 图变量冗余初始化提示_不触发
graph_type: server
"""

from __future__ import annotations

from engine.graph.models.package_model import GraphVariableConfig
from _prelude import *


GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="当前激活数量",
        variable_type="整数",
        default_value=0,
        description="用于测试：默认 0",
        is_exposed=False,
    ),
]


class 图变量冗余初始化提示_不触发:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        设置节点图变量(self.game, 变量名="当前激活数量", 变量值=1, 是否触发事件=False)
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(
        tmp_path,
        "graph_var_redundant_init_on_entity_created_02.py",
        graph_code,
    )
    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)

    hits = [issue for issue in report.issues if issue.code == "CODE_GRAPH_VAR_REDUNDANT_INIT_DEFAULT"]
    assert not hits, "设置值不等于默认值时，不应产生冗余初始化提示"


