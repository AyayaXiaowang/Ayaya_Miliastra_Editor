from __future__ import annotations

from typing import Callable, Dict, Iterable, Mapping, Optional, Sequence, Tuple

from PyQt6 import QtCore, QtWidgets

from engine.resources.package_index_manager import PackageIndexManager
from engine.resources.package_index import PackageIndex
from engine.resources.package_view import PackageView
from engine.resources.resource_manager import ResourceManager
from engine.resources.resource_manager import ResourceType
from engine.resources.unclassified_resource_view import UnclassifiedResourceView
from ui.foundation import input_dialogs
from ui.foundation.theme_manager import Sizes
from ui.foundation.toolbar_utils import apply_standard_toolbar
from ui.graph.library_mixins import SearchFilterMixin, ConfirmDialogMixin
from ui.graph.library_pages.library_scaffold import LibraryChangeEvent, LibraryPageMixin, LibrarySelection
from ui.graph.library_pages.management_tree_helpers import (
    build_management_category_items_for_tree,
)
from ui.management.section_registry import (
    MANAGEMENT_RESOURCE_BINDINGS,
    MANAGEMENT_RESOURCE_ORDER,
    MANAGEMENT_RESOURCE_TITLES,
)
from ui.panels.panel_scaffold import PanelScaffold, SectionCard


