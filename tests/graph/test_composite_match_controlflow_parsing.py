from __future__ import annotations

from pathlib import Path

from engine.graph.graph_code_parser import GraphCodeParser
from engine.nodes.node_registry import clear_all_registries_for_tests
from engine.utils.runtime_scope import set_active_package_id
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

def _parse_file_in_demo_package(*, workspace: Path, graph_path: Path):
    """使用“演示项目”作用域解析临时节点图文件（需要加载该包下的复合节点）。"""
    set_active_package_id("演示项目")
    clear_all_registries_for_tests()
    try:
        parser = GraphCodeParser(workspace)
        return parser.parse_file(graph_path)
    finally:
        set_active_package_id(None)
        clear_all_registries_for_tests()


def test_composite_match_break_inside_loop_creates_break_edge(tmp_path: Path) -> None:
    """回归：match over 复合节点流程出口的分支体内 break 必须正确连到循环节点【跳出循环】。"""
    workspace = _workspace_root()

    graph_code = '''
"""
graph_id: graph_composite_match_break_in_loop
graph_name: 复合match_循环内break
graph_type: server
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 复合match_循环内break:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity
        self.分支器 = 多分支_示例_类格式(self.game, owner_entity)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        for 轮次 in range(3):
            match self.分支器.按整数多分支(分支值=轮次):
                case "分支为0":
                    break
                case "分支为其他":
                    设置节点图变量(self.game, 变量名="调试_计数", 变量值=轮次, 是否触发事件=False)
        设置节点图变量(self.game, 变量名="调试_结束", 变量值=0, 是否触发事件=False)
'''
    for_line = _find_line_number(graph_code, "for 轮次 in range(3):")
    match_line = _find_line_number(graph_code, "match self.分支器.按整数多分支(分支值=轮次):")
    break_line = _find_line_number(graph_code, "break")
    after_loop_set_line = _find_line_number(
        graph_code,
        '设置节点图变量(self.game, 变量名="调试_结束", 变量值=0, 是否触发事件=False)',
    )

    graph_path = _write_graph_code(tmp_path, "graph_composite_match_break_in_loop.py", graph_code)
    model, _meta = _parse_file_in_demo_package(workspace=workspace, graph_path=graph_path)

    loop_nodes = [
        node
        for node in model.nodes.values()
        if getattr(node, "title", "") == "有限循环"
        and int(getattr(node, "source_lineno", 0) or 0) == for_line
    ]
    assert loop_nodes, "期望 for range(...) 被解析为【有限循环】节点"
    loop_node = loop_nodes[0]

    composite_nodes = [
        node
        for node in model.nodes.values()
        if getattr(node, "title", "") == "多分支_示例_类格式"
        and int(getattr(node, "source_lineno", 0) or 0) == match_line
    ]
    assert composite_nodes, "期望 match subject 被识别为复合节点调用并创建复合节点（多分支_示例_类格式）"
    composite_node = composite_nodes[0]

    after_loop_set_nodes = [
        node
        for node in model.nodes.values()
        if getattr(node, "title", "") == "设置节点图变量"
        and int(getattr(node, "source_lineno", 0) or 0) == after_loop_set_line
    ]
    assert after_loop_set_nodes, "期望循环后的【设置节点图变量】节点存在"
    after_loop_set_node = after_loop_set_nodes[0]

    break_nodes = [
        node
        for node in model.nodes.values()
        if getattr(node, "title", "") == "跳出循环"
        and int(getattr(node, "source_lineno", 0) or 0) == break_line
    ]
    assert break_nodes, "期望 break 被物化为【跳出循环】节点"
    break_node = break_nodes[0]

    edge_to_break = [
        edge
        for edge in model.edges.values()
        if edge.src_node == composite_node.id
        and edge.src_port == "分支为0"
        and edge.dst_node == break_node.id
        and edge.dst_port == "流程入"
    ]
    assert edge_to_break, "回归：未找到复合节点分支为0 ->【跳出循环】的流程边"

    edge_break_to_loop = [
        edge
        for edge in model.edges.values()
        if edge.src_node == break_node.id
        and edge.src_port == "流程出"
        and edge.dst_node == loop_node.id
        and edge.dst_port == "跳出循环"
    ]
    assert edge_break_to_loop, "回归：未找到【跳出循环】-> 循环节点【跳出循环】的流程边"

    # break 分支不应接续到循环体后续语句（本例中 match 后没有其它循环体语句，主要防止错误接续到循环外）
    fallthrough_edges = [
        edge
        for edge in model.edges.values()
        if edge.src_node == composite_node.id
        and edge.src_port == "分支为0"
        and edge.dst_node == after_loop_set_node.id
    ]
    assert not fallthrough_edges, "回归：break 分支不应直接连到循环外的后续流程节点"


