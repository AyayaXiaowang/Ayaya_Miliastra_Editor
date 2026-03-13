"""实体摆放组件 - 文件列表形式"""

from __future__ import annotations

from typing import Optional, Union

from PyQt6 import QtCore, QtGui, QtWidgets

from app.ui.graph.library_mixins import ConfirmDialogMixin, SearchFilterMixin, ToolbarMixin
from app.ui.graph.library_pages.category_tree_mixin import EntityCategoryTreeMixin
from app.ui.graph.library_pages.entity_placement.constants import CATEGORY_ALL
from app.ui.graph.library_pages.entity_placement.instance_list_mixin import (
    EntityPlacementInstanceListMixin,
)
from app.ui.graph.library_pages.entity_placement.instance_ops_mixin import (
    EntityPlacementInstanceOpsMixin,
)
from app.ui.graph.library_pages.entity_placement.level_entity_mixin import (
    EntityPlacementLevelEntityMixin,
)
from app.ui.graph.library_pages.entity_placement.merge_decorations_mixin import (
    EntityPlacementMergeDecorationsMixin,
)
from app.ui.graph.library_pages.entity_placement.protocol_mixin import (
    EntityPlacementProtocolMixin,
)
from app.ui.graph.library_pages.entity_placement.ui_mixin import EntityPlacementUiMixin
from app.ui.graph.library_pages.library_scaffold import LibraryChangeEvent, LibraryPageMixin
from app.ui.graph.library_pages.standard_dual_pane_list_page import StandardDualPaneListPage
from engine.resources.global_resource_view import GlobalResourceView
from engine.resources.package_view import PackageView


class EntityPlacementWidget(
    StandardDualPaneListPage,
    EntityPlacementUiMixin,
    EntityPlacementProtocolMixin,
    EntityPlacementLevelEntityMixin,
    EntityPlacementInstanceListMixin,
    EntityPlacementInstanceOpsMixin,
    EntityPlacementMergeDecorationsMixin,
    LibraryPageMixin,
    SearchFilterMixin,
    ToolbarMixin,
    EntityCategoryTreeMixin,
    ConfirmDialogMixin,
):
    """实体摆放界面 - 文件列表形式"""

    selection_changed = QtCore.pyqtSignal(object)
    data_changed = QtCore.pyqtSignal(LibraryChangeEvent)

    def __init__(self, parent=None):
        """初始化实体摆放页面。"""
        super().__init__(
            parent,
            title="实体摆放",
            description="浏览与管理元件实体，支持分类筛选与快速定位。",
        )
        self._standard_shortcuts: list[QtGui.QShortcut] = []
        self.current_package: Optional[Union[PackageView, GlobalResourceView]] = None
        self.current_category: str = CATEGORY_ALL
        self._category_items: dict[str, QtWidgets.QTreeWidgetItem] = {}
        self._setup_ui()
        self.apply_list_widget_style()

