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


def test_dict_subscript_load_is_rewritten_and_allowed_server(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_dict_subscript_load_ok
graph_name: 字典下标读取_自动改写_通过
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 字典下标读取_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        字典: "字符串-整数字典" = {"a": 1}
        键: "字符串" = "a"
        值: "整数" = 字典[键]

        if 是否相等(self.game, 输入1=值, 输入2=1):
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_dict_subscript_load_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_dict_get_is_rewritten_and_allowed_server(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_dict_get_ok
graph_name: 字典get_自动改写_通过
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 字典get_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        字典: "字符串-整数字典" = {"a": 1}
        键: "字符串" = "a"
        值: "整数" = 字典.get(键)

        if 是否相等(self.game, 输入1=值, 输入2=1):
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_dict_get_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_dict_get_is_rewritten_and_allowed_client(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_dict_get_client_ok
graph_name: 字典get_client_自动改写_通过
graph_type: client
"""

from __future__ import annotations

from _prelude import *


class 字典get_client_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_节点图开始(self):
        # client 侧缺少【拼装字典】节点，因此这里用【获取自定义变量】拿到一个字典值作为输入来源。
        字典: "字符串-整数字典" = 获取自定义变量(self.game, 目标实体=self.owner_entity, 变量名="测试字典")
        键: "字符串" = "a"
        值: "整数" = 字典.get(键)

        if 是否相等(self.game, 输入1=值, 输入2=1):
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_dict_get_client_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_dict_subscript_assign_is_rewritten_and_allowed_server(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_dict_subscript_assign_ok
graph_name: 字典下标写入_自动改写_通过
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 字典下标写入_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        字典: "字符串-整数字典" = {"a": 1}
        键: "字符串" = "b"
        新值: "整数" = 加法运算(self.game, 左值=1, 右值=1)

        字典[键] = 新值
        return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_dict_subscript_assign_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_dict_pop_is_rewritten_and_allowed_server(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_dict_pop_ok
graph_name: 字典pop_自动改写_通过
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 字典pop_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        字典: "字符串-整数字典" = {"a": 1, "b": 2}
        键: "字符串" = "a"
        字典.pop(键)
        return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_dict_pop_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_del_dict_subscript_is_rewritten_and_allowed_server(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_del_dict_subscript_ok
graph_name: del_字典下标_自动改写_通过
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class del_字典下标_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        字典: "字符串-整数字典" = {"a": 1}
        键: "字符串" = "a"

        del 字典[键]
        return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_del_dict_subscript_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_in_dict_compare_is_rewritten_and_allowed_server(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_in_dict_ok
graph_name: in_字典_自动改写_通过
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class in_字典_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        字典: "字符串-整数字典" = {"a": 1}
        键: "字符串" = "a"

        if 键 in 字典:
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_in_dict_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"

