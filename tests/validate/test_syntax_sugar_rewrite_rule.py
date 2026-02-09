from __future__ import annotations

import ast
from pathlib import Path

from engine.graph.utils.syntax_sugar_rewriter import rewrite_graph_code_syntax_sugars
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


def test_bit_read_fold_form1_is_rewritten_to_single_node_call_server() -> None:
    source = '''
from __future__ import annotations


class 按位读出折叠_形态1:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        值: "整数" = 255
        起始位: "整数" = 2
        结束位: "整数" = 5
        结果: "整数" = ((值 >> 起始位) & ((1 << (结束位 - 起始位 + 1)) - 1))
        return
'''
    tree = ast.parse(source)
    rewritten_tree, rewrite_issues = rewrite_graph_code_syntax_sugars(tree, scope="server")
    assert not rewrite_issues

    rewritten_text = ast.unparse(rewritten_tree)
    assert rewritten_text.count("按位读出(") == 1
    assert "按位与(" not in rewritten_text
    assert "右移运算(" not in rewritten_text
    assert "左移运算(" not in rewritten_text


def test_bit_read_fold_form2_is_rewritten_to_single_node_call_server() -> None:
    source = '''
from __future__ import annotations


class 按位读出折叠_形态2:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        值: "整数" = 255
        起始位: "整数" = 2
        结束位: "整数" = 5
        结果: "整数" = ((值 & (((1 << (结束位 - 起始位 + 1)) - 1) << 起始位)) >> 起始位)
        return
'''
    tree = ast.parse(source)
    rewritten_tree, rewrite_issues = rewrite_graph_code_syntax_sugars(tree, scope="server")
    assert not rewrite_issues

    rewritten_text = ast.unparse(rewritten_tree)
    assert rewritten_text.count("按位读出(") == 1
    assert "按位与(" not in rewritten_text
    assert "右移运算(" not in rewritten_text
    assert "左移运算(" not in rewritten_text


def test_bit_write_fold_inline_is_rewritten_to_single_node_call_server() -> None:
    source = '''
from __future__ import annotations


class 按位写入折叠_内联:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        被写入值: "整数" = 0
        写入值: "整数" = 3
        起始位: "整数" = 2
        结束位: "整数" = 5
        结果: "整数" = (被写入值 & ~(((1 << (结束位 - 起始位 + 1)) - 1) << 起始位)) | (写入值 << 起始位)
        return
'''
    tree = ast.parse(source)
    rewritten_tree, rewrite_issues = rewrite_graph_code_syntax_sugars(tree, scope="server")
    assert not rewrite_issues

    rewritten_text = ast.unparse(rewritten_tree)
    assert rewritten_text.count("按位写入(") == 1
    assert "按位与(" not in rewritten_text
    assert "按位或(" not in rewritten_text
    assert "按位取补运算(" not in rewritten_text
    assert "左移运算(" not in rewritten_text


def test_bit_write_fold_two_step_template_is_rewritten_to_single_node_call_server() -> None:
    source = '''
from __future__ import annotations


class 按位写入折叠_两步模板:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        被写入值: "整数" = 0
        写入值: "整数" = 3
        起始位: "整数" = 2
        结束位: "整数" = 5

        掩码: "整数" = (((1 << (结束位 - 起始位 + 1)) - 1) << 起始位)
        结果: "整数" = (被写入值 & ~掩码) | (写入值 << 起始位)
        return
'''
    tree = ast.parse(source)
    rewritten_tree, rewrite_issues = rewrite_graph_code_syntax_sugars(tree, scope="server")
    assert not rewrite_issues

    rewritten_text = ast.unparse(rewritten_tree)
    assert rewritten_text.count("按位写入(") == 1
    assert "掩码" not in rewritten_text
    assert "按位与(" not in rewritten_text
    assert "按位或(" not in rewritten_text
    assert "按位取补运算(" not in rewritten_text
    assert "左移运算(" not in rewritten_text


def test_mod_operator_is_rewritten_to_positive_mod_template_server_when_shared_composite_disabled() -> None:
    source = '''
from __future__ import annotations


class 正模_百分号_自动改写:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        a: "整数" = -1
        b: "整数" = 4
        r: "整数" = a % b
        return
'''
    tree = ast.parse(source)
    rewritten_tree, rewrite_issues = rewrite_graph_code_syntax_sugars(tree, scope="server", enable_shared_composite_sugars=False)
    assert not rewrite_issues

    rewritten_text = ast.unparse(rewritten_tree)
    assert "%" not in rewritten_text
    assert rewritten_text.count("模运算(") == 2
    assert rewritten_text.count("加法运算(") == 1


