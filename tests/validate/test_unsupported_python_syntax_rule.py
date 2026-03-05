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


def test_while_is_reported_as_error(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_while_not_supported
graph_name: while_不支持_必须报错
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class while_不支持_必须报错:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        while True:
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_while_not_supported.py", graph_code)
    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    assert any(issue.code == "CODE_WHILE_NOT_SUPPORTED" for issue in report.issues), "while 必须报错"


def test_continue_is_reported_as_error(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_continue_not_supported
graph_name: continue_不支持_必须报错
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class continue_不支持_必须报错:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        for i in range(1):
            continue
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_continue_not_supported.py", graph_code)
    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    assert any(issue.code == "CODE_CONTINUE_NOT_SUPPORTED" for issue in report.issues), "continue 必须报错"


def test_for_else_is_reported_as_error(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_for_else_not_supported
graph_name: for_else_不支持_必须报错
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class for_else_不支持_必须报错:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        for i in range(1):
            break
        else:
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_for_else_not_supported.py", graph_code)
    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    assert any(issue.code == "CODE_FOR_ELSE_NOT_SUPPORTED" for issue in report.issues), "for...else 必须报错"


def test_try_except_is_reported_as_error(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_try_not_supported
graph_name: try_except_不支持_必须报错
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class try_except_不支持_必须报错:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        try:
            return
        except Exception:
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_try_not_supported.py", graph_code)
    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    assert any(issue.code == "CODE_TRY_EXCEPT_NOT_SUPPORTED" for issue in report.issues), "try/except 必须报错"


def test_comprehension_is_reported_as_error(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_comp_not_supported
graph_name: 推导式_不支持_必须报错
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 推导式_不支持_必须报错:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        结果列表: "整数列表" = [i for i in [1, 2]]
        return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_comp_not_supported.py", graph_code)
    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    assert any(issue.code == "CODE_COMPREHENSION_NOT_SUPPORTED" for issue in report.issues), "推导式必须报错"


def test_python_function_call_is_reported_as_error(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_python_call_not_allowed
graph_name: Python函数调用_不允许_必须报错
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class Python函数调用_不允许_必须报错:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        sorted([2, 1])
        return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_python_call_not_allowed.py", graph_code)
    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    assert any(issue.code == "CODE_PYTHON_FUNCTION_CALL_FORBIDDEN" for issue in report.issues), "Python 函数调用必须报错"


def test_assert_is_reported_as_error(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_assert_not_supported
graph_name: assert_不支持_必须报错
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class assert_不支持_必须报错:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        assert True
        return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_assert_not_supported.py", graph_code)
    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    assert any(issue.code == "CODE_ASSERT_NOT_SUPPORTED" for issue in report.issues), "assert 必须报错"


def test_data_node_call_as_statement_is_reported_as_error(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_data_node_call_stmt_forbidden
graph_name: 纯数据节点调用作为语句_禁止
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 纯数据节点调用作为语句_禁止:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        加法运算(self.game, 左值=1, 右值=1)
        return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_data_node_call_stmt_forbidden.py", graph_code)
    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    assert any(issue.code == "CODE_DATA_NODE_CALL_STATEMENT_FORBIDDEN" for issue in report.issues), "纯数据节点调用作为语句必须报错"


def test_range_arg_call_is_reported_as_error(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_range_arg_call_forbidden
graph_name: range参数含调用_禁止
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class range参数含调用_禁止:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        列表: "整数列表" = [1, 2, 3]
        for 序号 in range(len(列表)):
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_range_arg_call_forbidden.py", graph_code)
    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    assert any(issue.code == "CODE_RANGE_ARG_NOT_SIMPLE" for issue in report.issues), "range 参数包含调用必须报错"


def test_range_step_is_reported_as_error(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_range_step_not_supported
graph_name: range_step_不支持_必须报错
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class range_step_不支持_必须报错:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        for 序号 in range(0, 10, 2):
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_range_step_not_supported.py", graph_code)
    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    assert any(issue.code == "CODE_RANGE_CALL_ARGS_COUNT_INVALID" for issue in report.issues), "range step 参数必须报错"


