from __future__ import annotations

from tests._helpers.project_paths import get_repo_root

from engine.graph import GraphCodeParser
from engine.layout import LayoutService
from engine.layout.internal.constants import PORT_EXIT_LOOP
from engine.layout.utils.graph_query_utils import is_flow_edge
from engine.nodes.node_registry import clear_all_registries_for_tests
from engine.utils.runtime_scope import set_active_package_id


PROJECT_ROOT = get_repo_root()


def test_forge_hero_weapon_browse_and_select_has_no_foldback_edges() -> None:
    """
    回归用户反馈（复合执行节点 + 自动排版）：

    当图中包含复合执行节点时（带流程口的复合节点调用），自动排版不应产生明显的“右→左折返”回头线。
    展示型仓库不依赖本地私有项目存档，因此选择公开模板图作为回归输入。
    """
    graph_file = (
        PROJECT_ROOT
        / "assets"
        / "资源库"
        / "项目存档"
        / "示例项目模板"
        / "节点图"
        / "server"
        / "实体节点图"
        / "模板示例"
        / "模板示例_延迟执行_复合节点用法.py"
    )
    # 复合节点解析需要按“共享根 + 当前项目存档根”作用域加载；本用例选择的是示例项目模板下的复合节点图。
    set_active_package_id("示例项目模板")
    clear_all_registries_for_tests()
    try:
        parser = GraphCodeParser(PROJECT_ROOT)
        model, _ = parser.parse_file(graph_file)
    finally:
        set_active_package_id(None)
        clear_all_registries_for_tests()

    result = LayoutService.compute_layout(
        model,
        clone_model=True,
        workspace_path=PROJECT_ROOT,
        include_augmented_model=True,
    )
    augmented = result.augmented_model
    assert augmented is not None

    foldback_edges: list[tuple[str, str, float, str, str, float, str, str]] = []
    for edge in augmented.edges.values():
        src_node_id = getattr(edge, "src_node", None)
        dst_node_id = getattr(edge, "dst_node", None)
        if not isinstance(src_node_id, str) or not isinstance(dst_node_id, str):
            continue

        src_node = augmented.nodes.get(src_node_id)
        dst_node = augmented.nodes.get(dst_node_id)
        if src_node is None or dst_node is None:
            continue

        # 兼容“跳出循环”类回边：该连线允许向左，不纳入本回归断言。
        if is_flow_edge(augmented, edge):
            dst_port_obj = dst_node.get_input_port(getattr(edge, "dst_port", None))
            if dst_port_obj is not None and str(dst_port_obj.name) == str(PORT_EXIT_LOOP):
                continue

        src_x = float(src_node.pos[0])
        dst_x = float(dst_node.pos[0])
        if dst_x < src_x - 1e-6:
            foldback_edges.append(
                (
                    src_node_id,
                    str(src_node.title or ""),
                    src_x,
                    dst_node_id,
                    str(dst_node.title or ""),
                    dst_x,
                    str(getattr(edge, "src_port", "") or ""),
                    str(getattr(edge, "dst_port", "") or ""),
                )
            )

    assert not foldback_edges, (
        "期望该模板图不存在折返边（dst_x < src_x），"
        f"但发现 {len(foldback_edges)} 条。示例：{foldback_edges[:3]}"
    )


