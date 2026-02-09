from __future__ import annotations

from engine.graph.models.graph_model import GraphModel, NodeDefRef, NodeModel, PortModel, EdgeModel
from engine.nodes.node_definition_loader import NodeDef
from engine.resources.graph_loader import GraphLoader


def test_effective_port_types_cache_propagates_local_var_value_from_initial_constant() -> None:
    """回归：获取局部变量（server 形态）应将“值”输出端口类型透传为“初始值”的有效类型。"""
    model = GraphModel(graph_id="g_local_var", graph_name="g_local_var")
    model.metadata = {"graph_type": "server"}

    node = NodeModel(
        id="n_local_var",
        title="获取局部变量",
        category="查询节点",
        node_def_ref=NodeDefRef(kind="builtin", key="查询节点/获取局部变量"),
        inputs=[PortModel(name="初始值", is_input=True)],
        outputs=[PortModel(name="局部变量", is_input=False), PortModel(name="值", is_input=False)],
        input_constants={"初始值": "hello"},
    )
    node._rebuild_port_maps()
    model.nodes[node.id] = node

    node_library = {
        "查询节点/获取局部变量": NodeDef(
            name="获取局部变量",
            category="查询节点",
            inputs=["初始值"],
            outputs=["局部变量", "值"],
            input_types={"初始值": "泛型"},
            output_types={"局部变量": "局部变量", "值": "泛型"},
        )
    }

    GraphLoader._apply_port_type_snapshots(model, node_library=node_library)

    assert model.nodes["n_local_var"].input_types["初始值"] == "字符串"
    assert model.nodes["n_local_var"].output_types["值"] == "字符串"


def test_effective_port_types_cache_derives_compose_dict_key_value_from_output_alias() -> None:
    """回归：拼装字典的 键*/值* 端口应按输出“字典”的别名字典类型收敛。"""
    model = GraphModel(graph_id="g_dict", graph_name="g_dict")
    model.metadata = {
        "port_type_overrides": {
            "n_dict": {"字典": "字符串_整数字典"},
        }
    }

    node = NodeModel(
        id="n_dict",
        title="拼装字典",
        category="运算节点",
        node_def_ref=NodeDefRef(kind="builtin", key="运算节点/拼装字典"),
        inputs=[PortModel(name="键0", is_input=True), PortModel(name="值0", is_input=True)],
        outputs=[PortModel(name="字典", is_input=False)],
    )
    node._rebuild_port_maps()
    model.nodes[node.id] = node

    node_library = {
        "运算节点/拼装字典": NodeDef(
            name="拼装字典",
            category="运算节点",
            inputs=["键0", "值0"],
            outputs=["字典"],
            input_types={"键0": "泛型", "值0": "泛型"},
            output_types={"字典": "泛型字典"},
            dynamic_port_type="泛型",
        )
    }

    GraphLoader._apply_port_type_snapshots(model, node_library=node_library)

    assert model.nodes["n_dict"].output_types["字典"] == "字符串_整数字典"
    assert model.nodes["n_dict"].input_types["键0"] == "字符串"
    assert model.nodes["n_dict"].input_types["值0"] == "整数"


def test_effective_port_types_cache_propagates_downstream_input_type_to_upstream_generic_output() -> None:
    """回归：当下游泛型输入端口通过常量已确定具体类型时，上游泛型输出端口应可随连线推断为同型。"""
    model = GraphModel(graph_id="g_propagate", graph_name="g_propagate")

    src = NodeModel(
        id="n_src",
        title="源节点",
        category="运算节点",
        node_def_ref=NodeDefRef(kind="builtin", key="运算节点/源节点"),
        inputs=[],
        outputs=[PortModel(name="结果", is_input=False)],
    )
    src._rebuild_port_maps()
    dst = NodeModel(
        id="n_dst",
        title="目标节点",
        category="运算节点",
        node_def_ref=NodeDefRef(kind="builtin", key="运算节点/目标节点"),
        inputs=[PortModel(name="输入", is_input=True)],
        outputs=[],
        input_constants={"输入": 1},
    )
    dst._rebuild_port_maps()
    model.nodes[src.id] = src
    model.nodes[dst.id] = dst
    model.edges["e1"] = EdgeModel(
        id="e1",
        src_node="n_src",
        src_port="结果",
        dst_node="n_dst",
        dst_port="输入",
    )

    node_library = {
        "运算节点/源节点": NodeDef(
            name="源节点",
            category="运算节点",
            inputs=[],
            outputs=["结果"],
            output_types={"结果": "泛型"},
        ),
        "运算节点/目标节点": NodeDef(
            name="目标节点",
            category="运算节点",
            inputs=["输入"],
            outputs=[],
            input_types={"输入": "泛型"},
        ),
    }

    GraphLoader._apply_port_type_snapshots(model, node_library=node_library)

    assert model.nodes["n_dst"].input_types["输入"] == "整数"
    assert model.nodes["n_src"].output_types["结果"] == "整数"


