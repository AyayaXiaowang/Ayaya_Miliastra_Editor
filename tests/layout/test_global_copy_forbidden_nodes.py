"""
回归：跨块复制必须跳过语义敏感的查询节点。

背景：
- 布局增强阶段（GlobalCopyManager）会把跨块共享的“纯数据节点”复制到各块内，减少跨块连线。
- 但部分无流程端口的查询节点与块内作用域/状态绑定（例如【获取局部变量】返回的句柄），一旦被复制会导致语义分叉。

本文件验证：
1) 【获取局部变量】跨块共享时不应生成数据副本（is_data_node_copy=True）。
2) 普通纯数据节点跨块共享时仍应按规则生成副本并重定向边。
"""

from engine.graph.models import GraphModel, NodeModel, EdgeModel, PortModel
from engine.layout.internal.layout_models import LayoutBlock
from engine.layout.utils.global_copy_manager import GlobalCopyManager


def _create_flow_node(node_id: str) -> NodeModel:
    flow_node = NodeModel(
        id=node_id,
        title="测试流程节点",
        category="测试节点",
        inputs=[
            PortModel(name="流程入", is_input=True),
            PortModel(name="输入", is_input=True),
        ],
        outputs=[
            PortModel(name="流程出", is_input=False),
            PortModel(name="输出", is_input=False),
        ],
    )
    flow_node._rebuild_port_maps()
    return flow_node


def _create_pure_data_node(node_id: str, *, title: str) -> NodeModel:
    data_node = NodeModel(
        id=node_id,
        title=title,
        category="查询节点",
        inputs=[PortModel(name="输入", is_input=True)],
        outputs=[PortModel(name="输出", is_input=False)],
    )
    data_node._rebuild_port_maps()
    return data_node


def _create_data_edge(
    edge_id: str,
    *,
    src_node_id: str,
    src_port_name: str,
    dst_node_id: str,
    dst_port_name: str,
) -> EdgeModel:
    return EdgeModel(
        id=edge_id,
        src_node=src_node_id,
        src_port=src_port_name,
        dst_node=dst_node_id,
        dst_port=dst_port_name,
    )


def test_global_copy_forbidden_local_variable_getter_not_copied() -> None:
    model = GraphModel(graph_id="test_forbidden_local_var", graph_name="test_forbidden_local_var")

    flow_node_block_1 = _create_flow_node("flow_1")
    flow_node_block_2 = _create_flow_node("flow_2")

    local_variable_getter = NodeModel(
        id="local_var_get",
        title="获取局部变量",
        category="查询节点",
        inputs=[PortModel(name="初始值", is_input=True)],
        outputs=[
            PortModel(name="局部变量", is_input=False),
            PortModel(name="值", is_input=False),
        ],
    )
    local_variable_getter._rebuild_port_maps()

    model.nodes[flow_node_block_1.id] = flow_node_block_1
    model.nodes[flow_node_block_2.id] = flow_node_block_2
    model.nodes[local_variable_getter.id] = local_variable_getter

    # local_var_get -> flow_1 / flow_2（跨块共享）
    model.edges["edge_lv_flow1"] = _create_data_edge(
        "edge_lv_flow1",
        src_node_id=local_variable_getter.id,
        src_port_name="值",
        dst_node_id=flow_node_block_1.id,
        dst_port_name="输入",
    )
    model.edges["edge_lv_flow2"] = _create_data_edge(
        "edge_lv_flow2",
        src_node_id=local_variable_getter.id,
        src_port_name="值",
        dst_node_id=flow_node_block_2.id,
        dst_port_name="输入",
    )

    block_1 = LayoutBlock(flow_nodes=[flow_node_block_1.id], order_index=1)
    block_2 = LayoutBlock(flow_nodes=[flow_node_block_2.id], order_index=2)

    manager = GlobalCopyManager(model, [block_1, block_2])
    manager.analyze_dependencies()
    manager.execute_copy_plan()

    # 1) 不生成 local_var_get 的副本节点
    copy_nodes = [
        node
        for node in model.nodes.values()
        if bool(getattr(node, "is_data_node_copy", False))
        and str(getattr(node, "original_node_id", "") or "") == local_variable_getter.id
    ]
    assert not copy_nodes

    # 2) 副本不存在，边语义应保持为 local_var_get -> flow_2（不应重定向到不存在的副本）
    assert any(
        edge.src_node == local_variable_getter.id and edge.dst_node == flow_node_block_2.id
        for edge in model.edges.values()
    )

    # 3) block_data_nodes 仅 owner 块包含原始节点，避免同一原始节点被多个块重复放置
    block_1_data_nodes = manager.get_block_data_nodes("block_1")
    block_2_data_nodes = manager.get_block_data_nodes("block_2")
    assert local_variable_getter.id in block_1_data_nodes
    assert local_variable_getter.id not in block_2_data_nodes


