"""管理配置库页面 - 列表式管理界面。

设计目标：
- 与元件库 / 实体摆放 / 战斗预设等页面保持一致的“左分类 + 右列表 + 顶部工具栏+搜索”范式；
- 将计时器 / 关卡变量 / 预设点等典型管理配置以文件列表形式集中呈现；
- 为主窗口提供 `data_changed` / `active_section_changed` / `ui_control_group_manager`
  等接口，兼容现有的持久化与右侧“界面控件设置”标签联动逻辑。
"""

from __future__ import annotations

from typing import Dict, Optional, Union, Tuple

from PyQt6 import QtCore, QtWidgets

from engine.resources.global_resource_view import GlobalResourceView
from engine.resources.package_view import PackageView
from app.ui.foundation.theme_manager import Sizes
from app.ui.foundation.toast_notification import ToastNotification
from app.ui.graph.library_mixins import (
    ConfirmDialogMixin,
    SearchFilterMixin,
    ToolbarMixin,
    rebuild_list_with_preserved_selection,
)
from app.ui.graph.library_pages.library_scaffold import (
    DualPaneLibraryScaffold,
    LibraryChangeEvent,
    LibraryPageMixin,
    LibrarySelection,
)
from app.ui.graph.library_pages.management_sections import (
    BaseManagementSection,
    ManagementRowData,
    MANAGEMENT_SECTION_MAP,
)
from app.ui.management.section_registry import (
    MANAGEMENT_SECTIONS,
    ManagementSectionSpec,
)
from app.ui.panels.ui_control_group_manager import UIControlGroupManager
from app.ui.panels.panel_scaffold import SectionCard


ManagementPackage = Union[PackageView, GlobalResourceView]


