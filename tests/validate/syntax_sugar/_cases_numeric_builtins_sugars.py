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


def test_print_is_rewritten_and_allowed_server(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_print_ok
graph_name: print_自动改写_通过
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class print_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        计数: "整数" = 加法运算(self.game, 左值=1, 右值=0)
        print(计数)
        print("hello")
        return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_print_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_pow_is_rewritten_and_allowed_server(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_pow_ok
graph_name: pow_自动改写_通过
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class pow_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        底数: "整数" = 加法运算(self.game, 左值=2, 右值=0)
        指数: "整数" = 加法运算(self.game, 左值=3, 右值=0)
        结果: "整数" = pow(底数, 指数)

        if 是否相等(self.game, 输入1=结果, 输入2=8):
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_pow_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_math_pow_is_rewritten_and_allowed_server(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_math_pow_ok
graph_name: math_pow_自动改写_通过
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class math_pow_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        底数: "浮点数" = 加法运算(self.game, 左值=2.0, 右值=0.0)
        指数: "浮点数" = 加法运算(self.game, 左值=3.0, 右值=0.0)
        结果: "浮点数" = math.pow(底数, 指数)

        if 是否相等(self.game, 输入1=结果, 输入2=8.0):
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_math_pow_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_math_fabs_is_rewritten_and_allowed_server(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_math_fabs_ok
graph_name: math_fabs_自动改写_通过
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class math_fabs_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        负数: "浮点数" = 减法运算(self.game, 左值=0.0, 右值=1.0)
        结果: "浮点数" = math.fabs(负数)

        if 是否相等(self.game, 输入1=结果, 输入2=1.0):
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_math_fabs_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_math_fabs_is_rewritten_and_allowed_client(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_math_fabs_client_ok
graph_name: math_fabs_client_自动改写_通过
graph_type: client
"""

from __future__ import annotations

from _prelude import *


class math_fabs_client_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_节点图开始(self):
        负数: "浮点数" = 减法运算(self.game, 左值=0.0, 右值=1.0)
        结果: "浮点数" = math.fabs(负数)

        if 是否相等(self.game, 输入1=结果, 输入2=1.0):
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_math_fabs_client_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_max_min_list_are_rewritten_and_allowed_server(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_max_min_list_ok
graph_name: max_min_列表_自动改写_通过
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class max_min_列表_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        整数列表: "整数列表" = [1, 2, 3]
        最大值: "整数" = max(整数列表)
        最小值: "整数" = min(整数列表)

        if 是否相等(self.game, 输入1=最大值, 输入2=3):
            return
        if 是否相等(self.game, 输入1=最小值, 输入2=1):
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_max_min_list_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_max_two_args_is_rewritten_and_allowed_client(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_max_two_args_client_ok
graph_name: max_两参数_client_自动改写_通过
graph_type: client
"""

from __future__ import annotations

from _prelude import *


class max_两参数_client_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_节点图开始(self):
        A: "整数" = 加法运算(self.game, 左值=1, 右值=0)
        B: "整数" = 加法运算(self.game, 左值=2, 右值=0)
        最大值: "整数" = max(A, B)

        if 是否相等(self.game, 输入1=最大值, 输入2=2):
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_max_two_args_client_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_abs_is_rewritten_and_allowed_client(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_abs_client_ok
graph_name: abs_client_自动改写_通过
graph_type: client
"""

from __future__ import annotations

from _prelude import *


class abs_client_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_节点图开始(self):
        负数: "整数" = 减法运算(self.game, 左值=0, 右值=3)
        绝对值: "整数" = abs(负数)

        if 是否相等(self.game, 输入1=绝对值, 输入2=3):
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_abs_client_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_builtin_type_conversions_are_rewritten_and_allowed_server(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_type_conversions_ok
graph_name: 类型转换_内置函数_自动改写_通过
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 类型转换_内置函数_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        浮点值: "浮点数" = 加法运算(self.game, 左值=1.25, 右值=0.0)

        整数值: "整数" = int(浮点值)
        字符串值: "字符串" = str(整数值)
        布尔值: "布尔值" = bool(整数值)
        浮点值2: "浮点数" = float(整数值)

        if 是否相等(self.game, 输入1=整数值, 输入2=1):
            return
        if 是否相等(self.game, 输入1=字符串值, 输入2="1"):
            return
        if 布尔值:
            return
        if 浮点值2 > 0.0:
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_type_conversions_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_builtin_type_conversions_are_rewritten_and_allowed_client(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_type_conversions_client_ok
graph_name: 类型转换_内置函数_client_自动改写_通过
graph_type: client
"""

from __future__ import annotations

from _prelude import *


class 类型转换_内置函数_client_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_节点图开始(self):
        整数值: "整数" = 加法运算(self.game, 左值=1, 右值=0)
        字符串值: "字符串" = str(整数值)
        布尔值: "布尔值" = bool(整数值)

        if 是否相等(self.game, 输入1=字符串值, 输入2="1"):
            return
        if 布尔值:
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_type_conversions_client_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_round_floor_ceil_are_rewritten_and_allowed_server(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_rounding_ok
graph_name: 取整_内置函数_自动改写_通过
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 取整_内置函数_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        浮点值: "浮点数" = 加法运算(self.game, 左值=1.25, 右值=0.0)
        四舍五入结果: "整数" = round(浮点值)
        向下取整结果: "整数" = floor(浮点值)
        向上取整结果: "整数" = ceil(浮点值)

        if 是否相等(self.game, 输入1=四舍五入结果, 输入2=1):
            return
        if 是否相等(self.game, 输入1=向下取整结果, 输入2=1):
            return
        if 是否相等(self.game, 输入1=向上取整结果, 输入2=2):
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_rounding_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_round_is_forbidden_in_client(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_rounding_client_forbidden
graph_name: 取整_client_禁止
graph_type: client
"""

from __future__ import annotations

from _prelude import *


class 取整_client_禁止:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_节点图开始(self):
        浮点值: "浮点数" = 加法运算(self.game, 左值=1.25, 右值=0.0)
        结果: "整数" = round(浮点值)
        if 是否相等(self.game, 输入1=结果, 输入2=1):
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_rounding_client_forbidden.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert "CODE_ROUNDING_NOT_SUPPORTED_IN_CLIENT" in error_codes

