from __future__ import annotations

from tests._helpers.project_paths import get_repo_root

from engine.graph.models import GraphModel, NodeModel, EdgeModel, PortModel
from engine.layout.internal.layout_models import LayoutBlock
from engine.layout.utils.global_copy_manager import GlobalCopyManager
from engine.layout.utils.local_variable_relay_inserter import (
    LOCAL_VAR_RELAY_NODE_ID_PREFIX,
    insert_local_variable_relays_after_global_copy,
    parse_local_var_relay_forced_slot_index,
)
from engine.nodes.node_registry import get_node_registry
from engine.configs.settings import settings
from engine.layout.internal.constants import NODE_WIDTH_DEFAULT, compute_slot_width_from_node_width
from engine.layout.utils.coordinate_assigner_x import compute_data_x_positions


PROJECT_ROOT = get_repo_root()


def test_local_variable_relay_inserter_splits_long_within_block_flow_to_flow_data_edge() -> None:
    """回归：同一块内跨越过多流程节点的 flow→flow 数据边会被拆分为“源 -> relay -> 目标”。"""
    model = GraphModel(graph_id="test_local_var_relay", graph_name="test_local_var_relay")

    # 源：事件节点【实体创建时】输出“事件源GUID”
    source_flow = NodeModel(
        id="flow_1",
        title="实体创建时",
        category="事件节点",
        inputs=[],
        outputs=[
            PortModel(name="流程出", is_input=False),
            PortModel(name="事件源实体", is_input=False),
            PortModel(name="事件源GUID", is_input=False),
        ],
    )
    source_flow._rebuild_port_maps()

    # 目标：执行节点【设置局部变量】输入“值”（且具备流程端口以参与块内 flow_nodes 序列）
    target_flow = NodeModel(
        id="flow_10",
        title="设置局部变量",
        category="执行节点",
        inputs=[
            PortModel(name="流程入", is_input=True),
            PortModel(name="局部变量", is_input=True),
            PortModel(name="值", is_input=True),
        ],
        outputs=[PortModel(name="流程出", is_input=False)],
    )
    target_flow._rebuild_port_maps()

    model.nodes[source_flow.id] = source_flow
    model.nodes[target_flow.id] = target_flow

    # 构造块内的流程链：flow_1 -> flow_2 -> ... -> flow_10
    # 中间节点只需要具备流程端口即可（无需真实业务端口）
    for index in range(2, 10):
        flow_id = f"flow_{index}"
        intermediate = NodeModel(
            id=flow_id,
            title=f"中间节点{index}",
            category="执行节点",
            inputs=[PortModel(name="流程入", is_input=True)],
            outputs=[PortModel(name="流程出", is_input=False)],
        )
        intermediate._rebuild_port_maps()
        model.nodes[flow_id] = intermediate

    for index in range(1, 10):
        model.edges[f"edge_flow_{index}_{index+1}"] = EdgeModel(
            id=f"edge_flow_{index}_{index+1}",
            src_node=f"flow_{index}",
            src_port="流程出",
            dst_node=f"flow_{index+1}",
            dst_port="流程入",
        )

    # 长跨度数据边：flow_1.事件源GUID -> flow_10.值
    original_edge = EdgeModel(
        id="edge_long",
        src_node=source_flow.id,
        src_port="事件源GUID",
        dst_node=target_flow.id,
        dst_port="值",
    )
    model.edges[original_edge.id] = original_edge

    # 构造 1 个块：同一块内包含 flow_1..flow_10
    layout_blocks: list[LayoutBlock] = []
    layout_blocks.append(LayoutBlock(flow_nodes=[f"flow_{i}" for i in range(1, 11)], order_index=1, last_node_branches=[]))

    # 全局复制阶段：仅用于生成 block_data_nodes 映射（本测试不需要执行 copy plan）
    copy_manager = GlobalCopyManager(model, layout_blocks)
    copy_manager.analyze_dependencies()

    node_registry = get_node_registry(PROJECT_ROOT, include_composite=True)

    forced_by_block, all_relay_nodes, did_mutate = insert_local_variable_relays_after_global_copy(
        model=model,
        layout_blocks=layout_blocks,
        global_copy_manager=copy_manager,
        max_block_distance=5,
        node_registry=node_registry,
    )

    assert did_mutate
    assert original_edge.id not in model.edges, "原始长边应被移除并替换为 relay 链"

    relay_node_ids = [node_id for node_id in model.nodes.keys() if str(node_id).startswith(LOCAL_VAR_RELAY_NODE_ID_PREFIX)]
    assert len(relay_node_ids) == 1

    relay_node_id = relay_node_ids[0]
    assert relay_node_id in all_relay_nodes
    assert relay_node_id in forced_by_block.get("block_1", set())
    assert parse_local_var_relay_forced_slot_index(relay_node_id) == 5, "阈值=5 时应落在从源节点起第 5 步的槽位"

    # 断言连线链条：flow_1 -> relay -> flow_10
    relay_in_edges = [
        edge for edge in model.edges.values() if edge.dst_node == relay_node_id and edge.dst_port == "初始值"
    ]
    relay_out_edges = [
        edge for edge in model.edges.values() if edge.src_node == relay_node_id and edge.src_port == "值"
    ]
    assert len(relay_in_edges) == 1
    assert len(relay_out_edges) == 1
    assert relay_in_edges[0].src_node == source_flow.id
    assert relay_out_edges[0].dst_node == target_flow.id
    assert relay_out_edges[0].dst_port == "值"


