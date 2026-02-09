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


def test_ui_custom_var_name_too_long_reports_error(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: ui_custom_var_name_too_long_01
graph_name: UI自定义变量名过长_报错
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class UI自定义变量名过长_报错:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        # ui_ 前缀 + snake_case：触发长度上限校验
        设置自定义变量(self.game, 目标实体=事件源实体, 变量名="ui_page_level_select_int", 变量值=0, 是否触发事件=False)
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "ui_custom_var_name_too_long_01.py", graph_code)
    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)

    codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert "CODE_CUSTOM_VAR_NAME_TOO_LONG" in codes


def test_non_ui_or_non_snake_case_custom_var_name_not_limited_by_ui_rule(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: custom_var_name_long_cn_01
graph_name: 中文自定义变量名_不受UI长度规则影响
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 中文自定义变量名_不受UI长度规则影响:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        设置自定义变量(self.game, 目标实体=事件源实体, 变量名="锻刀英雄_冒险_是否进行中", 变量值=False, 是否触发事件=False)
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "custom_var_name_long_cn_01.py", graph_code)
    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)

    error_issues = [issue for issue in report.issues if issue.level == "error"]
    assert not error_issues, f"期望无错误，但得到: {[i.code for i in error_issues]}"

