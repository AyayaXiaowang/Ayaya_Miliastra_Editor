from __future__ import annotations

from pathlib import Path

from engine.validate.api import validate_files
from tests._helpers.project_paths import get_repo_root


def _workspace_root() -> Path:
    return get_repo_root()


def _make_temp_graph_code(tmp_dir: Path, code: str) -> Path:
    target = tmp_dir / "temp_if_condition_inline_compare.py"
    target.write_text(code, encoding="utf-8")
    return target


def test_if_inline_eq_is_allowed(tmp_path: Path) -> None:
    """受控放开：if 条件中允许直接写 `A == B`。"""
    graph_code = '''
"""
graph_id: test_if_inline_eq_allowed
graph_name: if内联比较允许_eq
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class if内联比较允许_eq:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        整数A: "整数" = 加法运算(self.game, 左值=1, 右值=0)
        整数B: "整数" = 加法运算(self.game, 左值=2, 右值=0)

        if 整数A == 整数B:
            return
'''
    workspace = _workspace_root()
    graph_path = _make_temp_graph_code(tmp_path, graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    inline_compare_issues = [
        issue for issue in report.issues if issue.code == "CODE_IF_INLINE_COMPARISON"
    ]
    assert not inline_compare_issues, "if 条件 `==` 应当被允许（不应报 CODE_IF_INLINE_COMPARISON）"


def test_if_inline_gt_is_forbidden(tmp_path: Path) -> None:
    """受控放开：仍禁止“不支持的 Compare 形态”（例如链式比较）。"""
    graph_code = '''
"""
graph_id: test_if_inline_gt_forbidden
graph_name: if内联比较禁止_链式比较
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class if内联比较禁止_链式比较:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        整数A: "整数" = 加法运算(self.game, 左值=1, 右值=0)
        整数B: "整数" = 加法运算(self.game, 左值=2, 右值=0)

        # 链式比较（a < b < c）不支持：应触发语法糖改写 issue 并在校验期报错
        if 整数A < 整数B < 3:
            return
'''
    workspace = _workspace_root()
    graph_path = _make_temp_graph_code(tmp_path, graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    chain_compare_issues = [
        issue for issue in report.issues if issue.code == "CODE_COMPARE_CHAIN_FORBIDDEN"
    ]
    assert chain_compare_issues, "链式比较应当在校验期报错（CODE_COMPARE_CHAIN_FORBIDDEN）"

