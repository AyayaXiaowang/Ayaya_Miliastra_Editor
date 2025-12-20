from __future__ import annotations

from pathlib import Path

from engine.validate.api import validate_files
from engine.configs.settings import settings


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _make_temp_graph_code(tmp_dir: Path, code: str) -> Path:
    target = tmp_dir / "temp_event_name_graph.py"
    target.write_text(code, encoding="utf-8")
    return target


def test_unknown_event_name_in_module_constant_is_reported(tmp_path: Path) -> None:
    """事件名通过模块常量传入时，若既不是内置事件也不是信号名/ID，应报错。"""
    graph_code = '''
""" 
graph_id: test_unknown_event_name_in_constant
graph_name: 未知事件名校验_模块常量
graph_type: server
"""

from __future__ import annotations

from _prelude import *

事件名常量: "字符串" = "阿这"


class 未知事件名校验_模块常量:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_阿这(self, 事件源实体, 事件源GUID, 信号来源实体):
        return

    def register_handlers(self):
        self.game.register_event_handler(
            事件名常量,
            self.on_阿这,
            owner=self.owner_entity,
        )
'''
    workspace = _workspace_root()
    settings.set_config_path(workspace)
    graph_path = _make_temp_graph_code(tmp_path, graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    unknown_event_issues = [
        issue for issue in report.issues if issue.code == "CODE_UNKNOWN_EVENT_NAME"
    ]
    assert unknown_event_issues, "应当检测到模块常量事件名为未知事件"


def test_signal_name_in_module_constant_is_allowed(tmp_path: Path) -> None:
    """事件名通过模块常量传入时，若可解析为信号名称，则应放行。"""
    graph_code = '''
""" 
graph_id: test_signal_event_name_in_constant
graph_name: 信号事件名校验_模块常量
graph_type: server
"""

from __future__ import annotations

from _prelude import *

# 使用仓库内明确随版本分发的测试信号名称，避免依赖本地私有/未入库资源。
事件名常量: "字符串" = "测试信号_全部参数类型"


class 信号事件名校验_模块常量:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_阿这(self, 事件源实体, 事件源GUID, 信号来源实体):
        return

    def register_handlers(self):
        self.game.register_event_handler(
            事件名常量,
            self.on_阿这,
            owner=self.owner_entity,
        )
'''
    workspace = _workspace_root()
    settings.set_config_path(workspace)
    graph_path = _make_temp_graph_code(tmp_path, graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    unknown_event_issues = [
        issue for issue in report.issues if issue.code == "CODE_UNKNOWN_EVENT_NAME"
    ]
    assert not unknown_event_issues


