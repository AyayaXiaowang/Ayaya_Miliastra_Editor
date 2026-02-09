from __future__ import annotations

from pathlib import Path

from engine.validate.api import validate_files
from tests._helpers.project_paths import get_repo_root


def _workspace_root() -> Path:
    return get_repo_root()


def _make_temp_graph_code(tmp_dir: Path, code: str) -> Path:
    target = tmp_dir / "temp_event_handler_signature_graph.py"
    target.write_text(code, encoding="utf-8")
    return target


def test_builtin_event_handler_signature_missing_param_is_reported(tmp_path: Path) -> None:
    """内置事件（如 选项卡选中时）回调参数缺失/错名时应报错（避免运行期 kwargs 绑定失败）。"""
    graph_code = '''
"""
graph_id: test_event_handler_signature_missing_param
graph_name: 事件回调签名校验_缺参应报错
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 事件回调签名校验_缺参应报错:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    # 故意使用与事件节点输出端口不一致的参数名/数量（缺少“事件源实体”“选择者实体”等）
    def on_选项卡选中时(self, 选中者实体, 选中者实体GUID, 选项卡序号):
        return

    def register_handlers(self):
        self.game.register_event_handler(
            "选项卡选中时",
            self.on_选项卡选中时,
            owner=self.owner_entity,
        )
'''
    workspace = _workspace_root()
    graph_path = _make_temp_graph_code(tmp_path, graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    mismatch_issues = [
        issue for issue in report.issues if issue.code == "CODE_EVENT_HANDLER_SIGNATURE_MISMATCH"
    ]
    assert mismatch_issues, "应当检测到内置事件回调签名不匹配（缺参/错名）"


def test_builtin_event_handler_signature_exact_match_passes(tmp_path: Path) -> None:
    """内置事件回调参数与事件节点输出端口一致（剔除流程端口）时不应报错。"""
    graph_code = '''
"""
graph_id: test_event_handler_signature_exact_match
graph_name: 事件回调签名校验_一致不报错
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 事件回调签名校验_一致不报错:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    # 参数名与事件节点输出端口一致（剔除流程端口）
    def on_选项卡选中时(self, 事件源实体, 事件源GUID, 选项卡序号, 选择者实体):
        return

    def register_handlers(self):
        self.game.register_event_handler(
            "选项卡选中时",
            self.on_选项卡选中时,
            owner=self.owner_entity,
        )
'''
    workspace = _workspace_root()
    graph_path = _make_temp_graph_code(tmp_path, graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    mismatch_issues = [
        issue for issue in report.issues if issue.code == "CODE_EVENT_HANDLER_SIGNATURE_MISMATCH"
    ]
    assert not mismatch_issues


def test_builtin_event_handler_signature_wrong_param_name_is_reported(tmp_path: Path) -> None:
    """内置事件回调参数数量一致但参数名不匹配时也应报错（避免 kwargs 绑定失败或语义歧义）。"""
    graph_code = '''
"""
graph_id: test_event_handler_signature_wrong_param_name
graph_name: 事件回调签名校验_错名应报错
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 事件回调签名校验_错名应报错:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    # “选择者实体”写成了“选中者实体”（数量一致但参数名不匹配）
    def on_选项卡选中时(self, 事件源实体, 事件源GUID, 选项卡序号, 选中者实体):
        return

    def register_handlers(self):
        self.game.register_event_handler(
            "选项卡选中时",
            self.on_选项卡选中时,
            owner=self.owner_entity,
        )
'''
    workspace = _workspace_root()
    graph_path = _make_temp_graph_code(tmp_path, graph_code)

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    mismatch_issues = [
        issue for issue in report.issues if issue.code == "CODE_EVENT_HANDLER_SIGNATURE_MISMATCH"
    ]
    assert mismatch_issues


