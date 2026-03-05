from __future__ import annotations

"""项目存档页（Packages view）薄门面。

对外保持稳定导入路径：
    from app.ui.graph.library_pages.package_library_widget import PackageLibraryWidget

具体实现位于：
    app.ui.graph.library_pages.package_library.widget
"""

from app.ui.graph.library_pages.package_library.widget import PackageLibraryWidget

__all__ = [
    "PackageLibraryWidget",
]

