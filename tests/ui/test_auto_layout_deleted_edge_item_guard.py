from __future__ import annotations

from dataclasses import dataclass

from PyQt6 import QtWidgets, sip

from app.ui.graph.graph_view.auto_layout.auto_layout_controller import AutoLayoutController


def _ensure_qt_app() -> QtWidgets.QApplication:
    app_instance = QtWidgets.QApplication.instance()
    if app_instance is None:
        app_instance = QtWidgets.QApplication([])
    return app_instance


@dataclass
class _DummyModel:
    nodes: dict
    edges: dict
    metadata: dict


class _DummyScene:
    def __init__(self, deleted_edge_item: object) -> None:
        self.model = _DummyModel(nodes={}, edges={}, metadata={})
        self.node_library = None
        self.edge_items = {"edge_1": deleted_edge_item}
        self.node_items = {}
        self._edges_by_node_id: dict = {"node_1": {deleted_edge_item}}
        self.removed_items: list[object] = []

    def removeItem(self, item: object) -> None:  # noqa: N802 (Qt API naming)
        # 若 AutoLayoutController 仍对已删除对象调用 removeItem，本测试应失败（复现崩溃风险）。
        assert not sip.isdeleted(item)
        self.removed_items.append(item)

    def add_edge_item(self, _edge: object) -> None:
        # 本测试不关心新增边
        return

    def add_node_item(self, _node: object) -> None:
        # 本测试不关心新增节点
        return

    def update(self) -> None:
        return


class _DummyGraphView:
    def __init__(self, scene: _DummyScene) -> None:
        self._scene = scene

    def scene(self) -> _DummyScene:  # noqa: D401 (Qt naming)
        return self._scene


def test_auto_layout_controller_skips_deleted_edge_items_when_clearing_scene_edges(monkeypatch) -> None:
    _ensure_qt_app()

    # NOTE:
    # 在 Windows + pytest 环境下对真实 QGraphicsItem 调用 `sip.delete(...)` 容易触发进程级崩溃
    # （例如 STATUS_STACK_BUFFER_OVERRUN）。这里用 monkeypatch 模拟“已删除”状态来覆盖护栏逻辑。
    deleted_edge_item = QtWidgets.QGraphicsLineItem()
    monkeypatch.setattr(sip, "isdeleted", lambda obj: obj is deleted_edge_item)
    assert sip.isdeleted(deleted_edge_item)

    scene = _DummyScene(deleted_edge_item)
    view = _DummyGraphView(scene)

    AutoLayoutController.run(view)  # 不应抛异常

    assert scene.edge_items == {}, "edge_items 应被清空（包含已删除对象）"
    assert scene._edges_by_node_id == {}, "邻接索引应被清空，避免悬空引用"


