from __future__ import annotations

import pytest
from PyQt6 import QtWidgets

from engine.graph.models.graph_model import GraphModel
from app.ui.graph.graph_scene import GraphScene
from app.ui.graph.graph_view import GraphView
from app.ui.controllers.graph_editor_controller import GraphEditorController
from app.models.edit_session_capabilities import EditSessionCapabilities


class _DummyResourceManager:
    """满足 GraphEditorController 构造所需的最小占位对象。"""


def _ensure_qt_app() -> QtWidgets.QApplication:
    app_instance = QtWidgets.QApplication.instance()
    if app_instance is None:
        app_instance = QtWidgets.QApplication([])
    return app_instance


def test_graph_scene_rejects_mismatched_read_only_and_capabilities() -> None:
    _ensure_qt_app()
    model = GraphModel()
    with pytest.raises(ValueError):
        GraphScene(
            model,
            read_only=False,  # 与 read_only_preview 冲突
            edit_session_capabilities=EditSessionCapabilities.read_only_preview(),
        )


def test_graph_editor_controller_keeps_view_and_scene_capabilities_in_sync() -> None:
    _ensure_qt_app()

    capabilities = EditSessionCapabilities.interactive_preview()
    model = GraphModel()
    scene = GraphScene(model, read_only=False, edit_session_capabilities=capabilities)
    view = GraphView(scene, edit_session_capabilities=capabilities)

    controller = GraphEditorController(
        resource_manager=_DummyResourceManager(),  # type: ignore[arg-type]
        model=model,
        scene=scene,
        view=view,
        node_library={},
        edit_session_capabilities=capabilities,
        parent=None,
    )

    # 初始：可交互 -> view/scene 都不应只读，且开放“添加节点”入口
    assert controller.edit_session_capabilities.can_interact is True
    assert controller.scene.read_only is False
    assert controller.view.read_only is False
    assert controller.view.on_add_node_callback is not None

    # 切到只读预览：view/scene 必须同步只读，并关闭“添加节点”入口
    read_only_capabilities = EditSessionCapabilities.read_only_preview()
    controller.set_edit_session_capabilities(read_only_capabilities)
    assert controller.edit_session_capabilities.can_interact is False
    assert controller.scene.read_only is True
    assert controller.view.read_only is True
    assert controller.view.on_add_node_callback is None


def test_graph_editor_controller_load_graph_applies_capabilities() -> None:
    _ensure_qt_app()

    capabilities = EditSessionCapabilities.read_only_preview()
    initial_model = GraphModel()
    initial_scene = GraphScene(
        initial_model,
        read_only=True,
        edit_session_capabilities=capabilities,
        node_library={},
    )
    view = GraphView(initial_scene, edit_session_capabilities=capabilities)

    controller = GraphEditorController(
        resource_manager=_DummyResourceManager(),  # type: ignore[arg-type]
        model=initial_model,
        scene=initial_scene,
        view=view,
        node_library={},
        edit_session_capabilities=capabilities,
        parent=None,
    )

    graph_data = {
        "graph_id": "graph_test",
        "graph_name": "测试图",
        "nodes": [],
        "edges": [],
        "graph_variables": [],
        "metadata": {},
    }
    controller.load_graph("graph_test", graph_data, container=None)

    assert controller.scene.read_only is True
    assert controller.view.read_only is True
    assert controller.view.on_add_node_callback is None


def test_graph_editor_controller_open_graph_for_editing_restores_interactive_capabilities() -> None:
    """回归：从只读态进入编辑器打开图时，不应残留只读导致自动排版入口消失。"""
    _ensure_qt_app()

    capabilities = EditSessionCapabilities.read_only_preview()
    model = GraphModel()
    scene = GraphScene(
        model,
        read_only=True,
        edit_session_capabilities=capabilities,
        node_library={},
    )
    view = GraphView(scene, edit_session_capabilities=capabilities)

    controller = GraphEditorController(
        resource_manager=_DummyResourceManager(),  # type: ignore[arg-type]
        model=model,
        scene=scene,
        view=view,
        node_library={},
        edit_session_capabilities=capabilities,
        parent=None,
    )

    graph_data = {
        "graph_id": "graph_test",
        "graph_name": "测试图",
        "nodes": [],
        "edges": [],
        "graph_variables": [],
        "metadata": {},
    }
    controller.open_graph_for_editing("graph_test", graph_data, container=None)

    assert controller.edit_session_capabilities.can_interact is True
    assert controller.edit_session_capabilities.can_validate is True
    assert controller.scene.read_only is False
    assert controller.view.read_only is False


