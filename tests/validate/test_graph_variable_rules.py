from __future__ import annotations

from pathlib import Path

from engine.validate.api import validate_files
from engine.graph.utils.metadata_extractor import extract_metadata_from_code
from tests._helpers.project_paths import get_repo_root


def _workspace_root() -> Path:
    return get_repo_root()


def _write_graph_code(tmp_dir: Path, filename: str, source: str) -> Path:
    target = tmp_dir / filename
    target.write_text(source, encoding="utf-8")
    return target


def test_graph_variable_usage_without_declaration_reports_issue(tmp_path: Path) -> None:
    """未声明 GRAPH_VARIABLES 时使用图变量，应触发声明缺失错误。"""
    graph_code = '''
""" 
graph_id: graph_var_missing_decl
graph_name: 图变量未声明测试
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 图变量未声明测试:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        设置节点图变量(self.game, 变量名="未声明变量", 值=1)
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_var_missing_decl.py", graph_code)

    report = validate_files(
        [graph_path],
        workspace,
        strict_entity_wire_only=False,
        use_cache=False,
    )
    declaration_issues = [
        issue for issue in report.issues if issue.code == "CODE_GRAPH_VAR_DECLARATION"
    ]

    assert declaration_issues, "未声明 GRAPH_VARIABLES 却使用图变量时，应报声明缺失错误"
    assert any(
        "未在文件顶部声明任何 GRAPH_VARIABLES" in issue.message
        for issue in declaration_issues
    ), "错误信息应提示缺少 GRAPH_VARIABLES 声明"


def test_graph_variable_with_invalid_type_reports_issue(tmp_path: Path) -> None:
    """GRAPH_VARIABLES 中包含未知类型名时，应触发类型校验错误。"""
    graph_code = '''
""" 
graph_id: graph_var_invalid_type
graph_name: 图变量类型非法测试
graph_type: server
"""

from __future__ import annotations

from engine.graph.models.package_model import GraphVariableConfig
from _prelude import *


GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="非法类型变量",
        variable_type="不存在的类型",
        default_value=0,
        description="用于触发类型名校验",
        is_exposed=False,
    ),
]


class 图变量类型非法测试:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        获取节点图变量(self.game, 变量名="非法类型变量")
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_var_invalid_type.py", graph_code)

    report = validate_files(
        [graph_path],
        workspace,
        strict_entity_wire_only=False,
        use_cache=False,
    )
    type_issues = [issue for issue in report.issues if issue.code == "CODE_UNKNOWN_TYPE_NAME"]

    assert type_issues, "GRAPH_VARIABLES 中存在未知类型名时，应报类型非法错误"
    assert any(
        "GRAPH_VARIABLES" in issue.message and "未知类型名" in issue.message
        for issue in type_issues
    ), "错误信息应指出 GRAPH_VARIABLES 中的类型非法"


def test_graph_variable_default_value_negative_number_is_extracted() -> None:
    """GRAPH_VARIABLES 中默认值包含负数字面量（如 -1.0）时，应能被静态提取为真实数值。"""
    graph_code = '''
"""
graph_id: graph_var_negative_default
graph_name: 图变量负数默认值测试
graph_type: server
"""

from __future__ import annotations

from engine.graph.models.package_model import GraphVariableConfig

GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="相对下沉方向",
        variable_type="三维向量",
        default_value=(0.0, -1.0, 0.0),
        description="测试负数字面量是否能正确提取",
        is_exposed=True,
    ),
]
'''
    metadata = extract_metadata_from_code(graph_code)
    assert metadata.graph_variables, "应当能从 GRAPH_VARIABLES 中提取图变量元数据"
    first_var = metadata.graph_variables[0]
    assert first_var.get("default_value") == (
        0.0,
        -1.0,
        0.0,
    ), "包含负数字面量的三维向量默认值应被正确提取"

