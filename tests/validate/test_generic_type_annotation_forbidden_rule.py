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


def test_generic_type_annotation_in_typed_dict_is_forbidden(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_generic_type_annotation_forbidden
graph_name: 显式泛型注解_必须报错
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 显式泛型注解_必须报错:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        # 违规：显式类型注解中包含“泛型家族”占位类型（这里是值类型为『泛型字典』）
        测试字典: "字符串-泛型字典" = {"a": 1}
        长度: "整数" = len(测试字典)
        if 是否相等(self.game, 输入1=长度, 输入2=1):
            return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(
        tmp_path,
        "graph_generic_type_annotation_forbidden.py",
        graph_code,
    )

    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)
    issues = [issue for issue in report.issues if issue.code == "CODE_GENERIC_TYPE_ANNOTATION_FORBIDDEN"]
    assert issues, "显式类型注解中包含泛型家族（如『字符串-泛型字典』）时应报错"


