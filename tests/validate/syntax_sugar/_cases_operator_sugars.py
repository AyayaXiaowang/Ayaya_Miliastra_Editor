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


def test_vector_cross_is_rewritten_and_allowed_server(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_vector_cross_ok
graph_name: 三维向量外积_运算符_自动改写_通过
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 三维向量外积_运算符_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        向量A: "三维向量" = (1.0, 0.0, 0.0)
        向量B: "三维向量" = (0.0, 1.0, 0.0)
        结果: "三维向量" = 向量A ^ 向量B

        期望: "三维向量" = (0.0, 0.0, 1.0)
        if 是否相等(self.game, 输入1=结果, 输入2=期望):
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_vector_cross_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_vector_cross_is_rewritten_and_allowed_client(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_vector_cross_client_ok
graph_name: 三维向量外积_client_运算符_自动改写_通过
graph_type: client
"""

from __future__ import annotations

from _prelude import *


class 三维向量外积_client_运算符_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_节点图开始(self):
        向量A: "三维向量" = (1.0, 0.0, 0.0)
        向量B: "三维向量" = (0.0, 1.0, 0.0)
        结果: "三维向量" = 向量A ^ 向量B

        期望: "三维向量" = (0.0, 0.0, 1.0)
        if 是否相等(self.game, 输入1=结果, 输入2=期望):
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_vector_cross_client_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_bool_xor_is_rewritten_and_allowed_server(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_bool_xor_ok
graph_name: 布尔异或_运算符_自动改写_通过
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 布尔异或_运算符_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        条件A: "布尔值" = 是否相等(self.game, 输入1=1, 输入2=1)
        条件B: "布尔值" = 是否相等(self.game, 输入1=1, 输入2=0)

        if 条件A ^ 条件B:
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_bool_xor_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_bool_xor_is_rewritten_and_allowed_client(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_bool_xor_client_ok
graph_name: 布尔异或_client_运算符_自动改写_通过
graph_type: client
"""

from __future__ import annotations

from _prelude import *


class 布尔异或_client_运算符_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_节点图开始(self):
        条件A: "布尔值" = 是否相等(self.game, 输入1=1, 输入2=1)
        条件B: "布尔值" = 是否相等(self.game, 输入1=1, 输入2=0)

        if 条件A ^ 条件B:
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_bool_xor_client_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_numeric_compare_is_rewritten_in_if_server(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_numeric_compare_if_ok
graph_name: 数值比较_if_自动改写_通过
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 数值比较_if_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        A: "整数" = 加法运算(self.game, 左值=2, 右值=0)
        B: "整数" = 加法运算(self.game, 左值=1, 右值=0)

        if A > B:
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_numeric_compare_if_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_numeric_compare_is_rewritten_in_if_client(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_numeric_compare_if_client_ok
graph_name: 数值比较_if_client_自动改写_通过
graph_type: client
"""

from __future__ import annotations

from _prelude import *


class 数值比较_if_client_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_节点图开始(self):
        A: "整数" = 加法运算(self.game, 左值=2, 右值=0)
        B: "整数" = 加法运算(self.game, 左值=1, 右值=0)

        if A > B:
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_numeric_compare_if_client_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_boolop_and_is_rewritten_and_allowed_client(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_boolop_and_client_ok
graph_name: and_client_自动改写_通过
graph_type: client
"""

from __future__ import annotations

from _prelude import *


class and_client_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_节点图开始(self):
        条件1: "布尔值" = 是否相等(self.game, 输入1=1, 输入2=1)
        条件2: "布尔值" = 是否相等(self.game, 输入1=1, 输入2=1)

        if 条件1 and 条件2:
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_boolop_and_client_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_augassign_is_rewritten_and_allowed(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_augassign_ok
graph_name: 增量赋值_自动改写_通过
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 增量赋值_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        计数: "整数" = 加法运算(self.game, 左值=0, 右值=0)
        计数 += 1

        if 是否相等(self.game, 输入1=计数, 输入2=1):
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_augassign_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_binop_add_is_rewritten_and_allowed(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_binop_add_ok
graph_name: 二元运算加法_自动改写_通过
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 二元运算加法_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        整数A: "整数" = 加法运算(self.game, 左值=1, 右值=2)
        整数B: "整数" = 加法运算(self.game, 左值=3, 右值=4)
        结果: "整数" = 整数A + 整数B

        if 是否相等(self.game, 输入1=结果, 输入2=10):
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_binop_add_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"

