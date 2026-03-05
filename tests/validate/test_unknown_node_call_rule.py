from __future__ import annotations

from pathlib import Path

from engine.validate.api import validate_files
from tests._helpers.project_paths import get_repo_root


def _workspace_root() -> Path:
    return get_repo_root()


def _make_temp_graph_code(tmp_dir: Path, code: str) -> Path:
    target = tmp_dir / "temp_unknown_node_call_graph.py"
    target.write_text(code, encoding="utf-8")
    return target


def test_unknown_node_call_with_self_game_is_reported(tmp_path: Path) -> None:
    """当 Graph Code 出现 `未知函数(self.game, ...)` 形态时，应在校验阶段报错，避免拼写错误静默绕过。"""
    graph_code = '''
""" 
graph_id: test_unknown_node_call
graph_name: 未知节点调用校验
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 未知节点调用校验:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        # 伪造一个不存在的“节点函数名”，但形态符合 `xxx(self.game, ...)`
        未知节点函数(
            self.game,
            任意参数=1,
        )
'''
    workspace = _workspace_root()
    graph_path = _make_temp_graph_code(tmp_path, graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    unknown_call_issues = [
        issue
        for issue in report.issues
        if issue.code == "CODE_UNKNOWN_NODE_CALL"
    ]
    assert unknown_call_issues, "应当检测到未知节点函数名调用（形如 xxx(self.game, ...)）"


