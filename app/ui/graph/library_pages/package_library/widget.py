from __future__ import annotations

from typing import Dict, Optional, Tuple

from PyQt6 import QtCore, QtWidgets

from engine.resources.package_index_manager import PackageIndexManager
from engine.resources.resource_manager import ResourceManager, ResourceType

from app.runtime.services.resource_preview_scan_service import ResourcePreviewScanService
from app.ui.graph.library_mixins import ConfirmDialogMixin, SearchFilterMixin
from app.ui.graph.library_pages.library_scaffold import (
    DualPaneLibraryScaffold,
    LibraryChangeEvent,
    LibraryPageMixin,
    LibrarySelection,
)
from app.ui.graph.library_pages.package_library.actions_mixin import (
    PackageLibraryActionsMixin,
)
from app.ui.graph.library_pages.package_library.detail_tree_mixin import (
    PackageLibraryDetailTreeMixin,
)
from app.ui.graph.library_pages.package_library.lazy_tree_mixin import (
    PackageLibraryLazyTreeMixin,
)
from app.ui.graph.library_pages.package_library.package_list_mixin import (
    PackageLibraryPackageListMixin,
)
from app.ui.graph.library_pages.package_library.preview_mixin import (
    PackageLibraryPreviewMixin,
)
from app.ui.graph.library_pages.package_library.resource_text_mixin import (
    PackageLibraryResourceTextMixin,
)
from app.ui.graph.library_pages.package_library.ui_mixin import PackageLibraryUiMixin


