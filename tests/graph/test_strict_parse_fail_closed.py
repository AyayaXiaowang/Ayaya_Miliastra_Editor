from __future__ import annotations

from pathlib import Path

import pytest

from engine.graph.graph_code_parser import GraphCodeParser, GraphParseError
from engine.nodes.node_registry import clear_all_registries_for_tests
from engine.utils.runtime_scope import set_active_package_id
from engine.validate.node_graph_validator import validate_file
from tests._helpers.project_paths import get_repo_root


def _workspace_root() -> Path:
    return get_repo_root()


def _write_graph_code(tmp_dir: Path, filename: str, source: str) -> Path:
    target = tmp_dir / filename
    target.write_text(source, encoding="utf-8")
    return target


def test_strict_parse_rejects_python_method_call(tmp_path: Path) -> None:
    """严格模式：发现 Python 原生方法调用时应 fail-closed（拒绝产错图）。"""
    workspace = _workspace_root()
    parser = GraphCodeParser(workspace, strict=True)

    graph_code = '''
"""
graph_id: graph_strict_reject_python_method_call
graph_name: 严格解析_拒绝Python方法调用
graph_type: server
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 严格解析_拒绝Python方法调用:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        文本: "字符串" = "abc"
        # 不支持：Python 原生方法调用（解析器会跳过，严格模式必须直接报错）
        文本.upper()
        设置节点图变量(self.game, 变量名="调试_文本", 变量值=文本, 是否触发事件=False)
'''
    graph_path = _write_graph_code(tmp_path, "graph_strict_reject_python_method_call.py", graph_code)
    with pytest.raises(GraphParseError):
        parser.parse_file(graph_path)


def test_strict_parse_rejects_composite_match_without_valid_cases(tmp_path: Path) -> None:
    """严格模式：复合 match 若无法匹配到任何有效流程出口，应 fail-closed。"""
    workspace = _workspace_root()
    set_active_package_id("演示项目")
    clear_all_registries_for_tests()
    parser = GraphCodeParser(workspace, strict=True)

    graph_code = '''
"""
graph_id: graph_strict_reject_composite_match_no_valid_case
graph_name: 严格解析_拒绝复合match无有效分支
graph_type: server
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 严格解析_拒绝复合match无有效分支:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity
        self.分支器 = 多分支_示例_类格式(self.game, owner_entity)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        分支值: "整数" = 获取随机整数(self.game, 下限=0, 上限=2)
        match self.分支器.按整数多分支(分支值=分支值):
            case "不存在的出口":
                设置节点图变量(self.game, 变量名="调试_文本", 变量值=0, 是否触发事件=False)
'''
    graph_path = _write_graph_code(tmp_path, "graph_strict_reject_composite_match_no_valid_case.py", graph_code)
    try:
        with pytest.raises(GraphParseError):
            parser.parse_file(graph_path)
    finally:
        set_active_package_id(None)
        clear_all_registries_for_tests()


def test_validate_file_reports_ir_errors_for_composite_match_case_label_not_found(tmp_path: Path) -> None:
    """validate_file：IR 收集到的“无法可靠建模”错误必须作为 error 暴露（避免 UI 加载失败但校验通过）。"""
    graph_code = '''
"""
graph_id: graph_validate_reports_ir_errors_composite_match_case_wildcard
graph_name: 校验_应报告IR错误_复合match_case通配
graph_type: server
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403

GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="调试_文本",
        variable_type="整数",
        default_value=0,
        is_exposed=False,
    ),
]


class 校验_应报告IR错误_复合match_case通配:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity
        # 复合节点实例属性名需可被 IR 稳定识别（建议包含复合节点类名），否则会退化为普通 match。
        self.多分支_示例_类格式 = 多分支_示例_类格式(self.game, owner_entity)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        分支值: "整数" = 获取随机整数(self.game, 下限=0, 上限=2)
        match self.多分支_示例_类格式.按整数多分支(分支值=分支值):
            case "不存在的出口":
                设置节点图变量(self.game, 变量名="调试_文本", 变量值=0, 是否触发事件=False)
'''
    graph_path = _write_graph_code(
        tmp_path,
        "graph_validate_reports_ir_errors_composite_match_case_wildcard.py",
        graph_code,
    )
    set_active_package_id("演示项目")
    clear_all_registries_for_tests()
    try:
        passed, errors, warnings = validate_file(graph_path)
    finally:
        set_active_package_id(None)
        clear_all_registries_for_tests()
    assert not passed
    assert len(errors) >= 1
    assert any(
        (
            ("match 复合节点调用" in message and "未找到同名流程出口" in message)
            or ("match 复合节点调用" in message and "未能匹配到任何有效分支标签" in message)
        )
        for message in errors
    )
    # 不要求 warnings 为空：校验应尽力产出更多信息，但必须 fail-closed（passed=False）
    warning_messages = warnings
    assert isinstance(warning_messages, list)


