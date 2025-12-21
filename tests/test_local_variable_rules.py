from __future__ import annotations

from pathlib import Path

from engine.validate.api import validate_files


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _write_graph_code(tmp_dir: Path, filename: str, source: str) -> Path:
    target = tmp_dir / filename
    target.write_text(source, encoding="utf-8")
    return target


def test_local_variable_without_initial_value_in_graph_reports_issue(tmp_path: Path) -> None:
    """Graph Code 中显式使用【获取局部变量】但未提供『初始值』时，应报错。"""
    graph_code = '''
""" 
graph_id: graph_local_var_missing_initial
graph_name: 局部变量缺少初始值_图
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 局部变量缺少初始值_图:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        局部句柄, 当前值 = 获取局部变量(self.game)
        设置局部变量(self.game, 局部变量=局部句柄, 值=1)
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_local_var_missing_initial.py", graph_code)

    report = validate_files(
        [graph_path],
        workspace,
        strict_entity_wire_only=False,
        use_cache=False,
    )
    issues = [issue for issue in report.issues if issue.code == "CODE_LOCAL_VAR_INITIAL_REQUIRED"]

    assert issues, "显式使用【获取局部变量】但未提供『初始值』时，应报局部变量初始值缺失错误"


def test_local_variable_with_initial_value_in_graph_is_ok(tmp_path: Path) -> None:
    """Graph Code 中【获取局部变量】提供了『初始值』时，不应报本规则错误。"""
    graph_code = '''
""" 
graph_id: graph_local_var_with_initial
graph_name: 局部变量有初始值_图
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 局部变量有初始值_图:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        局部句柄, 当前值 = 获取局部变量(self.game, 初始值=0)
        设置局部变量(self.game, 局部变量=局部句柄, 值=1)
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_local_var_with_initial.py", graph_code)

    report = validate_files(
        [graph_path],
        workspace,
        strict_entity_wire_only=False,
        use_cache=False,
    )
    issues = [issue for issue in report.issues if issue.code == "CODE_LOCAL_VAR_INITIAL_REQUIRED"]

    assert not issues, "【获取局部变量】已提供『初始值』时，不应触发局部变量初始值缺失错误"


def test_local_variable_without_initial_value_in_composite_reports_issue(tmp_path: Path) -> None:
    """复合节点类格式中使用【获取局部变量】但未提供『初始值』时，应报错。"""
    composite_code = '''
"""
composite_id: composite_local_var_missing_initial
composite_name: 复合_局部变量缺少初始值
description: 用于验证复合节点中的局部变量初始值校验规则
scope: server
"""

from runtime.engine.graph_prelude_server import *
from engine.nodes.composite_spec import composite_class, data_method


@composite_class
class 复合_局部变量缺少初始值:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    @data_method(
        inputs=[],
        outputs=[("结果", "整数")],
    )
    def 计算(self):
        局部句柄, 当前值 = 获取局部变量(self.game)
        设置局部变量(self.game, 局部变量=局部句柄, 值=1)
        return 当前值
'''
    workspace = _workspace_root()
    composite_path = _write_graph_code(
        tmp_path,
        "composite_local_var_missing_initial.py",
        composite_code,
    )

    report = validate_files(
        [composite_path],
        workspace,
        strict_entity_wire_only=False,
        use_cache=False,
    )
    issues = [issue for issue in report.issues if issue.code == "CODE_LOCAL_VAR_INITIAL_REQUIRED"]

    assert issues, "复合节点中使用【获取局部变量】但未提供『初始值』时，应报局部变量初始值缺失错误"


def test_local_variable_missing_game_arg_reports_issue(tmp_path: Path) -> None:
    """Graph Code 中【获取局部变量】若未显式传入 self.game/game，应报错（避免绕过节点调用启发式）。"""
    graph_code = '''
""" 
graph_id: graph_local_var_missing_game_arg
graph_name: 局部变量缺少game参数_图
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 局部变量缺少game参数_图:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        局部句柄, 当前值 = 获取局部变量(初始值=0)
        设置局部变量(self.game, 局部变量=局部句柄, 值=1)
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_local_var_missing_game_arg.py", graph_code)
    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    issues = [issue for issue in report.issues if issue.code == "CODE_NODE_CALL_GAME_REQUIRED"]
    assert issues, "已知节点【获取局部变量】未显式传入 self.game/game 时，应报缺少 game 参数错误"


def test_local_variable_result_not_selected_reports_issue(tmp_path: Path) -> None:
    """Graph Code 中【获取局部变量】若将二元返回值当作单值使用，应报错。"""
    graph_code = '''
""" 
graph_id: graph_local_var_output_not_selected
graph_name: 局部变量未选择输出_图
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 局部变量未选择输出_图:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        当前值 = 获取局部变量(self.game, 初始值=0)
        log_info(str(当前值))
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_local_var_output_not_selected.py", graph_code)
    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    issues = [
        issue
        for issue in report.issues
        if issue.code == "CODE_LOCAL_VAR_OUTPUT_SELECTION_REQUIRED"
    ]
    assert issues, "【获取局部变量】未选择输出（未解包/未下标）时，应报错"


def test_local_variable_subscript_select_output_is_ok(tmp_path: Path) -> None:
    """Graph Code 中允许通过下标显式选择【获取局部变量】的输出端口。"""
    graph_code = '''
""" 
graph_id: graph_local_var_subscript_select_output
graph_name: 局部变量下标选择输出_图
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 局部变量下标选择输出_图:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        当前值 = 获取局部变量(self.game, 初始值=0)[1]
        log_info(str(当前值))
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_local_var_subscript_select_output.py", graph_code)
    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    blocked_codes = {
        "CODE_NODE_CALL_GAME_REQUIRED",
        "CODE_LOCAL_VAR_OUTPUT_SELECTION_REQUIRED",
        "CODE_LOCAL_VAR_OUTPUT_INDEX_INVALID",
    }
    issues = [issue for issue in report.issues if issue.code in blocked_codes]
    assert not issues, "下标选择输出的写法不应触发【获取局部变量】用法校验错误"


def test_known_node_call_missing_game_reports_issue(tmp_path: Path) -> None:
    """Graph Code 中，只要函数名在节点库里，就必须显式传入 self.game/game。"""
    graph_code = '''
""" 
graph_id: graph_known_node_missing_game_arg
graph_name: 已知节点缺少game参数_图
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 已知节点缺少game参数_图:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        消失延迟秒数: "浮点数" = 获取节点图变量(变量名="消失延迟秒数")
        log_info(str(消失延迟秒数))
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_known_node_missing_game_arg.py", graph_code)
    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    issues = [issue for issue in report.issues if issue.code == "CODE_NODE_CALL_GAME_REQUIRED"]
    assert issues, "已知节点调用漏传 self.game/game 时，应触发通用 game 参数校验"


