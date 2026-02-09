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


def test_dict_literal_rewrite_allows_non_empty_dict_in_method_body(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_dict_literal_ok
graph_name: 字典字面量_自动拼装_通过
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 字典字面量_自动拼装_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        字典示例: "字符串-整数字典" = {"a": 1, "b": 2}
        是否包含: "布尔值" = 查询字典是否包含特定键(self.game, 字典=字典示例, 键="a")
        if 是否包含:
            return
        return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_dict_literal_ok.py", graph_code)

    report = validate_files(
        [graph_path],
        workspace,
        strict_entity_wire_only=False,
        use_cache=False,
    )
    error_issues = [issue for issue in report.issues if issue.level == "error"]
    assert not error_issues, f"期望无错误，但得到: {[i.code for i in error_issues]}"


def test_empty_dict_literal_is_forbidden(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_empty_dict_literal_forbidden
graph_name: 空字典字面量_禁止
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 空字典字面量_禁止:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        空字典: "字符串-整数字典" = {}
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_empty_dict_literal_forbidden.py", graph_code)

    report = validate_files(
        [graph_path],
        workspace,
        strict_entity_wire_only=False,
        use_cache=False,
    )
    codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert "CODE_EMPTY_DICT_LITERAL_FORBIDDEN" in codes


def test_dict_literal_too_long_is_forbidden(tmp_path: Path) -> None:
    pairs = ", ".join(f'"k{i}": {i}' for i in range(51))
    graph_code = f'''
"""
graph_id: graph_dict_literal_too_long_forbidden
graph_name: 字典字面量_超过上限_禁止
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 字典字面量_超过上限_禁止:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        过长字典: "字符串-整数字典" = {{{pairs}}}
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_dict_literal_too_long_forbidden.py", graph_code)

    report = validate_files(
        [graph_path],
        workspace,
        strict_entity_wire_only=False,
        use_cache=False,
    )
    codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert "CODE_DICT_LITERAL_TOO_LONG" in codes


def test_for_in_dict_literal_is_forbidden(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_for_in_dict_literal_forbidden
graph_name: for_in_字典字面量_禁止
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class for_in_字典字面量_禁止:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        for 当前元素 in {"a": 1, "b": 2}:
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_for_in_dict_literal_forbidden.py", graph_code)

    report = validate_files(
        [graph_path],
        workspace,
        strict_entity_wire_only=False,
        use_cache=False,
    )
    codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert "CODE_DICT_LITERAL_FOR_ITER_FORBIDDEN" in codes


def test_dict_literal_enforces_same_type_for_keys(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_dict_literal_same_type_keys_required
graph_name: 字典字面量_键同型_报错
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 字典字面量_键同型_报错:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        字典: "字符串-整数字典" = {"a": 1, 2: 2}
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_dict_literal_same_type_keys_required.py", graph_code)

    report = validate_files(
        [graph_path],
        workspace,
        strict_entity_wire_only=False,
        use_cache=False,
    )
    codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert "PORT_SAME_TYPE_REQUIRED" in codes


def test_dict_literal_enforces_key_generic_constraints(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_dict_literal_key_constraint_violation
graph_name: 字典字面量_键约束_报错
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 字典字面量_键约束_报错:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        字典: "字符串-整数字典" = {True: 1}
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_dict_literal_key_constraint_violation.py", graph_code)

    report = validate_files(
        [graph_path],
        workspace,
        strict_entity_wire_only=False,
        use_cache=False,
    )
    codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert "PORT_GENERIC_CONSTRAINT_VIOLATION" in codes


