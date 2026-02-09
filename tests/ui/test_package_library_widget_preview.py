from __future__ import annotations

import re

from PyQt6 import QtWidgets

from tests._helpers.project_paths import get_repo_root
from engine.resources.resource_context import build_resource_index_context
from app.ui.graph.library_pages.package_library_widget import PackageLibraryWidget


_app = QtWidgets.QApplication.instance()
if _app is None:
    _app = QtWidgets.QApplication([])


def _find_top_level_item_by_prefix(
    tree: QtWidgets.QTreeWidget, prefix: str
) -> QtWidgets.QTreeWidgetItem | None:
    for i in range(tree.topLevelItemCount()):
        item = tree.topLevelItem(i)
        if item is None:
            continue
        if item.text(0).startswith(prefix):
            return item
    return None


def _extract_count_from_title(text: str) -> int:
    match = re.search(r"\((\d+)\)", text)
    if not match:
        return -1
    return int(match.group(1))


def test_package_library_widget_preview_tree_default_collapsed() -> None:
    repo_root = get_repo_root()
    resource_manager, package_index_manager = build_resource_index_context(
        repo_root,
        init_settings_first=False,
    )
    widget = PackageLibraryWidget(resource_manager, package_index_manager)

    widget._current_package_id = "演示项目"
    widget._render_package_detail("演示项目")

    graph_root = _find_top_level_item_by_prefix(widget.detail_tree, "节点图")
    assert graph_root is not None

    # 默认折叠：未展开前不应生成子项（避免“默认展开”造成信息噪音与卡顿）。
    assert graph_root.childCount() == 0


def test_package_library_widget_preview_graphs_visible_even_when_resource_manager_is_scoped_elsewhere() -> None:
    """回归：预览任意存档都应能看到节点图列表，不应受当前 ResourceManager 作用域影响。"""
    repo_root = get_repo_root()
    resource_manager, package_index_manager = build_resource_index_context(
        repo_root,
        init_settings_first=False,
    )

    # 模拟当前作用域不等于预览目标存档（旧实现会因此预览为空）。
    resource_manager.set_active_package_id("测试项目")

    widget = PackageLibraryWidget(resource_manager, package_index_manager)

    widget._current_package_id = "演示项目"
    widget._render_package_detail("演示项目")

    graph_root = _find_top_level_item_by_prefix(widget.detail_tree, "节点图")
    assert graph_root is not None
    count = _extract_count_from_title(graph_root.text(0))
    assert count >= 1

    # 展开后应能懒加载出至少 1 条节点图条目。
    widget._on_detail_tree_item_expanded(graph_root)
    assert graph_root.childCount() >= 1

    assert any(
        (
            (graph_root.child(i) is not None)
            and (graph_root.child(i).text(0) == "节点图")
            and bool(graph_root.child(i).toolTip(1))
        )
        for i in range(graph_root.childCount())
    )


def test_package_library_widget_switch_to_current_emits_package_load_requested() -> None:
    repo_root = get_repo_root()
    resource_manager, package_index_manager = build_resource_index_context(
        repo_root,
        init_settings_first=False,
    )
    widget = PackageLibraryWidget(resource_manager, package_index_manager)

    captured: list[str] = []
    widget.package_load_requested.connect(lambda package_id: captured.append(package_id))

    widget._current_package_id = "演示项目"
    widget.open_btn.click()

    assert captured == ["演示项目"]


