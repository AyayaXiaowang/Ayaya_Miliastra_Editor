from __future__ import annotations

import pytest
from PyQt6 import QtCore, QtGui, QtWidgets

from app.models.edit_session_capabilities import EditSessionCapabilities
from app.ui.graph.graph_canvas_host import GraphCanvasHost
from app.ui.graph.graph_view.shared_graph_view_lease import SharedGraphViewLeaseManager


def _ensure_qt_app() -> QtWidgets.QApplication:
    app_instance = QtWidgets.QApplication.instance()
    if app_instance is None:
        app_instance = QtWidgets.QApplication([])
    return app_instance


class _DummyOverlayManager:
    def __init__(self) -> None:
        self.stop_called: bool = False

    def stop_all_animations(self) -> None:
        self.stop_called = True


class _DummyScene:
    def __init__(self) -> None:
        self.node_library: object | None = None


class _DummyViewport(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._rect = QtCore.QRect(0, 0, 800, 600)

    def rect(self) -> QtCore.QRect:
        return QtCore.QRect(self._rect)


class _DummyGraphView(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.enable_click_signals: bool = False
        self.show_coordinates: bool = False
        self.node_library: object | None = None
        self.overlay_manager = _DummyOverlayManager()

        self._scene = _DummyScene()
        self._viewport = _DummyViewport()
        self._transform = QtGui.QTransform()
        self._center_scene_pos = QtCore.QPointF(0.0, 0.0)
        self._trans_anchor = None
        self._resize_anchor = None
        self.restore_called: bool = False
        self.extra_button: object | None = None
        self.extensions_visible: bool = True

    def viewport(self) -> _DummyViewport:
        return self._viewport

    def scene(self) -> object:
        return self._scene

    def mapToScene(self, point: QtCore.QPoint) -> QtCore.QPointF:
        return QtCore.QPointF(float(point.x()), float(point.y()))

    def transform(self) -> QtGui.QTransform:
        return QtGui.QTransform(self._transform)

    def setTransform(self, transform: QtGui.QTransform) -> None:
        self._transform = QtGui.QTransform(transform)

    def resetTransform(self) -> None:
        self._transform = QtGui.QTransform()

    def scale(self, sx: float, sy: float) -> None:
        self._transform = QtGui.QTransform(self._transform).scale(float(sx), float(sy))

    def centerOn(self, pos: QtCore.QPointF) -> None:
        self._center_scene_pos = QtCore.QPointF(pos)

    def transformationAnchor(self):
        return self._trans_anchor

    def resizeAnchor(self):
        return self._resize_anchor

    def setTransformationAnchor(self, anchor) -> None:
        self._trans_anchor = anchor

    def setResizeAnchor(self, anchor) -> None:
        self._resize_anchor = anchor

    def restore_all_opacity(self) -> None:
        self.restore_called = True

    def set_extra_top_right_button(self, button: object | None) -> None:
        self.extra_button = button

    def set_top_right_extensions_visible(self, visible: bool) -> None:
        self.extensions_visible = bool(visible)


class _DummyGraphController:
    def __init__(self, capabilities: EditSessionCapabilities) -> None:
        self.edit_session_capabilities = capabilities
        self.set_calls: list[EditSessionCapabilities] = []

    def set_edit_session_capabilities(self, capabilities: EditSessionCapabilities) -> None:
        self.edit_session_capabilities = capabilities
        self.set_calls.append(capabilities)


def test_shared_graph_view_lease_acquire_and_release_roundtrip() -> None:
    _ensure_qt_app()
    lease_manager = SharedGraphViewLeaseManager()

    graph_view = _DummyGraphView()
    todo_preview_host = GraphCanvasHost()
    graph_editor_host = GraphCanvasHost()

    preview_edit_button = QtWidgets.QPushButton("编辑")
    graph_editor_todo_button = QtWidgets.QPushButton("前往执行")
    node_library = object()

    before_capabilities = EditSessionCapabilities.full_editing()
    graph_controller = _DummyGraphController(before_capabilities)

    assert float(graph_view.transform().m11()) == pytest.approx(1.0)

    lease_manager.acquire_for_todo_preview(
        graph_view=graph_view,  # type: ignore[arg-type]
        todo_preview_host=todo_preview_host,
        graph_controller=graph_controller,
        preview_edit_button=preview_edit_button,
        node_library=node_library,
    )

    assert lease_manager.owner == SharedGraphViewLeaseManager.OWNER_TODO_PREVIEW
    assert graph_view.parentWidget() is todo_preview_host
    assert graph_view.enable_click_signals is True
    assert graph_view.show_coordinates is True
    assert preview_edit_button.isVisible() is True
    assert graph_view.extra_button is preview_edit_button
    assert graph_view.node_library is node_library
    assert getattr(graph_view.scene(), "node_library") is node_library
    assert graph_controller.edit_session_capabilities == EditSessionCapabilities.read_only_preview()

    # 模拟：预览侧执行 fit_all/聚焦后把缩放拉到极小（压缩状态）
    graph_view.resetTransform()
    graph_view.scale(0.02, 0.02)
    assert float(graph_view.transform().m11()) == pytest.approx(0.02)

    lease_manager.release_to_graph_editor(
        graph_view=graph_view,  # type: ignore[arg-type]
        graph_editor_host=graph_editor_host,
        graph_controller=graph_controller,
        graph_editor_todo_button=graph_editor_todo_button,
        todo_preview_edit_button=preview_edit_button,
    )

    assert lease_manager.owner == SharedGraphViewLeaseManager.OWNER_GRAPH_EDITOR
    assert graph_view.parentWidget() is graph_editor_host
    assert graph_view.enable_click_signals is False
    assert graph_view.restore_called is True
    assert graph_view.overlay_manager.stop_called is True
    assert preview_edit_button.isVisible() is False
    assert graph_view.extra_button is graph_editor_todo_button
    assert graph_controller.edit_session_capabilities == before_capabilities
    # 归还编辑器后应恢复为借出前的缩放（避免把“压缩状态”带回编辑器）
    assert float(graph_view.transform().m11()) == pytest.approx(1.0)


def test_shared_graph_view_lease_acquire_is_idempotent_for_same_host() -> None:
    _ensure_qt_app()
    lease_manager = SharedGraphViewLeaseManager()

    graph_view = _DummyGraphView()
    todo_preview_host = GraphCanvasHost()
    graph_controller = _DummyGraphController(EditSessionCapabilities.full_editing())

    lease_manager.acquire_for_todo_preview(
        graph_view=graph_view,  # type: ignore[arg-type]
        todo_preview_host=todo_preview_host,
        graph_controller=graph_controller,
        preview_edit_button=None,
        node_library=None,
    )
    lease_manager.acquire_for_todo_preview(
        graph_view=graph_view,  # type: ignore[arg-type]
        todo_preview_host=todo_preview_host,
        graph_controller=graph_controller,
        preview_edit_button=None,
        node_library=None,
    )

    assert lease_manager.owner == SharedGraphViewLeaseManager.OWNER_TODO_PREVIEW
    assert graph_view.parentWidget() is todo_preview_host


def test_shared_graph_view_lease_acquire_raises_when_host_mismatch() -> None:
    _ensure_qt_app()
    lease_manager = SharedGraphViewLeaseManager()

    graph_view = _DummyGraphView()
    graph_controller = _DummyGraphController(EditSessionCapabilities.full_editing())

    todo_preview_host_1 = GraphCanvasHost()
    todo_preview_host_2 = GraphCanvasHost()

    lease_manager.acquire_for_todo_preview(
        graph_view=graph_view,  # type: ignore[arg-type]
        todo_preview_host=todo_preview_host_1,
        graph_controller=graph_controller,
        preview_edit_button=None,
        node_library=None,
    )

    with pytest.raises(RuntimeError):
        lease_manager.acquire_for_todo_preview(
            graph_view=graph_view,  # type: ignore[arg-type]
            todo_preview_host=todo_preview_host_2,
            graph_controller=graph_controller,
            preview_edit_button=None,
            node_library=None,
        )


def test_shared_graph_view_lease_release_raises_when_host_mismatch() -> None:
    _ensure_qt_app()
    lease_manager = SharedGraphViewLeaseManager()

    graph_view = _DummyGraphView()
    graph_controller = _DummyGraphController(EditSessionCapabilities.full_editing())

    graph_editor_host_1 = GraphCanvasHost()
    graph_editor_host_2 = GraphCanvasHost()

    lease_manager.release_to_graph_editor(
        graph_view=graph_view,  # type: ignore[arg-type]
        graph_editor_host=graph_editor_host_1,
        graph_controller=graph_controller,
        graph_editor_todo_button=None,
        todo_preview_edit_button=None,
    )

    with pytest.raises(RuntimeError):
        lease_manager.release_to_graph_editor(
            graph_view=graph_view,  # type: ignore[arg-type]
            graph_editor_host=graph_editor_host_2,
            graph_controller=graph_controller,
            graph_editor_todo_button=None,
            todo_preview_edit_button=None,
        )


