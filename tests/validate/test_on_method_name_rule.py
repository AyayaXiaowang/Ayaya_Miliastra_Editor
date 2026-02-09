from __future__ import annotations

from pathlib import Path

from engine.configs.settings import settings
from engine.validate.api import validate_files
from tests._helpers.project_paths import get_repo_root


def _workspace_root() -> Path:
    return get_repo_root()


def _make_temp_graph_code(tmp_dir: Path, code: str) -> Path:
    target = tmp_dir / "temp_on_method_name_graph.py"
    target.write_text(code, encoding="utf-8")
    return target


def test_unknown_on_method_name_is_reported_even_if_not_registered(tmp_path: Path) -> None:
    """只要定义了 def on_XXX，XXX 不是内置事件/已定义信号，就必须报错（即使没 register）。"""
    graph_code = '''
""" 
graph_id: test_on_method_unknown
graph_name: on_方法名校验_未知应报错
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class on_方法名校验_未知应报错:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_阿这(self, 事件源实体, 事件源GUID, 信号来源实体):
        return

    def register_handlers(self):
        return
'''
    workspace = _workspace_root()
    settings.set_config_path(workspace)
    graph_path = _make_temp_graph_code(tmp_path, graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    issues = [issue for issue in report.issues if issue.code == "CODE_ON_METHOD_NAME_UNKNOWN"]
    assert issues, "应当检测到 on_ 方法名使用了未定义事件/信号"


def test_builtin_event_on_method_name_is_allowed(tmp_path: Path) -> None:
    """on_<内置事件名> 允许存在（是否 register 由其他规则负责）。"""
    graph_code = '''
""" 
graph_id: test_on_method_builtin_ok
graph_name: on_方法名校验_内置事件允许
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class on_方法名校验_内置事件允许:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        return

    def register_handlers(self):
        return
'''
    workspace = _workspace_root()
    settings.set_config_path(workspace)
    graph_path = _make_temp_graph_code(tmp_path, graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    issues = [issue for issue in report.issues if issue.code == "CODE_ON_METHOD_NAME_UNKNOWN"]
    assert not issues


def test_signal_name_on_method_name_is_allowed(tmp_path: Path) -> None:
    """on_<信号名称> 允许存在。"""
    # 该用例依赖示例包下的信号定义（assets/资源库/项目存档/示例项目模板/管理配置/信号）。
    from engine.resources.definition_schema_view import set_default_definition_schema_view_active_package_id
    from engine.signal import invalidate_default_signal_repository_cache
    from engine.utils.runtime_scope import set_active_package_id

    graph_code = '''
""" 
graph_id: test_on_method_signal_name_ok
graph_name: on_方法名校验_信号名允许
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class on_方法名校验_信号名允许:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_测试信号_全部参数类型(self, 事件源实体, 事件源GUID, 信号来源实体):
        return

    def register_handlers(self):
        return
'''
    workspace = _workspace_root()
    settings.set_config_path(workspace)
    graph_path = _make_temp_graph_code(tmp_path, graph_code)

    set_active_package_id("示例项目模板")
    set_default_definition_schema_view_active_package_id("示例项目模板")
    invalidate_default_signal_repository_cache()
    try:
        report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
        issues = [issue for issue in report.issues if issue.code == "CODE_ON_METHOD_NAME_UNKNOWN"]
        assert not issues
    finally:
        set_active_package_id(None)
        set_default_definition_schema_view_active_package_id(None)
        invalidate_default_signal_repository_cache()


