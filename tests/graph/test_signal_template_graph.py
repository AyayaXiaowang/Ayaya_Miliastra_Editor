from __future__ import annotations

from pathlib import Path

from tests._helpers.project_paths import get_repo_root

from engine.graph.graph_code_parser import GraphCodeParser
from engine.graph.models.graph_model import GraphModel
from engine.graph.common import (
    SIGNAL_SEND_NODE_TITLE,
    SIGNAL_LISTEN_NODE_TITLE,
)
from engine.nodes.node_definition_loader import load_all_nodes


def _load_workspace_node_library() -> dict:
    workspace_root = get_repo_root()
    return load_all_nodes(workspace_root, include_composite=True, verbose=False)


def _load_template_graph_model() -> GraphModel:
    # 该模板图依赖示例包下的信号定义（assets/资源库/项目存档/示例项目模板/管理配置/信号）。
    # GraphCodeParser 默认 strict=True；若不切换作用域，信号仓库为空，会导致【监听信号】缺少“信号名”常量并触发 fail-closed。
    from engine.resources.definition_schema_view import set_default_definition_schema_view_active_package_id
    from engine.signal import invalidate_default_signal_repository_cache
    from engine.utils.runtime_scope import set_active_package_id

    workspace_root = get_repo_root()
    graph_path = (
        workspace_root
        / "assets"
        / "资源库"
        / "项目存档"
        / "示例项目模板"
        / "节点图"
        / "server"
        / "实体节点图"
        / "模板示例"
        / "模板示例_信号全类型_发送与监听.py"
    )
    assert graph_path.is_file()
    set_active_package_id("示例项目模板")
    set_default_definition_schema_view_active_package_id("示例项目模板")
    invalidate_default_signal_repository_cache()
    try:
        node_library = _load_workspace_node_library()
        parser = GraphCodeParser(workspace_root, node_library=node_library, verbose=False)
        model, _ = parser.parse_file(graph_path)
        return model
    finally:
        set_active_package_id(None)
        set_default_definition_schema_view_active_package_id(None)
        invalidate_default_signal_repository_cache()


def test_signal_template_graph_has_send_and_listen_signal_nodes() -> None:
    model = _load_template_graph_model()
    titles = {node.title for node in model.nodes.values()}
    assert SIGNAL_SEND_NODE_TITLE in titles
    assert SIGNAL_LISTEN_NODE_TITLE in titles


def test_signal_template_graph_listen_node_has_signal_binding_and_outputs() -> None:
    model = _load_template_graph_model()
    bindings = model.metadata.get("signal_bindings") or {}
    assert isinstance(bindings, dict)

    listen_nodes = [
        node for node in model.nodes.values() if node.title == SIGNAL_LISTEN_NODE_TITLE
    ]
    assert listen_nodes, "模板图中应至少包含一个【监听信号】节点"

    listen_node = listen_nodes[0]
    binding = bindings.get(listen_node.id) or {}
    assert isinstance(binding, dict)
    signal_id = binding.get("signal_id")
    assert isinstance(signal_id, str) and signal_id, "监听信号节点应在解析阶段写入 signal_id 绑定"

    # 事件节点的输出端口应包含信号参数（除流程与事件源外）
    output_names = [port.name for port in listen_node.outputs]
    assert "事件源实体" in output_names
    assert "事件源GUID" in output_names
    assert "信号来源实体" in output_names
    # 其中至少应包含若干以“参数”结尾的端口（来自信号定义）
    assert any(name.endswith("参数") for name in output_names)



