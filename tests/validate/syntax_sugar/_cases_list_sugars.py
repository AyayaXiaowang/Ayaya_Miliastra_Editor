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


def test_list_subscript_load_is_rewritten_and_allowed_server(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_list_subscript_load_ok
graph_name: 列表下标读取_自动改写_通过
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 列表下标读取_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        整数A: "整数" = 加法运算(self.game, 左值=1, 右值=0)
        整数B: "整数" = 加法运算(self.game, 左值=2, 右值=0)
        目标列表: "整数列表" = [整数A, 整数B]

        序号: "整数" = 加法运算(self.game, 左值=0, 右值=0)
        当前值: "整数" = 目标列表[序号]

        if 是否相等(self.game, 输入1=当前值, 输入2=1):
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_list_subscript_load_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_list_subscript_load_is_rewritten_and_allowed_client(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_list_subscript_load_client_ok
graph_name: 列表下标读取_client_自动改写_通过
graph_type: client
"""

from __future__ import annotations

from _prelude import *


class 列表下标读取_client_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_节点图开始(self):
        整数A: "整数" = 加法运算(self.game, 左值=1, 右值=0)
        整数B: "整数" = 加法运算(self.game, 左值=2, 右值=0)
        目标列表: "整数列表" = [整数A, 整数B]

        序号: "整数" = 加法运算(self.game, 左值=0, 右值=0)
        当前值: "整数" = 目标列表[序号]

        if 是否相等(self.game, 输入1=当前值, 输入2=1):
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_list_subscript_load_client_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_len_list_is_rewritten_and_allowed_server(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_len_list_ok
graph_name: len_列表_自动改写_通过
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class len_列表_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        列表: "整数列表" = [1, 2, 3]
        长度: "整数" = len(列表)

        if 是否相等(self.game, 输入1=长度, 输入2=3):
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_len_list_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_len_list_is_rewritten_and_allowed_client(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_len_list_client_ok
graph_name: len_列表_client_自动改写_通过
graph_type: client
"""

from __future__ import annotations

from _prelude import *


class len_列表_client_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_节点图开始(self):
        列表: "整数列表" = [1, 2, 3]
        长度: "整数" = len(列表)

        if 是否相等(self.game, 输入1=长度, 输入2=3):
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_len_list_client_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_in_list_compare_is_rewritten_and_allowed(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_in_list_ok
graph_name: in_列表_自动改写_通过
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class in_列表_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        列表: "整数列表" = [1, 2, 3]
        值: "整数" = 加法运算(self.game, 左值=1, 右值=1)

        if 值 in 列表:
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_in_list_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_list_append_is_rewritten_and_allowed_server(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_list_append_ok
graph_name: 列表append_自动改写_通过
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 列表append_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        目标列表: "整数列表" = [1, 2]
        追加值: "整数" = 加法运算(self.game, 左值=3, 右值=0)
        目标列表.append(追加值)

        长度: "整数" = len(目标列表)
        if 是否相等(self.game, 输入1=长度, 输入2=3):
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_list_append_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_list_pop_is_rewritten_and_allowed_server(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_list_pop_ok
graph_name: 列表pop_自动改写_通过
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 列表pop_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        目标列表: "整数列表" = [1, 2, 3]
        序号: "整数" = 加法运算(self.game, 左值=0, 右值=0)
        目标列表.pop(序号)

        长度: "整数" = len(目标列表)
        if 是否相等(self.game, 输入1=长度, 输入2=2):
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_list_pop_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_enumerate_for_is_rewritten_and_allowed(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_enumerate_for_ok
graph_name: enumerate_for_语法糖_自动改写_通过
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class enumerate_for_语法糖_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        整数列表: "整数列表" = [1, 2, 3]
        总和: "整数" = 加法运算(self.game, 左值=0, 右值=0)

        for 序号, 当前元素 in enumerate(整数列表):
            总和 += 当前元素

        if 是否相等(self.game, 输入1=总和, 输入2=6):
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_enumerate_for_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"

