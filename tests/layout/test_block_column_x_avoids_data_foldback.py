from __future__ import annotations

from pathlib import Path

from tests._helpers.project_paths import get_repo_root

from engine.graph import GraphCodeParser
from engine.layout import LayoutService
from engine.layout.internal.constants import PORT_EXIT_LOOP
from engine.layout.utils.graph_query_utils import is_flow_edge


PROJECT_ROOT = get_repo_root()


def test_template_loop_iterate_int_list_has_no_foldback_edges() -> None:
    """
    回归用户反馈（模板示例_循环遍历整数列表）：

    当块间紧凑 X 贴近关闭（列左对齐）时，跨块 data 边不应出现“右→左折返”。
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
        / "模板示例_循环遍历整数列表.py"
    )
    parser = GraphCodeParser(PROJECT_ROOT)
    model, _ = parser.parse_file(graph_file)

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
        "期望模板示例_循环遍历整数列表不存在折返边（dst_x < src_x），"
        f"但发现 {len(foldback_edges)} 条。示例：{foldback_edges[:3]}"
    )


