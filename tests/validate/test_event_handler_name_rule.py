from __future__ import annotations

from pathlib import Path

from engine.validate.api import validate_files
from tests._helpers.project_paths import get_repo_root


def _workspace_root() -> Path:
    return get_repo_root()


def _make_temp_graph_code(tmp_dir: Path, code: str) -> Path:
    target = tmp_dir / "temp_event_handler_name_graph.py"
    target.write_text(code, encoding="utf-8")
    return target


def test_builtin_event_handler_name_with_suffix_is_reported(tmp_path: Path) -> None:
    """内置事件（如 定时器触发时）注册回调时，回调名不允许在 on_<事件名> 后追加后缀。"""
    graph_code = '''
""" 
graph_id: test_event_handler_name_suffix
graph_name: 事件回调命名校验_追加后缀应报错
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 事件回调命名校验_追加后缀应报错:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_定时器触发时_波次倒计时(self, 事件源实体, 事件源GUID, 定时器名称, 定时器序列序号, 循环次数):
        return

    def register_handlers(self):
        self.game.register_event_handler(
            "定时器触发时",
            self.on_定时器触发时_波次倒计时,
            owner=self.owner_entity,
        )
'''
    workspace = _workspace_root()
    graph_path = _make_temp_graph_code(tmp_path, graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    mismatch_issues = [
        issue for issue in report.issues if issue.code == "CODE_EVENT_HANDLER_NAME_MISMATCH"
    ]
    assert mismatch_issues, "应当检测到内置事件回调命名不规范（追加后缀）"


def test_builtin_event_handler_name_exact_match_passes(tmp_path: Path) -> None:
    """内置事件注册回调时，回调名为 on_<事件名> 时不应触发该规则。"""
    graph_code = '''
""" 
graph_id: test_event_handler_name_exact
graph_name: 事件回调命名校验_标准命名不报错
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 事件回调命名校验_标准命名不报错:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_定时器触发时(self, 事件源实体, 事件源GUID, 定时器名称, 定时器序列序号, 循环次数):
        return

    def register_handlers(self):
        self.game.register_event_handler(
            "定时器触发时",
            self.on_定时器触发时,
            owner=self.owner_entity,
        )
'''
    workspace = _workspace_root()
    graph_path = _make_temp_graph_code(tmp_path, graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    mismatch_issues = [
        issue for issue in report.issues if issue.code == "CODE_EVENT_HANDLER_NAME_MISMATCH"
    ]
    assert not mismatch_issues


def test_signal_event_handler_name_is_not_forced(tmp_path: Path) -> None:
    """信号事件（signal_id）允许自定义回调名，不应触发内置事件回调命名规则。"""
    graph_code = '''
""" 
graph_id: test_event_handler_name_signal
graph_name: 事件回调命名校验_信号不强制
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 事件回调命名校验_信号不强制:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        return

    def handle_signal_callback(self, 事件源实体, 事件源GUID, 信号来源实体):
        return

    def register_handlers(self):
        self.game.register_event_handler(
            "signal_all_supported_types_example",
            self.handle_signal_callback,
            owner=self.owner_entity,
        )
'''
    workspace = _workspace_root()
    graph_path = _make_temp_graph_code(tmp_path, graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    mismatch_issues = [
        issue for issue in report.issues if issue.code == "CODE_EVENT_HANDLER_NAME_MISMATCH"
    ]
    assert not mismatch_issues


