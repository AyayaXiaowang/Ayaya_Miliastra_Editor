from __future__ import annotations

from engine.graph.composite_code_parser import CompositeCodeParser
from engine.graph.models.graph_model import GraphModel
from engine.nodes.node_definition_loader import load_all_nodes

from tests._helpers.project_paths import get_repo_root


def test_flow_exit_pin_ignores_loop_body_terminals() -> None:
    """循环体内的“无出边流程端口”语义上是 continue，不应被绑定为方法级流程出口。"""
    workspace_root = get_repo_root()
    composite_path = (
        workspace_root
        / "assets"
        / "资源库"
        / "共享"
        / "复合节点库"
        / "composite_布尔值列表_任意为真.py"
    )
    assert composite_path.is_file()

    node_library = load_all_nodes(workspace_root, include_composite=False, verbose=False)
    parser = CompositeCodeParser(node_library=node_library, verbose=False)
    cfg = parser.parse_file(composite_path)
    graph = GraphModel.deserialize(cfg.sub_graph)
    title_by_id = {node_id: node.title for node_id, node in graph.nodes.items()}

    flow_out_pin = next(
        (
            pin
            for pin in cfg.virtual_pins
            if (not pin.is_input) and pin.is_flow and pin.pin_name == "完成"
        ),
        None,
    )
    assert flow_out_pin is not None, "该复合节点应包含名为“完成”的流程出虚拟引脚"
    assert flow_out_pin.mapped_ports, "流程出虚拟引脚应至少映射到一个内部流程出口端口"

    mapped_titles_and_ports = [
        (title_by_id.get(mp.node_id, ""), mp.port_name) for mp in flow_out_pin.mapped_ports
    ]

    assert (
        ("列表迭代循环", "循环完成") in mapped_titles_and_ports
    ), "流程出“完成”应至少锚定到循环节点的“循环完成”出口"
    assert (
        ("双分支", "否") not in mapped_titles_and_ports
    ), "循环体内的“双分支/否”代表继续下一轮迭代，不应被当作方法出口"


