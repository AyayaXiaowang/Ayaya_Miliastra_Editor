from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Callable, Dict, Iterable, Mapping, Optional, Sequence, Tuple

from PyQt6 import QtCore, QtWidgets

from engine.resources.package_index_manager import PackageIndexManager
from engine.resources.package_index import PackageIndex
from engine.resources.package_view import PackageView
from engine.resources.resource_manager import ResourceManager
from engine.resources.resource_manager import ResourceType
from engine.resources.index_disk_consistency import collect_package_index_disk_consistency
from engine.resources.management_naming_rules import get_id_field_for_type
from engine.graph.utils.metadata_extractor import load_graph_metadata_from_file
from engine.utils.resource_library_layout import get_packages_root_dir, get_shared_root_dir
from app.ui.foundation import input_dialogs
from app.ui.foundation import dialog_utils
from app.ui.foundation.theme_manager import Sizes
from app.ui.foundation.toolbar_utils import apply_standard_toolbar
from app.ui.graph.library_mixins import (
    SearchFilterMixin,
    ConfirmDialogMixin,
    rebuild_list_with_preserved_selection,
)
from app.ui.graph.library_pages.library_scaffold import (
    DualPaneLibraryScaffold,
    LibraryChangeEvent,
    LibraryPageMixin,
    LibrarySelection,
)
from app.ui.graph.library_pages.management_tree_helpers import (
    build_management_category_items_for_tree,
)
from app.ui.management.section_registry import (
    MANAGEMENT_RESOURCE_BINDINGS,
    MANAGEMENT_RESOURCE_DEFAULT_SECTION_KEYS,
    MANAGEMENT_RESOURCE_ORDER,
    MANAGEMENT_RESOURCE_TITLES,
)
from app.ui.panels.panel_scaffold import SectionCard
from app.ui.graph.graph_library.graph_resource_load_thread import GraphResourceLoadThread


