from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, List

if __package__:
    from ._bootstrap import ensure_workspace_root_on_sys_path, get_workspace_root
else:
    from _bootstrap import ensure_workspace_root_on_sys_path, get_workspace_root

def _load_ocr_engine() -> None:
    """在导入 PyQt6 之前预热 OCR 引擎，避免 DLL 冲突。"""
    from rapidocr_onnxruntime import RapidOCR

    ocr_engine = RapidOCR()
    # 仅为触发 DLL 初始化与模型加载，不在后续逻辑中复用该实例
    del ocr_engine


def _build_package_view_candidates(
    workspace_root: Path,
) -> tuple["ResourceManager", "PackageIndexManager", List["PackageView"]]:
    """构造资源管理器与若干可用的 PackageView。"""
    from engine.resources.resource_manager import ResourceManager
    from engine.resources.package_index_manager import PackageIndexManager
    from engine.resources.package_index import PackageIndex
    from engine.resources.package_view import PackageView

    resource_manager = ResourceManager(workspace_root)
    package_index_manager = PackageIndexManager(workspace_root, resource_manager)

    packages: List[PackageView] = []
    for info in package_index_manager.list_packages():
        package_id_value = info.get("package_id")
        if not isinstance(package_id_value, str) or not package_id_value:
            continue
        package_id = package_id_value
        index: Optional[PackageIndex] = package_index_manager.load_package_index(package_id)
        if index is None:
            continue
        packages.append(PackageView(index, resource_manager))

    return resource_manager, package_index_manager, packages


def _run_template_library_smoke(
    resource_manager: "ResourceManager",
    package_views: List["PackageView"],
) -> None:
    """对元件库页面做一次基础构造与刷新冒烟测试。"""
    from engine.resources.global_resource_view import GlobalResourceView
    from app.ui.graph.library_pages.template_library_widget import TemplateLibraryWidget

    if package_views:
        package_like = package_views[0]
    else:
        package_like = GlobalResourceView(resource_manager)

    widget = TemplateLibraryWidget()
    widget.set_package(package_like)
    widget.refresh_templates()

    category_items = getattr(widget, "_category_items", {})
    for item in category_items.values():
        widget._on_category_clicked(item, 0)

    widget._filter_templates("")


def _run_entity_placement_smoke(
    resource_manager: "ResourceManager",
    package_views: List["PackageView"],
) -> None:
    """对实体摆放页面做一次基础构造与刷新冒烟测试。"""
    from engine.resources.global_resource_view import GlobalResourceView
    from app.ui.graph.library_pages.entity_placement_widget import EntityPlacementWidget

    if package_views:
        package_like = package_views[0]
    else:
        package_like = GlobalResourceView(resource_manager)

    widget = EntityPlacementWidget()
    widget.set_package(package_like)
    widget.refresh_instances()

    category_tree = widget.category_tree
    for index in range(category_tree.topLevelItemCount()):
        group_item = category_tree.topLevelItem(index)
        if group_item is None:
            continue
        for child_index in range(group_item.childCount()):
            child = group_item.child(child_index)
            if child is None:
                continue
            widget._on_category_clicked(child, 0)

    widget._on_search_text_changed("")


def _run_graph_library_smoke(
    resource_manager: "ResourceManager",
    package_index_manager: "PackageIndexManager",
) -> None:
    """对节点图库页面做一次基础构造与刷新冒烟测试。"""
    from engine.resources.global_resource_view import GlobalResourceView
    from app.ui.graph.library_pages.graph_library_widget import GraphLibraryWidget

    widget = GraphLibraryWidget(resource_manager, package_index_manager)

    widget.refresh()

    type_combo = widget.type_combo
    for index in range(type_combo.count()):
        widget._on_type_changed(index)

    widget._filter_graphs("")

    global_view = GlobalResourceView(resource_manager)
    widget.set_package(global_view)


def _run_package_library_smoke(
    resource_manager: "ResourceManager",
    package_index_manager: "PackageIndexManager",
) -> None:
    """对存档库页面做一次基础构造与刷新冒烟测试。"""
    from app.ui.graph.library_pages.package_library_widget import PackageLibraryWidget

    widget = PackageLibraryWidget(resource_manager, package_index_manager)
    widget.refresh()

    package_list = widget.package_list
    for row in range(package_list.count()):
        package_list.setCurrentRow(row)
        widget._on_package_selected()


def main() -> None:
    """UI 资源库相关页面的冒烟测试入口。

    默认行为：
    - 预热 RapidOCR（在导入 PyQt6 之前），与正式启动路径保持一致；
    - 构造各库页面并执行基础刷新与筛选。

    特殊参数：
    - 传入 `--skip-ocr` 时跳过 RapidOCR 预热，便于在某些缺少 onnxruntime DLL 的环境中运行纯 UI 冒烟测试。
    """
    skip_ocr = "--skip-ocr" in sys.argv
    if skip_ocr:
        sys.argv = [arg for arg in sys.argv if arg != "--skip-ocr"]

    workspace_root = get_workspace_root()
    ensure_workspace_root_on_sys_path()

    from engine.utils.logging.console_sanitizer import install_ascii_safe_print
    from engine.configs.settings import settings
    from PyQt6 import QtWidgets

    install_ascii_safe_print()

    if not skip_ocr:
        _load_ocr_engine()

    settings.set_config_path(workspace_root)
    settings.load()

    qt_app = QtWidgets.QApplication(sys.argv)

    resource_manager, package_index_manager, package_views = _build_package_view_candidates(
        workspace_root
    )

    print("Running TemplateLibraryWidget smoke test...")
    _run_template_library_smoke(resource_manager, package_views)
    print("TemplateLibraryWidget smoke test done.")

    print("Running EntityPlacementWidget smoke test...")
    _run_entity_placement_smoke(resource_manager, package_views)
    print("EntityPlacementWidget smoke test done.")

    print("Running GraphLibraryWidget smoke test...")
    _run_graph_library_smoke(resource_manager, package_index_manager)
    print("GraphLibraryWidget smoke test done.")

    print("Running PackageLibraryWidget smoke test...")
    _run_package_library_smoke(resource_manager, package_index_manager)
    print("PackageLibraryWidget smoke test done.")

    qt_app.quit()


if __name__ == "__main__":
    main()