def test_local_variable_relay_inserter_shares_relay_chain_by_source_port() -> None:
    """
    回归：当多个远端消费者都来自同一个源节点的同一个数据输出端口时，
    应共用一条 relay 链，而不是每条边都插一套 relay。
    """
    model = GraphModel(graph_id="test_local_var_relay_shared", graph_name="test_local_var_relay_shared")

    # flow_1：事件节点【实体创建时】输出“事件源GUID”
    source_flow = NodeModel(
        id="flow_1",
        title="实体创建时",
        category="事件节点",
        inputs=[],
        outputs=[
            PortModel(name="流程出", is_input=False),
            PortModel(name="事件源GUID", is_input=False),
        ],
    )
    source_flow._rebuild_port_maps()
    model.nodes[source_flow.id] = source_flow

    # flow_2..flow_12：补齐块内 flow_nodes 序列（中间节点仅需流程端口）
    for index in range(2, 13):
        flow_id = f"flow_{index}"
        if index in {10, 11, 12}:
            # 消费者：执行节点【设置局部变量】输入“值”
            node = NodeModel(
                id=flow_id,
                title="设置局部变量",
                category="执行节点",
                inputs=[
                    PortModel(name="流程入", is_input=True),
                    PortModel(name="局部变量", is_input=True),
                    PortModel(name="值", is_input=True),
                ],
                outputs=[PortModel(name="流程出", is_input=False)],
            )
        else:
            node = NodeModel(
                id=flow_id,
                title=f"中间节点{index}",
                category="执行节点",
                inputs=[PortModel(name="流程入", is_input=True)],
                outputs=[PortModel(name="流程出", is_input=False)],
            )
        node._rebuild_port_maps()
        model.nodes[flow_id] = node

    # 三条长边：都来自 flow_1.事件源GUID，去往不同远端消费者
    original_edges = [
        EdgeModel(id="edge_long_10", src_node="flow_1", src_port="事件源GUID", dst_node="flow_10", dst_port="值"),
        EdgeModel(id="edge_long_11", src_node="flow_1", src_port="事件源GUID", dst_node="flow_11", dst_port="值"),
        EdgeModel(id="edge_long_12", src_node="flow_1", src_port="事件源GUID", dst_node="flow_12", dst_port="值"),
    ]
    for edge in original_edges:
        model.edges[edge.id] = edge

    layout_blocks: list[LayoutBlock] = [
        LayoutBlock(flow_nodes=[f"flow_{i}" for i in range(1, 13)], order_index=1, last_node_branches=[]),
    ]
    copy_manager = GlobalCopyManager(model, layout_blocks)
    copy_manager.analyze_dependencies()
    node_registry = get_node_registry(PROJECT_ROOT, include_composite=True)

    forced_by_block, all_relay_nodes, did_mutate = insert_local_variable_relays_after_global_copy(
        model=model,
        layout_blocks=layout_blocks,
        global_copy_manager=copy_manager,
        max_block_distance=5,
        node_registry=node_registry,
    )

    assert did_mutate
    for edge in original_edges:
        assert edge.id not in model.edges

    # max_distance(flow_1->flow_12)=11，阈值=5：应生成 slot=5 与 slot=10 两个 relay（共享）
    relay_node_ids = sorted(
        [node_id for node_id in model.nodes.keys() if str(node_id).startswith(LOCAL_VAR_RELAY_NODE_ID_PREFIX)]
    )
    assert len(relay_node_ids) == 2, "三个消费者应共享两段 relay 链，而不是各插各的"

    slots = sorted([parse_local_var_relay_forced_slot_index(node_id) for node_id in relay_node_ids])
    assert slots == [5, 10]

    for relay_node_id in relay_node_ids:
        assert relay_node_id in all_relay_nodes
        assert relay_node_id in forced_by_block.get("block_1", set())

    relay_slot_5 = [node_id for node_id in relay_node_ids if parse_local_var_relay_forced_slot_index(node_id) == 5][0]
    relay_slot_10 = [node_id for node_id in relay_node_ids if parse_local_var_relay_forced_slot_index(node_id) == 10][0]

    # 共享链边：flow_1 -> relay(5) -> relay(10)
    chain_edge_1 = [
        edge
        for edge in model.edges.values()
        if edge.src_node == "flow_1"
        and edge.src_port == "事件源GUID"
        and edge.dst_node == relay_slot_5
        and edge.dst_port == "初始值"
    ]
    chain_edge_2 = [
        edge
        for edge in model.edges.values()
        if edge.src_node == relay_slot_5
        and edge.src_port == "值"
        and edge.dst_node == relay_slot_10
        and edge.dst_port == "初始值"
    ]
    assert len(chain_edge_1) == 1
    assert len(chain_edge_2) == 1

    # 消费者分叉：flow_10/11 从 slot_5 分叉；flow_12 从 slot_10 分叉
    to_flow_10 = [
        edge for edge in model.edges.values() if edge.dst_node == "flow_10" and edge.dst_port == "值"
    ]
    to_flow_11 = [
        edge for edge in model.edges.values() if edge.dst_node == "flow_11" and edge.dst_port == "值"
    ]
    to_flow_12 = [
        edge for edge in model.edges.values() if edge.dst_node == "flow_12" and edge.dst_port == "值"
    ]
    assert len(to_flow_10) == 1 and to_flow_10[0].src_node == relay_slot_5 and to_flow_10[0].src_port == "值"
    assert len(to_flow_11) == 1 and to_flow_11[0].src_node == relay_slot_5 and to_flow_11[0].src_port == "值"
    assert len(to_flow_12) == 1 and to_flow_12[0].src_node == relay_slot_10 and to_flow_12[0].src_port == "值"


