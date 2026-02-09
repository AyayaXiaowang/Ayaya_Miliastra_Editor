"""
回归测试：块识别阶段的分支遍历顺序不应导致“兄弟分支的初始化流程节点”被编号到最后一个块。

背景（对应真实反馈）：
- 在 `模板示例_语法糖归一化_循环奖励发放` 中，IR 会在 else 分支生成【设置局部变量】执行节点；
- 若块识别采用 DFS 深度优先遍历，可能先沿着另一条分支走完整个后续流程，
  导致 else 分支的【设置局部变量】所在块被分配到最后一个 `block_N`；
- UI 按块序号堆叠时会把该分支节点推到图的最下方，造成“分块分错”的观感。

本测试只验证关键约束：
- 该模板图中生成的【设置局部变量】不应处于最后一个块。
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

    # 目标：else 分支生成的【设置局部变量】不应被 DFS 顺序推到最后一个块。
    # 约定：该示例中 else 分支源码行号更靠后，因此用 source_lineno 最大者近似指代“else 分支的 set_local_var”。
    target_node = max(set_nodes, key=lambda n: int(getattr(n, "source_lineno", 0) or 0))
    set_block_index = block_index_by_node.get(target_node.id)
    assert isinstance(set_block_index, int)
    assert 1 <= set_block_index < len(blocks)


