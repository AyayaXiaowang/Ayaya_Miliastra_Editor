from __future__ import annotations

import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
if not __package__:
    raise SystemExit(
        "请从项目根目录使用模块方式运行：\n"
        "  python -X utf8 -m tools.validate.check_validate_graph_line_numbers [graph_id]\n"
        "（不再支持通过脚本内 sys.path.insert 的方式运行）"
    )

from engine.resources import ResourceManager, ResourceType, build_resource_manager  # noqa: E402
from engine.graph.models import GraphModel  # noqa: E402
from engine.graph import validate_graph  # noqa: E402


def pick_graph_id(resource_manager: ResourceManager) -> str:
    graph_ids = resource_manager.list_resources(ResourceType.GRAPH)
    if not graph_ids:
        print("[ERROR] 未找到任何节点图资源")
        sys.exit(1)
    return graph_ids[0]


def main() -> None:
    rm = build_resource_manager(WORKSPACE)
    # 优先使用传入的 graph_id
    args = sys.argv[1:]
    if args:
        graph_id = args[0]
    else:
        graph_id = pick_graph_id(rm)
    print(f"[INFO] 载入节点图: {graph_id}")

    data = rm.load_resource(ResourceType.GRAPH, graph_id)
    if not data:
        print(f"[ERROR] 加载失败: {graph_id}")
        sys.exit(1)

    graph_data = data.get("data", data)
    model = GraphModel.deserialize(graph_data)

    # 寻找一个“执行节点”且存在“流程入”的节点，并且当前确实有入边
    incoming_by_node: dict[str, list[str]] = {}
    for edge in model.edges.values():
        incoming_by_node.setdefault(edge.dst_node, []).append(edge.id)

    victim_node_id = ""
    victim_edge_id = ""
    for n in model.nodes.values():
        if n.category == "执行节点":
            # 检查是否存在名为“流程入”的输入端口
            has_flow_in = any(p.is_input and p.name == "流程入" for p in n.inputs)
            if not has_flow_in:
                continue
            in_edges = incoming_by_node.get(n.id, [])
            if in_edges:
                victim_node_id = n.id
                victim_edge_id = in_edges[0]
                break

    if not victim_node_id:
        print("[WARN] 未找到用于验证的候选节点（执行节点且有“流程入”的入边）")
        sys.exit(0)

    # 暂时移除一条入边，制造“流程入口未连接”的错误
    removed_edge = model.edges.pop(victim_edge_id)
    node = model.nodes[victim_node_id]
    print(f"[INFO] 移除连线以制造错误: {removed_edge.src_node}.{removed_edge.src_port} -> {removed_edge.dst_node}.{removed_edge.dst_port}")
    print(f"[INFO] 目标节点: {node.category}/{node.title}, source_lineno={node.source_lineno}, source_end_lineno={node.source_end_lineno}")

    errors = validate_graph(model)
    if not errors:
        print("[WARN] 未产生任何错误，无法验证行号输出")
        sys.exit(0)

    # 打印第一条错误，观察是否包含“第X~Y行”
    print("=== 校验输出（第一条） ===")
    print(errors[0])


if __name__ == "__main__":
    main()


