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


def test_dict_mutation_requires_graph_var_reports_error(tmp_path: Path) -> None:
    """字典来自【拼装字典/建立字典】且被执行节点修改后仍复用，应报错并引导改用节点图变量。"""
    graph_code = '''
"""
graph_id: graph_dict_mutation_requires_graph_var_bad
graph_name: 字典写回语义_局部_禁止
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 字典写回语义_局部_禁止:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        价格表: "字符串-整数字典" = {"a": 1, "b": 2}
        对字典设置或新增键值对(self.game, 字典=价格表, 键="c", 值=3)

        # 写入后仍继续使用同一个“价格表”来源（典型写回语义诉求）
        长度: "整数" = 查询字典长度(self.game, 字典=价格表)
        条件: "布尔值" = 数值大于等于(self.game, 左值=长度, 右值=0)
        if 条件:
            return
        return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(
        tmp_path,
        "graph_dict_mutation_requires_graph_var_bad.py",
        graph_code,
    )
    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)

    codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert "CODE_DICT_MUTATION_REQUIRES_GRAPH_VAR" in codes


def test_dict_mutation_from_graph_var_allows_writeback(tmp_path: Path) -> None:
    """字典从【获取节点图变量】读取并被修改/复用，应允许（写回语义由节点图变量承载）。"""
    graph_code = '''
"""
graph_id: graph_dict_mutation_requires_graph_var_ok
graph_name: 字典写回语义_节点图变量_通过
graph_type: server
"""

from __future__ import annotations

from engine.graph.models.package_model import GraphVariableConfig
from _prelude import *


GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="运行时_价格表",
        variable_type="字典",
        default_value={},
        description="用于测试：以节点图变量承载可写回的字典引用",
        is_exposed=False,
        dict_key_type="字符串",
        dict_value_type="整数",
    ),
]


class 字典写回语义_节点图变量_通过:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        初始价格表: "字符串-整数字典" = {"a": 1, "b": 2}
        设置节点图变量(self.game, 变量名="运行时_价格表", 变量值=初始价格表, 是否触发事件=False)

        价格表: "字符串-整数字典" = 获取节点图变量(self.game, 变量名="运行时_价格表")
        对字典设置或新增键值对(self.game, 字典=价格表, 键="c", 值=3)

        长度: "整数" = 查询字典长度(self.game, 字典=价格表)
        条件: "布尔值" = 数值大于等于(self.game, 左值=长度, 右值=0)
        if 条件:
            return
        return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(
        tmp_path,
        "graph_dict_mutation_requires_graph_var_ok.py",
        graph_code,
    )
    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)

    codes = [issue.code for issue in report.issues if issue.level == "error"]
    assert "CODE_DICT_MUTATION_REQUIRES_GRAPH_VAR" not in codes


def test_dict_compute_multi_use_reports_warning(tmp_path: Path) -> None:
    """字典来自计算节点且被多个节点消费，应给出 warning 提醒（避免把它当作可写回引用使用）。"""
    graph_code = '''
"""
graph_id: graph_dict_compute_multi_use_warning
graph_name: 字典来源计算节点_多处使用_提示
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 字典来源计算节点_多处使用_提示:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        字典示例: "字符串-整数字典" = {"a": 1, "b": 2}
        长度: "整数" = 查询字典长度(self.game, 字典=字典示例)
        是否包含: "布尔值" = 查询字典是否包含特定键(self.game, 字典=字典示例, 键="a")
        if 是否包含:
            return
        return
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(
        tmp_path,
        "graph_dict_compute_multi_use_warning.py",
        graph_code,
    )
    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)

    hits = [issue for issue in report.issues if issue.code == "CODE_DICT_COMPUTE_MULTI_USE"]
    assert hits, "应产生 CODE_DICT_COMPUTE_MULTI_USE warning，用于提示计算节点字典被多处使用的重复求值/引用语义风险"
    assert any(issue.level == "warning" for issue in hits)


