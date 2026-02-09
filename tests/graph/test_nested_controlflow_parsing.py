from __future__ import annotations

from pathlib import Path

from engine.graph.graph_code_parser import GraphCodeParser
from tests._helpers.project_paths import get_repo_root


def _workspace_root() -> Path:
    return get_repo_root()


def _write_graph_code(tmp_dir: Path, filename: str, source: str) -> Path:
    target = tmp_dir / filename
    target.write_text(source, encoding="utf-8")
    return target


def _find_line_number(source: str, needle: str) -> int:
    needle_text = str(needle).strip()
    if not needle_text:
        raise ValueError("needle must be non-empty")
    for line_number, line in enumerate(source.splitlines(), start=1):
        if line.strip() == needle_text:
            return line_number
    raise ValueError(f"needle not found: {needle_text}")


def test_match_break_inside_loop_creates_break_edge(tmp_path: Path) -> None:
    """回归：match/case 分支体内的 break 必须能正确连到循环节点的【跳出循环】端口。

    关键点：
    - case 0 只有 break（无其它流程节点），也必须生成 break 的流程边；
    - break 分支不允许“继续向后接续”到 match 后的语句。
    """
    workspace = _workspace_root()
    parser = GraphCodeParser(workspace)

    graph_code = '''
"""
graph_id: graph_nested_match_break_in_loop
graph_name: 嵌套解析_多分支_循环内break
graph_type: server
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 嵌套解析_多分支_循环内break:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        计数: "整数" = 0
        for 轮次 in range(3):
            match 轮次:
                case 0:
                    break
                case _:
                    计数: "整数" = 计数 + 1
            设置节点图变量(self.game, 变量名="调试_计数", 变量值=计数, 是否触发事件=False)
'''
    for_line = _find_line_number(graph_code, "for 轮次 in range(3):")
    match_line = _find_line_number(graph_code, "match 轮次:")
    set_var_line = _find_line_number(
        graph_code,
        '设置节点图变量(self.game, 变量名="调试_计数", 变量值=计数, 是否触发事件=False)',
    )

    graph_path = _write_graph_code(tmp_path, "graph_nested_match_break_in_loop.py", graph_code)
    model, _meta = parser.parse_file(graph_path)

    loop_nodes = [
        node
        for node in model.nodes.values()
        if getattr(node, "title", "") == "有限循环"
        and int(getattr(node, "source_lineno", 0) or 0) == for_line
    ]
    assert loop_nodes, "期望 for range(...) 被解析为【有限循环】节点"
    loop_node = loop_nodes[0]

    branch_nodes = [
        node
        for node in model.nodes.values()
        if getattr(node, "title", "") == "多分支"
        and int(getattr(node, "source_lineno", 0) or 0) == match_line
    ]
    assert branch_nodes, "期望 match 语句被解析为【多分支】节点"
    branch_node = branch_nodes[0]

    set_graph_var_nodes = [
        node
        for node in model.nodes.values()
        if getattr(node, "title", "") == "设置节点图变量"
        and int(getattr(node, "source_lineno", 0) or 0) == set_var_line
    ]
    assert set_graph_var_nodes, "期望 match 后的【设置节点图变量】节点存在"
    set_graph_var_node = set_graph_var_nodes[0]

    # 1) 必须存在 break 边：从【多分支】端口 "0" 直接连到循环节点的【跳出循环】输入
    break_edges = [
        edge
        for edge in model.edges.values()
        if edge.src_node == branch_node.id
        and edge.src_port == "0"
        and edge.dst_node == loop_node.id
        and edge.dst_port == "跳出循环"
    ]
    assert break_edges, "回归：未找到 case 0 -> break 的【跳出循环】流程边"

    # 2) break 分支不允许“继续向后接续”到 match 后的流程语句
    fallthrough_edges = [
        edge
        for edge in model.edges.values()
        if edge.src_node == branch_node.id
        and edge.src_port == "0"
        and edge.dst_node == set_graph_var_node.id
    ]
    assert not fallthrough_edges, "回归：break 分支不应连到 match 后的流程节点（出现了 fallthrough）"


