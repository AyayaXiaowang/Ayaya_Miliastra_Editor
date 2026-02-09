from __future__ import annotations

from pathlib import Path

from engine.validate.api import validate_files
from tests._helpers.project_paths import get_repo_root


def _workspace_root() -> Path:
    return get_repo_root()


def _make_temp_graph_code(tmp_dir: Path, code: str) -> Path:
    target = tmp_dir / "temp_signal_graph.py"
    target.write_text(code, encoding="utf-8")
    return target


def _validate_in_example_package_scope(*, graph_path: Path, workspace: Path):
    # 该文件的用例依赖示例包下的信号定义（assets/资源库/项目存档/示例项目模板/管理配置/信号）。
    from engine.resources.definition_schema_view import set_default_definition_schema_view_active_package_id
    from engine.signal import invalidate_default_signal_repository_cache
    from engine.utils.runtime_scope import set_active_package_id

    set_active_package_id("示例项目模板")
    set_default_definition_schema_view_active_package_id("示例项目模板")
    invalidate_default_signal_repository_cache()
    try:
        return validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    finally:
        set_active_package_id(None)
        set_default_definition_schema_view_active_package_id(None)
        invalidate_default_signal_repository_cache()


def test_send_signal_with_unknown_param_produces_error(tmp_path: Path) -> None:
    """发送信号使用信号定义中不存在的参数名时，应在代码级校验阶段报错。"""
    # 使用已存在的信号『名称』，参数名刻意写错一个。
    graph_code = '''
""" 
graph_id: test_signal_extra_param
graph_name: 信号参数名校验_额外参数
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 信号参数名校验_额外参数:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        自身实体: "实体" = 获取自身实体(self.game)
        发送信号(
            self.game,
            信号名="测试信号_全部参数类型",
            不存在的参数=1,
        )
'''
    workspace = _workspace_root()
    graph_path = _make_temp_graph_code(tmp_path, graph_code)

    report = _validate_in_example_package_scope(graph_path=graph_path, workspace=workspace)
    extra_param_issues = [
        issue
        for issue in report.issues
        if issue.code == "CODE_SIGNAL_EXTRA_PARAMS"
    ]
    assert extra_param_issues, "应当检测到发送信号中存在未在信号定义中声明的参数名"


def test_send_signal_with_only_defined_params_passes(tmp_path: Path) -> None:
    """发送信号仅使用信号定义中存在的参数名，且“信号名”使用信号名称时，不应触发参数名错误。"""
    graph_code = '''
""" 
graph_id: test_signal_params_ok
graph_name: 信号参数名校验_合法参数
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 信号参数名校验_合法参数:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        自身实体: "实体" = 获取自身实体(self.game)
        发送信号(
            self.game,
            信号名="测试信号_全部参数类型",
            整数参数=1,
        )
'''
    workspace = _workspace_root()
    graph_path = _make_temp_graph_code(tmp_path, graph_code)

    report = _validate_in_example_package_scope(graph_path=graph_path, workspace=workspace)
    # 允许有其他规则报出的错误或警告，这里只要求“额外参数名”错误不存在。
    extra_param_issues = [
        issue
        for issue in report.issues
        if issue.code == "CODE_SIGNAL_EXTRA_PARAMS"
    ]
    assert not extra_param_issues


def test_send_signal_with_signal_id_as_name_produces_error(tmp_path: Path) -> None:
    """当“信号名”参数填写的是信号 ID 而非名称时，应在代码级校验阶段报错。"""
    graph_code = '''
""" 
graph_id: test_signal_use_id_as_name
graph_name: 信号名校验_误用ID
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 信号名校验_误用ID:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        自身实体: "实体" = 获取自身实体(self.game)
        发送信号(
            self.game,
            信号名="signal_all_supported_types_example",
            整数参数=1,
        )
'''
    workspace = _workspace_root()
    graph_path = _make_temp_graph_code(tmp_path, graph_code)

    report = _validate_in_example_package_scope(graph_path=graph_path, workspace=workspace)
    id_not_allowed_issues = [
        issue
        for issue in report.issues
        if issue.code == "CODE_SIGNAL_ID_NOT_ALLOWED"
    ]
    assert id_not_allowed_issues, "应当检测到“信号名”参数误用了信号 ID 而不是名称"



