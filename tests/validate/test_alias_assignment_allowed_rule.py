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


def test_alias_assignment_between_runtime_vars_is_allowed(tmp_path: Path) -> None:
    """允许：运行期变量（节点输出）之间的别名赋值。

    语义：不生成新节点，仅将“目标变量名”映射到同一数据来源；后续使用目标变量名应与使用源变量一致。
    """
    graph_code = '''
"""
graph_id: graph_alias_assignment_runtime_ok
graph_name: 别名赋值_运行期变量_通过
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 别名赋值_运行期变量_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        当前次数: "整数" = 加法运算(self.game, 左值=1, 右值=1)
        新次数: "整数" = 当前次数
        新次数 += 1

        if 是否相等(self.game, 输入1=新次数, 输入2=3):
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_alias_assignment_runtime_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_alias_copy_from_stable_named_constant_is_allowed(tmp_path: Path) -> None:
    """允许：`A` 在别名点之前稳定为字面量常量时，`B=A` 可折叠为常量。"""
    graph_code = '''
"""
graph_id: graph_alias_assignment_named_const_stable_ok
graph_name: 别名赋值_命名常量_稳定_通过
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 别名赋值_命名常量_稳定_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        常量A: "整数" = 1
        别名B: "整数" = 常量A
        if 是否相等(self.game, 输入1=别名B, 输入2=1):
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_alias_assignment_named_const_stable_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_alias_copy_from_named_constant_is_forbidden_when_source_changed(tmp_path: Path) -> None:
    """仍然禁止：若 `A` 在别名点前被运行期赋值覆盖，则 `B=A` 不能按常量折叠。"""
    graph_code = '''
"""
graph_id: graph_alias_assignment_named_const_changed_forbidden
graph_name: 别名赋值_命名常量_覆盖后_禁止
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 别名赋值_命名常量_覆盖后_禁止:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        常量A: "整数" = 1
        常量A = 加法运算(self.game, 左值=常量A, 右值=1)
        别名B: "整数" = 常量A
        if 是否相等(self.game, 输入1=别名B, 输入2=2):
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_alias_assignment_named_const_changed_forbidden.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert "CODE_NO_CONST_ALIAS_ASSIGNMENT" in codes