def test_local_variable_relay_forced_slot_is_applied_by_compute_data_x_positions() -> None:
    """回归：relay node_id 编码的 slot 会在 X 轴分配阶段被优先采用（用于真正缩短长线）。"""
    settings.set_config_path(PROJECT_ROOT)

    model = GraphModel(graph_id="test_local_var_relay_slot", graph_name="test_local_var_relay_slot")
    model.nodes["flow_1"] = NodeModel(
        id="flow_1",
        title="实体创建时",
        category="事件节点",
        inputs=[],
        outputs=[PortModel(name="流程出", is_input=False)],
    )
    model.nodes["flow_1"]._rebuild_port_maps()
    model.nodes["flow_10"] = NodeModel(
        id="flow_10",
        title="设置局部变量",
        category="执行节点",
        inputs=[PortModel(name="流程入", is_input=True)],
        outputs=[PortModel(name="流程出", is_input=False)],
    )
    model.nodes["flow_10"]._rebuild_port_maps()

    relay_node_id = f"{LOCAL_VAR_RELAY_NODE_ID_PREFIX}1_slot_5_deadbeef00_01"
    model.nodes[relay_node_id] = NodeModel(
        id=relay_node_id,
        title="获取局部变量",
        category="查询节点",
        inputs=[PortModel(name="初始值", is_input=True)],
        outputs=[PortModel(name="值", is_input=False)],
    )
    model.nodes[relay_node_id]._rebuild_port_maps()

    # 构造最小 BlockLayoutContext：只验证 compute_data_x_positions 的“slot override”逻辑
    from engine.layout.blocks.block_layout_context import BlockLayoutContext

    slot_width = compute_slot_width_from_node_width(float(NODE_WIDTH_DEFAULT))
    context = BlockLayoutContext(
        model=model,
        flow_node_ids=["flow_1", "flow_10"],
        node_width=float(NODE_WIDTH_DEFAULT),
        node_height=200.0,
        data_base_y=200.0,
        flow_to_data_gap=40.0,
        data_stack_gap=40.0,
        ui_node_header_height=0.0,
        ui_row_height=0.0,
        input_port_to_data_gap=20.0,
        global_layout_context=None,
        block_order_index=1,
        event_flow_title=None,
        event_flow_id=None,
        shared_edge_indices=None,
    )
    context.data_nodes_in_order = [relay_node_id]

    # 即便该节点被链信息覆盖，也必须优先使用 node_id 编码的 slot
    context.data_chain_ids_by_node[relay_node_id] = [1]
    context.chain_target_flow[1] = "flow_10"
    context.node_position_in_chain[(relay_node_id, 1)] = 0

    flow_x_positions = {"flow_1": 0.0, "flow_10": 9.0}
    data_x_positions = compute_data_x_positions(context, flow_x_positions)
    assert data_x_positions.get(relay_node_id) == 5.0

    # 额外断言：slot 被写回 node_slot_index，便于后续阶段复用
    assert context.node_slot_index.get(relay_node_id) == 5