def test_match_case_without_flow_nodes_can_continue(tmp_path: Path) -> None:
    """回归：某个 case 只生成“纯数据节点”时，该分支仍应允许继续接续 match 后的流程节点。"""
    workspace = _workspace_root()
    parser = GraphCodeParser(workspace)

    graph_code = '''
"""
graph_id: graph_nested_match_case_without_flow
graph_name: 嵌套解析_多分支_无流程节点分支仍可接续
graph_type: server
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 嵌套解析_多分支_无流程节点分支仍可接续:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        分支: "整数" = 获取随机整数(self.game, 下限=0, 上限=1)
        match 分支:
            case 0:
                结果: "整数" = 1 + 1
            case _:
                结果: "整数" = 2 + 2
        设置节点图变量(self.game, 变量名="调试_结果", 变量值=结果, 是否触发事件=False)
'''
    match_line = _find_line_number(graph_code, "match 分支:")
    set_var_line = _find_line_number(
        graph_code,
        '设置节点图变量(self.game, 变量名="调试_结果", 变量值=结果, 是否触发事件=False)',
    )

    graph_path = _write_graph_code(tmp_path, "graph_nested_match_case_without_flow.py", graph_code)
    model, _meta = parser.parse_file(graph_path)

    branch_nodes = [
        node
        for node in model.nodes.values()
        if getattr(node, "title", "") == "多分支"
        and int(getattr(node, "source_lineno", 0) or 0) == match_line
    ]
    assert branch_nodes, "期望 match 语句被解析为【多分支】节点"
    branch_node = branch_nodes[0]

    set_graph_var_nodes = [
        node
        for node in model.nodes.values()
        if getattr(node, "title", "") == "设置节点图变量"
        and int(getattr(node, "source_lineno", 0) or 0) == set_var_line
    ]
    assert set_graph_var_nodes, "期望 match 后的【设置节点图变量】节点存在"
    set_graph_var_node = set_graph_var_nodes[0]

    # case 0 分支只会生成“获取局部变量/加法运算”等纯数据节点（无流程节点），
    # 因此必须允许从【多分支】端口 "0" 直接接续到 match 之后的流程节点。
    continuation_edges = [
        edge
        for edge in model.edges.values()
        if edge.src_node == branch_node.id
        and edge.src_port == "0"
        and edge.dst_node == set_graph_var_node.id
    ]
    assert continuation_edges, "回归：case 0 无流程节点时也应能接续到 match 后的流程节点"


def test_if_inside_loop_models_local_var_updates(tmp_path: Path) -> None:
    """回归：for 循环内嵌套 if-else 且两侧都对同一变量赋值时，应稳定建模为局部变量更新。"""
    workspace = _workspace_root()
    parser = GraphCodeParser(workspace)

    graph_code = '''
"""
graph_id: graph_nested_if_in_loop_local_var
graph_name: 嵌套解析_if_in_for_局部变量
graph_type: server
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 嵌套解析_if_in_for_局部变量:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        累计: "整数" = 0
        for 轮次 in range(3):
            if 轮次 == 1:
                累计: "整数" = 累计 + 10
            else:
                累计: "整数" = 累计 + 1
        设置节点图变量(self.game, 变量名="调试_累计", 变量值=累计, 是否触发事件=False)
'''
    init_line = _find_line_number(graph_code, '累计: "整数" = 0')
    assign_if_line = _find_line_number(graph_code, '累计: "整数" = 累计 + 10')
    assign_else_line = _find_line_number(graph_code, '累计: "整数" = 累计 + 1')

    graph_path = _write_graph_code(tmp_path, "graph_nested_if_in_loop_local_var.py", graph_code)
    model, _meta = parser.parse_file(graph_path)

    get_nodes = [
        node
        for node in model.nodes.values()
        if getattr(node, "title", "") == "获取局部变量"
    ]
    set_nodes = [
        node
        for node in model.nodes.values()
        if getattr(node, "title", "") == "设置局部变量"
    ]

    assert len(get_nodes) == 1
    assert len(set_nodes) == 2

    get_lines = sorted({int(n.source_lineno) for n in get_nodes if getattr(n, "source_lineno", 0)})
    set_lines = sorted({int(n.source_lineno) for n in set_nodes if getattr(n, "source_lineno", 0)})
    assert get_lines == [init_line]
    assert set_lines == sorted([assign_if_line, assign_else_line])


