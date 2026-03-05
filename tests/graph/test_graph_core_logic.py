from app.ui.graph.logic.signal_logic import (
    build_signal_node_def_proxy,
    plan_signal_port_sync,
    resolve_signal_binding,
)
from app.ui.graph.logic.struct_logic import (
    build_struct_node_def_proxy,
    plan_struct_port_sync,
    resolve_struct_binding,
)
from engine.graph.common import (
    SIGNAL_LISTEN_NODE_TITLE,
    SIGNAL_LISTEN_STATIC_OUTPUTS,
    SIGNAL_NAME_PORT_NAME,
    SIGNAL_SEND_NODE_TITLE,
    SIGNAL_SEND_STATIC_INPUTS,
    STRUCT_NAME_PORT_NAME,
    STRUCT_SPLIT_NODE_TITLE,
    STRUCT_SPLIT_STATIC_INPUTS,
    STRUCT_SPLIT_STATIC_OUTPUTS,
)
from engine.graph.models.graph_model import NodeModel, PortModel
from engine.graph.models.package_model import SignalConfig, SignalParameterConfig
from engine.nodes.node_definition_loader import NodeDef


def test_signal_logic_builds_proxy_and_plan_for_send_node() -> None:
    signal_config = SignalConfig(
        signal_id="sig_send",
        signal_name="测试信号",
        parameters=[
            SignalParameterConfig(name="能量", parameter_type="Float"),
            SignalParameterConfig(name="标签", parameter_type="String"),
        ],
    )
    signals = {"sig_send": signal_config}
    node = NodeModel(
        id="node_send",
        title=SIGNAL_SEND_NODE_TITLE,
        category="测试",
        inputs=[
            PortModel(name=SIGNAL_SEND_STATIC_INPUTS[0], is_input=True),
            PortModel(name=SIGNAL_SEND_STATIC_INPUTS[1], is_input=True),
        ],
        outputs=[],
    )
    base_def = NodeDef(
        name=SIGNAL_SEND_NODE_TITLE,
        category="测试",
        inputs=list(SIGNAL_SEND_STATIC_INPUTS),
        outputs=["流程出"],
    )

    context = resolve_signal_binding(node, signals, bound_signal_id="sig_send")
    assert context is not None

    proxy = build_signal_node_def_proxy(node.title, base_def, context)
    assert proxy is not None
    assert proxy.input_types["能量"] == "Float"
    assert proxy.input_types["标签"] == "String"

    plan = plan_signal_port_sync(node, context)
    assert set(plan.add_inputs) == {"能量", "标签"}
    assert plan.bound_signal_id == "sig_send"
    assert plan.signal_name_constant == "测试信号"
    assert plan.add_outputs == []


def test_signal_logic_infers_binding_from_constant_for_listen_node() -> None:
    signal_config = SignalConfig(
        signal_id="sig_listen",
        signal_name="监听信号",
        parameters=[SignalParameterConfig(name="事件", parameter_type="Guid")],
    )
    signals = {"sig_listen": signal_config}
    node = NodeModel(
        id="node_listen",
        title=SIGNAL_LISTEN_NODE_TITLE,
        category="测试",
        inputs=[],
        outputs=[],
        input_constants={SIGNAL_NAME_PORT_NAME: "监听信号"},
    )
    base_def = NodeDef(
        name=SIGNAL_LISTEN_NODE_TITLE,
        category="测试",
        inputs=[SIGNAL_NAME_PORT_NAME],
        outputs=list(SIGNAL_LISTEN_STATIC_OUTPUTS),
    )

    context = resolve_signal_binding(node, signals, bound_signal_id=None)
    assert context is not None
    assert context.bound_signal_id == "sig_listen"

    proxy = build_signal_node_def_proxy(node.title, base_def, context)
    assert proxy is not None
    assert proxy.output_types["事件"] == "Guid"

    plan = plan_signal_port_sync(node, context)
    assert plan.bound_signal_id == "sig_listen"
    assert SIGNAL_NAME_PORT_NAME in plan.add_inputs
    assert plan.add_outputs == ["事件"]


def test_struct_logic_plans_ports_for_split_node() -> None:
    struct_payload = {
        "name": "玩家属性",
        "value": [
            {"key": "生命", "param_type": "Int32"},
            {"key": "攻击", "param_type": "Float"},
        ],
    }
    structs = {"struct_player": struct_payload}
    binding_payload = {
        "struct_id": "struct_player",
        "struct_name": "玩家属性",
        "field_names": ["生命", "攻击"],
    }
    context = resolve_struct_binding(binding_payload, structs)
    assert context is not None

    base_def = NodeDef(
        name=STRUCT_SPLIT_NODE_TITLE,
        category="测试",
        inputs=list(STRUCT_SPLIT_STATIC_INPUTS),
        outputs=list(STRUCT_SPLIT_STATIC_OUTPUTS),
    )

    proxy = build_struct_node_def_proxy(STRUCT_SPLIT_NODE_TITLE, base_def, context)
    assert proxy is not None
    assert proxy.output_types["生命"] == "整数"
    assert proxy.output_types["攻击"] == "浮点数"

    node = NodeModel(
        id="node_split",
        title=STRUCT_SPLIT_NODE_TITLE,
        category="测试",
        inputs=[PortModel(name=STRUCT_SPLIT_STATIC_INPUTS[0], is_input=True)],
        outputs=[],
    )

    plan = plan_struct_port_sync(node, context)
    assert plan.struct_id == "struct_player"
    assert plan.struct_name_constant == "玩家属性"
    assert set(plan.add_outputs) == {"生命", "攻击"}
    assert plan.add_inputs == []

