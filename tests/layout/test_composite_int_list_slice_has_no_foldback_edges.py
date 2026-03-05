from __future__ import annotations

from tests._helpers.project_paths import get_repo_root

from engine.graph.composite_code_parser import CompositeCodeParser
from engine.graph.models.graph_model import GraphModel
from engine.layout.internal.constants import PORT_EXIT_LOOP
from engine.layout.utils.graph_query_utils import is_flow_edge
from engine.nodes.node_definition_loader import load_all_nodes


PROJECT_ROOT = get_repo_root()


def test_composite_int_list_slice_has_no_foldback_edges() -> None:
    """
    回归用户反馈（复合节点：整数列表_切片）：

    自动排版后，不应出现“右→左折返”的回头线（跳出循环回边除外）。
    """
    composite_file = (
        PROJECT_ROOT
        / "assets"
        / "资源库"
        / "共享"
        / "复合节点库"
        / "composite_整数列表_切片.py"
    )
    assert composite_file.is_file()

    node_library = load_all_nodes(PROJECT_ROOT, include_composite=False, verbose=False)
    parser = CompositeCodeParser(
        node_library=node_library,
        verbose=False,
        workspace_path=PROJECT_ROOT,
    )
    cfg = parser.parse_file(composite_file)
    graph = GraphModel.deserialize(cfg.sub_graph)

    foldback_edges: list[tuple[str, str, float, str, str, float, str, str]] = []

    for edge in graph.edges.values():
        src_node_id = getattr(edge, "src_node", None)
        dst_node_id = getattr(edge, "dst_node", None)
        if not isinstance(src_node_id, str) or not isinstance(dst_node_id, str):
            continue

        src_node = graph.nodes.get(src_node_id)
        dst_node = graph.nodes.get(dst_node_id)
        if src_node is None or dst_node is None:
            continue

        # 兼容“跳出循环”类回边：该连线允许向左，不纳入本回归断言。
        if is_flow_edge(graph, edge):
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
        "期望 composite_整数列表_切片 不存在折返边（dst_x < src_x），"
        f"但发现 {len(foldback_edges)} 条。示例：{foldback_edges[:3]}"
    )


