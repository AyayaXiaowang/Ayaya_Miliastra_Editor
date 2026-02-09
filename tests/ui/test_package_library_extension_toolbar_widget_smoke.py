from __future__ import annotations

from pathlib import Path


def test_package_library_extension_toolbar_widget_smoke(tmp_path: Path) -> None:
    """冒烟：PackageLibraryWidget 扩展工具栏应支持插件注入自定义 widget（幂等）。"""
    from PyQt6 import QtWidgets

    from engine.resources.package_index_manager import PackageIndexManager
    from engine.resources.resource_manager import ResourceManager
    from app.ui.graph.library_pages.package_library_widget import PackageLibraryWidget

    _app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    workspace_root = tmp_path / "workspace"
    (workspace_root / "assets" / "资源库").mkdir(parents=True, exist_ok=True)

    resource_manager = ResourceManager(workspace_root)
    package_index_manager = PackageIndexManager(workspace_root, resource_manager)

    widget = PackageLibraryWidget(resource_manager, package_index_manager)

    def _create_progress(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
        bar = QtWidgets.QProgressBar(parent)
        bar.setRange(0, 10)
        bar.setValue(3)
        return bar

    progress1 = widget.ensure_extension_toolbar_widget("test.progress", _create_progress, visible=True)
    assert isinstance(progress1, QtWidgets.QProgressBar)
    assert progress1.value() == 3

    # 幂等：同 key 复用同一实例
    progress2 = widget.ensure_extension_toolbar_widget("test.progress", _create_progress, visible=False)
    assert progress2 is progress1
    assert not progress2.isVisible()