def test_mod_operator_is_rewritten_to_shared_positive_mod_composite_call_server() -> None:
    source = '''
from __future__ import annotations


class 正模_百分号_共享复合_自动改写:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        a: "整数" = -1
        b: "整数" = 4
        r: "整数" = a % b
        return
'''
    tree = ast.parse(source)
    rewritten_tree, rewrite_issues = rewrite_graph_code_syntax_sugars(tree, scope="server", enable_shared_composite_sugars=True)
    assert not rewrite_issues

    rewritten_text = ast.unparse(rewritten_tree)
    assert "%" not in rewritten_text
    assert rewritten_text.count("整数_正模运算(") == 1
    assert rewritten_text.count("_共享复合_整数_正模运算") >= 2  # __init__ 注入 + 调用点
    assert rewritten_text.count(".计算(") == 1
    assert "模运算(self.game" not in rewritten_text
    assert "加法运算(" not in rewritten_text


def test_mod_node_call_is_not_rewritten_server() -> None:
    source = '''
from __future__ import annotations


class 正模_显式模运算节点调用_保持原语义:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        a: "整数" = -1
        r: "整数" = 模运算(self.game, 被模数=a, 模数=4)
        return
'''
    tree = ast.parse(source)
    rewritten_tree, rewrite_issues = rewrite_graph_code_syntax_sugars(tree, scope="server", enable_shared_composite_sugars=True)
    assert not rewrite_issues

    rewritten_text = ast.unparse(rewritten_tree)
    assert rewritten_text.count("模运算(") == 1
    assert "加法运算(" not in rewritten_text
    assert "_共享复合_整数_正模运算" not in rewritten_text


def test_random_random_is_rewritten_and_allowed_server(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_random_random_ok
graph_name: random_random_自动改写_通过
graph_type: server
"""

from __future__ import annotations

import random

from _prelude import *


class random_random_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        随机值: "浮点数" = random.random()

        if 是否相等(self.game, 输入1=随机值, 输入2=随机值):
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_random_random_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_random_random_is_rewritten_and_allowed_client(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_random_random_client_ok
graph_name: random_random_client_自动改写_通过
graph_type: client
"""

from __future__ import annotations

import random

from _prelude import *


class random_random_client_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_节点图开始(self):
        随机值: "浮点数" = random.random()

        if 是否相等(self.game, 输入1=随机值, 输入2=随机值):
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_random_random_client_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_time_time_is_rewritten_and_allowed_server(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_time_time_ok
graph_name: time_time_自动改写_通过
graph_type: server
"""

from __future__ import annotations

import time

from _prelude import *


class time_time_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        时间戳: "整数" = time.time()

        if 是否相等(self.game, 输入1=时间戳, 输入2=时间戳):
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_time_time_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_datetime_fromtimestamp_is_rewritten_and_allowed_server(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_datetime_fromtimestamp_ok
graph_name: datetime_fromtimestamp_自动改写_通过
graph_type: server
"""

from __future__ import annotations

from datetime import datetime

from _prelude import *


class datetime_fromtimestamp_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        年: "整数"
        月: "整数"
        日: "整数"
        时: "整数"
        分: "整数"
        秒: "整数"
        年, 月, 日, 时, 分, 秒 = datetime.fromtimestamp(0)

        if 是否相等(self.game, 输入1=年, 输入2=年):
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_datetime_fromtimestamp_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_datetime_isoweekday_is_rewritten_and_allowed_server(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_datetime_isoweekday_ok
graph_name: datetime_isoweekday_自动改写_通过
graph_type: server
"""

from __future__ import annotations

from datetime import datetime

from _prelude import *


class datetime_isoweekday_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        星期: "整数" = datetime.fromtimestamp(0).isoweekday()

        if 是否相等(self.game, 输入1=星期, 输入2=星期):
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_datetime_isoweekday_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_datetime_weekday_plus_one_is_rewritten_and_allowed_server(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_datetime_weekday_plus_one_ok
graph_name: datetime_weekday_plus_one_自动改写_通过
graph_type: server
"""

from __future__ import annotations

from datetime import datetime

from _prelude import *


class datetime_weekday_plus_one_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        星期: "整数" = datetime.fromtimestamp(0).weekday() + 1

        if 是否相等(self.game, 输入1=星期, 输入2=星期):
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_datetime_weekday_plus_one_ok.py", graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    error_codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert not error_codes, f"期望无错误，但得到: {error_codes}"


def test_datetime_timestamp_is_rewritten_and_allowed_server(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_datetime_timestamp_ok
graph_name: datetime_timestamp_自动改写_通过
graph_type: server
"""

from __future__ import annotations

from datetime import datetime

from _prelude import *


class datetime_timestamp_自动改写_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        时间戳: "整数" = datetime(2025, 1, 2, 3, 4, 5).timestamp()

        if 是否相等(self.game, 输入1=时间戳, 输入2=时间戳):
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_datetime_timestamp_ok.py", graph_code)

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