def test_local_variable_relay_inserter_splits_long_within_block_pure_data_source_edges() -> None:
    """
    回归：当纯数据节点（无流程端口）作为源，其输出端口被多个远端流程节点消费，且跨度超过阈值时，
    应按“最早消费者流程节点”为锚点插入共享的【获取局部变量】relay 链，并仅重写超过阈值的消费者边。

    典型场景：查询节点【以GUID查询实体】输出“实体”同时连接到多个【播放限时特效】的“目标实体”。
    """
    model = GraphModel(graph_id="test_local_var_relay_pure_data_src", graph_name="test_local_var_relay_pure_data_src")

    # 纯数据源：查询节点【以GUID查询实体】输出“实体”
    data_src = NodeModel(
        id="data_query_1",
        title="以GUID查询实体",
        category="查询节点",
        inputs=[PortModel(name="GUID", is_input=True)],
        outputs=[PortModel(name="实体", is_input=False)],
    )
    data_src._rebuild_port_maps()
    model.nodes[data_src.id] = data_src

    # 构造 1 个块内的流程链：flow_1 .. flow_12
    # 使用真实执行节点【播放限时特效】作为消费者（具备流程口 + 目标实体入参）
    for index in range(1, 13):
        flow_id = f"flow_{index}"
        node = NodeModel(
            id=flow_id,
            title="播放限时特效",
            category="执行节点",
            inputs=[
                PortModel(name="流程入", is_input=True),
                PortModel(name="特效资产", is_input=True),
                PortModel(name="目标实体", is_input=True),
                PortModel(name="挂接点名称", is_input=True),
                PortModel(name="是否跟随目标运动", is_input=True),
                PortModel(name="是否跟随目标旋转", is_input=True),
                PortModel(name="位置偏移", is_input=True),
                PortModel(name="旋转偏移", is_input=True),
                PortModel(name="缩放倍率", is_input=True),
                PortModel(name="是否播放自带的音效", is_input=True),
            ],
            outputs=[PortModel(name="流程出", is_input=False)],
        )
        node._rebuild_port_maps()
        model.nodes[flow_id] = node

    # 三条消费者边：最早消费者 flow_2（锚点），中间 flow_7（<=阈值），最远 flow_12（>阈值）
    original_edges = [
        EdgeModel(
            id="edge_data_to_flow_02",
            src_node=data_src.id,
            src_port="实体",
            dst_node="flow_2",
            dst_port="目标实体",
        ),
        EdgeModel(
            id="edge_data_to_flow_07",
            src_node=data_src.id,
            src_port="实体",
            dst_node="flow_7",
            dst_port="目标实体",
        ),
        EdgeModel(
            id="edge_data_to_flow_12",
            src_node=data_src.id,
            src_port="实体",
            dst_node="flow_12",
            dst_port="目标实体",
        ),
    ]
    for edge in original_edges:
        model.edges[edge.id] = edge

    layout_blocks: list[LayoutBlock] = [
        LayoutBlock(flow_nodes=[f"flow_{i}" for i in range(1, 13)], order_index=1, last_node_branches=[]),
    ]
    copy_manager = GlobalCopyManager(model, layout_blocks)
    copy_manager.analyze_dependencies()
    node_registry = get_node_registry(PROJECT_ROOT, include_composite=True)

    threshold = 5
    forced_by_block, all_relay_nodes, did_mutate = insert_local_variable_relays_after_global_copy(
        model=model,
        layout_blocks=layout_blocks,
        global_copy_manager=copy_manager,
        max_block_distance=threshold,
        node_registry=node_registry,
    )

    assert did_mutate

    # 预期：锚点=flow_2(index=1)，最远 flow_12(index=11)，跨度=10>阈值=5 => 生成一个 relay(slot=1+5=6)
    relay_node_ids = sorted(
        [node_id for node_id in model.nodes.keys() if str(node_id).startswith(LOCAL_VAR_RELAY_NODE_ID_PREFIX)]
    )
    assert len(relay_node_ids) == 1
    relay_node_id = relay_node_ids[0]
    assert parse_local_var_relay_forced_slot_index(relay_node_id) == 6
    assert relay_node_id in all_relay_nodes
    assert relay_node_id in forced_by_block.get("block_1", set())

    # 边重写：最远消费者（flow_12）应被改为 relay -> flow_12；锚点与阈值内消费者保持原边
    assert "edge_data_to_flow_12" not in model.edges
    rewritten_to_flow_12 = [
        edge
        for edge in model.edges.values()
        if edge.dst_node == "flow_12" and edge.dst_port == "目标实体"
    ]
    assert len(rewritten_to_flow_12) == 1
    assert rewritten_to_flow_12[0].src_node == relay_node_id
    assert rewritten_to_flow_12[0].src_port == "值"

    assert "edge_data_to_flow_02" in model.edges
    assert "edge_data_to_flow_07" in model.edges

    # 共享链边：data_src.实体 -> relay.初始值
    chain_edges = [
        edge
        for edge in model.edges.values()
        if edge.src_node == data_src.id
        and edge.src_port == "实体"
        and edge.dst_node == relay_node_id
        and edge.dst_port == "初始值"
    ]
    assert len(chain_edges) == 1


