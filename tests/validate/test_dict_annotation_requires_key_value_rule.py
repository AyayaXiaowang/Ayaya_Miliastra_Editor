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


def test_bare_dict_annotation_reports_issue(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_bare_dict_annotation_forbidden
graph_name: 裸字典注解_必须报错
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 裸字典注解_必须报错:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        测试字典: "字典" = {"a": 1}
        长度: "整数" = len(测试字典)
        if 是否相等(self.game, 输入1=长度, 输入2=1):
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_bare_dict_annotation_forbidden.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    issues = [issue for issue in report.issues if issue.code == "CODE_DICT_ANNOTATION_REQUIRES_KEY_VALUE"]
    assert issues, "使用裸 '字典' 类型注解时应报错（要求显式键/值类型）"


def test_typed_dict_annotation_is_allowed(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_typed_dict_annotation_ok
graph_name: 显式字典注解_通过
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 显式字典注解_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        测试字典: "字符串-整数字典" = {"a": 1}
        长度: "整数" = len(测试字典)
        if 是否相等(self.game, 输入1=长度, 输入2=1):
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_typed_dict_annotation_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    issue_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert "CODE_DICT_ANNOTATION_REQUIRES_KEY_VALUE" not in issue_codes, (
        "使用显式『键类型-值类型字典』注解时不应触发裸字典注解错误"
    )