def test_composite_match_data_only_case_can_continue(tmp_path: Path) -> None:
    """回归：复合 match 的某个分支体仅含纯数据节点时，仍应允许接续到 match 后的流程节点。"""
    workspace = _workspace_root()

    graph_code = '''
"""
graph_id: graph_composite_match_data_only_case_continue
graph_name: 复合match_纯数据分支可接续
graph_type: server
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 复合match_纯数据分支可接续:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity
        self.分支器 = 多分支_示例_类格式(self.game, owner_entity)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        分支值: "整数" = 获取随机整数(self.game, 下限=0, 上限=2)
        结果: "整数" = 0 + 0
        match self.分支器.按整数多分支(分支值=分支值):
            case "分支为0":
                结果: "整数" = 0 + 10
            case "分支为其他":
                结果: "整数" = 0 + 20
        设置节点图变量(self.game, 变量名="调试_结果", 变量值=结果, 是否触发事件=False)
'''
    init_line = _find_line_number(graph_code, '结果: "整数" = 0 + 0')
    assign_a_line = _find_line_number(graph_code, '结果: "整数" = 0 + 10')
    assign_b_line = _find_line_number(graph_code, '结果: "整数" = 0 + 20')

    graph_path = _write_graph_code(tmp_path, "graph_composite_match_data_only_case_continue.py", graph_code)
    model, _meta = _parse_file_in_demo_package(workspace=workspace, graph_path=graph_path)

    get_nodes = [n for n in model.nodes.values() if getattr(n, "title", "") == "获取局部变量"]
    set_nodes = [n for n in model.nodes.values() if getattr(n, "title", "") == "设置局部变量"]

    # 初始化应被建模为【获取局部变量】，两条分支为【设置局部变量】
    assert len(get_nodes) == 1
    assert len(set_nodes) == 2

    get_lines = sorted({int(n.source_lineno) for n in get_nodes if getattr(n, "source_lineno", 0)})
    set_lines = sorted({int(n.source_lineno) for n in set_nodes if getattr(n, "source_lineno", 0)})
    assert get_lines == [init_line]
    assert set_lines == sorted([assign_a_line, assign_b_line])


def test_composite_match_return_case_does_not_continue(tmp_path: Path) -> None:
    """回归：复合 match 的某个分支若直接 return，应不接续到 match 后语句。"""
    workspace = _workspace_root()

    graph_code = '''
"""
graph_id: graph_composite_match_return_case_no_continue
graph_name: 复合match_return分支不接续
graph_type: server
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 复合match_return分支不接续:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity
        self.分支器 = 多分支_示例_类格式(self.game, owner_entity)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        分支值: "整数" = 获取随机整数(self.game, 下限=0, 上限=2)
        match self.分支器.按整数多分支(分支值=分支值):
            case "分支为0":
                return
            case "分支为其他":
                设置节点图变量(self.game, 变量名="调试_继续", 变量值=1, 是否触发事件=False)
        设置节点图变量(self.game, 变量名="调试_结束", 变量值=2, 是否触发事件=False)
'''
    match_line = _find_line_number(graph_code, "match self.分支器.按整数多分支(分支值=分支值):")
    after_match_set_line = _find_line_number(
        graph_code,
        '设置节点图变量(self.game, 变量名="调试_结束", 变量值=2, 是否触发事件=False)',
    )

    graph_path = _write_graph_code(tmp_path, "graph_composite_match_return_case_no_continue.py", graph_code)
    model, _meta = _parse_file_in_demo_package(workspace=workspace, graph_path=graph_path)

    composite_nodes = [
        node
        for node in model.nodes.values()
        if getattr(node, "title", "") == "多分支_示例_类格式"
        and int(getattr(node, "source_lineno", 0) or 0) == match_line
    ]
    assert composite_nodes, "期望 match subject 被识别为复合节点调用并创建复合节点（多分支_示例_类格式）"
    composite_node = composite_nodes[0]

    after_match_nodes = [
        node
        for node in model.nodes.values()
        if getattr(node, "title", "") == "设置节点图变量"
        and int(getattr(node, "source_lineno", 0) or 0) == after_match_set_line
    ]
    assert after_match_nodes, "期望 match 后的【设置节点图变量】节点存在"
    after_match_node = after_match_nodes[0]

    # return 的分支为0 不应直接接续到 match 后语句
    illegal_edges = [
        edge
        for edge in model.edges.values()
        if edge.src_node == composite_node.id
        and edge.src_port == "分支为0"
        and edge.dst_node == after_match_node.id
    ]
    assert not illegal_edges, "回归：return 分支不应连到 match 后的流程节点"