class PackageLibraryWidget(
    DualPaneLibraryScaffold,
    SearchFilterMixin,
    ConfirmDialogMixin,
    LibraryPageMixin,
    PackageLibraryUiMixin,
    PackageLibraryPackageListMixin,
    PackageLibraryPreviewMixin,
    PackageLibraryLazyTreeMixin,
    PackageLibraryDetailTreeMixin,
    PackageLibraryResourceTextMixin,
    PackageLibraryActionsMixin,
):
    """项目存档页面：列出项目存档、查看包含内容、重命名与删除。

    - 左侧：项目存档列表
    - 右侧：内容详情（元件/节点图/战斗预设/管理配置/关卡实体）
    - 顶部：操作区（重命名、删除、刷新）
    """

    # 当用户在右侧详情树中点击某个基础资源条目时发射：
    # kind: "template" | "instance" | "level_entity" | "graph" | "combat_*"
    # resource_id: 资源 ID 或实体摆放 ID（instance_id；关卡实体情况下同为 instance_id）
    resource_activated = QtCore.pyqtSignal(str, str)

    # 当用户在右侧详情树中双击可跳转的资源条目时发射：
    # entity_type: "template" | "instance" | "level_entity"
    # entity_id:   资源 ID 或实体摆放 ID（instance_id）
    # package_id:  当前存档 ID（仅在具体存档视图下有效）
    jump_to_entity_requested = QtCore.pyqtSignal(str, str, str)

    # 当用户在右侧详情树中双击节点图条目时发射：
    # graph_id:   节点图 ID
    # graph_data: 反序列化后的图数据字典
    graph_double_clicked = QtCore.pyqtSignal(str, dict)

    # 当用户在右侧详情树中双击管理配置分类或具体条目时发射：
    # section_key: 管理页面的 section 标识（例如 "equipment_data" / "save_points" / "signals"）
    # item_id:     管理记录 ID；单配置类管理项下为空字符串
    # package_id:  当前存档 ID 或特殊视图 ID（"global_view"）
    management_item_requested = QtCore.pyqtSignal(str, str, str)

    # 当用户在右侧详情树中点击管理配置条目时发射（用于在当前视图右侧展示管理属性摘要）：
    # resource_key: PackageIndex.resources.management 中的键（如 "timer" / "save_points" / "signals"）
    # resource_id : 聚合资源 ID；为空字符串时表示仅选中了分类节点
    management_resource_activated = QtCore.pyqtSignal(str, str)

    # 存档结构发生变化（新增/重命名/删除）时发射，用于上层刷新存档下拉框等视图。
    packages_changed = QtCore.pyqtSignal()

    # 当用户在左侧存档列表中“显式请求切换为当前存档”时发射（用于同步主窗口当前存档上下文）。
    package_load_requested = QtCore.pyqtSignal(str)

    # 提供与其它库页一致的变更事件入口；当前仅在重命名/删除存档时使用。
    data_changed = QtCore.pyqtSignal(LibraryChangeEvent)

    COMBAT_RESOURCE_TYPES: dict[str, ResourceType] = {
        "player_templates": ResourceType.PLAYER_TEMPLATE,
        "player_classes": ResourceType.PLAYER_CLASS,
        "unit_statuses": ResourceType.UNIT_STATUS,
        "skills": ResourceType.SKILL,
        "projectiles": ResourceType.PROJECTILE,
        "items": ResourceType.ITEM,
    }
    # 战斗预设子分类在项目存档页中的中文显示名称，保持与战斗预设页面的术语一致。
    COMBAT_CATEGORY_TITLES: dict[str, str] = {
        "player_templates": "玩家模板",
        "player_classes": "职业",
        "unit_statuses": "单位状态",
        "skills": "技能",
        "projectiles": "本地投射物",
        "items": "道具",
    }

    # QTreeWidgetItem 自定义 role：用于在“轻量预览”下按需构建树子项
    _ROLE_LAZY_PAYLOAD = int(QtCore.Qt.ItemDataRole.UserRole) + 10
    _ROLE_TREE_ACTION = int(QtCore.Qt.ItemDataRole.UserRole) + 11
    _LAZY_KIND_RESOURCE_SECTION = "resource_section"
    _LAZY_KIND_COMBAT_CATEGORY = "combat_category"
    _LAZY_KIND_MANAGEMENT_CATEGORY = "management_category"
    _ACTION_LOAD_MORE = "load_more"

    # 预览体验：默认展示每个分类前 N 条，避免一次性创建过多 TreeWidgetItem 导致卡顿。
    _PREVIEW_CHILD_LIMIT = 30
    # 用户点击“加载更多”时每次追加的条数
    _LOAD_MORE_CHUNK_SIZE = 200

    # 存档库（PACKAGES）页中，“管理配置”分类显示名称的局部覆写。
    # 说明：大部分分类标题来自 `app.ui.management.section_registry.MANAGEMENT_RESOURCE_TITLES`；
    # 如需在本页面内进一步细化/消歧，可在此追加覆写。
    _MANAGEMENT_CATEGORY_LABEL_OVERRIDES: dict[str, str] = {}

    def __init__(
        self,
        resource_manager: ResourceManager,
        package_index_manager: PackageIndexManager,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(
            parent,
            title="项目存档",
            description="浏览并管理全部项目存档、共享资源视图与其包含的资源。",
        )
        self.rm = resource_manager
        self.pim = package_index_manager

        self._current_package_id: str = ""
        # 预览（磁盘扫描）服务：不依赖 ResourceManager 当前作用域，按 root_key+type 缓存扫描结果。
        self._preview_scan_service = ResourcePreviewScanService()

        # 资源显示名缓存（避免右侧树展开时重复 IO）
        self._resource_name_cache: Dict[Tuple[ResourceType, str], str] = {}
        self._graph_display_name_cache: Dict[str, str] = {}
        self._resource_extra_cache: Dict[Tuple[ResourceType, str], Tuple[str, str]] = {}

        # 扩展工具栏容器（供私有扩展注入按钮/状态控件）
        self._extension_toolbar_buttons: Dict[str, QtWidgets.QAbstractButton] = {}
        self._extension_toolbar_widgets: Dict[str, QtWidgets.QWidget] = {}
        self._extension_toolbar_layout: QtWidgets.QHBoxLayout | None = None
        self._extension_toolbar_widget_host: QtWidgets.QWidget | None = None

        self._setup_ui()
        self.refresh()

    # === LibraryPage 协议实现 ===
    def set_context(self, view: object) -> None:
        """项目存档页与具体 PackageView 无直接绑定关系，此处忽略上下文参数，仅重新加载列表。"""
        _ = view
        self.reload()

    def reload(self) -> None:
        """重新加载项目存档列表并尽量保持当前选中状态。"""
        self.refresh()

    def get_selection(self) -> Optional[LibrarySelection]:
        """返回当前选中的项目存档或特殊视图（若存在）。"""
        items = self.package_list.selectedItems()
        if not items:
            return None
        package_id = items[0].data(QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(package_id, str) or not package_id:
            return None
        return LibrarySelection(kind="package", id=package_id, context=None)

    def set_selection(self, selection: Optional[LibrarySelection]) -> None:
        """根据 LibrarySelection 恢复项目存档列表的当前选中状态。"""
        if selection is None:
            self.package_list.setCurrentItem(None)
            return
        if selection.kind != "package" or not selection.id:
            return
        target_id = selection.id
        for i in range(self.package_list.count()):
            item = self.package_list.item(i)
            if item is None:
                continue
            value = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if isinstance(value, str) and value == target_id:
                self.package_list.setCurrentItem(item)
                break


__all__ = [
    "PackageLibraryWidget",
]