def test_local_variable_relay_inserter_is_idempotent_for_pure_data_source_edges() -> None:
    """回归：对同一模型连续执行两次 inserter，第二次不应再次改线（尤其不应产生 relay 自环）。"""
    model = GraphModel(graph_id="test_local_var_relay_pure_data_idempotent", graph_name="test_local_var_relay_pure_data_idempotent")

    data_src = NodeModel(
        id="data_query_1",
        title="以GUID查询实体",
        category="查询节点",
        inputs=[PortModel(name="GUID", is_input=True)],
        outputs=[PortModel(name="实体", is_input=False)],
    )
    data_src._rebuild_port_maps()
    model.nodes[data_src.id] = data_src

    for index in range(1, 13):
        flow_id = f"flow_{index}"
        node = NodeModel(
            id=flow_id,
            title="播放限时特效",
            category="执行节点",
            inputs=[
                PortModel(name="流程入", is_input=True),
                PortModel(name="特效资产", is_input=True),
                PortModel(name="目标实体", is_input=True),
                PortModel(name="挂接点名称", is_input=True),
                PortModel(name="是否跟随目标运动", is_input=True),
                PortModel(name="是否跟随目标旋转", is_input=True),
                PortModel(name="位置偏移", is_input=True),
                PortModel(name="旋转偏移", is_input=True),
                PortModel(name="缩放倍率", is_input=True),
                PortModel(name="是否播放自带的音效", is_input=True),
            ],
            outputs=[PortModel(name="流程出", is_input=False)],
        )
        node._rebuild_port_maps()
        model.nodes[flow_id] = node

    original_edges = [
        EdgeModel(id="edge_data_to_flow_02", src_node=data_src.id, src_port="实体", dst_node="flow_2", dst_port="目标实体"),
        EdgeModel(id="edge_data_to_flow_07", src_node=data_src.id, src_port="实体", dst_node="flow_7", dst_port="目标实体"),
        EdgeModel(id="edge_data_to_flow_12", src_node=data_src.id, src_port="实体", dst_node="flow_12", dst_port="目标实体"),
    ]
    for edge in original_edges:
        model.edges[edge.id] = edge

    layout_blocks: list[LayoutBlock] = [
        LayoutBlock(flow_nodes=[f"flow_{i}" for i in range(1, 13)], order_index=1, last_node_branches=[]),
    ]
    node_registry = get_node_registry(PROJECT_ROOT, include_composite=True)

    copy_manager_1 = GlobalCopyManager(model, layout_blocks)
    copy_manager_1.analyze_dependencies()
    _, _, did_mutate_1 = insert_local_variable_relays_after_global_copy(
        model=model,
        layout_blocks=layout_blocks,
        global_copy_manager=copy_manager_1,
        max_block_distance=5,
        node_registry=node_registry,
    )
    assert did_mutate_1

    relay_node_ids = sorted([nid for nid in model.nodes.keys() if str(nid).startswith(LOCAL_VAR_RELAY_NODE_ID_PREFIX)])
    assert len(relay_node_ids) == 1
    relay_node_id = relay_node_ids[0]

    # 第一次之后必须存在源->relay.初始值 的链边，且不存在 relay->relay 自环
    assert any(
        edge.src_node == data_src.id and edge.dst_node == relay_node_id and edge.dst_port == "初始值"
        for edge in model.edges.values()
    )
    assert not any(edge.src_node == relay_node_id and edge.dst_node == relay_node_id for edge in model.edges.values())

    # 第二次：方案B（清理→重建）会先还原并删除旧 relay，再按同样规则重建；
    # 因此允许 did_mutate=True，但最终结构必须保持稳定且不产生自环。
    nodes_sig_after_first = sorted(
        [
            (
                node.id,
                node.title,
                node.category,
                tuple(port.name for port in (node.inputs or [])),
                tuple(port.name for port in (node.outputs or [])),
            )
            for node in model.nodes.values()
        ]
    )
    edges_sig_after_first = sorted(
        [
            (
                edge.id,
                edge.src_node,
                edge.src_port,
                edge.dst_node,
                edge.dst_port,
            )
            for edge in model.edges.values()
        ]
    )
    copy_manager_2 = GlobalCopyManager(model, layout_blocks)
    copy_manager_2.analyze_dependencies()
    _, _, did_mutate_2 = insert_local_variable_relays_after_global_copy(
        model=model,
        layout_blocks=layout_blocks,
        global_copy_manager=copy_manager_2,
        max_block_distance=5,
        node_registry=node_registry,
    )
    assert did_mutate_2
    assert any(
        edge.src_node == data_src.id and edge.dst_node == relay_node_id and edge.dst_port == "初始值"
        for edge in model.edges.values()
    )
    assert not any(edge.src_node == relay_node_id and edge.dst_node == relay_node_id for edge in model.edges.values())

    nodes_sig_after_second = sorted(
        [
            (
                node.id,
                node.title,
                node.category,
                tuple(port.name for port in (node.inputs or [])),
                tuple(port.name for port in (node.outputs or [])),
            )
            for node in model.nodes.values()
        ]
    )
    edges_sig_after_second = sorted(
        [
            (
                edge.id,
                edge.src_node,
                edge.src_port,
                edge.dst_node,
                edge.dst_port,
            )
            for edge in model.edges.values()
        ]
    )
    assert nodes_sig_after_second == nodes_sig_after_first
    assert edges_sig_after_second == edges_sig_after_first