class PackageLibraryWidget(DualPaneLibraryScaffold, SearchFilterMixin, ConfirmDialogMixin, LibraryPageMixin):
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
    # 设计约定：
    # - 左侧列表的**单击/选中**仅用于本页预览，不应影响主窗口顶部的当前存档；
    # - 只有“切换为当前”按钮或双击条目才会发射该信号并触发主窗口切包保护入口。
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
    _LAZY_KIND_UI_SOURCE = "ui_source"
    _ACTION_LOAD_MORE = "load_more"

    # 预览体验：默认展示每个分类前 N 条，避免一次性创建过多 TreeWidgetItem 导致卡顿。
    _PREVIEW_CHILD_LIMIT = 30
    # 用户点击“加载更多”时每次追加的条数
    _LOAD_MORE_CHUNK_SIZE = 200

    # 存档库（PACKAGES）页中，“管理配置”分类显示名称的局部覆写。
    # 说明：大部分分类标题来自 `app.ui.management.section_registry.MANAGEMENT_RESOURCE_TITLES`；
    # 如需在本页面内进一步细化/消歧，可在此追加覆写。
    _MANAGEMENT_CATEGORY_LABEL_OVERRIDES: dict[str, str] = {}

    def __init__(self, resource_manager: ResourceManager, package_index_manager: PackageIndexManager, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(
            parent,
            title="项目存档",
            description="浏览并管理全部项目存档、共享资源视图与其包含的资源。",
        )
        self.rm = resource_manager
        self.pim = package_index_manager

        self._current_package_id: str = ""
        self._resource_name_cache: Dict[Tuple[ResourceType, str], str] = {}
        self._graph_display_name_cache: Dict[str, str] = {}
        self._resource_cache: Dict[ResourceType, list[str]] = {}
        self._resource_extra_cache: Dict[Tuple[ResourceType, str], Tuple[str, str]] = {}
        # 预览页：按 root_key（shared / package_id）缓存“磁盘扫描得到的资源 ID 列表”，避免切换预览时重复扫描。
        self._preview_resource_ids_cache: Dict[Tuple[str, ResourceType], list[str]] = {}
        self._last_index_disk_consistency_report = None
        self._extension_toolbar_buttons: Dict[str, QtWidgets.QAbstractButton] = {}
        self._extension_toolbar_widgets: Dict[str, QtWidgets.QWidget] = {}
        self._extension_toolbar_layout: QtWidgets.QHBoxLayout | None = None
        self._extension_toolbar_widget_host: QtWidgets.QWidget | None = None

        self._setup_ui()
        self.refresh()

    # === LibraryPage 协议实现 ===

    def set_context(self, view: object) -> None:
        """项目存档页与具体 PackageView 无直接绑定关系，此处忽略上下文参数，仅重新加载列表。

        设计上项目存档页始终展示全部项目存档以及共享资源视图，
        因此 set_context 仅作为统一协议占位，方便主窗口按统一入口管理所有库页。
        """
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

    # === UI ===
    def _setup_ui(self) -> None:
        # 顶部：标题右侧放搜索框，快速过滤项目存档列表
        self.search_edit = QtWidgets.QLineEdit(self)
        self.search_edit.setPlaceholderText("搜索项目存档...")
        self.search_edit.setMinimumHeight(Sizes.INPUT_HEIGHT)
        self.add_action_widget(self.search_edit)
        self.connect_search(self.search_edit, self._filter_packages, placeholder="搜索项目存档...")

        # 标题下方：项目存档操作按钮行（重命名/删除/刷新）
        toolbar_widget = QtWidgets.QWidget()
        toolbar_layout = QtWidgets.QHBoxLayout(toolbar_widget)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(Sizes.SPACING_MEDIUM)
        apply_standard_toolbar(toolbar_layout)

        # 插件扩展区：允许私有扩展在不触碰内部 layout 的情况下追加按钮
        extension_toolbar_widget = QtWidgets.QWidget(toolbar_widget)
        extension_toolbar_layout = QtWidgets.QHBoxLayout(extension_toolbar_widget)
        extension_toolbar_layout.setContentsMargins(0, 0, 0, 0)
        extension_toolbar_layout.setSpacing(Sizes.SPACING_MEDIUM)
        self._extension_toolbar_layout = extension_toolbar_layout
        self._extension_toolbar_widget_host = extension_toolbar_widget
        toolbar_layout.addWidget(extension_toolbar_widget)

        self.rename_btn = QtWidgets.QPushButton("重命名")
        self.open_btn = QtWidgets.QPushButton("切换为当前")
        self.clone_btn = QtWidgets.QPushButton("复制")
        self.delete_btn = QtWidgets.QPushButton("删除")
        self.refresh_btn = QtWidgets.QPushButton("刷新")

        self.rename_btn.clicked.connect(self._on_rename)
        self.open_btn.clicked.connect(self._on_open_clicked)
        self.clone_btn.clicked.connect(self._on_clone)
        self.delete_btn.clicked.connect(self._on_delete)
        self.refresh_btn.clicked.connect(self.refresh)

        toolbar_layout.addWidget(self.rename_btn)
        toolbar_layout.addWidget(self.open_btn)
        toolbar_layout.addWidget(self.clone_btn)
        toolbar_layout.addWidget(self.delete_btn)
        toolbar_layout.addWidget(self.refresh_btn)
        toolbar_layout.addStretch(1)
        self.set_status_widget(toolbar_widget)

        self.package_list = QtWidgets.QListWidget()
        self.package_list.setObjectName("leftPanel")
        # 不要锁死宽度：该页面使用 QSplitter，左侧列表需要允许用户拖拽分隔线改变宽度。
        # 默认宽度仍以主题 token 为基准，初始分配由 splitter.setSizes(...) 负责。
        self.package_list.setMinimumWidth(Sizes.LEFT_PANEL_WIDTH)
        self.package_list.itemSelectionChanged.connect(self._on_package_selected)
        self.package_list.itemDoubleClicked.connect(self._on_package_item_double_clicked)
        self.package_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)

        # 右侧：包详情（标题 + 树）
        right_container = QtWidgets.QWidget(self)
        right_layout = QtWidgets.QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        self.header_label = QtWidgets.QLabel("")
        header_font = self.header_label.font()
        header_font.setPointSize(Sizes.FONT_LARGE)
        header_font.setBold(True)
        self.header_label.setFont(header_font)
        right_layout.addWidget(self.header_label)

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
        # 展开节点时按需构建子项，避免在切换存档预览时批量创建大量 TreeWidgetItem 造成卡顿。
        self.detail_tree.itemExpanded.connect(self._on_detail_tree_item_expanded)
        right_layout.addWidget(self.detail_tree, 1)

        self.build_dual_pane(
            self.package_list,
            right_container,
            left_title="项目存档列表",
            left_description="选择项目存档或特殊视图",
            right_title="项目存档内容详情",
            right_description="查看元件、实体、管理配置等资源",
        )
        # 左侧默认收窄，但允许用户拖到更宽
        self._splitter.setSizes([Sizes.LEFT_PANEL_WIDTH, 1000])
        # 说明：索引一致性检查属于内部诊断能力，不在 UI 中暴露（避免干扰普通用户）。

    def _on_open_clicked(self) -> None:
        """显式切换为当前存档：发射 package_load_requested，由主窗口走切包保护入口处理。"""
        package_id = str(self._current_package_id or "").strip()
        if not package_id:
            return
        self.package_load_requested.emit(package_id)

    def _on_package_item_double_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        """双击左侧存档条目：视为显式切换为当前存档。"""
        if item is None:
            return
        package_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(package_id, str) or not package_id:
            return
        self.package_load_requested.emit(package_id)

    # === 插件扩展：工具栏按钮 ===
    def ensure_extension_toolbar_button(
        self,
        key: str,
        text: str,
        *,
        tooltip: str = "",
        on_clicked: Callable[[], None] | None = None,
        enabled: bool = True,
    ) -> QtWidgets.QPushButton:
        """确保“扩展工具栏”存在一个按钮（幂等）。

        约定：
        - key 必须唯一且非空；同 key 多次调用会复用同一个按钮实例；
        - 为避免插件重复 install 导致多次 connect，这里不会自动替换既有 clicked 连接。
        """
        normalized_key = str(key or "").strip()
        if not normalized_key:
            raise ValueError("extension toolbar button key 不能为空")

        existing = self._extension_toolbar_buttons.get(normalized_key)
        if existing is not None:
            if not isinstance(existing, QtWidgets.QPushButton):
                raise TypeError(
                    f"extension toolbar key 已存在但不是 QPushButton: key={normalized_key!r}, type={type(existing).__name__}"
                )
            existing.setText(str(text))
            if tooltip:
                existing.setToolTip(str(tooltip))
            existing.setEnabled(bool(enabled))
            return existing

        if self._extension_toolbar_layout is None:
            raise RuntimeError("extension toolbar layout 未初始化（_setup_ui 尚未完成）")

        button = QtWidgets.QPushButton(str(text))
        if tooltip:
            button.setToolTip(str(tooltip))
        button.setEnabled(bool(enabled))
        if on_clicked is not None:
            button.clicked.connect(on_clicked)
        self._extension_toolbar_layout.addWidget(button)
        self._extension_toolbar_buttons[normalized_key] = button
        return button

    def ensure_extension_toolbar_widget(
        self,
        key: str,
        create_widget: Callable[[QtWidgets.QWidget], QtWidgets.QWidget],
        *,
        visible: bool = True,
    ) -> QtWidgets.QWidget:
        """确保“扩展工具栏”存在一个自定义 widget（幂等）。

        设计目的：允许插件在项目存档页工具栏注入非按钮控件（例如进度条/状态指示器），
        同时避免插件直接访问内部 layout 私有字段。

        约定：
        - key 必须唯一且非空；
        - 同 key 多次调用会复用同一个 widget 实例；
        - key 不可与 ensure_extension_toolbar_button 的 key 冲突。
        """
        normalized_key = str(key or "").strip()
        if not normalized_key:
            raise ValueError("extension toolbar widget key 不能为空")
        if normalized_key in self._extension_toolbar_buttons:
            raise RuntimeError(f"extension toolbar key 已被按钮占用：{normalized_key!r}")

        existing = self._extension_toolbar_widgets.get(normalized_key)
        if existing is not None:
            existing.setVisible(bool(visible))
            return existing

        if self._extension_toolbar_layout is None:
            raise RuntimeError("extension toolbar layout 未初始化（_setup_ui 尚未完成）")
        if self._extension_toolbar_widget_host is None:
            raise RuntimeError("extension toolbar host 未初始化（_setup_ui 尚未完成）")

        widget = create_widget(self._extension_toolbar_widget_host)
        if not isinstance(widget, QtWidgets.QWidget):
            raise TypeError(
                f"create_widget 必须返回 QWidget（key={normalized_key!r}, got={type(widget).__name__}）"
            )
        widget.setVisible(bool(visible))
        self._extension_toolbar_layout.addWidget(widget)
        self._extension_toolbar_widgets[normalized_key] = widget
        return widget

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
        - "instance"     → 实体摆放
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
        elif section_title == "实体摆放":
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
        """当用户在项目存档内容详情中点击某一行时，发射资源激活信号。

        设计约定：
        - 对真正代表资源条目的行生效（模板/实体摆放/关卡实体/节点图/部分战斗预设类型）；
        - 管理配置条目通过独立信号 `management_resource_activated` 通知主窗口；
        - 根分组行或仅用于展示统计信息的行不发射任何信号。
        """
        value = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        management_value = item.data(0, QtCore.Qt.ItemDataRole.UserRole + 1)

        if isinstance(value, tuple) and len(value) == 2:
            kind, resource_id = value
            if isinstance(kind, str) and isinstance(resource_id, str) and kind and resource_id:
                self.resource_activated.emit(kind, resource_id)
                return

        # 管理配置条目：仅当 UserRole+1 中标记了 (resource_key, resource_id) 时发射单击信号，
        # 用于在当前视图右侧通过 ManagementPropertyPanel 展示摘要与“所属存档”行。
        if isinstance(management_value, dict):
            binding_key = management_value.get("binding_key")
            item_id = management_value.get("item_id")
            if (
                isinstance(binding_key, str)
                and isinstance(item_id, str)
                and binding_key
                and item_id
            ):
                self.management_resource_activated.emit(binding_key, item_id)
                return

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
        """当用户在项目存档内容详情中双击某一行时，触发跨页面跳转。

        交互约定：
        - 单击：仅在当前主窗口右侧属性/图属性面板中以只读方式预览；
        - 双击：跳转到对应的编辑上下文：
            - 元件 / 实体摆放 / 关卡实体 → 根据当前项目存档切换到元件库或实体摆放，并选中目标条目；
            - 节点图               → 直接在节点图编辑器中以独立方式打开。
        """
        # “加载更多”占位：双击后为其父节点追加条目
        action = item.data(0, self._ROLE_TREE_ACTION)
        if isinstance(action, str) and action == self._ACTION_LOAD_MORE:
            parent_item = item.parent()
            if parent_item is not None:
                self._load_more_children_for_item(parent_item)
                self.detail_tree.expandItem(parent_item)
            return

        resource_value = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if isinstance(resource_value, tuple) and len(resource_value) == 2:
            kind, resource_id = resource_value
            if not isinstance(kind, str) or not isinstance(resource_id, str):
                return
            if not kind or not resource_id:
                return

            # 模板 / 实体摆放 / 关卡实体：依赖当前项目存档上下文，通过导航协调器跳转到对应页面。
            if kind in ("template", "instance", "level_entity"):
                package_id_for_entity = self._current_package_id
                if not package_id_for_entity or self._is_special_id(package_id_for_entity):
                    # 聚合视图下没有唯一的项目存档上下文，仅提供只读预览，不执行跳转。
                    return
                self.jump_to_entity_requested.emit(kind, resource_id, package_id_for_entity)
                return

            # 节点图：直接打开对应节点图进行编辑（不依赖具体项目存档容器）。
            if kind == "graph":
                # 后台加载：避免 load_resource(ResourceType.GRAPH, ...) 在 UI 线程阻塞
                generation = int(getattr(self, "_async_graph_open_generation", 0) or 0) + 1
                setattr(self, "_async_graph_open_generation", generation)

                prev_thread = getattr(self, "_async_graph_open_thread", None)
                if prev_thread is not None and hasattr(prev_thread, "isRunning") and prev_thread.isRunning():
                    prev_thread.requestInterruption()
                setattr(self, "_async_graph_open_thread", None)

                thread = GraphResourceLoadThread(resource_manager=self.rm, graph_id=resource_id, parent=self)
                setattr(self, "_async_graph_open_thread", thread)

                def _on_finished() -> None:
                    if int(getattr(self, "_async_graph_open_generation", 0) or 0) != int(generation):
                        return
                    result = getattr(thread, "result", None)
                    if result is None or not isinstance(result.graph_data, dict):
                        return
                    self.graph_double_clicked.emit(resource_id, result.graph_data)

                thread.finished.connect(_on_finished)
                thread.start()
                return

        # 管理配置：根据 section_key + item_id 请求主窗口跳转到对应管理页面。
        management_value = item.data(0, QtCore.Qt.ItemDataRole.UserRole + 1)
        if isinstance(management_value, dict):
            jump_section_key = management_value.get("jump_section_key")
            item_id = management_value.get("item_id", "")
            if not isinstance(jump_section_key, str) or not jump_section_key:
                return
            if not isinstance(item_id, str):
                return
            section_key = jump_section_key
        else:
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
        """根据搜索文本过滤项目存档列表。"""
        self.filter_list_items(self.package_list, text)
        self.ensure_current_item_visible_or_select_first(self.package_list)

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
        """刷新项目存档列表"""
        self._clear_display_name_cache()
        self._clear_preview_scan_cache()
        previous_key = self._current_package_id or None

        def build_items() -> None:
            # 先插入共享资源视图
            item_global = QtWidgets.QListWidgetItem("共享资源")
            item_global.setData(QtCore.Qt.ItemDataRole.UserRole, "global_view")
            item_global.setToolTip("浏览共享资源（所有项目存档可见；不可重命名/删除）")
            self.package_list.addItem(item_global)

            # 再加载普通项目存档
            packages = self.pim.list_packages()
            for pkg in packages:
                item = QtWidgets.QListWidgetItem(pkg["name"])  # 文本为名称
                item.setData(QtCore.Qt.ItemDataRole.UserRole, pkg["package_id"])  # 存放ID
                description = pkg.get("description", "")
                if description:
                    item.setToolTip(description)
                self.package_list.addItem(item)

        def get_item_key(list_item: QtWidgets.QListWidgetItem) -> Optional[str]:
            value = list_item.data(QtCore.Qt.ItemDataRole.UserRole)
            if isinstance(value, str):
                return value
            return None

        rebuild_list_with_preserved_selection(
            self.package_list,
            previous_key=previous_key,
            had_selection_before_refresh=bool(previous_key),
            build_items=build_items,
            key_getter=get_item_key,
            on_restored_selection=None,
            on_first_selection=None,
            on_cleared_selection=None,
        )

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
        if not isinstance(pkg_id, str) or not pkg_id:
            self._current_package_id = ""
            self._render_empty_detail()
            self._update_action_state()
            return
        self._current_package_id = pkg_id
        self._render_package_detail(pkg_id)
        self._update_action_state()

    def _on_package_item_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        """用户点击项目存档列表条目时，通知主窗口同步项目存档上下文。"""
        if item is None:
            return
        package_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(package_id, str) or not package_id:
            return
        self.package_load_requested.emit(package_id)

    def _is_special_id(self, package_id: str) -> bool:
        return package_id == "global_view"

    def _update_action_state(self) -> None:
        is_special = self._is_special_id(self._current_package_id)
        can_edit = bool(self._current_package_id) and not is_special
        self.rename_btn.setEnabled(can_edit)
        self.clone_btn.setEnabled(can_edit)
        self.delete_btn.setEnabled(can_edit)
        # 预览模式下允许切换到当前存档（含 global_view）；无选中则禁用。
        self.open_btn.setEnabled(bool(self._current_package_id))
        self._reset_index_disk_consistency_ui_state()

    def _render_empty_detail(self) -> None:
        self.header_label.setText("未选择项目存档")
        self.detail_tree.clear()
        self._reset_index_disk_consistency_ui_state()

    def _render_package_detail(self, package_id: str) -> None:
        self.detail_tree.setUpdatesEnabled(False)
        self.detail_tree.clear()
        self._reset_index_disk_consistency_ui_state()

        # 预览视图：默认仅展示“分类 + 计数”（保持折叠），展开时懒加载前 N 条并提供“加载更多”入口。
        if package_id == "global_view":
            self._render_global_view_overview()
        else:
            self._render_package_index_overview(package_id)
        self.detail_tree.setUpdatesEnabled(True)

    def _reset_index_disk_consistency_ui_state(self) -> None:
        """刷新“索引一致性”检查条的启用态与文案。"""
        if not hasattr(self, "consistency_status_label"):
            return
        self._last_index_disk_consistency_report = None
        self.consistency_status_label.setText("索引一致性：未检查")

        can_check = bool(self._current_package_id) and (not self._is_special_id(self._current_package_id))
        if hasattr(self, "consistency_check_btn"):
            self.consistency_check_btn.setEnabled(bool(can_check))
        if hasattr(self, "consistency_fix_btn"):
            self.consistency_fix_btn.setEnabled(bool(can_check))

    # ===== 预览（磁盘扫描）=====
    def _clear_preview_scan_cache(self) -> None:
        self._preview_resource_ids_cache.clear()

    def _get_preview_root_dir(self, package_id: str) -> Path | None:
        """返回该 package_id 在“预览”语义下应扫描的资源根目录（共享根 or 项目存档根）。"""
        resource_library_dir = getattr(self.rm, "resource_library_dir", None)
        if not isinstance(resource_library_dir, Path):
            return None

        normalized = str(package_id or "").strip()
        if not normalized:
            return None

        if normalized == "global_view":
            return get_shared_root_dir(resource_library_dir)
        return get_packages_root_dir(resource_library_dir) / normalized

    @staticmethod
    def _is_ui_plugin_enabled() -> bool:
        """是否已加载私有 UI 插件（Web 工具入口已启用）。

        注意：
        - 该门禁用于“是否展示 UI 相关分类/入口”，不应绑定到 Playwright/自动转换能力；
        - 自动转换（HTML->bundle）可以不启用，但 Web 预览/手动导入导出仍可用。
        """
        from app.common.private_extension_registry import is_ui_tools_plugin_enabled

        return is_ui_tools_plugin_enabled()

    def _resolve_management_category_label(self, resource_key: str) -> str:
        override = self._MANAGEMENT_CATEGORY_LABEL_OVERRIDES.get(resource_key)
        if override:
            return override
        return MANAGEMENT_RESOURCE_TITLES.get(resource_key, resource_key)

    @staticmethod
    def _resolve_management_jump_section_key(binding_key: str) -> str:
        normalized = str(binding_key or "").strip()
        if not normalized:
            return ""
        mapped = MANAGEMENT_RESOURCE_DEFAULT_SECTION_KEYS.get(normalized)
        if isinstance(mapped, str) and mapped:
            return mapped
        return normalized

    @staticmethod
    def _build_management_item_marker(
        *,
        binding_key: str,
        item_id: str,
        jump_section_key: str,
    ) -> dict:
        return {
            "binding_key": str(binding_key or ""),
            "item_id": str(item_id or ""),
            "jump_section_key": str(jump_section_key or ""),
        }

    def _build_preview_management_category_map(
        self,
        *,
        package_root_dir: Path,
        shared_root_dir: Path | None,
        package_root_key: str,
        include_shared: bool,
        ui_plugin_enabled: bool,
    ) -> dict[str, tuple[Sequence[str], Optional[ResourceType]]]:
        """为“预览（磁盘扫描）”构建管理配置分类映射。

        关键点：
        - 对“具体项目存档”视图：管理配置按“共享根 + 项目存档根”合并展示，避免出现
          “项目本身没放结构体/信号文件，但实际上可用的共享定义在 UI 中看不到”的错觉；
        - UI 工作流不再以“管理配置资源”形式维护（HTML 为真源，派生物入运行时缓存），因此这里不再按资源桶展示 UI页面/UI布局/UI控件模板。
        """
        mapping: dict[str, tuple[Sequence[str], Optional[ResourceType]]] = {}

        for resource_key in MANAGEMENT_RESOURCE_ORDER:
            resource_type = MANAGEMENT_RESOURCE_BINDINGS.get(resource_key)

            if resource_type is None:
                mapping[resource_key] = ([], None)
                continue

            package_ids = self._get_preview_resource_ids(
                root_key=package_root_key,
                root_dir=package_root_dir,
                resource_type=resource_type,
            )

            shared_ids: list[str] = []
            if include_shared and shared_root_dir is not None and shared_root_dir.exists() and shared_root_dir.is_dir():
                shared_ids = self._get_preview_resource_ids(
                    root_key="shared",
                    root_dir=shared_root_dir,
                    resource_type=resource_type,
                )

            if package_ids and shared_ids:
                merged = sorted(set(package_ids).union(shared_ids), key=lambda text: text.casefold())
            elif package_ids:
                merged = list(package_ids)
            else:
                merged = list(shared_ids)

            mapping[resource_key] = (merged, resource_type)

        return mapping

    @staticmethod
    def _extract_python_module_level_string_constant(file_path: Path, *, constant_name: str) -> str:
        """从 Python 文件中提取模块级字符串常量（SIGNAL_ID / STRUCT_ID 等）。"""
        code_text = file_path.read_text(encoding="utf-8-sig")
        parsed_tree = ast.parse(code_text, filename=str(file_path))
        for node in parsed_tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if not isinstance(target, ast.Name):
                        continue
                    if target.id != constant_name:
                        continue
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        return node.value.value.strip()
            if isinstance(node, ast.AnnAssign):
                if not isinstance(node.target, ast.Name):
                    continue
                if node.target.id != constant_name:
                    continue
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    return node.value.value.strip()
        return ""

    def _scan_resource_ids_under_root(self, *, root_dir: Path, resource_type: ResourceType) -> list[str]:
        """在给定资源根目录下扫描某一资源类型的 ID 列表（不依赖 ResourceManager 当前作用域）。"""
        resource_dir = root_dir / Path(str(resource_type.value))
        if not resource_dir.exists() or not resource_dir.is_dir():
            return []

        # Python 代码资源：递归扫描
        if resource_type in {ResourceType.GRAPH, ResourceType.SIGNAL, ResourceType.STRUCT_DEFINITION}:
            ids: list[str] = []
            py_files = sorted(
                list(resource_dir.rglob("*.py")),
                key=lambda path: path.as_posix().casefold(),
            )
            for py_file in py_files:
                if not py_file.is_file():
                    continue
                if py_file.name.startswith("_"):
                    continue
                if "校验" in py_file.stem:
                    continue
                if py_file.parent.name == "__pycache__":
                    continue

                resource_id = ""
                if resource_type == ResourceType.GRAPH:
                    meta = load_graph_metadata_from_file(py_file)
                    resource_id = str(meta.graph_id or "").strip() or py_file.stem
                elif resource_type == ResourceType.SIGNAL:
                    resource_id = self._extract_python_module_level_string_constant(
                        py_file,
                        constant_name="SIGNAL_ID",
                    )
                else:
                    resource_id = self._extract_python_module_level_string_constant(
                        py_file,
                        constant_name="STRUCT_ID",
                    )

                if isinstance(resource_id, str) and resource_id.strip():
                    ids.append(resource_id.strip())
            ids.sort(key=lambda text: text.casefold())
            return ids

        # JSON 资源：只扫描直接子文件
        id_field = get_id_field_for_type(resource_type) or "id"
        ids: list[str] = []
        json_files = sorted(
            list(resource_dir.glob("*.json")),
            key=lambda path: path.as_posix().casefold(),
        )
        for json_file in json_files:
            if not json_file.is_file():
                continue
            payload = json.loads(json_file.read_text(encoding="utf-8-sig"))
            if not isinstance(payload, dict):
                continue
            value = payload.get(id_field)
            if not isinstance(value, str) or not value.strip():
                continue
            ids.append(value.strip())
        ids.sort(key=lambda text: text.casefold())
        return ids

    def _get_preview_resource_ids(self, *, root_key: str, root_dir: Path, resource_type: ResourceType) -> list[str]:
        cache_key = (str(root_key), resource_type)
        cached = self._preview_resource_ids_cache.get(cache_key)
        if isinstance(cached, list):
            return list(cached)
        ids = self._scan_resource_ids_under_root(root_dir=root_dir, resource_type=resource_type)
        self._preview_resource_ids_cache[cache_key] = list(ids)
        return list(ids)

    def _on_check_index_disk_consistency_clicked(self) -> None:
        """检查当前选中项目存档的“索引 vs 磁盘”一致性，并展示可复制报告。"""
        package_id = str(self._current_package_id or "").strip()
        if not package_id or self._is_special_id(package_id):
            return

        report = collect_package_index_disk_consistency(
            package_id=package_id,
            resource_manager=self.rm,
            package_index_manager=self.pim,
        )
        self._last_index_disk_consistency_report = report

        summary = (
            f"missing={report.total_missing} orphan={report.total_orphan} "
            f"dup_index={report.total_duplicate_index} dup_disk={report.total_duplicate_disk}"
        )
        self.consistency_status_label.setText(f"索引一致性：{summary}")

        report_text = report.render_text(max_items_per_list=200)
        if report.has_issues():
            dialog_utils.show_error_dialog(
                self,
                "索引一致性检查结果",
                f"发现索引/磁盘不一致：{summary}",
                details=report_text,
                copy_text=report_text,
            )
            return

        dialog_utils.show_info_dialog(self, "索引一致性检查结果", f"✅ 未发现索引/磁盘不一致：{summary}")

    def _on_repair_index_disk_consistency_clicked(self) -> None:
        """尝试修复：重建当前项目存档作用域资源索引并刷新 UI。"""
        package_id = str(self._current_package_id or "").strip()
        if not package_id or self._is_special_id(package_id):
            return

        if not dialog_utils.ask_yes_no_dialog(
            self,
            "尝试修复索引一致性",
            "将执行：\n"
            "- 重建资源索引（共享根 + 当前项目存档根）\n"
            "- 失效当前项目存档的 PackageIndex 派生缓存\n"
            "- 刷新项目存档页面\n\n"
            "注意：这不会自动修复“磁盘重复 ID / 非法资源文件”，此类问题需要手动处理。",
            default_yes=False,
        ):
            return

        self.rm.rebuild_index(active_package_id=package_id)
        self.pim.invalidate_package_index_cache(package_id)
        self.refresh()
        # 修复后立即再跑一次检查，让用户看到结果是否归零
        self._on_check_index_disk_consistency_clicked()

    def _render_global_view_overview(self) -> None:
        """渲染共享资源视图的预览（分类 + 计数；展开时懒加载）。"""
        root_dir = self._get_preview_root_dir("global_view")
        if root_dir is None or not root_dir.exists() or not root_dir.is_dir():
            self.header_label.setText("共享资源目录不存在")
            return

        root_key = "shared"
        total_count = 0

        templates = self._get_preview_resource_ids(
            root_key=root_key,
            root_dir=root_dir,
            resource_type=ResourceType.TEMPLATE,
        )
        instances = self._get_preview_resource_ids(
            root_key=root_key,
            root_dir=root_dir,
            resource_type=ResourceType.INSTANCE,
        )
        graphs = self._get_preview_resource_ids(
            root_key=root_key,
            root_dir=root_dir,
            resource_type=ResourceType.GRAPH,
        )

        total_count += self._add_lazy_resource_section_root("元件", ResourceType.TEMPLATE, templates)
        total_count += self._add_lazy_resource_section_root("实体摆放", ResourceType.INSTANCE, instances)
        total_count += self._add_lazy_resource_section_root("节点图", ResourceType.GRAPH, graphs)

        total_count += self._add_lazy_nested_combat_section_root(
            "战斗预设",
            {
                sub_key: (
                    self._get_preview_resource_ids(
                        root_key=root_key,
                        root_dir=root_dir,
                        resource_type=resource_type,
                    ),
                    resource_type,
                )
                for sub_key, resource_type in self.COMBAT_RESOURCE_TYPES.items()
            },
        )

        total_count += self._add_lazy_nested_management_section_root(
            "管理配置",
            self._build_preview_management_category_map(
                package_root_dir=root_dir,
                shared_root_dir=root_dir,
                package_root_key=root_key,
                include_shared=False,
                ui_plugin_enabled=self._is_ui_plugin_enabled(),
            ),
        )

        self.header_label.setText(f"共享资源（共 {total_count} 项）")


    def _render_package_index_overview(self, package_id: str) -> None:
        """渲染具体项目存档的预览（分类 + 计数；展开时懒加载）。"""
        root_dir = self._get_preview_root_dir(package_id)
        if root_dir is None or not root_dir.exists() or not root_dir.is_dir():
            self.header_label.setText("项目存档不存在")
            return

        pkg_info = None
        if hasattr(self.pim, "get_package_info"):
            pkg_info = self.pim.get_package_info(package_id)  # type: ignore[attr-defined]
        title = str(pkg_info.get("name") if isinstance(pkg_info, dict) else "") or str(package_id)

        root_key = str(package_id)
        total_count = 0

        templates = self._get_preview_resource_ids(
            root_key=root_key,
            root_dir=root_dir,
            resource_type=ResourceType.TEMPLATE,
        )
        instances = self._get_preview_resource_ids(
            root_key=root_key,
            root_dir=root_dir,
            resource_type=ResourceType.INSTANCE,
        )
        graphs = self._get_preview_resource_ids(
            root_key=root_key,
            root_dir=root_dir,
            resource_type=ResourceType.GRAPH,
        )

        # 关卡实体：约定 ID 为 level_<package_id>；存在则单独展示并从“实体摆放”中剔除，避免重复计数。
        level_entity_id = f"level_{package_id}"
        if level_entity_id in instances:
            total_count += self._add_level_entity_row_by_id(level_entity_id)
            instances = [rid for rid in instances if rid != level_entity_id]
        else:
            self._add_simple_section("关卡实体", "(未设置)", item_count=0)

        total_count += self._add_lazy_resource_section_root("元件", ResourceType.TEMPLATE, templates)
        total_count += self._add_lazy_resource_section_root("实体摆放", ResourceType.INSTANCE, instances)
        total_count += self._add_lazy_resource_section_root("节点图", ResourceType.GRAPH, graphs)

        total_count += self._add_lazy_nested_combat_section_root(
            "战斗预设",
            {
                sub_key: (
                    self._get_preview_resource_ids(
                        root_key=root_key,
                        root_dir=root_dir,
                        resource_type=resource_type,
                    ),
                    resource_type,
                )
                for sub_key, resource_type in self.COMBAT_RESOURCE_TYPES.items()
            },
        )

        total_count += self._add_lazy_nested_management_section_root(
            "管理配置",
            self._build_preview_management_category_map(
                package_root_dir=root_dir,
                shared_root_dir=self._get_preview_root_dir("global_view"),
                package_root_key=root_key,
                include_shared=True,
                ui_plugin_enabled=self._is_ui_plugin_enabled(),
            ),
        )

        self.header_label.setText(f"{title}（共 {total_count} 项）")

    def _add_lazy_resource_section_root(
        self,
        section_title: str,
        resource_type: ResourceType,
        resource_ids: Sequence[str],
    ) -> int:
        """添加一个“资源分类根节点”，并在展开/默认展开时按需加载叶子条目。"""
        ordered_ids = list(resource_ids)
        item_count = len(ordered_ids)

        root_title = section_title if item_count <= 0 else f"{section_title} ({item_count})"
        root_item = QtWidgets.QTreeWidgetItem([root_title, "", "", ""])

        if item_count > 0:
            root_item.setChildIndicatorPolicy(
                QtWidgets.QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
            )
            root_item.setData(
                0,
                self._ROLE_LAZY_PAYLOAD,
                {
                    "kind": self._LAZY_KIND_RESOURCE_SECTION,
                    "section_title": section_title,
                    "resource_type": resource_type,
                    "ids": ordered_ids,
                    "next_index": 0,
                },
            )

        self.detail_tree.addTopLevelItem(root_item)
        return item_count

    def _add_lazy_nested_combat_section_root(
        self,
        root_title: str,
        category_resources_map: Mapping[str, tuple[Sequence[str], Optional[ResourceType]]],
    ) -> int:
        """添加“战斗预设”根节点，子分类在展开/默认展开时按需加载条目。"""
        root_item = QtWidgets.QTreeWidgetItem([root_title, "", "", ""])

        total_count = 0
        for resource_key in sorted(category_resources_map.keys()):
            resource_ids, resource_type = category_resources_map[resource_key]
            ordered_ids = list(resource_ids)
            if not ordered_ids:
                continue
            total_count += len(ordered_ids)

            category_label = self.COMBAT_CATEGORY_TITLES.get(resource_key, resource_key)
            category_display_title = f"{category_label} ({len(ordered_ids)})"
            category_item = QtWidgets.QTreeWidgetItem([category_display_title, "", "", ""])
            category_item.setChildIndicatorPolicy(
                QtWidgets.QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
            )

            combat_kind: Optional[str]
            if resource_key == "player_templates":
                combat_kind = "combat_player_template"
            elif resource_key == "player_classes":
                combat_kind = "combat_player_class"
            elif resource_key == "skills":
                combat_kind = "combat_skill"
            elif resource_key == "items":
                combat_kind = "combat_item"
            else:
                combat_kind = None

            category_item.setData(
                0,
                self._ROLE_LAZY_PAYLOAD,
                {
                    "kind": self._LAZY_KIND_COMBAT_CATEGORY,
                    "category_label": category_label,
                    "combat_kind": combat_kind,
                    "resource_type": resource_type,
                    "ids": ordered_ids,
                    "next_index": 0,
                },
            )
            root_item.addChild(category_item)

        if total_count > 0:
            root_item.setText(0, f"{root_title} ({total_count})")
        self.detail_tree.addTopLevelItem(root_item)
        return total_count

    def _add_lazy_nested_management_section_root(
        self,
        root_title: str,
        category_resources_map: Mapping[str, tuple[Sequence[str], Optional[ResourceType]]],
    ) -> int:
        """添加“管理配置”根节点，子分类在展开时按需加载条目。"""
        root_item = QtWidgets.QTreeWidgetItem([root_title, "", "", ""])

        total_count = 0
        for resource_key in MANAGEMENT_RESOURCE_ORDER:
            resource_ids, resource_type = category_resources_map.get(resource_key, ([], None))
            ordered_ids = list(resource_ids)
            if not ordered_ids:
                continue
            # 结构体定义：按 payload 类型拆成“基础/局内存档”两个分类（与管理页一致）。
            if resource_key == "struct_definitions":
                basic_ids: list[str] = []
                ingame_ids: list[str] = []
                if isinstance(resource_type, ResourceType):
                    for struct_id in ordered_ids:
                        payload = self.rm.load_resource(resource_type, struct_id) or {}
                        if not isinstance(payload, dict):
                            continue
                        struct_type_value = payload.get("struct_ype") or payload.get("struct_type")
                        struct_type = (
                            str(struct_type_value).strip()
                            if isinstance(struct_type_value, str)
                            else ""
                        )
                        if struct_type == "ingame_save":
                            ingame_ids.append(struct_id)
                        else:
                            basic_ids.append(struct_id)
                else:
                    basic_ids = list(ordered_ids)

                def _append_struct_category(*, label: str, ids: list[str], jump_section_key: str) -> None:
                    nonlocal total_count
                    if not ids:
                        return
                    total_count += len(ids)
                    category_display_title = f"{label} ({len(ids)})"
                    category_item = QtWidgets.QTreeWidgetItem([category_display_title, "", "", ""])
                    category_item.setData(
                        0,
                        QtCore.Qt.ItemDataRole.UserRole + 1,
                        self._build_management_item_marker(
                            binding_key="struct_definitions",
                            item_id="",
                            jump_section_key=jump_section_key,
                        ),
                    )
                    category_item.setChildIndicatorPolicy(
                        QtWidgets.QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
                    )
                    category_item.setData(
                        0,
                        self._ROLE_LAZY_PAYLOAD,
                        {
                            "kind": self._LAZY_KIND_MANAGEMENT_CATEGORY,
                            "resource_key": "struct_definitions",
                            "category_label": label,
                            "resource_type": resource_type,
                            "ids": ids,
                            "next_index": 0,
                            "jump_section_key": jump_section_key,
                        },
                    )
                    root_item.addChild(category_item)

                _append_struct_category(label="🧬 基础结构体定义", ids=basic_ids, jump_section_key="struct_definitions")
                _append_struct_category(label="💾 局内存档结构体定义", ids=ingame_ids, jump_section_key="ingame_struct_definitions")
                continue

            total_count += len(ordered_ids)

            category_label = self._resolve_management_category_label(resource_key)
            category_display_title = f"{category_label} ({len(ordered_ids)})"
            category_item = QtWidgets.QTreeWidgetItem([category_display_title, "", "", ""])

            jump_section_key = self._resolve_management_jump_section_key(resource_key)
            category_item.setData(
                0,
                QtCore.Qt.ItemDataRole.UserRole + 1,
                self._build_management_item_marker(
                    binding_key=resource_key,
                    item_id="",
                    jump_section_key=jump_section_key,
                ),
            )
            category_item.setChildIndicatorPolicy(
                QtWidgets.QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
            )
            category_item.setData(
                0,
                self._ROLE_LAZY_PAYLOAD,
                {
                    "kind": self._LAZY_KIND_MANAGEMENT_CATEGORY,
                    "resource_key": resource_key,
                    "category_label": category_label,
                    "resource_type": resource_type,
                    "ids": ordered_ids,
                    "next_index": 0,
                    "jump_section_key": jump_section_key,
                },
            )
            root_item.addChild(category_item)

        if total_count > 0:
            root_item.setText(0, f"{root_title} ({total_count})")
        self.detail_tree.addTopLevelItem(root_item)
        return total_count

    def _on_detail_tree_item_expanded(self, item: QtWidgets.QTreeWidgetItem) -> None:
        """展开分类节点时加载预览条目（前 N 条），并提供“加载更多”入口。"""
        if item is None:
            return
        self._ensure_preview_children_for_item(item)

    def _ensure_preview_children_for_item(self, item: QtWidgets.QTreeWidgetItem) -> None:
        """确保该分类节点至少加载了预览条目（前 N 条）。"""
        self._ensure_lazy_children_loaded(item, ensure_total=self._PREVIEW_CHILD_LIMIT)

    def _load_more_children_for_item(self, item: QtWidgets.QTreeWidgetItem) -> None:
        """追加加载更多条目。"""
        self._ensure_lazy_children_loaded(item, add_count=self._LOAD_MORE_CHUNK_SIZE)

    def _ensure_lazy_children_loaded(
        self,
        item: QtWidgets.QTreeWidgetItem,
        *,
        ensure_total: int | None = None,
        add_count: int | None = None,
    ) -> None:
        payload = item.data(0, self._ROLE_LAZY_PAYLOAD)
        if not isinstance(payload, dict):
            return

        ids = payload.get("ids")
        if not isinstance(ids, list) or not ids:
            return

        raw_next = payload.get("next_index", 0)
        next_index = raw_next if isinstance(raw_next, int) and raw_next >= 0 else 0
        total = len(ids)

        if ensure_total is not None:
            ensure_value = ensure_total if isinstance(ensure_total, int) else 0
            if ensure_value < 0:
                ensure_value = 0
            target_index = min(total, max(next_index, ensure_value))
        else:
            delta = add_count if isinstance(add_count, int) and add_count > 0 else self._LOAD_MORE_CHUNK_SIZE
            target_index = min(total, next_index + delta)

        if target_index <= next_index:
            self._sync_load_more_item(item, remaining=total - next_index)
            return

        # 先移除旧的“加载更多”占位，再追加新条目。
        self._remove_trailing_load_more_item(item)

        for idx in range(next_index, target_index):
            resource_id = ids[idx]
            if not isinstance(resource_id, str) or not resource_id:
                continue
            leaf_item = self._build_leaf_item_from_lazy_payload(payload, resource_id)
            item.addChild(leaf_item)

        payload["next_index"] = target_index
        item.setData(0, self._ROLE_LAZY_PAYLOAD, payload)

        self._sync_load_more_item(item, remaining=total - target_index)

    def _sync_load_more_item(self, item: QtWidgets.QTreeWidgetItem, *, remaining: int) -> None:
        """确保末尾的“加载更多”占位与 remaining 一致。"""
        self._remove_trailing_load_more_item(item)
        if isinstance(remaining, int) and remaining > 0:
            item.addChild(self._build_load_more_item(remaining))

    def _remove_trailing_load_more_item(self, item: QtWidgets.QTreeWidgetItem) -> None:
        if item.childCount() <= 0:
            return
        last = item.child(item.childCount() - 1)
        if last is None:
            return
        action = last.data(0, self._ROLE_TREE_ACTION)
        if isinstance(action, str) and action == self._ACTION_LOAD_MORE:
            item.takeChild(item.childCount() - 1)

    def _build_load_more_item(self, remaining: int) -> QtWidgets.QTreeWidgetItem:
        text = f"… 加载更多（剩余 {remaining} 项）"
        load_item = QtWidgets.QTreeWidgetItem(["", text, "", ""])
        load_item.setData(0, self._ROLE_TREE_ACTION, self._ACTION_LOAD_MORE)
        load_item.setToolTip(1, "双击此行加载更多条目")
        return load_item

    def _build_leaf_item_from_lazy_payload(
        self,
        payload: dict,
        resource_id: str,
    ) -> QtWidgets.QTreeWidgetItem:
        """根据懒加载 payload 构建单条叶子节点。"""
        kind = payload.get("kind", "")

        # 资源分类（元件/实体摆放/节点图）
        if kind == self._LAZY_KIND_RESOURCE_SECTION:
            section_title = payload.get("section_title", "")
            section_text = section_title if isinstance(section_title, str) else ""

            resource_type = payload.get("resource_type", None)
            display_name = resource_id
            guid_text = ""
            graphs_text = ""
            if isinstance(resource_type, ResourceType):
                if resource_type == ResourceType.GRAPH:
                    display_name = self._resolve_graph_display_name(resource_id)
                else:
                    display_name = self._display_name(resource_type, resource_id)
                    guid_text, graphs_text = self._get_resource_extra_info(resource_type, resource_id)

            child_item = QtWidgets.QTreeWidgetItem(
                [section_text, str(display_name or resource_id), guid_text, graphs_text]
            )
            child_item.setToolTip(1, resource_id)
            self._set_item_resource_kind(child_item, section_text, resource_id)
            return child_item

        # 战斗预设分类（玩家模板/职业/技能/道具...）
        if kind == self._LAZY_KIND_COMBAT_CATEGORY:
            category_label = payload.get("category_label", "")
            category_text = category_label if isinstance(category_label, str) else ""
            combat_kind = payload.get("combat_kind", None)

            resource_type = payload.get("resource_type", None)
            display_name = resource_id
            guid_text = ""
            graphs_text = ""
            if isinstance(resource_type, ResourceType):
                display_name = self._display_name(resource_type, resource_id)
                guid_text, graphs_text = self._get_resource_extra_info(resource_type, resource_id)

            entry_item = QtWidgets.QTreeWidgetItem(
                [category_text, str(display_name or resource_id), guid_text, graphs_text]
            )
            entry_item.setToolTip(1, resource_id)
            if isinstance(combat_kind, str) and combat_kind:
                entry_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, (combat_kind, resource_id))
            return entry_item

        # 管理配置分类
        if kind == self._LAZY_KIND_MANAGEMENT_CATEGORY:
            resource_key = payload.get("resource_key", "")
            resource_key_text = resource_key if isinstance(resource_key, str) else ""
            category_label = payload.get("category_label", "")
            category_text = category_label if isinstance(category_label, str) else ""

            resource_type = payload.get("resource_type", None)
            display_name = resource_id
            guid_text = ""
            graphs_text = ""
            if isinstance(resource_type, ResourceType):
                display_name = self._display_name(resource_type, resource_id)
                if resource_type != ResourceType.GRAPH:
                    guid_text, graphs_text = self._get_resource_extra_info(resource_type, resource_id)

            entry_item = QtWidgets.QTreeWidgetItem(
                [category_text, str(display_name or resource_id), guid_text, graphs_text]
            )
            entry_item.setToolTip(1, resource_id)
            if resource_key_text:
                jump_section_key = payload.get("jump_section_key", "")
                jump_section_key_text = (
                    jump_section_key if isinstance(jump_section_key, str) else ""
                )
                if not jump_section_key_text:
                    jump_section_key_text = self._resolve_management_jump_section_key(resource_key_text)
                entry_item.setData(
                    0,
                    QtCore.Qt.ItemDataRole.UserRole + 1,
                    self._build_management_item_marker(
                        binding_key=resource_key_text,
                        item_id=resource_id,
                        jump_section_key=jump_section_key_text,
                    ),
                )
            return entry_item

        # 兜底：不应发生
        return QtWidgets.QTreeWidgetItem(["", resource_id, "", ""])

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
            self._build_management_item_marker(
                binding_key=resource_key,
                item_id="",
                jump_section_key=self._resolve_management_jump_section_key(resource_key),
            ),
        )

        for signal_id, signal_name in entries:
            entry_item = QtWidgets.QTreeWidgetItem([category_label, signal_name, "", ""])
            entry_item.setToolTip(1, signal_id)
            entry_item.setData(
                0,
                QtCore.Qt.ItemDataRole.UserRole + 1,
                self._build_management_item_marker(
                    binding_key=resource_key,
                    item_id=signal_id,
                    jump_section_key=self._resolve_management_jump_section_key(resource_key),
                ),
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

    def _add_level_entity_row_by_id(self, level_entity_id: str) -> int:
        if not isinstance(level_entity_id, str) or not level_entity_id:
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

    def _list_resources_cached(self, resource_type: ResourceType) -> list[str]:
        cached = self._resource_cache.get(resource_type)
        if cached is not None:
            return cached
        values = sorted(self.rm.list_resources(resource_type))
        self._resource_cache[resource_type] = values
        return values


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
            "重命名项目存档",
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

    def _on_clone(self) -> None:
        """复制当前选中的项目存档为新的项目存档目录。"""
        if not self._current_package_id or self._is_special_id(self._current_package_id):
            return
        pkg_id = self._current_package_id
        current_item = self.package_list.currentItem()
        if not current_item:
            return
        current_name = current_item.text()
        default_name = f"{current_name}_副本" if current_name else f"{pkg_id}_副本"

        new_name = input_dialogs.prompt_text(
            self,
            "复制项目存档",
            "请输入新项目存档名称:",
            text=default_name,
        )
        if not new_name:
            return

        # 复制前尽量保存当前包（确保复制到的目录状态完整）
        window = self.window()
        package_controller = getattr(window, "package_controller", None) if window is not None else None
        if package_controller is not None:
            current_package_id = getattr(package_controller, "current_package_id", None)
            if current_package_id == pkg_id:
                save_now = getattr(package_controller, "save_now", None)
                if callable(save_now):
                    save_now()

        new_package_id = self.pim.clone_package(pkg_id, new_name)
        self.packages_changed.emit()
        self.refresh()

        # 复制完成后默认切换到新项目存档，方便继续编辑（交给主窗口的切包保护入口处理）
        self.package_load_requested.emit(str(new_package_id))

    def _on_delete(self) -> None:
        if not self._current_package_id or self._is_special_id(self._current_package_id):
            return
        pkg_id = self._current_package_id
        if not self.confirm(
            "删除项目存档",
            "仅删除项目存档本身，不会删除包内引用的资源。\n确定要删除吗？",
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


