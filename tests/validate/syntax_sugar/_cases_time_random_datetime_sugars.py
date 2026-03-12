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

