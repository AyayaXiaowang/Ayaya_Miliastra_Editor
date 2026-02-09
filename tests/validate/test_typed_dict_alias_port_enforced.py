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


def test_typed_dict_alias_port_rejects_wrong_value_type(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_typed_dict_alias_port_value_type_mismatch
graph_name: 别名字典端口_键值类型不匹配_报错
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 别名字典端口_键值类型不匹配_报错:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        自身实体: "实体" = 获取自身实体(self.game)
        占位_配置ID: "配置ID" = 1000000001

        修改物品收购表中道具收购信息(
            self.game,
            商店归属者实体=自身实体,
            商店序号=1,
            商品道具配置ID=占位_配置ID,
            收购货币字典={占位_配置ID: "不是整数"},
            是否可收购=True,
        )
        return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(
        tmp_path, "graph_typed_dict_alias_port_value_type_mismatch.py", graph_code
    )

    report = validate_files(
        [graph_path],
        workspace,
        strict_entity_wire_only=False,
        use_cache=False,
    )
    codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert "PORT_TYPED_DICT_ALIAS_MISMATCH" in codes


def test_typed_dict_alias_port_accepts_config_id_to_int_dict(tmp_path: Path) -> None:
    graph_code = '''
"""
graph_id: graph_typed_dict_alias_port_ok
graph_name: 别名字典端口_配置ID整数字典_通过
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 别名字典端口_配置ID整数字典_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        自身实体: "实体" = 获取自身实体(self.game)
        占位_配置ID: "配置ID" = 1000000001

        修改物品收购表中道具收购信息(
            self.game,
            商店归属者实体=自身实体,
            商店序号=1,
            商品道具配置ID=占位_配置ID,
            收购货币字典={占位_配置ID: 2005},
            是否可收购=True,
        )
        return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_typed_dict_alias_port_ok.py", graph_code)

    report = validate_files(
        [graph_path],
        workspace,
        strict_entity_wire_only=False,
        use_cache=False,
    )
    error_issues = [issue for issue in report.issues if issue.level == "error"]
    assert not error_issues, f"期望无错误，但得到: {[i.code for i in error_issues]}"


