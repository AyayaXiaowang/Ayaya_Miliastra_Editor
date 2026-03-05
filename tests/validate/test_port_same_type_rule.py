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


def test_same_type_rule_blocks_guid_vs_string_in_is_equal(tmp_path: Path) -> None:
    """是否相等：GUID vs 字符串 应触发“同型输入”错误。"""
    graph_code = '''
""" 
graph_id: graph_same_type_eq_guid_string
graph_name: 同型输入校验_是否相等_GUID_字符串
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 同型输入校验_是否相等_GUID_字符串:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        自身实体: "实体" = 获取自身实体(self.game)
        自身GUID: "GUID" = 以实体查询GUID(self.game, 实体=自身实体)
        是否命中: "布尔值" = 是否相等(self.game, 输入1=自身GUID, 输入2="123")
        if 是否命中:
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_same_type_eq_guid_string.py", graph_code)

    report = validate_files(
        [graph_path],
        workspace,
        strict_entity_wire_only=False,
        use_cache=False,
    )
    issues = [issue for issue in report.issues if issue.code == "PORT_SAME_TYPE_REQUIRED"]
    assert issues, "是否相等 输入1/输入2 类型不一致时，应触发 PORT_SAME_TYPE_REQUIRED"


def test_same_type_rule_blocks_int_float_in_numeric_greater(tmp_path: Path) -> None:
    """数值大于：整数 vs 浮点数 应触发“同型输入”错误（整数≠浮点数）。"""
    graph_code = '''
""" 
graph_id: graph_same_type_numeric_gt_int_float
graph_name: 同型输入校验_数值大于_整数_浮点数
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 同型输入校验_数值大于_整数_浮点数:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        是否大于: "布尔值" = 数值大于(self.game, 左值=1, 右值=1.0)
        if 是否大于:
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(
        tmp_path, "graph_same_type_numeric_gt_int_float.py", graph_code
    )

    report = validate_files(
        [graph_path],
        workspace,
        strict_entity_wire_only=False,
        use_cache=False,
    )
    issues = [issue for issue in report.issues if issue.code == "PORT_SAME_TYPE_REQUIRED"]
    assert issues, "数值大于 左值/右值 类型不一致时，应触发 PORT_SAME_TYPE_REQUIRED"