class ManagementLibraryWidget(
    DualPaneLibraryScaffold,
    LibraryPageMixin,
    SearchFilterMixin,
    ToolbarMixin,
    ConfirmDialogMixin,
):
    """管理配置库主界面。"""

    # 任意条目完成一次“真实数据修改”（增删改）后发射，用于上层触发立即持久化。
    data_changed = QtCore.pyqtSignal(LibraryChangeEvent)
    # 左侧分类当前选中的 section key 变化时发射（例如 "timer" / "variable" / "preset_point"）。
    active_section_changed = QtCore.pyqtSignal(str)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(
            parent,
            title="管理配置",
            description="按模块浏览与管理关卡计时器、变量、预设点等配置，保持与战斗预设页面一致的列表体验。",
        )
        self.current_package: Optional[ManagementPackage] = None
        # section_key → Section 实例（仅包含已迁移到列表式管理的类型）
        self._sections: Dict[str, BaseManagementSection] = dict(MANAGEMENT_SECTION_MAP)

        # 来自 section_registry 的集中配置
        self._section_specs: list[ManagementSectionSpec] = list(MANAGEMENT_SECTIONS)
        self._spec_by_key: Dict[str, ManagementSectionSpec] = {
            spec.key: spec for spec in self._section_specs
        }
        # 左侧树节点缓存（每个管理类型一个一级节点，不再按“系统服务/关卡配置”等父分组）。
        self._tree_items: Dict[str, QtWidgets.QTreeWidgetItem] = {}

        self._current_section_key: Optional[str] = None

        self.search_edit: Optional[QtWidgets.QLineEdit] = None
        self.add_button: Optional[QtWidgets.QPushButton] = None
        self.delete_button: Optional[QtWidgets.QPushButton] = None
        self.edit_button: Optional[QtWidgets.QPushButton] = None
        self.category_tree: Optional[QtWidgets.QTreeWidget] = None
        self.item_list: Optional[QtWidgets.QListWidget] = None
        self.right_stack: Optional[QtWidgets.QStackedWidget] = None
        self.list_container: Optional[QtWidgets.QWidget] = None
        self._right_section_card: Optional[SectionCard] = None

        # 供主窗口右侧“界面控件设置”面板绑定的管理器实例。
        self.ui_control_group_manager: UIControlGroupManager = UIControlGroupManager(self)

        self._setup_ui()

    # ------------------------------------------------------------------ 对外接口

    # === LibraryPage 协议实现 ===

    def set_context(self, package: ManagementPackage) -> None:
        """设置当前存档或全局资源视图（统一库页入口）。"""
        self.current_package = package
        # 界面控件组管理器同样绑定当前视图，供右侧设置面板使用。
        if isinstance(self.ui_control_group_manager, UIControlGroupManager):
            self.ui_control_group_manager.set_package(package)
        self._refresh_items()

    def set_package(self, package: ManagementPackage) -> None:
        """兼容旧接口，内部委托给 set_context。"""
        self.set_context(package)

    def reload(self) -> None:
        """在当前上下文下全量刷新管理配置列表并负责选中恢复。"""
        self._refresh_items()

    def get_current_section_key(self) -> Optional[str]:
        """返回当前选中的 section key。"""
        return self._current_section_key

    def get_selection(self) -> Optional[LibrarySelection]:
        """返回当前列表中选中的管理条目（若存在）。"""
        if self.item_list is None:
            return None
        current_item = self.item_list.currentItem()
        user_data = self._get_item_user_data(current_item)
        if user_data is None:
            return None
        section_key, item_id = user_data
        return LibrarySelection(
            kind="management",
            id=item_id,
            context={"section_key": section_key, "scope": self._describe_current_scope()},
        )

    def set_selection(self, selection: Optional[LibrarySelection]) -> None:
        """根据 LibrarySelection 恢复管理条目选中状态。"""
        if self.item_list is None:
            return
        if selection is None:
            self.item_list.setCurrentItem(None)
            return
        if selection.kind != "management":
            return
        if not isinstance(selection.context, dict):
            return
        section_key_any = selection.context.get("section_key")
        if not isinstance(section_key_any, str) or not section_key_any:
            return
        target_section_key = section_key_any
        target_item_id = selection.id
        if not target_item_id:
            return

        # 仅在当前 section 与目标 section 一致时尝试恢复列表选中；
        # 若不一致，由调用方负责先切换 section 再调用 set_selection。
        if self._current_section_key != target_section_key:
            return

        for row_index in range(self.item_list.count()):
            list_item = self.item_list.item(row_index)
            user_data = self._get_item_user_data(list_item)
            if user_data == (target_section_key, target_item_id):
                self.item_list.setCurrentItem(list_item)
                break

    def get_current_selection(self) -> Optional[Tuple[str, str]]:
        """返回当前列表中选中的 (section_key, item_id)（兼容旧接口）。"""
        selection = self.get_selection()
        if selection is None:
            return None
        if not isinstance(selection.context, dict):
            return None
        section_key_any = selection.context.get("section_key")
        if not isinstance(section_key_any, str) or not section_key_any:
            return None
        return section_key_any, selection.id

    def focus_section_and_item(self, section_key: str, item_id: str) -> None:
        """根据 section_key 与 item_id 在管理库中选中对应条目。

        - section_key: 管理页面的内部 key（例如 "equipment_data" / "save_points" / "signals"）。
        - item_id    : 记录 ID；为空字符串时仅切换到对应 section，不强制选中具体记录。
        """
        if not section_key:
            return
        if self.category_tree is None or self.item_list is None:
            return

        tree_item = self._tree_items.get(section_key)
        if tree_item is None:
            return

        # 切换左侧分类，会触发右侧列表刷新与 active_section_changed。
        self.category_tree.setCurrentItem(tree_item)
        self._on_category_clicked(tree_item, 0)

        if not item_id:
            return

        for row_index in range(self.item_list.count()):
            list_item = self.item_list.item(row_index)
            user_data = self._get_item_user_data(list_item)
            if user_data == (section_key, item_id):
                self.item_list.setCurrentItem(list_item)
                break

    # ------------------------------------------------------------------ UI 装配

    def _setup_ui(self) -> None:
        """构建管理配置库页面的 UI 结构。"""
        self._build_toolbar_and_search()
        self._build_left_and_right_panes()
        self._init_category_tree()

    def _build_toolbar_and_search(self) -> None:
        """顶部：工具栏 + 搜索（按钮在左，搜索在右）。"""
        search_edit = QtWidgets.QLineEdit(self)
        search_edit.setPlaceholderText("搜索管理配置...")
        search_edit.setMinimumHeight(Sizes.INPUT_HEIGHT)
        self.search_edit = search_edit
        self.add_action_widget(search_edit)

        toolbar_container = QtWidgets.QWidget(self)
        toolbar_layout = QtWidgets.QHBoxLayout(toolbar_container)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        self.init_toolbar(toolbar_layout)

        self.add_button = QtWidgets.QPushButton("+ 新建", toolbar_container)
        self.delete_button = QtWidgets.QPushButton("删除", toolbar_container)
        for button in (self.add_button, self.delete_button):
            button.setMinimumHeight(Sizes.BUTTON_HEIGHT)

        buttons: list[QtWidgets.QAbstractButton] = [
            self.add_button,
            self.delete_button,
        ]

        self.setup_toolbar_with_search(toolbar_layout, buttons, search_edit)
        self.set_status_widget(toolbar_container)

        self.add_button.clicked.connect(self._on_add_item_clicked)
        self.delete_button.clicked.connect(self._on_delete_item_clicked)

        self.connect_search(search_edit, self._filter_items, placeholder="搜索管理配置...")

    def _build_left_and_right_panes(self) -> None:
        """主体：左侧分类树 + 右侧内容堆栈。"""
        category_tree = QtWidgets.QTreeWidget()
        category_tree.setHeaderLabel("管理分类")
        category_tree.setObjectName("leftPanel")
        # 不再固定宽度，让分类树在 SectionCard 内水平方向自适应，避免比卡片窄一截。
        # 仍保留一个合理的最小宽度，防止分割条被拖得过窄导致列名完全不可见。
        category_tree.setMinimumWidth(Sizes.LEFT_PANEL_WIDTH)
        self.category_tree = category_tree

        item_list = QtWidgets.QListWidget()
        item_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        item_list.setObjectName("managementItemList")
        self.item_list = item_list

        list_container = QtWidgets.QWidget()
        list_layout = QtWidgets.QVBoxLayout(list_container)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.addWidget(item_list)
        self.list_container = list_container

        right_stack = QtWidgets.QStackedWidget()
        right_stack.addWidget(list_container)
        right_stack.addWidget(self.ui_control_group_manager)
        self.right_stack = right_stack

        left_section_card, right_section_card = self.build_dual_pane(
            category_tree,
            right_stack,
            left_title="管理分类",
            left_description="按模块查看计时器、变量、预设点等管理配置",
            right_title="配置列表",
            right_description="在右侧按名称浏览与搜索当前模块下的配置条目",
        )
        self._right_section_card = right_section_card

        category_tree.itemClicked.connect(self._on_category_clicked)
        item_list.itemSelectionChanged.connect(self._on_item_selection_changed)
        # 选中变化用于处理刷新与程序化更新；点击事件保证“当前已选中条目首次点击”同样能驱动右侧管理属性面板。
        item_list.itemClicked.connect(self._on_item_clicked)

    def _init_category_tree(self) -> None:
        """根据 ManagementSectionSpec 构建左侧分类树（扁平结构）。

        设计约定：
        - 不再在 UI 中展示“系统服务/界面与模板/关卡配置”等父分组，
          每个管理类型（信号管理、结构体定义、外围系统管理、计时器管理等）
          直接作为一级节点出现，更贴近“文件夹 + 文件列表”的心智模型；
        - ManagementSectionSpec.group/group_title 仍保留在配置中，供其它视图
          （例如存档库）按需分组使用，但管理配置库页面自身忽略这层分组。
        """
        if self.category_tree is None:
            return

        self.category_tree.clear()
        self._tree_items.clear()

        for spec in self._section_specs:
            tree_item = QtWidgets.QTreeWidgetItem(self.category_tree)
            tree_item.setText(0, spec.title)
            tree_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, spec.key)
            self._tree_items[spec.key] = tree_item

        self.category_tree.expandAll()

        # 默认选中第一个已实现的 Section 或 UI 控件组
        initial_key: Optional[str] = None
        for spec in self._section_specs:
            key = spec.key
            if key in MANAGEMENT_SECTION_MAP or key == "ui_control_groups":
                initial_key = key
                break

        if initial_key is None:
            return
        initial_item = self._tree_items.get(initial_key)
        if initial_item is not None:
            self.category_tree.setCurrentItem(initial_item)
            self._on_category_clicked(initial_item, 0)

    # ------------------------------------------------------------------ 分类与列表刷新

    def _on_category_clicked(self, item: QtWidgets.QTreeWidgetItem, column: int) -> None:
        """左侧分类点击时切换当前 Section 与右侧展示模式。"""
        _ = column
        section_key_value = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not section_key_value:
            return
        section_key = str(section_key_value)
        self._current_section_key = section_key
        self._update_right_section_header(section_key)

        self._switch_right_panel_for_section(section_key)
        self._refresh_items()
        self.active_section_changed.emit(section_key)

    def _update_right_section_header(self, section_key: str) -> None:
        """根据当前管理类型更新右侧卡片标题。"""
        if self._right_section_card is None:
            return
        spec = self._spec_by_key.get(section_key)
        if spec is None:
            self._right_section_card.set_title("配置列表")
            return
        self._right_section_card.set_title(spec.title)

    def _switch_right_panel_for_section(self, section_key: str) -> None:
        """根据当前 section 切换右侧堆栈页面及工具栏可用状态。"""
        if self.right_stack is None or self.list_container is None:
            return

        if section_key == "ui_control_groups":
            target_index = self.right_stack.indexOf(self.ui_control_group_manager)
            if target_index != -1:
                self.right_stack.setCurrentIndex(target_index)
            self._set_toolbar_enabled(False)
            return

        list_index = self.right_stack.indexOf(self.list_container)
        if list_index != -1:
            self.right_stack.setCurrentIndex(list_index)
        has_section = section_key in self._sections
        self._set_toolbar_enabled(has_section)

    def _set_toolbar_enabled(self, enabled: bool) -> None:
        """根据当前上下文启用/禁用“新建/删除/编辑”按钮。"""
        if self.add_button is not None:
            self.add_button.setEnabled(enabled)
        if self.delete_button is not None:
            self.delete_button.setEnabled(enabled)
        if self.edit_button is not None:
            self.edit_button.setEnabled(enabled)

    def _refresh_items(self, preferred_key: Optional[Tuple[str, str]] = None) -> None:
        """根据当前 section 重新构建右侧列表内容。

        行为约定：
        - 若刷新前存在选中条目且该条目仍在当前 section 的结果集中，则恢复该选中；
        - 若刷新后当前列表为空且刷新前存在选中条目，则显式通知主窗口“当前无任何可选记录”，
          由主窗口负责收起右侧管理属性面板与相关编辑页；
        - 若刷新前不存在选中条目但刷新后列表非空，则默认选中第一条记录，
          让右侧属性面板自然切换到新的上下文。
        """
        if self.item_list is None:
            return

        current_item_before_refresh = self.item_list.currentItem()
        had_selection_before_refresh = current_item_before_refresh is not None

        if not self.current_package or not self._current_section_key:
            self.item_list.clear()
            if had_selection_before_refresh:
                self._emit_selection_to_main_window_from_row_data(None, None)
            return

        section = self._sections.get(self._current_section_key)
        if section is None:
            # 该管理类型尚未接入 Section 实现，列表保持为空，仅通过上层属性面板或其它入口查看。
            self.item_list.clear()
            if had_selection_before_refresh:
                self._emit_selection_to_main_window_from_row_data(None, self._current_section_key)
            return
        previous_user_data: Optional[Tuple[str, str]] = (
            self._get_item_user_data(current_item_before_refresh)
            if current_item_before_refresh is not None
            else None
        )
        # 当调用方提供 preferred_key 时，优先尝试选中该业务键（例如新建后的记录）。
        target_previous_key: Optional[Tuple[str, str]] = (
            preferred_key if preferred_key is not None else previous_user_data
        )

        def build_items() -> None:
            if self.item_list is None or self.current_package is None:
                return
            for row_data in section.iter_rows(self.current_package):
                self._add_row_item(row_data)

        def get_item_key(list_item: QtWidgets.QListWidgetItem) -> Optional[Tuple[str, str]]:
            return self._get_item_user_data(list_item)

        def emit_empty_selection() -> None:
            if self._current_section_key is None:
                self._emit_selection_to_main_window_from_row_data(None, None)
            else:
                self._emit_selection_to_main_window_from_row_data(
                    None,
                    self._current_section_key,
                )

        effective_had_selection = bool(target_previous_key) or had_selection_before_refresh

        rebuild_list_with_preserved_selection(
            self.item_list,
            previous_key=target_previous_key,
            had_selection_before_refresh=effective_had_selection,
            build_items=build_items,
            key_getter=get_item_key,
            on_restored_selection=None,
            on_first_selection=None,
            on_cleared_selection=emit_empty_selection,
        )
        # 列表重建完成后，若当前仍有选中条目，则主动触发一次选中处理，
        # 确保右侧管理属性面板与专用编辑面板（例如结构体详情）能够基于最新数据刷新，
        # 即使刷新前后选中的业务键未变也会重新加载内容。
        if self.item_list is not None:
            current_item_after_refresh = self.item_list.currentItem()
            if current_item_after_refresh is not None:
                self._on_item_selection_changed()

    def _describe_current_scope(self) -> str:
        """根据当前资源视图返回简单 scope 标识，用于变更事件上下文。"""
        if isinstance(self.current_package, PackageView):
            return "package"
        if isinstance(self.current_package, GlobalResourceView):
            return "global"
        return "unknown"

    def _add_row_item(self, row_data: ManagementRowData) -> None:
        """向列表中添加一行管理配置条目。"""
        if self.item_list is None:
            return

        display_text = row_data.name or ""
        list_item = QtWidgets.QListWidgetItem(display_text)
        list_item.setData(QtCore.Qt.ItemDataRole.UserRole, row_data.user_data)
        # 额外缓存一份行数据，便于在选中变化时直接构造右侧属性摘要，
        # 避免再次遍历 Section.iter_rows。
        list_item.setData(QtCore.Qt.ItemDataRole.UserRole + 2, row_data)

        tooltip_lines = [
            f"名称: {row_data.name}",
            f"类型: {row_data.type_name}",
        ]
        if row_data.attr1:
            tooltip_lines.append(row_data.attr1)
        if row_data.attr2:
            tooltip_lines.append(row_data.attr2)
        if row_data.attr3:
            tooltip_lines.append(row_data.attr3)
        if row_data.description:
            tooltip_lines.append(f"描述: {row_data.description}")
        if row_data.last_modified:
            tooltip_lines.append(f"修改时间: {row_data.last_modified}")
        list_item.setToolTip("\n".join(tooltip_lines))

        search_tokens = [
            row_data.name,
            row_data.type_name,
            row_data.attr1,
            row_data.attr2,
            row_data.attr3,
            row_data.description,
            row_data.last_modified,
        ]
        search_value = " ".join(token for token in search_tokens if token)
        list_item.setData(QtCore.Qt.ItemDataRole.UserRole + 1, search_value.casefold())

        self.item_list.addItem(list_item)

    # ------------------------------------------------------------------ 工具栏与搜索

    def _filter_items(self, text: str) -> None:
        """根据聚合搜索字段过滤列表条目。"""
        if self.item_list is None:
            return

        def get_search_text(list_item: QtWidgets.QListWidgetItem) -> str:
            value = list_item.data(QtCore.Qt.ItemDataRole.UserRole + 1)
            return str(value) if value is not None else list_item.text()

        self.filter_list_items(self.item_list, text, text_getter=get_search_text)

    # ------------------------------------------------------------------ 列表交互与 CRUD

    def _get_item_user_data(
        self,
        list_item: Optional[QtWidgets.QListWidgetItem],
    ) -> Optional[Tuple[str, str]]:
        if list_item is None:
            return None
        user_data = list_item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(user_data, tuple) or len(user_data) != 2:
            return None
        section_key, item_id = user_data
        if not isinstance(section_key, str) or not isinstance(item_id, str):
            return None
        return section_key, item_id

    def _get_row_data_from_item(
        self,
        list_item: Optional[QtWidgets.QListWidgetItem],
    ) -> Optional[ManagementRowData]:
        """从列表项中恢复聚合行数据。

        优先读取在 _add_row_item 中缓存的 ManagementRowData，
        如不存在则根据 section_key + item_id 在当前 Section 中重新构造。
        """
        if list_item is None:
            return None

        cached_value = list_item.data(QtCore.Qt.ItemDataRole.UserRole + 2)
        if isinstance(cached_value, ManagementRowData):
            return cached_value

        user_data = self._get_item_user_data(list_item)
        if user_data is None:
            return None
        section_key, item_id = user_data

        section = self._sections.get(section_key)
        if section is None or not self.current_package:
            return None

        for row_data in section.iter_rows(self.current_package):
            if row_data.user_data == (section_key, item_id):
                return row_data
        return None

    @staticmethod
    def _split_label_and_value(raw_text: str) -> Tuple[str, str]:
        """将形如“字段: 值”的文本拆分为 (字段, 值)。"""
        stripped_text = raw_text.strip()
        if not stripped_text:
            return "", ""

        for separator in (":", "："):
            if separator in stripped_text:
                label_text, value_text = stripped_text.split(separator, 1)
                return label_text.strip(), value_text.strip()

        return "信息", stripped_text

    def _emit_selection_to_main_window_from_row_data(
        self,
        row_data: Optional[ManagementRowData],
        section_key: Optional[str],
    ) -> None:
        """将当前选中条目的概要信息上报给主窗口，用于驱动右侧管理属性面板。

        约定：
        - 当没有有效选中记录时，通知主窗口清空并收起“属性”标签；
        - 当存在选中记录时，根据行数据构造 (label, value) 对列表。
        """
        main_window = self.window()
        handler = getattr(main_window, "_on_management_selection_changed", None)
        if not callable(handler):
            return

        if row_data is None or section_key is None:
            self.notify_selection_state(False, context={"source": "management", "section_key": section_key})
            handler(False, "", "", [])
            return

        self.notify_selection_state(True, context={"source": "management", "section_key": section_key})
        spec = self._spec_by_key.get(section_key)
        panel_title = spec.title if spec is not None else "详情"
        panel_description = "在左侧选择一条记录查看详情，并在主界面右侧直接编辑。"

        detail_rows: list[Tuple[str, str]] = []
        if row_data.name:
            detail_rows.append(("名称", row_data.name))
        if row_data.type_name:
            detail_rows.append(("类型", row_data.type_name))

        for attribute_text in (row_data.attr1, row_data.attr2, row_data.attr3):
            if not attribute_text:
                continue
            label_text, value_text = self._split_label_and_value(attribute_text)
            if not value_text:
                continue
            if not label_text:
                label_text = "属性"
            detail_rows.append((label_text, value_text))

        if row_data.description:
            detail_rows.append(("描述", row_data.description))
        if row_data.last_modified:
            detail_rows.append(("最后修改时间", row_data.last_modified))

        handler(bool(detail_rows), panel_title, panel_description, detail_rows)

    def _resolve_active_section(self) -> Optional[BaseManagementSection]:
        if not self._current_section_key:
            return None
        return self._sections.get(self._current_section_key)

    def _on_item_selection_changed(self) -> None:
        """列表选中变化时的回调。

        当选中具体管理记录时，将聚合行信息上报给主窗口，驱动右侧
        `ManagementPropertyPanel` 以只读表单形式展示摘要；
        当无有效选中或仅为占位条目时，通知主窗口清空并收起对应标签。
        """
        if self.item_list is None:
            print("[MANAGEMENT-LIB] selection changed: <no-list-widget>")
            return

        current_item = self.item_list.currentItem()
        user_data = self._get_item_user_data(current_item)
        if user_data is None:
            print("[MANAGEMENT-LIB] selection changed: <none>")
            self._emit_selection_to_main_window_from_row_data(None, None)
            return

        section_key, item_id = user_data
        print(
            "[MANAGEMENT-LIB] selection changed:",
            f"section_key={section_key!r}, item_id={item_id!r}",
        )
        # 占位条目仅承担“打开旧管理页面”的导航职责，不在右侧展示摘要。
        if item_id == "__OPEN__":
            self._emit_selection_to_main_window_from_row_data(None, section_key)
            return

        row_data = self._get_row_data_from_item(current_item)
        self._emit_selection_to_main_window_from_row_data(row_data, section_key)

    def _on_item_clicked(self, _item: QtWidgets.QListWidgetItem) -> None:
        """列表项单击时，同步触发选中逻辑，保证默认选中条目在首次点击时也能驱动右侧面板。"""
        self._on_item_selection_changed()

    def _on_add_item_clicked(self) -> None:
        section = self._resolve_active_section()
        if section is None:
            # 非列表式 section（例如“界面控件组”等）暂不提供直接在库页面中新建，
            # 统一通过旧管理页处理。
            return
        if not self.current_package:
            self.show_warning("警告", "请先选择或创建存档")
            return

        # 记录新建前该 Section 下已有的业务键集合，用于在创建后识别新增记录，
        # 从而在刷新列表时优先选中新建的条目。
        previous_keys: set[Tuple[str, str]] = set()
        for row_data in section.iter_rows(self.current_package):
            previous_keys.add(row_data.user_data)

        if section.create_item(self, self.current_package):
            new_key: Optional[Tuple[str, str]] = None
            for row_data in section.iter_rows(self.current_package):
                if row_data.user_data not in previous_keys:
                    new_key = row_data.user_data
                    break

            self._refresh_items(preferred_key=new_key)

            if new_key is not None:
                new_section_key, new_item_id = new_key
                event = LibraryChangeEvent(
                    kind="management",
                    id=new_item_id,
                    operation="create",
                    context={
                        "section_key": new_section_key,
                        "scope": self._describe_current_scope(),
                    },
                )
                self.data_changed.emit(event)

    def _on_delete_item_clicked(self) -> None:
        section = self._resolve_active_section()
        if section is None:
            # 非列表式 section 在库页面中不直接支持删除。
            return
        if not self.current_package or self.item_list is None:
            return

        current_item = self.item_list.currentItem()
        user_data = self._get_item_user_data(current_item)
        if user_data is None:
            self.show_warning("警告", "请先选择要删除的记录")
            return
        section_key, item_id = user_data

        display_name = current_item.text() if current_item is not None else item_id
        if not self.confirm("确认删除", f"确定要删除 '{display_name}' 吗？"):
            return

        if section.delete_item(self.current_package, item_id):
            self._refresh_items()
            event = LibraryChangeEvent(
                kind="management",
                id=item_id,
                operation="delete",
                context={
                    "section_key": section_key,
                    "scope": self._describe_current_scope(),
                },
            )
            self.data_changed.emit(event)
            ToastNotification.show_message(self, f"已删除管理配置项 '{display_name}'。", "success")

    # ------------------------------------------------------------------ 旧页面桥接（已移除）



