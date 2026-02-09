from __future__ import annotations

from PyQt6 import QtWidgets

from engine.configs.settings import settings
from engine.graph.models import GraphModel, NodeDefRef, NodeModel, PortModel
from engine.nodes.node_registry import get_node_registry

from app.ui.graph.graph_scene import GraphScene

from tests._helpers.project_paths import get_repo_root


def _ensure_qapplication() -> QtWidgets.QApplication:
    app_instance = QtWidgets.QApplication.instance()
    if app_instance is None:
        app_instance = QtWidgets.QApplication([])
    return app_instance


def test_graph_scene_get_node_def_respects_graph_type_scope_variants(monkeypatch) -> None:
    """
    回归：GraphScene.get_node_def 必须依据 GraphModel.metadata["graph_type"]
    优先命中 `类别/名称#{scope}` 变体，避免误取 server 版本导致：
    - 端口类型缺失（NodeDef.get_port_type 抛错）
    - UI 连线创建时端口找不到（边被跳过）
    """
    _ensure_qapplication()

    # 避免 GraphScene 在构造阶段因 SHOW_BASIC_BLOCKS 触发布局计算（本用例只测 node_def 解析）
    monkeypatch.setattr(settings, "SHOW_BASIC_BLOCKS", False)

    repo_root = get_repo_root()
    node_library = get_node_registry(repo_root, include_composite=True).get_library()

    model = GraphModel()
    model.metadata["graph_type"] = "client"
    scene = GraphScene(model, read_only=True, node_library=node_library)

    # client: 弧度转角度 输入端口为“弧度”，而 server 版本为“弧度值”
    rad_to_deg_node = NodeModel(
        id="node_radian_to_degree",
        title="弧度转角度",
        category="运算节点",
        node_def_ref=NodeDefRef(kind="builtin", key="运算节点/弧度转角度#client"),
        pos=(0.0, 0.0),
        inputs=[PortModel(name="弧度", is_input=True)],
        outputs=[PortModel(name="角度", is_input=False)],
    )
    resolved = scene.get_node_def(rad_to_deg_node)
    assert resolved is not None
    assert resolved.get_port_type("弧度", True) == "浮点数"
    assert resolved.get_port_type("角度", False) == "浮点数"

    # client: 设置局部变量 输入端口为“变量名/变量值”，server 版本为“局部变量/值”
    set_local_var_node = NodeModel(
        id="node_set_local_var",
        title="设置局部变量",
        category="执行节点",
        node_def_ref=NodeDefRef(kind="builtin", key="执行节点/设置局部变量#client"),
        pos=(0.0, 0.0),
        inputs=[
            PortModel(name="流程入", is_input=True),
            PortModel(name="变量名", is_input=True),
            PortModel(name="变量值", is_input=True),
        ],
        outputs=[PortModel(name="流程出", is_input=False)],
    )
    set_local_var_def = scene.get_node_def(set_local_var_node)
    assert set_local_var_def is not None
    assert set_local_var_def.get_port_type("变量名", True) == "字符串"
    assert set_local_var_def.get_port_type("变量值", True) == "泛型"


def test_graph_scene_populate_sample_client_graph_renders_all_edges(monkeypatch) -> None:
    """
    回归：模板示例 client 图在 UI 装配时必须做到“模型边 == 场景边”。

    该用例能同时覆盖：
    - scope-aware 解析是否正确命中 client 变体（否则会出现边引用不存在端口 → UI 跳边）
    - 节点定义是否缺失 inputs（缺失会导致 NodeModel 没有对应端口 → UI 跳边）
    """
    _ensure_qapplication()

    monkeypatch.setattr(settings, "SHOW_BASIC_BLOCKS", False)

    from engine.configs.resource_types import ResourceType
    from engine.graph.semantic import GraphSemanticPass
    from engine.resources.resource_manager import ResourceManager
    from app.ui.graph.scene_builder import populate_scene_from_model

    repo_root = get_repo_root()
    resource_manager = ResourceManager(repo_root)
    # ResourceManager 默认仅索引“共享根”；本用例使用项目存档内的模板示例 client 图，因此需要显式指定作用域。
    resource_manager.rebuild_index(active_package_id="示例项目模板")
    graph_id = "client_template_syntax_sugar_random_vector_01"

    # 强制从 .py 重新解析，避免误用旧缓存掩盖回归
    resource_manager.invalidate_graph_for_reparse(graph_id)
    payload = resource_manager.load_resource(ResourceType.GRAPH, graph_id)
    assert isinstance(payload, dict) and isinstance(payload.get("data"), dict)

    model = GraphModel.deserialize(payload["data"])
    GraphSemanticPass.apply(model)

    node_library = get_node_registry(repo_root, include_composite=True).get_library()
    scene = GraphScene(model, read_only=True, node_library=node_library)
    populate_scene_from_model(scene, enable_batch_mode=True)

    missing_edge_ids = set(model.edges.keys()) - set(scene.edge_items.keys())
    assert missing_edge_ids == set(), f"UI 装配后存在缺失连线（会表现为孤立节点）: {sorted(missing_edge_ids)[:20]}"


