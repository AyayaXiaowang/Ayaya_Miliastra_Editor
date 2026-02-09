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


def test_list_literal_rewrite_allows_non_empty_list_in_method_body(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_list_literal_ok
graph_name: 列表字面量_自动拼装_通过
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 列表字面量_自动拼装_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        整数A: "整数" = 加法运算(self.game, 左值=1, 右值=2)
        整数B: "整数" = 加法运算(self.game, 左值=3, 右值=4)
        整数列表示例: "整数列表" = [整数A, 整数B]

        for 当前元素 in 整数列表示例:
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_list_literal_ok.py", graph_code)

    report = validate_files(
        [graph_path],
        workspace,
        strict_entity_wire_only=False,
        use_cache=False,
    )
    error_issues = [issue for issue in report.issues if issue.level == "error"]
    assert not error_issues, f"期望无错误，但得到: {[i.code for i in error_issues]}"


def test_for_in_list_literal_is_forbidden(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_for_in_list_literal_ok
graph_name: for_in_列表字面量_自动拼装_通过
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class for_in_列表字面量_自动拼装_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        for 当前元素 in [1, 2, 3]:
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_for_in_list_literal_ok.py", graph_code)

    report = validate_files(
        [graph_path],
        workspace,
        strict_entity_wire_only=False,
        use_cache=False,
    )
    codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert "CODE_LIST_LITERAL_FOR_ITER_FORBIDDEN" in codes


def test_empty_list_literal_is_forbidden(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_empty_list_literal_forbidden
graph_name: 空列表字面量_禁止
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 空列表字面量_禁止:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        空列表: "整数列表" = []
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_empty_list_literal_forbidden.py", graph_code)

    report = validate_files(
        [graph_path],
        workspace,
        strict_entity_wire_only=False,
        use_cache=False,
    )
    codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert "CODE_EMPTY_LIST_LITERAL_FORBIDDEN" in codes


def test_list_literal_too_long_is_forbidden(tmp_path: Path) -> None:
    elements = ", ".join(str(i) for i in range(101))
    graph_code = f'''
"""
graph_id: graph_list_literal_too_long_forbidden
graph_name: 列表字面量_超过上限_禁止
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 列表字面量_超过上限_禁止:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        过长列表: "整数列表" = [{elements}]
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_list_literal_too_long_forbidden.py", graph_code)

    report = validate_files(
        [graph_path],
        workspace,
        strict_entity_wire_only=False,
        use_cache=False,
    )
    codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert "CODE_LIST_LITERAL_TOO_LONG" in codes


def test_list_literal_enforces_same_type_via_build_list(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_list_literal_same_type_required
graph_name: 列表字面量_同型输入_报错
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 列表字面量_同型输入_报错:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        整数A: "整数" = 加法运算(self.game, 左值=1, 右值=2)
        浮点B: "浮点数" = 加法运算(self.game, 左值=1.0, 右值=2.0)
        列表: "整数列表" = [整数A, 浮点B]
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_list_literal_same_type_required.py", graph_code)

    report = validate_files(
        [graph_path],
        workspace,
        strict_entity_wire_only=False,
        use_cache=False,
    )
    codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert "PORT_SAME_TYPE_REQUIRED" in codes


def test_list_subscript_assignment_is_rewritten_and_allowed(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_list_subscript_assign_ok
graph_name: 列表下标赋值_自动改写_通过
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 列表下标赋值_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        整数A: "整数" = 加法运算(self.game, 左值=1, 右值=2)
        整数B: "整数" = 加法运算(self.game, 左值=3, 右值=4)
        目标列表: "整数列表" = [整数A, 整数B]

        序号: "整数" = 加法运算(self.game, 左值=0, 右值=0)
        新值: "整数" = 加法运算(self.game, 左值=10, 右值=0)
        目标列表[序号] = 新值
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_list_subscript_assign_ok.py", graph_code)

    report = validate_files(
        [graph_path],
        workspace,
        strict_entity_wire_only=False,
        use_cache=False,
    )
    error_issues = [issue for issue in report.issues if issue.level == "error"]
    assert not error_issues, f"期望无错误，但得到: {[i.code for i in error_issues]}"


def test_del_list_subscript_is_rewritten_and_allowed(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_del_list_subscript_ok
graph_name: del_列表下标_自动改写_通过
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class del_列表下标_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        整数A: "整数" = 加法运算(self.game, 左值=1, 右值=2)
        整数B: "整数" = 加法运算(self.game, 左值=3, 右值=4)
        目标列表: "整数列表" = [整数A, 整数B]

        序号: "整数" = 加法运算(self.game, 左值=0, 右值=0)
        del 目标列表[序号]
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_del_list_subscript_ok.py", graph_code)

    report = validate_files(
        [graph_path],
        workspace,
        strict_entity_wire_only=False,
        use_cache=False,
    )
    error_issues = [issue for issue in report.issues if issue.level == "error"]
    assert not error_issues, f"期望无错误，但得到: {[i.code for i in error_issues]}"


def test_list_insert_extend_clear_are_rewritten_and_allowed(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_list_methods_ok
graph_name: 列表方法_insert_extend_clear_自动改写_通过
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 列表方法_insert_extend_clear_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        整数A: "整数" = 加法运算(self.game, 左值=1, 右值=2)
        整数B: "整数" = 加法运算(self.game, 左值=3, 右值=4)
        目标列表: "整数列表" = [整数A, 整数B]

        插入序号: "整数" = 加法运算(self.game, 左值=0, 右值=0)
        插入值: "整数" = 加法运算(self.game, 左值=99, 右值=0)
        目标列表.insert(插入序号, 插入值)

        接入列表: "整数列表" = [插入值]
        目标列表.extend(接入列表)

        目标列表.clear()
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_list_methods_ok.py", graph_code)

    report = validate_files(
        [graph_path],
        workspace,
        strict_entity_wire_only=False,
        use_cache=False,
    )
    error_issues = [issue for issue in report.issues if issue.level == "error"]
    assert not error_issues, f"期望无错误，但得到: {[i.code for i in error_issues]}"


def test_list_subscript_slice_is_forbidden(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_list_subscript_slice_forbidden
graph_name: 列表下标切片_禁止
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 列表下标切片_禁止:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        整数A: "整数" = 加法运算(self.game, 左值=1, 右值=2)
        整数B: "整数" = 加法运算(self.game, 左值=3, 右值=4)
        目标列表: "整数列表" = [整数A, 整数B]

        起始: "整数" = 加法运算(self.game, 左值=0, 右值=0)
        结束: "整数" = 加法运算(self.game, 左值=1, 右值=0)
        新值: "整数" = 加法运算(self.game, 左值=10, 右值=0)
        目标列表[起始:结束] = 新值
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_list_subscript_slice_forbidden.py", graph_code)

    report = validate_files(
        [graph_path],
        workspace,
        strict_entity_wire_only=False,
        use_cache=False,
    )
    codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert "CODE_LIST_SUBSCRIPT_INDEX_UNSUPPORTED" in codes


def test_list_subscript_chain_assign_is_forbidden(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_list_subscript_chain_assign_forbidden
graph_name: 列表下标链式赋值_禁止
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 列表下标链式赋值_禁止:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        整数A: "整数" = 加法运算(self.game, 左值=1, 右值=2)
        整数B: "整数" = 加法运算(self.game, 左值=3, 右值=4)
        列表1: "整数列表" = [整数A, 整数B]
        列表2: "整数列表" = [整数A, 整数B]

        序号: "整数" = 加法运算(self.game, 左值=0, 右值=0)
        新值: "整数" = 加法运算(self.game, 左值=10, 右值=0)
        列表1[序号] = 列表2[序号] = 新值
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_list_subscript_chain_assign_forbidden.py", graph_code)

    report = validate_files(
        [graph_path],
        workspace,
        strict_entity_wire_only=False,
        use_cache=False,
    )
    codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert "CODE_LIST_SUBSCRIPT_ASSIGN_CHAIN_FORBIDDEN" in codes


def test_del_list_multiple_subscripts_is_forbidden(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_del_list_multi_subscript_forbidden
graph_name: del_多个列表下标_禁止
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class del_多个列表下标_禁止:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        整数A: "整数" = 加法运算(self.game, 左值=1, 右值=2)
        整数B: "整数" = 加法运算(self.game, 左值=3, 右值=4)
        目标列表: "整数列表" = [整数A, 整数B]

        序号1: "整数" = 加法运算(self.game, 左值=0, 右值=0)
        序号2: "整数" = 加法运算(self.game, 左值=1, 右值=0)
        del 目标列表[序号1], 目标列表[序号2]
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_del_list_multi_subscript_forbidden.py", graph_code)

    report = validate_files(
        [graph_path],
        workspace,
        strict_entity_wire_only=False,
        use_cache=False,
    )
    codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert "CODE_LIST_SUBSCRIPT_DELETE_MULTIPLE_TARGETS_FORBIDDEN" in codes

