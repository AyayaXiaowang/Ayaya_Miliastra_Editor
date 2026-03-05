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


def test_custom_var_redundant_init_on_entity_created_reports_warning(tmp_path: Path) -> None:
    """on_实体创建时 中对【设置自定义变量】写入常量初始值应给出 warning。"""
    graph_code = '''
"""
graph_id: custom_var_redundant_init_on_entity_created_01
graph_name: 自定义变量冗余初始化提示_示例
graph_type: server
"""

from __future__ import annotations

from _prelude import *

自定义变量名_是否进行中: str = "锻刀英雄_冒险_是否进行中"
占位GUID: str = "1073742153"


class 自定义变量冗余初始化提示_示例:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        空列表: "GUID列表" = [事件源GUID]
        空列表.clear()

        设置自定义变量(self.game, 目标实体=事件源实体, 变量名=自定义变量名_是否进行中, 变量值=False, 是否触发事件=False)
        设置自定义变量(self.game, 目标实体=事件源实体, 变量名="锻刀英雄_冒险_当前玩家GUID", 变量值=占位GUID, 是否触发事件=False)
        设置自定义变量(self.game, 目标实体=事件源实体, 变量名="锻刀英雄_冒险_当前波次怪物实体列表", 变量值=空列表, 是否触发事件=False)
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(
        tmp_path,
        "custom_var_redundant_init_on_entity_created_01.py",
        graph_code,
    )
    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)

    hits = [issue for issue in report.issues if issue.code == "CODE_CUSTOM_VAR_REDUNDANT_INIT_ON_ENTITY_CREATED"]
    assert hits, "应产生 CODE_CUSTOM_VAR_REDUNDANT_INIT_ON_ENTITY_CREATED warning，用于提示 on_实体创建时 冗余初始化自定义变量"
    assert any(issue.level == "warning" for issue in hits)
    assert any("锻刀英雄_冒险_是否进行中" in issue.message for issue in hits)
    assert any("锻刀英雄_冒险_当前玩家GUID" in issue.message for issue in hits)
    assert any("锻刀英雄_冒险_当前波次怪物实体列表" in issue.message for issue in hits)


def test_custom_var_redundant_init_on_entity_created_not_reported_when_value_not_constant(
    tmp_path: Path,
) -> None:
    """当写入值不可静态识别为常量初始值（例如来自节点输出）时，不应提示。"""
    graph_code = '''
"""
graph_id: custom_var_redundant_init_on_entity_created_02
graph_name: 自定义变量冗余初始化提示_不触发
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 自定义变量冗余初始化提示_不触发:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        当前击杀数: "整数" = 获取自定义变量(self.game, 目标实体=事件源实体, 变量名="击杀数")
        新击杀数: "整数" = 加法运算(self.game, 左值=当前击杀数, 右值=1)
        设置自定义变量(self.game, 目标实体=事件源实体, 变量名="击杀数", 变量值=新击杀数, 是否触发事件=False)
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(
        tmp_path,
        "custom_var_redundant_init_on_entity_created_02.py",
        graph_code,
    )
    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)

    hits = [issue for issue in report.issues if issue.code == "CODE_CUSTOM_VAR_REDUNDANT_INIT_ON_ENTITY_CREATED"]
    assert not hits, "写入值不可静态识别为常量初始值时，不应产生冗余初始化提示"