def test_global_copy_forbidden_local_variable_getter_owner_prefers_left_column_over_order_index() -> None:
    """回归：禁止跨块复制的语义敏感节点（如【获取局部变量】）的 owner 块选择应以“最靠左列”为准。

    背景：
    - block_index(order_index) 是分块阶段的稳定编号，但不保证等于块的横向列位置；
    - 当列顺序与 block_index 不一致时，若仍按 block_index 选择 owner，会产生跨块数据回头线（右→左）。
    """
    model = GraphModel(graph_id="test_forbidden_owner_column", graph_name="test_forbidden_owner_column")

    # 约定：block_2 -> block_1（block_2 是父块，应位于更左列），但 order_index 反过来
    flow_node_right = _create_flow_node("flow_right")
    flow_node_left = _create_flow_node("flow_left")

    local_variable_getter = NodeModel(
        id="local_var_get",
        title="获取局部变量",
        category="查询节点",
        inputs=[PortModel(name="初始值", is_input=True)],
        outputs=[
            PortModel(name="局部变量", is_input=False),
            PortModel(name="值", is_input=False),
        ],
    )
    local_variable_getter._rebuild_port_maps()

    model.nodes[flow_node_right.id] = flow_node_right
    model.nodes[flow_node_left.id] = flow_node_left
    model.nodes[local_variable_getter.id] = local_variable_getter

    # local_var_get -> flow_right / flow_left（跨块共享）
    model.edges["edge_lv_right"] = _create_data_edge(
        "edge_lv_right",
        src_node_id=local_variable_getter.id,
        src_port_name="值",
        dst_node_id=flow_node_right.id,
        dst_port_name="输入",
    )
    model.edges["edge_lv_left"] = _create_data_edge(
        "edge_lv_left",
        src_node_id=local_variable_getter.id,
        src_port_name="值",
        dst_node_id=flow_node_left.id,
        dst_port_name="输入",
    )

    # 注意：order_index 故意与列顺序错开
    block_right = LayoutBlock(flow_nodes=[flow_node_right.id], order_index=1)
    block_left = LayoutBlock(
        flow_nodes=[flow_node_left.id],
        order_index=2,
        last_node_branches=[("默认", flow_node_right.id)],
    )

    manager = GlobalCopyManager(model, [block_right, block_left])
    manager.analyze_dependencies()
    manager.execute_copy_plan()

    # 断言：owner 选择应偏向“最靠左列”的 block_2（尽管其 order_index 更大）
    block_1_data_nodes = manager.get_block_data_nodes("block_1")
    block_2_data_nodes = manager.get_block_data_nodes("block_2")
    assert local_variable_getter.id not in block_1_data_nodes
    assert local_variable_getter.id in block_2_data_nodes


def test_global_copy_normal_pure_data_node_is_copied() -> None:
    model = GraphModel(graph_id="test_normal_copy", graph_name="test_normal_copy")

    flow_node_block_1 = _create_flow_node("flow_1")
    flow_node_block_2 = _create_flow_node("flow_2")
    shared_data_node = _create_pure_data_node("data_shared", title="普通纯数据节点")

    model.nodes[flow_node_block_1.id] = flow_node_block_1
    model.nodes[flow_node_block_2.id] = flow_node_block_2
    model.nodes[shared_data_node.id] = shared_data_node

    model.edges["edge_data_flow1"] = _create_data_edge(
        "edge_data_flow1",
        src_node_id=shared_data_node.id,
        src_port_name="输出",
        dst_node_id=flow_node_block_1.id,
        dst_port_name="输入",
    )
    model.edges["edge_data_flow2"] = _create_data_edge(
        "edge_data_flow2",
        src_node_id=shared_data_node.id,
        src_port_name="输出",
        dst_node_id=flow_node_block_2.id,
        dst_port_name="输入",
    )

    block_1 = LayoutBlock(flow_nodes=[flow_node_block_1.id], order_index=1)
    block_2 = LayoutBlock(flow_nodes=[flow_node_block_2.id], order_index=2)

    manager = GlobalCopyManager(model, [block_1, block_2])
    manager.analyze_dependencies()
    manager.execute_copy_plan()

    expected_copy_id = f"{shared_data_node.id}_copy_block_2_1"
    copied_node = model.nodes.get(expected_copy_id)
    assert copied_node is not None
    assert bool(getattr(copied_node, "is_data_node_copy", False)) is True
    assert str(getattr(copied_node, "original_node_id", "") or "") == shared_data_node.id
    assert str(getattr(copied_node, "copy_block_id", "") or "") == "block_2"

    # block_2 的消费者应连接到副本而不是原始节点
    assert any(
        edge.src_node == expected_copy_id and edge.dst_node == flow_node_block_2.id
        for edge in model.edges.values()
    )
    assert not any(
        edge.src_node == shared_data_node.id and edge.dst_node == flow_node_block_2.id
        for edge in model.edges.values()
    )

    # block_data_nodes 中，block_2 应包含副本而非原始节点
    block_1_data_nodes = manager.get_block_data_nodes("block_1")
    block_2_data_nodes = manager.get_block_data_nodes("block_2")
    assert shared_data_node.id in block_1_data_nodes
    assert shared_data_node.id not in block_2_data_nodes
    assert expected_copy_id in block_2_data_nodes