class PackageLibraryWidget(PanelScaffold, SearchFilterMixin, ConfirmDialogMixin, LibraryPageMixin):
    """存档页面：列出存档、查看包含内容、重命名与删除。
    
    - 左侧：存档列表
    - 右侧：内容详情（元件/节点图/战斗预设/管理配置/关卡实体）
    - 顶部：操作区（重命名、删除、刷新）
    """

    # 当用户在右侧详情树中点击某个基础资源条目时发射：
    # kind: "template" | "instance" | "level_entity" | "graph" | "combat_*"
    # resource_id: 资源 ID 或实例 ID（关卡实体情况下为实例 ID）
    resource_activated = QtCore.pyqtSignal(str, str)

    # 当用户在右侧详情树中双击可跳转的资源条目时发射：
    # entity_type: "template" | "instance" | "level_entity"
    # entity_id:   资源 ID 或实例 ID
    # package_id:  当前存档 ID（仅在具体存档视图下有效）
    jump_to_entity_requested = QtCore.pyqtSignal(str, str, str)

    # 当用户在右侧详情树中双击节点图条目时发射：
    # graph_id:   节点图 ID
    # graph_data: 反序列化后的图数据字典
    graph_double_clicked = QtCore.pyqtSignal(str, dict)

    # 当用户在右侧详情树中双击管理配置分类或具体条目时发射：
    # section_key: 管理页面的 section 标识（例如 "equipment_data" / "save_points" / "signals"）
    # item_id:     管理记录 ID；单配置类管理项下为空字符串
    # package_id:  当前存档 ID 或特殊视图 ID（"global_view" / "unclassified_view"）
    management_item_requested = QtCore.pyqtSignal(str, str, str)

    # 当用户在右侧详情树中点击管理配置条目时发射（用于在当前视图右侧展示管理属性摘要）：
    # resource_key: PackageIndex.resources.management 中的键（如 "timer" / "save_points" / "signals"）
    # resource_id : 聚合资源 ID；为空字符串时表示仅选中了分类节点
    management_resource_activated = QtCore.pyqtSignal(str, str)

    # 存档结构发生变化（新增/重命名/删除）时发射，用于上层刷新存档下拉框等视图。
    packages_changed = QtCore.pyqtSignal()

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
    # 战斗预设子分类在功能包库中的中文显示名称，保持与战斗预设页面的术语一致。
    COMBAT_CATEGORY_TITLES: dict[str, str] = {
        "player_templates": "玩家模板",
        "player_classes": "职业",
        "unit_statuses": "单位状态",
        "skills": "技能",
        "projectiles": "本地投射物",
        "items": "道具",
    }

    def __init__(self, resource_manager: ResourceManager, package_index_manager: PackageIndexManager, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(
            parent,
            title="存档库",
            description="浏览并管理全部存档、特殊视图与其包含的资源。",
        )
        self.rm = resource_manager
        self.pim = package_index_manager

        self._current_package_id: str = ""
        self._resource_name_cache: Dict[Tuple[ResourceType, str], str] = {}
        self._graph_display_name_cache: Dict[str, str] = {}
        self._resource_cache: Dict[ResourceType, list[str]] = {}
        self._resource_extra_cache: Dict[Tuple[ResourceType, str], Tuple[str, str]] = {}
        self._cached_unclassified_view: Optional[UnclassifiedResourceView] = None

        self._setup_ui()
        self.refresh()

    # === LibraryPage 协议实现 ===

    def set_context(self, view: object) -> None:
        """存档库与具体 PackageView 无直接绑定关系，此处忽略上下文参数，仅重新加载列表。

        设计上存档库始终展示全部存档以及两个聚合视图（全部/未分类），
        因此 set_context 仅作为统一协议占位，方便主窗口按统一入口管理所有库页。
        """
        _ = view
        self.reload()

    def reload(self) -> None:
        """重新加载存档列表并尽量保持当前选中状态。"""
        self.refresh()

    def get_selection(self) -> Optional[LibrarySelection]:
        """返回当前选中的存档或特殊视图（若存在）。"""
        items = self.package_list.selectedItems()
        if not items:
            return None
        package_id = items[0].data(QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(package_id, str) or not package_id:
            return None
        return LibrarySelection(kind="package", id=package_id, context=None)

    def set_selection(self, selection: Optional[LibrarySelection]) -> None:
        """根据 LibrarySelection 恢复存档列表的当前选中状态。"""
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

    # === UI ===
    def _setup_ui(self) -> None:
        # 顶部：标题右侧放搜索框，快速过滤存档列表
        self.search_edit = QtWidgets.QLineEdit(self)
        self.search_edit.setPlaceholderText("搜索存档...")
        self.search_edit.setMinimumHeight(Sizes.INPUT_HEIGHT)
        self.add_action_widget(self.search_edit)
        self.connect_search(self.search_edit, self._filter_packages, placeholder="搜索存档...")

        # 标题下方：存档操作按钮行（重命名/删除/刷新）
        toolbar_widget = QtWidgets.QWidget()
        toolbar_layout = QtWidgets.QHBoxLayout(toolbar_widget)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(Sizes.SPACING_MEDIUM)
        apply_standard_toolbar(toolbar_layout)
        self.rename_btn = QtWidgets.QPushButton("重命名")
        self.delete_btn = QtWidgets.QPushButton("删除")
        self.refresh_btn = QtWidgets.QPushButton("刷新")

        self.rename_btn.clicked.connect(self._on_rename)
        self.delete_btn.clicked.connect(self._on_delete)
        self.refresh_btn.clicked.connect(self.refresh)

        toolbar_layout.addWidget(self.rename_btn)
        toolbar_layout.addWidget(self.delete_btn)
        toolbar_layout.addWidget(self.refresh_btn)
        toolbar_layout.addStretch(1)
        self.set_status_widget(toolbar_widget)

        # 分割器
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)

        # 左侧：存档列表
        left = SectionCard("存档列表", "选择存档或特殊视图")
        self.package_list = QtWidgets.QListWidget()
        self.package_list.setObjectName("leftPanel")
        self.package_list.setFixedWidth(Sizes.LEFT_PANEL_WIDTH)
        self.package_list.itemSelectionChanged.connect(self._on_package_selected)
        self.package_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        left.add_content_widget(self.package_list, stretch=1)

        splitter.addWidget(left)

        # 右侧：包详情（树）
        right = SectionCard("存档内容详情", "查看元件、实体、管理配置等资源")
        self.header_label = QtWidgets.QLabel("")
        header_font = self.header_label.font()
        header_font.setPointSize(Sizes.FONT_LARGE)
        header_font.setBold(True)
        self.header_label.setFont(header_font)
        right.add_content_widget(self.header_label)

        self.detail_tree = QtWidgets.QTreeWidget()
        self.detail_tree.setHeaderLabels(["类别", "标识/名称", "GUID", "挂载节点图"])
        # 调整列宽：类别列略宽一些，保证中文类别标题与计数完整可见
        self.detail_tree.setColumnWidth(0, 220)
        self.detail_tree.setColumnWidth(1, 220)
        self.detail_tree.setColumnWidth(2, 200)
        self.detail_tree.setColumnWidth(3, 260)
        # 单击明细行时，将对应资源类型与 ID 交给主窗口，由主窗口决定如何在右侧属性面板中展示。
        self.detail_tree.itemClicked.connect(self._on_detail_item_activated)
        # 双击明细行时，尝试跳转到对应的编辑页面（元件库 / 实体摆放 / 节点图编辑器）。
        self.detail_tree.itemDoubleClicked.connect(self._on_detail_item_double_clicked)
        right.add_content_widget(self.detail_tree, stretch=1)

        splitter.addWidget(right)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        self.body_layout.addWidget(splitter, 1)

    # === 辅助：为树节点标记可预览的资源类型 ===
    def _set_item_resource_kind(
        self,
        item: QtWidgets.QTreeWidgetItem,
        section_title: str,
        resource_id: str,
        *,
        is_level_entity: bool = False,
    ) -> None:
        """根据所属分组与上下文，为叶子节点写入 (kind, resource_id) 数据。

        kind 取值：
        - "template"     → 元件
        - "instance"     → 实例
        - "level_entity" → 关卡实体
        - "graph"        → 节点图
        其它分组目前不在右侧属性面板中直接展开，保持为浏览用途。
        """
        if not resource_id:
            return
        if is_level_entity:
            kind = "level_entity"
        elif section_title == "元件":
            kind = "template"
        elif section_title == "实例":
            kind = "instance"
        elif section_title == "节点图":
            kind = "graph"
        else:
            return
        item.setData(0, QtCore.Qt.ItemDataRole.UserRole, (kind, resource_id))

    # === 交互 ===
    def _on_detail_item_activated(
        self,
        item: QtWidgets.QTreeWidgetItem,
        column: int,
    ) -> None:
        """当用户在存档内容详情中点击某一行时，发射资源激活信号。

        设计约定：
        - 对真正代表资源条目的行生效（模板/实例/关卡实体/节点图/部分战斗预设类型）；
        - 管理配置条目通过独立信号 `management_resource_activated` 通知主窗口；
        - 根分组行或仅用于展示统计信息的行不发射任何信号。
        """
        value = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        management_value = item.data(0, QtCore.Qt.ItemDataRole.UserRole + 1)
        print(
            "[PACKAGES] detail item activated:",
            f"column={column}, raw_kind={value!r}, management={management_value!r}",
        )

        if isinstance(value, tuple) and len(value) == 2:
            kind, resource_id = value
            if isinstance(kind, str) and isinstance(resource_id, str) and kind and resource_id:
                self.resource_activated.emit(kind, resource_id)
                return

        # 管理配置条目：仅当 UserRole+1 中标记了 (resource_key, resource_id) 时发射单击信号，
        # 用于在当前视图右侧通过 ManagementPropertyPanel 展示摘要与“所属存档”行。
        if isinstance(management_value, tuple) and len(management_value) == 2:
            resource_key, resource_id = management_value
            if (
                isinstance(resource_key, str)
                and isinstance(resource_id, str)
                and resource_key
                and resource_id
            ):
                self.management_resource_activated.emit(resource_key, resource_id)

    def _on_detail_item_double_clicked(
        self,
        item: QtWidgets.QTreeWidgetItem,
        column: int,
    ) -> None:
        """当用户在存档内容详情中双击某一行时，触发跨页面跳转。

        交互约定：
        - 单击：仅在当前主窗口右侧属性/图属性面板中以只读方式预览；
        - 双击：跳转到对应的编辑上下文：
            - 元件 / 实例 / 关卡实体 → 根据当前存档切换到元件库或实体摆放，并选中目标条目；
            - 节点图               → 直接在节点图编辑器中以独立方式打开。
        """
        resource_value = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if isinstance(resource_value, tuple) and len(resource_value) == 2:
            kind, resource_id = resource_value
            if not isinstance(kind, str) or not isinstance(resource_id, str):
                return
            if not kind or not resource_id:
                return

            # 模板 / 实例 / 关卡实体：依赖当前存档上下文，通过导航协调器跳转到对应页面。
            if kind in ("template", "instance", "level_entity"):
                package_id_for_entity = self._current_package_id
                if not package_id_for_entity or self._is_special_id(package_id_for_entity):
                    # “全部存档”“未分类存档”等聚合视图下没有唯一的存档上下文，仅提供只读预览，不执行跳转。
                    return
                self.jump_to_entity_requested.emit(kind, resource_id, package_id_for_entity)
                return

            # 节点图：直接打开对应节点图进行编辑（不依赖具体存档容器）。
            if kind == "graph":
                graph_data = self.rm.load_resource(ResourceType.GRAPH, resource_id)
                if not graph_data:
                    return
                if not isinstance(graph_data, dict):
                    return
                self.graph_double_clicked.emit(resource_id, graph_data)
                return

        # 管理配置：根据 section_key + item_id 请求主窗口跳转到对应管理页面。
        management_value = item.data(0, QtCore.Qt.ItemDataRole.UserRole + 1)
        if not isinstance(management_value, tuple) or len(management_value) != 2:
            return
        section_key, item_id = management_value
        if not isinstance(section_key, str) or not section_key:
            return
        if not isinstance(item_id, str):
            return
        package_id = self._current_package_id
        if not package_id:
            return
        self.management_item_requested.emit(section_key, item_id, package_id)

    def _filter_packages(self, text: str) -> None:
        """根据搜索文本过滤存档列表。"""
        self.filter_list_items(self.package_list, text)
        current_item = self.package_list.currentItem()
        if current_item is not None and current_item.isHidden():
            for i in range(self.package_list.count()):
                item = self.package_list.item(i)
                if item is not None and not item.isHidden():
                    self.package_list.setCurrentItem(item)
                    break

    # === Helpers ===
    def _display_name(self, resource_type: ResourceType, resource_id: str) -> str:
        """获取资源的显示名（优先中文名，回退ID）。"""
        cache_key = (resource_type, resource_id)
        cached = self._resource_name_cache.get(cache_key)
        if cached:
            return cached
        meta = self.rm.get_resource_metadata(resource_type, resource_id)
        if meta and meta.get("name"):
            name = meta["name"]
        else:
            name = resource_id
        self._resource_name_cache[cache_key] = name
        return name

    def _get_resource_extra_info(
        self,
        resource_type: ResourceType,
        resource_id: str,
    ) -> Tuple[str, str]:
        """获取资源的 GUID 与挂载节点图信息（名称汇总）。

        返回:
            (guid_text, graphs_text)
        """
        cache_key = (resource_type, resource_id)
        cached = self._resource_extra_cache.get(cache_key)
        if cached is not None:
            return cached

        guid_text = ""
        graphs_text = ""

        meta = self.rm.get_resource_metadata(resource_type, resource_id)
        if meta:
            raw_guid = meta.get("guid")
            if raw_guid:
                guid_text = str(raw_guid)

            raw_graph_ids = meta.get("graph_ids") or []
            if isinstance(raw_graph_ids, list) and raw_graph_ids:
                graph_names: list[str] = []
                for graph_id in raw_graph_ids:
                    if not isinstance(graph_id, str):
                        continue
                    graph_name = self._resolve_graph_display_name(graph_id)
                    if graph_name == graph_id:
                        graph_names.append(graph_name)
                    else:
                        graph_names.append(f"{graph_name} ({graph_id})")
                graphs_text = ", ".join(graph_names)

        result = (guid_text, graphs_text)
        self._resource_extra_cache[cache_key] = result
        return result

    # === Data ===
    def refresh(self) -> None:
        """刷新存档列表"""
        self._clear_display_name_cache()
        self.package_list.clear()
        # 先插入两类特殊视图
        item_global = QtWidgets.QListWidgetItem("全部存档")
        item_global.setData(QtCore.Qt.ItemDataRole.UserRole, "global_view")
        item_global.setToolTip("浏览全部资源（不可重命名/删除）")
        self.package_list.addItem(item_global)

        item_uncat = QtWidgets.QListWidgetItem("未分类存档")
        item_uncat.setData(QtCore.Qt.ItemDataRole.UserRole, "unclassified_view")
        item_uncat.setToolTip("浏览未被任何存档纳入的资源（不可重命名/删除）")
        self.package_list.addItem(item_uncat)

        # 再加载普通存档
        packages = self.pim.list_packages()
        for pkg in packages:
            item = QtWidgets.QListWidgetItem(pkg["name"])  # 文本为名称
            item.setData(QtCore.Qt.ItemDataRole.UserRole, pkg["package_id"])  # 存放ID
            description = pkg.get("description", "")
            if description:
                item.setToolTip(description)
            self.package_list.addItem(item)

        # 保持选择
        if self._current_package_id:
            for i in range(self.package_list.count()):
                it = self.package_list.item(i)
                if it is not None:
                    if it.data(QtCore.Qt.ItemDataRole.UserRole) == self._current_package_id:
                        self.package_list.setCurrentRow(i)
                        break

        if self.package_list.count() > 0 and not self._current_package_id:
            self.package_list.setCurrentRow(0)

        if self.package_list.count() == 0:
            self._current_package_id = ""
            self._render_empty_detail()

        # 重新应用当前搜索过滤，保持搜索体验一致
        if hasattr(self, "search_edit") and self.search_edit is not None:
            self._filter_packages(self.search_edit.text())

    def _on_package_selected(self) -> None:
        items = self.package_list.selectedItems()
        if not items:
            self._current_package_id = ""
            self._render_empty_detail()
            self._update_action_state()
            return
        pkg_id = items[0].data(QtCore.Qt.ItemDataRole.UserRole)
        self._current_package_id = pkg_id
        self._render_package_detail(pkg_id)
        self._update_action_state()

    def _is_special_id(self, package_id: str) -> bool:
        return package_id in ("global_view", "unclassified_view")

    def _update_action_state(self) -> None:
        is_special = self._is_special_id(self._current_package_id)
        can_edit = bool(self._current_package_id) and not is_special
        self.rename_btn.setEnabled(can_edit)
        self.delete_btn.setEnabled(can_edit)

    def _render_empty_detail(self) -> None:
        self.header_label.setText("未选择存档")
        self.detail_tree.clear()

    def _render_package_detail(self, package_id: str) -> None:
        self.detail_tree.setUpdatesEnabled(False)
        self.detail_tree.clear()

        if package_id == "global_view":
            self._render_global_view()
            self.detail_tree.setUpdatesEnabled(True)
            return

        if package_id == "unclassified_view":
            self._render_unclassified_view()
            self.detail_tree.setUpdatesEnabled(True)
            return

        self._render_package_index(package_id)
        self.detail_tree.setUpdatesEnabled(True)

    def _render_global_view(self) -> None:
        total_count = 0
        total_count += self._add_resource_section(
            "元件",
            self._list_resources_cached(ResourceType.TEMPLATE),
            ResourceType.TEMPLATE,
            assume_sorted=True,
        )
        total_count += self._add_resource_section(
            "实例",
            self._list_resources_cached(ResourceType.INSTANCE),
            ResourceType.INSTANCE,
            assume_sorted=True,
        )
        total_count += self._add_resource_section(
            "节点图",
            self._list_resources_cached(ResourceType.GRAPH),
            ResourceType.GRAPH,
            self._resolve_graph_display_name,
            assume_sorted=True,
        )
        total_count += self._add_nested_resource_section(
            "战斗预设",
            {
                sub_key: (self._list_resources_cached(resource_type), resource_type)
                for sub_key, resource_type in self.COMBAT_RESOURCE_TYPES.items()
            },
            assume_sorted=True,
        )
        total_count += self._add_nested_resource_section(
            "管理配置",
            self._build_management_map_from_resource_manager(),
            assume_sorted=True,
            mark_management_items=True,
        )
        self.detail_tree.expandAll()
        self.header_label.setText(f"全部存档（共 {total_count} 项）")

    def _render_unclassified_view(self) -> None:
        total_count = 0
        unclassified_view = self._get_unclassified_view()
        total_count += self._add_resource_section(
            "元件",
            sorted(unclassified_view.templates.keys()),
            ResourceType.TEMPLATE,
            assume_sorted=True,
        )
        total_count += self._add_resource_section(
            "实例",
            sorted(unclassified_view.instances.keys()),
            ResourceType.INSTANCE,
            assume_sorted=True,
        )
        total_count += self._add_resource_section(
            "节点图",
            sorted(unclassified_view.get_unclassified_graph_ids()),
            ResourceType.GRAPH,
            self._resolve_graph_display_name,
            assume_sorted=True,
        )
        combat_presets = unclassified_view.combat_presets
        combat_category_map = {
            "player_templates": (
                sorted(combat_presets.player_templates.keys()),
                ResourceType.PLAYER_TEMPLATE,
            ),
            "player_classes": (sorted(combat_presets.player_classes.keys()), ResourceType.PLAYER_CLASS),
            "unit_statuses": (sorted(combat_presets.unit_statuses.keys()), ResourceType.UNIT_STATUS),
            "skills": (sorted(combat_presets.skills.keys()), ResourceType.SKILL),
            "projectiles": (sorted(combat_presets.projectiles.keys()), ResourceType.PROJECTILE),
            "items": (sorted(combat_presets.items.keys()), ResourceType.ITEM),
        }
        total_count += self._add_nested_resource_section("战斗预设", combat_category_map, assume_sorted=True)
        management = unclassified_view.management
        total_count += self._add_nested_resource_section(
            "管理配置",
            self._build_management_map_from_view(management),
            assume_sorted=True,
            mark_management_items=True,
        )
        self.detail_tree.expandAll()
        self.header_label.setText(f"未分类存档（共 {total_count} 项）")

    def _render_package_index(self, package_id: str) -> None:
        index: Optional[PackageIndex] = self.pim.load_package_index(package_id)
        if not index:
            self.header_label.setText("存档不存在")
            return
        title = index.name or index.package_id
        total_count = 0
        total_count += self._add_level_entity_row(index)
        total_count += self._add_resource_section(
            "元件",
            sorted(index.resources.templates),
            ResourceType.TEMPLATE,
            assume_sorted=True,
        )
        total_count += self._add_resource_section(
            "实例",
            sorted(index.resources.instances),
            ResourceType.INSTANCE,
            assume_sorted=True,
        )
        total_count += self._add_resource_section(
            "节点图",
            sorted(index.resources.graphs),
            ResourceType.GRAPH,
            self._resolve_graph_display_name,
            assume_sorted=True,
        )
        total_count += self._add_nested_resource_section(
            "战斗预设",
            {
                sub_key: (sorted(id_list), self.COMBAT_RESOURCE_TYPES.get(sub_key))
                for sub_key, id_list in index.resources.combat_presets.items()
            },
            assume_sorted=True,
        )
        management_count = self._add_nested_resource_section(
            "管理配置",
            self._build_management_map_from_index_dict(index.resources.management),
            assume_sorted=True,
            mark_management_items=True,
        )
        signals_count = self._add_signals_section_for_package(index, management_count)
        total_count += management_count + signals_count
        self.detail_tree.expandAll()
        self.header_label.setText(f"{title}（共 {total_count} 项）")

    def _add_signals_section_for_package(
        self,
        index: PackageIndex,
        existing_management_count: int,
    ) -> int:
        """在“管理配置”下追加当前存档引用的信号列表。

        设计约定：
        - 信号定义来自代码级 Schema（DefinitionSchemaView）；
        - PackageIndex.signals 仅保存“本存档引用了哪些 signal_id”的摘要；
        - 这里基于 PackageView.signals 视图展示信号条目，与管理面板信号 Section 保持一致。
        """
        package_view = PackageView(index, self.rm)
        raw_signals = getattr(package_view, "signals", None)
        if not isinstance(raw_signals, dict) or not raw_signals:
            return 0

        entries: list[tuple[str, str]] = []
        for signal_id, config in raw_signals.items():
            if not isinstance(signal_id, str) or not signal_id:
                continue
            display_name = getattr(config, "signal_name", None)
            if not isinstance(display_name, str) or not display_name.strip():
                display_name = signal_id
            entries.append((signal_id, display_name.strip()))

        if not entries:
            return 0

        entries.sort(key=lambda pair: (pair[1], pair[0]))

        management_root: Optional[QtWidgets.QTreeWidgetItem] = None
        for i in range(self.detail_tree.topLevelItemCount()):
            candidate = self.detail_tree.topLevelItem(i)
            if candidate is None:
                continue
            root_text = candidate.text(0)
            if root_text.startswith("管理配置"):
                management_root = candidate
                break

        if management_root is None:
            management_root = QtWidgets.QTreeWidgetItem(["管理配置", "", "", ""])
            self.detail_tree.addTopLevelItem(management_root)

        resource_key = "signals"
        category_label = MANAGEMENT_RESOURCE_TITLES.get(resource_key, "信号管理")

        # 若已存在信号分类节点，先移除以避免重复。
        existing_signals_node: Optional[QtWidgets.QTreeWidgetItem] = None
        for i in range(management_root.childCount()):
            child = management_root.child(i)
            if child is None:
                continue
            if child.text(0).startswith(category_label):
                existing_signals_node = child
                break
        if existing_signals_node is not None:
            management_root.removeChild(existing_signals_node)

        section_count = len(entries)
        category_display_title = f"{category_label} ({section_count})"
        category_item = QtWidgets.QTreeWidgetItem([category_display_title, "", "", ""])
        category_item.setData(
            0,
            QtCore.Qt.ItemDataRole.UserRole + 1,
            (resource_key, ""),
        )

        for signal_id, signal_name in entries:
            entry_item = QtWidgets.QTreeWidgetItem([category_label, signal_name, "", ""])
            entry_item.setToolTip(1, signal_id)
            entry_item.setData(
                0,
                QtCore.Qt.ItemDataRole.UserRole + 1,
                (resource_key, signal_id),
            )
            category_item.addChild(entry_item)

        management_root.addChild(category_item)

        new_total_for_management = existing_management_count + section_count
        management_root.setText(0, f"管理配置 ({new_total_for_management})")

        return section_count

    def _add_simple_section(self, title: str, value: str, *, item_count: int = 0) -> int:
        display_title = title
        if item_count > 0:
            display_title = f"{title} ({item_count})"
        item = QtWidgets.QTreeWidgetItem([display_title, value, "", ""])
        self.detail_tree.addTopLevelItem(item)
        return item_count

    def _add_level_entity_row(self, index: PackageIndex) -> int:
        level_entity_id = index.level_entity_id
        if not level_entity_id:
            self._add_simple_section("关卡实体", "(未设置)", item_count=0)
            return 0

        guid_text, graphs_text = self._get_resource_extra_info(
            ResourceType.INSTANCE,
            level_entity_id,
        )
        item = QtWidgets.QTreeWidgetItem(
            ["关卡实体", level_entity_id, guid_text, graphs_text]
        )
        item.setToolTip(1, level_entity_id)
        self._set_item_resource_kind(item, "关卡实体", level_entity_id, is_level_entity=True)
        self.detail_tree.addTopLevelItem(item)
        return 1

    def _add_resource_section(
        self,
        section_title: str,
        resource_ids: Iterable[str],
        resource_type: Optional[ResourceType],
        display_name_resolver: Optional[Callable[[str], str]] = None,
        *,
        assume_sorted: bool = False,
    ) -> int:
        ordered_ids = list(resource_ids)
        if not assume_sorted:
            ordered_ids.sort()
        item_count = len(ordered_ids)
        root_title = section_title
        if item_count > 0:
            root_title = f"{section_title} ({item_count})"
        root_item = QtWidgets.QTreeWidgetItem([root_title, "", "", ""])
        for resource_id in ordered_ids:
            if display_name_resolver:
                display_name = display_name_resolver(resource_id)
            elif resource_type is not None:
                display_name = self._display_name(resource_type, resource_id)
            else:
                display_name = resource_id
            guid_text = ""
            graphs_text = ""
            if resource_type is not None and resource_type is not ResourceType.GRAPH:
                guid_text, graphs_text = self._get_resource_extra_info(
                    resource_type,
                    resource_id,
                )
            child_item = QtWidgets.QTreeWidgetItem(
                [section_title, display_name, guid_text, graphs_text]
            )
            child_item.setToolTip(1, resource_id)
            self._set_item_resource_kind(child_item, section_title, resource_id)
            root_item.addChild(child_item)
        self.detail_tree.addTopLevelItem(root_item)
        return item_count

    def _add_nested_resource_section(
        self,
        root_title: str,
        category_resources_map: Mapping[str, tuple[Sequence[str], Optional[ResourceType]]],
        *,
        assume_sorted: bool = False,
        mark_management_items: bool = False,
    ) -> int:
        root_item = QtWidgets.QTreeWidgetItem([root_title, "", "", ""])

        # 管理配置视图：由独立 helper 统一处理 signals / 单配置字段 / 常规字段三类资源。
        if mark_management_items:
            total_count = build_management_category_items_for_tree(
                root_item,
                category_resources_map,
                resource_manager=self.rm,
                mark_management_items=True,
                assume_sorted=assume_sorted,
                display_name_resolver=self._display_name,
                extra_info_resolver=self._get_resource_extra_info,
            )
        else:
            # 非管理类嵌套资源（目前用于战斗预设）：保持简单的“分类 → 资源条目”结构，
            # 并为部分类型（玩家模板/职业/技能）写入可点击的资源标记，供主窗口在存档视图中
            # 拉起对应的战斗详情面板。
            total_count = 0
            for resource_key in sorted(category_resources_map.keys()):
                resource_ids, resource_type = category_resources_map[resource_key]
                ordered_ids = list(resource_ids)
                if not assume_sorted:
                    ordered_ids.sort()
                if not ordered_ids:
                    continue

                category_label = self.COMBAT_CATEGORY_TITLES.get(resource_key, resource_key)
                category_count_for_section = len(ordered_ids)
                category_display_title = f"{category_label} ({category_count_for_section})"
                category_item = QtWidgets.QTreeWidgetItem([category_display_title, "", "", ""])

                for resource_id in ordered_ids:
                    if resource_type is not None:
                        display_name = self._display_name(resource_type, resource_id)
                    else:
                        display_name = resource_id

                    guid_text = ""
                    graphs_text = ""
                    if resource_type is not None and resource_type is not ResourceType.GRAPH:
                        guid_text, graphs_text = self._get_resource_extra_info(
                            resource_type,
                            resource_id,
                        )
                    entry_item = QtWidgets.QTreeWidgetItem(
                        [category_label, display_name, guid_text, graphs_text]
                    )
                    entry_item.setToolTip(1, resource_id)

                    combat_kind: Optional[str]
                    if resource_key == "player_templates":
                        combat_kind = "combat_player_template"
                    elif resource_key == "player_classes":
                        combat_kind = "combat_player_class"
                    elif resource_key == "skills":
                        combat_kind = "combat_skill"
                    else:
                        combat_kind = None
                    if combat_kind is not None:
                        entry_item.setData(
                            0,
                            QtCore.Qt.ItemDataRole.UserRole,
                            (combat_kind, resource_id),
                        )

                    category_item.addChild(entry_item)

                root_item.addChild(category_item)
                total_count += category_count_for_section

        if total_count > 0:
            root_item.setText(0, f"{root_title} ({total_count})")
        self.detail_tree.addTopLevelItem(root_item)
        return total_count

    def _build_management_map_from_resource_manager(self) -> dict[str, tuple[Sequence[str], Optional[ResourceType]]]:
        mapping: dict[str, tuple[Sequence[str], Optional[ResourceType]]] = {}
        for resource_key in MANAGEMENT_RESOURCE_ORDER:
            resource_type = MANAGEMENT_RESOURCE_BINDINGS[resource_key]
            mapping[resource_key] = (self._list_resources_cached(resource_type), resource_type)
        return mapping

    def _build_management_map_from_view(self, management_view) -> dict[str, tuple[Sequence[str], Optional[ResourceType]]]:
        mapping: dict[str, tuple[Sequence[str], Optional[ResourceType]]] = {}
        for resource_key in MANAGEMENT_RESOURCE_ORDER:
            resource_type = MANAGEMENT_RESOURCE_BINDINGS[resource_key]
            value = getattr(management_view, resource_key, {})
            if isinstance(value, dict):
                ids = sorted(value.keys())
            elif isinstance(value, (list, tuple, set)):
                ids = sorted(value)
            else:
                ids = []
            mapping[resource_key] = (ids, resource_type)
        return mapping

    def _build_management_map_from_index_dict(
        self, management_dict: Mapping[str, Sequence[str]]
    ) -> dict[str, tuple[Sequence[str], Optional[ResourceType]]]:
        result: dict[str, tuple[Sequence[str], Optional[ResourceType]]] = {}
        for resource_key in MANAGEMENT_RESOURCE_ORDER:
            resource_type = MANAGEMENT_RESOURCE_BINDINGS[resource_key]
            ids = list(management_dict.get(resource_key, []))
            ids.sort()
            result[resource_key] = (ids, resource_type)
        return result

    def _resolve_graph_display_name(self, graph_id: str) -> str:
        cached = self._graph_display_name_cache.get(graph_id)
        if cached:
            return cached
        metadata = self.rm.load_graph_metadata(graph_id) or {}
        name = metadata.get("name") or graph_id
        self._graph_display_name_cache[graph_id] = name
        return name

    def _clear_display_name_cache(self) -> None:
        self._resource_name_cache.clear()
        self._graph_display_name_cache.clear()
        self._resource_cache.clear()
        self._resource_extra_cache.clear()
        self._cached_unclassified_view = None

    def _list_resources_cached(self, resource_type: ResourceType) -> list[str]:
        cached = self._resource_cache.get(resource_type)
        if cached is not None:
            return cached
        values = sorted(self.rm.list_resources(resource_type))
        self._resource_cache[resource_type] = values
        return values

    def _get_unclassified_view(self) -> UnclassifiedResourceView:
        if self._cached_unclassified_view is None:
            self._cached_unclassified_view = UnclassifiedResourceView(self.rm, self.pim)
        return self._cached_unclassified_view

    # === Actions ===
    def _on_rename(self) -> None:
        if not self._current_package_id or self._is_special_id(self._current_package_id):
            return
        current_item = self.package_list.currentItem()
        if not current_item:
            return
        current_name = current_item.text()
        new_name = input_dialogs.prompt_text(
            self,
            "重命名存档",
            "请输入新名称:",
            text=current_name,
        )
        if not new_name:
            return
        self.pim.rename_package(self._current_package_id, new_name)
        self.packages_changed.emit()
        self.refresh()

        event = LibraryChangeEvent(
            kind="package",
            id=self._current_package_id,
            operation="update",
            context={"field": "name"},
        )
        self.data_changed.emit(event)

    def _on_delete(self) -> None:
        if not self._current_package_id or self._is_special_id(self._current_package_id):
            return
        pkg_id = self._current_package_id
        if not self.confirm(
            "删除存档",
            "仅删除存档本身，不会删除包内引用的资源。\n确定要删除吗？",
        ):
            return
        self.pim.delete_package(pkg_id)
        self._current_package_id = ""
        self.packages_changed.emit()
        self.refresh()

        event = LibraryChangeEvent(
            kind="package",
            id=pkg_id,
            operation="delete",
            context=None,
        )
        self.data_changed.emit(event)


