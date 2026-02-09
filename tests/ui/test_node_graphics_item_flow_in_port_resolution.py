from __future__ import annotations

from PyQt6 import QtWidgets

from engine.configs.settings import settings
from engine.graph.models import GraphModel, NodeDefRef, NodeModel, PortModel
from engine.nodes.node_registry import get_node_registry

from app.ui.graph.graph_scene import GraphScene
from app.ui.graph.scene_builder import populate_scene_from_model

from tests._helpers.project_paths import get_repo_root


def _ensure_qapplication() -> QtWidgets.QApplication:
    app_instance = QtWidgets.QApplication.instance()
    if app_instance is None:
        app_instance = QtWidgets.QApplication([])
    return app_instance


def test_node_graphics_item_flow_in_resolves_to_main_flow_entry(monkeypatch) -> None:
    """
    回归：当节点同时存在多个“流程输入端口”（例如：有限循环的“流程入/跳出循环”）时，
    UI 侧按端口名“流程入”查找/高亮必须命中真正的“流程入”端口，而不是被其它流程输入口覆盖。
    """
    _ensure_qapplication()

    # 本用例不关注基本块叠加，避免在 Scene 构造/绘制阶段触发布局与额外的图遍历。
    monkeypatch.setattr(settings, "SHOW_BASIC_BLOCKS", False)

    repo_root = get_repo_root()
    node_library = get_node_registry(repo_root, include_composite=True).get_library()

    loop_node = NodeModel(
        id="node_finite_loop",
        title="有限循环",
        category="执行节点",
        node_def_ref=NodeDefRef(kind="builtin", key="执行节点/有限循环"),
        pos=(0.0, 0.0),
        inputs=[
            PortModel(name="流程入", is_input=True),
            PortModel(name="跳出循环", is_input=True),
            PortModel(name="循环起始值", is_input=True),
            PortModel(name="循环终止值", is_input=True),
        ],
        outputs=[
            PortModel(name="循环体", is_input=False),
            PortModel(name="循环完成", is_input=False),
            PortModel(name="当前循环值", is_input=False),
        ],
    )

    model = GraphModel()
    model.metadata["graph_type"] = "server"
    model.nodes[loop_node.id] = loop_node
    loop_node._rebuild_port_maps()

    scene = GraphScene(model, read_only=True, node_library=node_library)
    populate_scene_from_model(scene, enable_batch_mode=True)

    node_item = scene.node_items.get(loop_node.id)
    assert node_item is not None

    flow_in_port_item = node_item.get_port_by_name("流程入", is_input=True)
    assert flow_in_port_item is not None
    assert flow_in_port_item.name == "流程入"

    exit_loop_port_item = node_item.get_port_by_name("跳出循环", is_input=True)
    assert exit_loop_port_item is not None
    assert exit_loop_port_item.name == "跳出循环"
    assert flow_in_port_item is not exit_loop_port_item


