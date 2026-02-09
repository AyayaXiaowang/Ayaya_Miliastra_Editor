from __future__ import annotations

from PyQt6 import QtCore, QtWidgets, sip

from app.ui.todo.todo_tree_graph_expander import _GraphExpandResultApplier


_app = QtWidgets.QApplication.instance()
if _app is None:
    _app = QtWidgets.QApplication([])


class _DummyPackage:
    def __init__(self, package_id: str) -> None:
        self.package_id = str(package_id or "")


class _DummyTreeManager(QtCore.QObject):
    MARKER_ROLE = int(QtCore.Qt.ItemDataRole.UserRole) + 42

    def __init__(
        self,
        tree: QtWidgets.QTreeWidget,
        *,
        graph_root_id: str,
        root_item: QtWidgets.QTreeWidgetItem,
        placeholder_item: QtWidgets.QTreeWidgetItem,
        package_id: str,
    ) -> None:
        super().__init__()
        self.tree = tree
        self._item_map = {str(graph_root_id or ""): root_item}
        self._graph_expand_placeholders = {str(graph_root_id or ""): placeholder_item}

        package = _DummyPackage(package_id)

        def _dependency_getter() -> tuple[object, object]:
            return (package, object())

        self._graph_expand_dependency_getter = _dependency_getter


def test_graph_expand_progress_does_not_touch_deleted_placeholder_item() -> None:
    tree = QtWidgets.QTreeWidget()

    graph_root_id = "graph_root"
    root_item = QtWidgets.QTreeWidgetItem(["root"])
    tree.addTopLevelItem(root_item)
    placeholder_item = QtWidgets.QTreeWidgetItem(["正在生成节点图步骤… 0%"])
    root_item.addChild(placeholder_item)

    manager = _DummyTreeManager(
        tree,
        graph_root_id=graph_root_id,
        root_item=root_item,
        placeholder_item=placeholder_item,
        package_id="测试项目",
    )

    applier = _GraphExpandResultApplier(
        tree_manager=manager,
        request_id=1,
        graph_root_id=graph_root_id,
        expected_package_id="测试项目",
        context=None,
    )

    # 模拟“整树刷新重建”：Qt 会释放旧的 C++ item，但 Python 引用仍可能保留在缓存 dict 中。
    tree.clear()
    QtWidgets.QApplication.processEvents()

    assert sip.isdeleted(placeholder_item)

    # 不应抛出 wrapped C/C++ object has been deleted
    applier.on_progress(1, graph_root_id, "测试项目", 1, 10, "stage")

    # 进度更新前应先清理无效缓存，避免后续继续触发崩溃
    assert graph_root_id not in manager._graph_expand_placeholders


