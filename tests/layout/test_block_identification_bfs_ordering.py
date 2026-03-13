"""
回归测试：块识别阶段采用 DFS（深度优先）时，块编号应体现“先走完一条分支，再回头处理兄弟分支”的顺序。

说明：
- 深度优先会导致某些“兄弟分支的初始化流程节点”被编号到较后的块（甚至最后一个块）；
- 这是预期行为：用于让块编号更贴近“从端口出发的阅读顺序”。

本测试锁住一个可观测的现象：
- 在 `模板示例_局部变量_分支设置` 中，源码行号更靠后的那一个【设置局部变量】节点（近似代表 else 分支）
  应落在最后一个块（DFS 先沿另一分支走完后续，再回头处理该分支）。
"""

from __future__ import annotations

from pathlib import Path

from engine.graph.graph_code_parser import GraphCodeParser
from tests._helpers.project_paths import get_repo_root

def test_template_reward_cycle_set_local_var_not_in_last_block() -> None:
    project_root = get_repo_root()
    template_path = (
        project_root
        / "assets"
        / "资源库"
        / "项目存档"
        / "示例项目模板"
        / "节点图"
        / "server"
        / "实体节点图"
        / "模板示例"
        / "模板示例_局部变量_分支设置.py"
    )

    parser = GraphCodeParser(project_root)
    model, _meta = parser.parse_file(template_path)

    blocks = list(getattr(model, "basic_blocks", []) or [])
    assert len(blocks) >= 2

    block_index_by_node: dict[str, int] = {}
    for index, block in enumerate(blocks, start=1):
        for node_id in (getattr(block, "nodes", []) or []):
            if isinstance(node_id, str) and node_id:
                block_index_by_node[node_id] = index

    set_nodes = [node for node in model.nodes.values() if getattr(node, "title", "") == "设置局部变量"]
    assert len(set_nodes) >= 1

    # 目标：DFS 顺序下，else 分支生成的【设置局部变量】会被推到较后（此处锁住为最后一个块）。
    # 约定：该示例中 else 分支源码行号更靠后，因此用 source_lineno 最大者近似指代“else 分支的 set_local_var”。
    target_node = max(set_nodes, key=lambda n: int(getattr(n, "source_lineno", 0) or 0))
    set_block_index = block_index_by_node.get(target_node.id)
    assert isinstance(set_block_index, int)
    assert set_block_index == len(blocks)


