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


def test_realtime_reparse_does_not_leak_method_local_constants_or_local_var_state(tmp_path: Path) -> None:
    """回归：同进程内连续解析两个 Graph Code 文件时，不应串用上一次解析的 VarEnv 状态。

    现象（修复前）：
    - 第一次解析将 `当前库存总件数: "整数" = 2` 记录为“方法体命名常量”；
    - 第二次解析中即便 `当前库存总件数` 已变为动态更新变量，
      仍会把 RHS 中的 `当前库存总件数` 误回填为常量 2，导致循环累计语义错误；
    - UI 表现为：清理缓存无效，必须重启软件（重置进程内解析器实例）才恢复正常。
    """
    workspace = _workspace_root()
    parser = GraphCodeParser(workspace)

    graph_code_a = '''
"""
graph_id: graph_reparse_state_isolation_a
graph_name: 实时重解析_状态隔离_A
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 实时重解析_状态隔离_A:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        列表: "整数列表" = [1, 2]
        当前库存总件数: "整数" = 2
        结果: "整数" = 当前库存总件数 + 1
        if 是否相等(self.game, 输入1=结果, 输入2=3):
            return
'''
    file_a = _write_graph_code(tmp_path, "graph_reparse_state_isolation_a.py", graph_code_a)
    parser.parse_file(file_a)

    graph_code_b = '''
"""
graph_id: graph_reparse_state_isolation_b
graph_name: 实时重解析_状态隔离_B
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 实时重解析_状态隔离_B:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        列表: "整数列表" = [1, 2]
        当前库存总件数: "整数" = 1 + 1
        for 当前元素 in 列表:
            当前库存总件数: "整数" = 当前库存总件数 + 当前元素
        if 是否相等(self.game, 输入1=当前库存总件数, 输入2=4):
            return
'''
    init_assignment_line = _find_line_number(graph_code_b, '当前库存总件数: "整数" = 1 + 1')
    loop_assignment_line = _find_line_number(
        graph_code_b,
        '当前库存总件数: "整数" = 当前库存总件数 + 当前元素',
    )

    file_b = _write_graph_code(tmp_path, "graph_reparse_state_isolation_b.py", graph_code_b)
    model_b, _meta_b = parser.parse_file(file_b)

    init_add_nodes = [
        node
        for node in model_b.nodes.values()
        if getattr(node, "title", "") == "加法运算"
        and int(getattr(node, "source_lineno", 0) or 0) == init_assignment_line
    ]
    assert init_add_nodes, "期望 `1 + 1` 被改写为【加法运算】节点（而不是被折叠为常量）"
    assert any(
        str(getattr(node, "input_constants", {}).get("左值", "")) == "1"
        and str(getattr(node, "input_constants", {}).get("右值", "")) == "1"
        for node in init_add_nodes
    ), "期望初始化加法节点的左右值常量均为 1"

    loop_add_nodes = [
        node
        for node in model_b.nodes.values()
        if getattr(node, "title", "") == "加法运算"
        and int(getattr(node, "source_lineno", 0) or 0) == loop_assignment_line
    ]
    assert loop_add_nodes, "期望循环内累计语句被改写为【加法运算】节点"

    # 关键断言：循环内加法的“左值”必须来自变量（有连线），不能被回填为旧常量 2。
    for add_node in loop_add_nodes:
        left_constant = str(getattr(add_node, "input_constants", {}).get("左值", "")).strip()
        assert left_constant != "2", "回归：检测到左值被错误回填为旧常量 2（状态泄漏）"

        has_left_edge = any(
            edge.dst_node == add_node.id and edge.dst_port == "左值"
            for edge in model_b.edges.values()
        )
        assert has_left_edge, "期望循环内加法节点的左值端口有数据连线（来自当前累计值）"


