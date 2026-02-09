"""战斗预设组件 - 文件列表形式"""

import copy

from PyQt6 import QtCore, QtWidgets, QtGui
from typing import Optional, Union, Tuple

from engine.resources.global_resource_view import GlobalResourceView
from engine.resources.package_view import PackageView
from engine.resources.package_index_manager import PackageIndexManager
from engine.resources.resource_manager import ResourceManager
from app.ui.foundation import input_dialogs
from app.ui.foundation.context_menu_builder import ContextMenuBuilder
from app.ui.foundation.id_generator import generate_prefixed_id
from app.ui.foundation.keymap_store import KeymapStore
from app.ui.foundation.theme_manager import Sizes
from app.ui.foundation.toast_notification import ToastNotification
from app.ui.graph.library_mixins import (
    ConfirmDialogMixin,
    SearchFilterMixin,
    ToolbarMixin,
    rebuild_list_with_preserved_selection,
)
from app.ui.graph.library_pages.combat_presets import (
    BaseCombatPresetSection,
    TableRowData,
    SECTION_SEQUENCE,
    SECTION_MAP,
    SECTION_SELECTION_LABELS,
    get_section_by_key,
    get_section_by_selection_label,
)
from app.ui.graph.library_pages.library_scaffold import (
    DualPaneLibraryScaffold,
    LibraryChangeEvent,
    LibraryPageMixin,
    LibrarySelection,
)
from app.ui.graph.library_pages.library_view_scope import describe_resource_view_scope
from engine.configs.resource_types import ResourceType
from engine.utils.logging.logger import log_debug


class CombatPresetsWidget(
    DualPaneLibraryScaffold,
    LibraryPageMixin,
    SearchFilterMixin,
    ToolbarMixin,
    ConfirmDialogMixin,
):
    """战斗预设界面 - 文件列表形式"""

    _SECTION_SPECS: dict[str, tuple[str, str, str, str, ResourceType]] = {
        # section_key: (bucket_key, id_field, name_field, id_prefix, resource_type)
        "player_template": ("player_templates", "template_id", "template_name", "player", ResourceType.PLAYER_TEMPLATE),
        "player_class": ("player_classes", "class_id", "class_name", "class", ResourceType.PLAYER_CLASS),
        "skill": ("skills", "skill_id", "skill_name", "skill", ResourceType.SKILL),
        "projectile": ("projectiles", "projectile_id", "projectile_name", "projectile", ResourceType.PROJECTILE),
        "unit_status": ("unit_statuses", "status_id", "status_name", "status", ResourceType.UNIT_STATUS),
        "item": ("items", "item_id", "item_name", "item", ResourceType.ITEM),
    }

    # 统一库页选中事件：发射 LibrarySelection（或 None 表示无有效选中）。
    selection_changed = QtCore.pyqtSignal(object)
    # 当任意战斗预设完成增删改操作时发射，用于上层触发保存或刷新其它视图
    data_changed = QtCore.pyqtSignal(LibraryChangeEvent)

    def __init__(self, parent=None):
        super().__init__(
            parent,
            title="战斗预设",
            description="浏览、筛选与管理战斗预设资源，支持分类定位与搜索。",
        )
        self._standard_shortcuts: list[QtGui.QShortcut] = []
        self.current_package: Optional[Union[PackageView, GlobalResourceView]] = None
        self.current_category: str = "all"
        # 复用 Section 中的玩家模板增删改逻辑
        self.player_template_section: Optional[BaseCombatPresetSection] = get_section_by_key(
            "player_template"
        )
        self._setup_ui()

    def _setup_ui(self) -> None:
        """设置 UI"""
        # 顶部：标题右侧放搜索框，作为战斗预设全局过滤入口
        self.search_edit = QtWidgets.QLineEdit(self)
        self.search_edit.setPlaceholderText("搜索战斗预设...")
        self.search_edit.setMinimumHeight(Sizes.INPUT_HEIGHT)
        self.add_action_widget(self.search_edit)

        # 标题下方：仅保留“新建/删除”等主操作按钮，编辑由右侧详情面板或其他入口负责
        toolbar_container = QtWidgets.QWidget()
        top_toolbar = QtWidgets.QHBoxLayout(toolbar_container)
        top_toolbar.setContentsMargins(0, 0, 0, 0)
        self.init_toolbar(top_toolbar)
        self.add_btn = QtWidgets.QPushButton("+ 新建", self)
        self.duplicate_btn = QtWidgets.QPushButton("复制", self)
        self.delete_btn = QtWidgets.QPushButton("删除", self)
        # 工具栏行只放操作按钮，搜索栏统一放在标题行右侧
        self.setup_toolbar_with_search(
            top_toolbar,
            [self.add_btn, self.duplicate_btn, self.delete_btn],
            None,
        )
        self.set_status_widget(toolbar_container)

        # 左侧：战斗预设分类树
        self.category_tree = QtWidgets.QTreeWidget()
        self.category_tree.setHeaderLabel("战斗预设分类")
        self.category_tree.setObjectName("leftPanel")
        # 不要锁死宽度：该页面使用 QSplitter，左侧分类树需要允许用户拖拽分隔线改变宽度。
        # 默认宽度仍以主题 token 为基准，初始分配由 splitter.setSizes(...) 负责。
        self.category_tree.setMinimumWidth(Sizes.LEFT_PANEL_WIDTH)

        # 右侧：统一使用列表视图浏览全部战斗预设类型（包括玩家模板）
        self.item_list = QtWidgets.QListWidget()
        self.item_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.item_list.setObjectName("combatPresetList")

        self.build_dual_pane(
            self.category_tree,
            self.item_list,
            left_title="战斗预设分类",
            left_description="按功能域查看预设模块",
            right_title="战斗预设列表",
            right_description="按分类与搜索浏览玩家模板与其他战斗预设类型",
        )
        # 左侧默认收窄，但允许用户拖到更宽
        self._splitter.setSizes([Sizes.LEFT_PANEL_WIDTH, 1000])

        self._init_category_tree()

        self.category_tree.itemClicked.connect(self._on_category_clicked)
        self.add_btn.clicked.connect(self._add_item)
        self.duplicate_btn.clicked.connect(self._duplicate_item)
        self.delete_btn.clicked.connect(self._delete_item)
        # 选中变化用于处理程序化刷新；点击事件用于保证“已选中条目首次点击”同样能驱动右侧面板。
        self.item_list.itemSelectionChanged.connect(self._on_item_selection_changed)
        self.item_list.itemClicked.connect(self._on_item_clicked)
        self.item_list.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.item_list.customContextMenuRequested.connect(self._show_item_context_menu)
        self.connect_search(self.search_edit, self._filter_items, placeholder="搜索战斗预设...")

        self._install_standard_shortcuts()

    def _install_standard_shortcuts(self) -> None:
        """统一快捷键（尽量与其它库页一致）。"""
        self._install_standard_shortcuts_impl()

    def apply_keymap_shortcuts(self, keymap_store: object) -> None:
        """由主窗口调用：在快捷键配置变更后刷新本页快捷键绑定。"""
        self._install_standard_shortcuts_impl(keymap_store=keymap_store)

    def _resolve_keymap_store(self) -> object | None:
        window_obj = self.window()
        app_state = getattr(window_obj, "app_state", None)
        return getattr(app_state, "keymap_store", None) if app_state is not None else None

    def _clear_standard_shortcuts(self) -> None:
        for shortcut in list(self._standard_shortcuts):
            shortcut.setEnabled(False)
            shortcut.deleteLater()
        self._standard_shortcuts.clear()

    def _primary_shortcut(self, action_id: str) -> str:
        keymap_store = self._resolve_keymap_store()
        get_primary = getattr(keymap_store, "get_primary_shortcut", None) if keymap_store is not None else None
        if callable(get_primary):
            return str(get_primary(action_id) or "")
        defaults = KeymapStore.get_default_shortcuts(action_id)
        return defaults[0] if defaults else ""

    def _install_standard_shortcuts_impl(self, *, keymap_store: object | None = None) -> None:
        resolved = keymap_store if keymap_store is not None else self._resolve_keymap_store()
        get_primary = getattr(resolved, "get_primary_shortcut", None) if resolved is not None else None

        def _primary(action_id: str) -> str:
            if callable(get_primary):
                return str(get_primary(action_id) or "")
            defaults = KeymapStore.get_default_shortcuts(action_id)
            return defaults[0] if defaults else ""

        self._clear_standard_shortcuts()

        shortcut_new = _primary("library.new")
        if shortcut_new:
            sc = QtGui.QShortcut(QtGui.QKeySequence(shortcut_new), self)
            sc.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(self._add_item)
            self._standard_shortcuts.append(sc)

        shortcut_dup = _primary("library.duplicate")
        if shortcut_dup:
            sc = QtGui.QShortcut(QtGui.QKeySequence(shortcut_dup), self.item_list)
            sc.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(self._duplicate_item)
            self._standard_shortcuts.append(sc)

        shortcut_delete = _primary("library.delete")
        if shortcut_delete:
            sc = QtGui.QShortcut(QtGui.QKeySequence(shortcut_delete), self.item_list)
            sc.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(self._delete_item)
            self._standard_shortcuts.append(sc)

        shortcut_rename = _primary("library.rename")
        if shortcut_rename:
            sc = QtGui.QShortcut(QtGui.QKeySequence(shortcut_rename), self.item_list)
            sc.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(self._rename_item)
            self._standard_shortcuts.append(sc)

        shortcut_move = _primary("library.move")
        if shortcut_move:
            sc = QtGui.QShortcut(QtGui.QKeySequence(shortcut_move), self.item_list)
            sc.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(self._change_selected_item_owner)
            self._standard_shortcuts.append(sc)

        shortcut_locate = _primary("library.locate_issues")
        if shortcut_locate:
            sc = QtGui.QShortcut(QtGui.QKeySequence(shortcut_locate), self.item_list)
            sc.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(self._locate_issues_for_selected_item)
            self._standard_shortcuts.append(sc)

    def _show_item_context_menu(self, pos: QtCore.QPoint) -> None:
        has_item = self.item_list.itemAt(pos) is not None
        shortcut_new = self._primary_shortcut("library.new") or None
        shortcut_dup = self._primary_shortcut("library.duplicate") or None
        shortcut_rename = self._primary_shortcut("library.rename") or None
        shortcut_move = self._primary_shortcut("library.move") or None
        shortcut_locate = self._primary_shortcut("library.locate_issues") or None
        shortcut_delete = self._primary_shortcut("library.delete") or None
        builder = ContextMenuBuilder(self)
        builder.add_action("新建", self._add_item, shortcut=shortcut_new)
        builder.add_separator()
        builder.add_action("复制", self._duplicate_item, enabled=has_item, shortcut=shortcut_dup)
        builder.add_action("重命名", self._rename_item, enabled=has_item, shortcut=shortcut_rename)
        builder.add_action(
            "移动（所属存档）", self._change_selected_item_owner, enabled=has_item, shortcut=shortcut_move
        )
        builder.add_separator()
        builder.add_action(
            "定位问题", self._locate_issues_for_selected_item, enabled=has_item, shortcut=shortcut_locate
        )
        builder.add_separator()
        builder.add_action("删除", self._delete_item, enabled=has_item, shortcut=shortcut_delete)
        builder.exec_for(self.item_list, pos)

    def _init_category_tree(self) -> None:
        """初始化分类树"""
        self.category_tree.clear()

        all_item = QtWidgets.QTreeWidgetItem(self.category_tree)
        all_item.setText(0, "📁 全部")
        all_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, "all")

        for section in SECTION_SEQUENCE:
            tree_item = QtWidgets.QTreeWidgetItem(self.category_tree)
            tree_item.setText(0, section.tree_label)
            tree_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, section.category_key)

        self.category_tree.setCurrentItem(all_item)

    # === LibraryPage 协议实现 ===

    def set_context(self, package: Union[PackageView, GlobalResourceView]) -> None:
        """设置当前存档或全局视图并刷新列表（统一库页入口）。"""
        self.current_package = package
        self._refresh_items()

    def ensure_default_selection(self) -> None:
        """在战斗预设模式下确保存在一个默认选中项，用于同步右侧详情。"""
        if self.item_list.currentRow() >= 0:
            return
        self._select_first_player_item()

    def reload(self) -> None:
        """在当前上下文下全量刷新战斗预设列表并负责选中恢复。"""
        self._refresh_items()

    def get_selection(self) -> Optional[LibrarySelection]:
        """返回当前列表中选中的战斗预设（若存在）。"""
        current_item = self.item_list.currentItem()
        user_data = self._get_item_user_data(current_item)
        if not user_data:
            return None
        section_key, item_id = user_data
        return LibrarySelection(
            kind="combat",
            id=item_id,
            context={
                "section_key": section_key,
                "scope": describe_resource_view_scope(self.current_package),
            },
        )

    def set_selection(self, selection: Optional[LibrarySelection]) -> None:
        """根据 LibrarySelection 恢复战斗预设选中状态。"""
        if selection is None:
            self.item_list.setCurrentItem(None)
            return
        if selection.kind != "combat":
            return
        if not isinstance(selection.context, dict):
            return
        section_key_any = selection.context.get("section_key")
        if not isinstance(section_key_any, str) or not section_key_any:
            return
        target_section_key = section_key_any
        target_id = selection.id
        if not target_id:
            return

        # 仅在当前分类包含目标 section 时进行恢复，避免无谓的分类切换
        for row_index in range(self.item_list.count()):
            item = self.item_list.item(row_index)
            user_data = self._get_item_user_data(item)
            if user_data is None:
                continue
            section_key, item_id = user_data
            if section_key == target_section_key and item_id == target_id:
                self.item_list.setCurrentItem(item)
                break

    def focus_section_and_item(self, section_key: str, item_id: str) -> None:
        """在战斗预设库中切换到指定分类并选中指定条目。

        用途：
        - 命令面板跳转
        - 引用列表/外部跳转
        """
        if not section_key:
            return
        if self.category_tree is None or self.item_list is None:
            return

        # 1) 切换左侧分类
        target_tree_item: Optional[QtWidgets.QTreeWidgetItem] = None
        iterator = QtWidgets.QTreeWidgetItemIterator(self.category_tree)
        while iterator.value() is not None:
            item = iterator.value()
            if item is None:
                iterator += 1
                continue
            key_any = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
            if str(key_any or "") == str(section_key or ""):
                target_tree_item = item
                break
            iterator += 1

        if target_tree_item is not None:
            self.category_tree.setCurrentItem(target_tree_item)
            self._on_category_clicked(target_tree_item, 0)

        # 2) 选中条目（使用 preferred_key 以避免依赖刷新前选中）
        if item_id:
            self._refresh_items(preferred_key=(str(section_key), str(item_id)))


    def _on_category_clicked(self, item: QtWidgets.QTreeWidgetItem, column: int) -> None:
        """分类点击"""
        category_key = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        self.current_category = category_key or "all"
        self._refresh_items()
        if self.current_category == "player_template" and self.item_list.currentRow() < 0:
            self._select_first_player_item()

    def _refresh_items(
        self,
        preferred_key: Optional[tuple[str, str]] = None,
    ) -> None:
        """刷新项目列表。

        preferred_key:
            - 当为 None 时，尽量恢复刷新前的选中条目；
            - 当不为 None 时，优先尝试选中给定的 (section_key, item_id)，
              例如在新建条目后直接聚焦到新建记录。
        """
        previous_user_data = self._get_item_user_data(self.item_list.currentItem())
        selection_key = preferred_key if preferred_key is not None else previous_user_data

        if previous_user_data is None:
            previous_section_key: Optional[str] = None
        else:
            previous_section_key = previous_user_data[0]

        if not self.current_package:
            self.item_list.clear()
            if previous_user_data is not None:
                emit_empty_selection()
            return

        if self.current_category == "all":
            sections: tuple[BaseCombatPresetSection, ...] = SECTION_SEQUENCE
        else:
            selected_section = SECTION_MAP.get(self.current_category)
            if not selected_section:
                self.item_list.clear()
                if previous_user_data is not None:
                    emit_empty_selection()
                return
            sections = (selected_section,)

        selection_restored: dict[str, bool] = {"value": False}

        def build_items() -> None:
            if not self.current_package:
                return
            for section in sections:
                self._append_section_rows(section)

        def get_item_key(list_item: QtWidgets.QListWidgetItem) -> Optional[tuple[str, str]]:
            return self._get_item_user_data(list_item)

        def mark_restored(user_data: tuple[str, str]) -> None:
            del user_data
            selection_restored["value"] = True

        def emit_empty_selection() -> None:
            self.notify_selection_state(
                False,
                context={"source": "combat", "section_key": previous_section_key},
            )
            self.selection_changed.emit(None)

        rebuild_list_with_preserved_selection(
            self.item_list,
            previous_key=selection_key,
            had_selection_before_refresh=previous_user_data is not None,
            build_items=build_items,
            key_getter=get_item_key,
            on_restored_selection=mark_restored,
            on_first_selection=None,
            on_cleared_selection=emit_empty_selection,
        )

        if selection_restored["value"]:
            return

        if self.current_category in ("all", "player_template"):
            # 仅在“全部/玩家模板”视图下才要求列表中存在玩家模板条目：
            # - 这些视图的默认选中策略以玩家模板为锚点；
            # - 其它分类（职业/技能/投射物/单位状态/道具）不应因“当前列表不包含玩家模板”
            #   而被误判为“无有效选中”，否则会导致右侧详情面板刚显示又被清空。
            has_player_template = False
            for row_index in range(self.item_list.count()):
                list_item = self.item_list.item(row_index)
                user_data = self._get_item_user_data(list_item)
                if not user_data:
                    continue
                section_key, _ = user_data
                if section_key == "player_template":
                    has_player_template = True
                    break

            if not has_player_template:
                self.notify_selection_state(
                    False,
                    context={"source": "combat", "section_key": "player_template"},
                )
                self.selection_changed.emit(None)
                return

            current_item = self.item_list.currentItem()
            current_user_data = self._get_item_user_data(current_item)
            if not current_user_data or current_user_data[0] != "player_template":
                self._select_first_player_item()

    def _append_section_rows(self, section: BaseCombatPresetSection) -> None:
        """将某个分类的所有行加入列表。"""
        if not self.current_package:
            return
        for row_data in section.iter_rows(self.current_package):
            self._add_row_item(row_data)

    def _add_row_item(self, row_data: TableRowData) -> None:
        """添加一条战斗预设到列表。"""
        # 列表文本仅展示名称，类型与其他属性通过 tooltip 与搜索聚合字段提供，
        # 与元件库和实体摆放页面保持一致的“只看名字”文件列表风格。
        display_text = row_data.name or ""

        item = QtWidgets.QListWidgetItem(display_text)
        # 业务标识：Section 键 + 条目 ID
        item.setData(QtCore.Qt.ItemDataRole.UserRole, row_data.user_data)

        # Tooltip：展示更完整的信息
        tooltip_lines: list[str] = [
            f"名称: {row_data.name}",
            f"类型: {row_data.type_name}",
        ]
        if row_data.attr1 and row_data.attr1 != "-":
            tooltip_lines.append(row_data.attr1)
        if row_data.attr2 and row_data.attr2 != "-":
            tooltip_lines.append(row_data.attr2)
        if row_data.attr3 and row_data.attr3 != "-":
            tooltip_lines.append(row_data.attr3)
        if row_data.description:
            tooltip_lines.append(f"描述: {row_data.description}")
        if row_data.last_modified:
            tooltip_lines.append(f"修改时间: {row_data.last_modified}")
        item.setToolTip("\n".join(tooltip_lines))

        # 搜索文本：聚合名称/类型/属性/描述/时间，便于统一过滤
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
        item.setData(QtCore.Qt.ItemDataRole.UserRole + 1, search_value.lower())

        self.item_list.addItem(item)

    def _filter_items(self, text: str) -> None:
        """过滤项目（按名称/类型/属性/描述等聚合字段）。"""
        def _get_search_text(item: QtWidgets.QListWidgetItem) -> str:
            value = item.data(QtCore.Qt.ItemDataRole.UserRole + 1)
            return str(value) if value is not None else item.text()

        self.filter_list_items(self.item_list, text, text_getter=_get_search_text)

    def _get_item_user_data(
        self,
        item: Optional[QtWidgets.QListWidgetItem],
    ) -> Optional[tuple[str, str]]:
        """读取指定条目绑定的 Section 与条目 ID。"""
        if item is None:
            return None
        user_data = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(user_data, tuple) or len(user_data) != 2:
            return None
        section_key, item_id = user_data
        if not isinstance(section_key, str) or not isinstance(item_id, str):
            return None
        return section_key, item_id

    def _on_item_selection_changed(self) -> None:
        """列表选中条目变化时，通知对应的右侧详情面板。"""
        current_item = self.item_list.currentItem()
        user_data = self._get_item_user_data(current_item)
        if not user_data:
            log_debug("[COMBAT-PRESETS] selection changed: <none>")
            self.notify_selection_state(False, context={"source": "combat", "section_key": None})
            self.selection_changed.emit(None)
            return
        section_key, item_id = user_data
        log_debug(
            "[COMBAT-PRESETS] selection changed: section_key={!r}, item_id={!r}",
            section_key,
            item_id,
        )

        if not item_id:
            self.notify_selection_state(False, context={"source": "combat", "section_key": section_key})
            self.selection_changed.emit(None)
            return

        selection = LibrarySelection(
            kind="combat",
            id=item_id,
            context={
                "section_key": section_key,
                "scope": describe_resource_view_scope(self.current_package),
            },
        )
        self.notify_selection_state(True, context={"source": "combat", "section_key": section_key})
        self.selection_changed.emit(selection)

    def _on_item_clicked(self, _item: QtWidgets.QListWidgetItem) -> None:
        """列表项单击时，同步触发选中逻辑，避免当前已选中条目首次点击不刷新右侧面板。"""
        self._on_item_selection_changed()

    def _add_item(self) -> None:
        """添加项目"""
        if not self.current_package:
            self.show_warning("警告", "请先选择或创建存档")
            return

        package_id_repr = getattr(self.current_package, "package_id", "<no-package-id>")
        print(
            "[COMBAT-PRESETS] 点击“+ 新建”按钮：",
            f"package_id={package_id_repr!r}, current_category={self.current_category!r}",
        )

        target_section = self._resolve_target_section()
        if not target_section:
            print(
                "[COMBAT-PRESETS] 解析目标 Section 失败：",
                f"package_id={package_id_repr!r}, current_category={self.current_category!r}",
            )
            return

        section_key_repr = getattr(target_section, "category_key", "<unknown-section-key>")
        section_type_name = getattr(target_section, "type_name", "<unknown-type-name>")
        print(
            "[COMBAT-PRESETS] 目标 Section 解析结果：",
            f"section_key={section_key_repr!r}, type_name={section_type_name!r}",
        )

        # 记录新建前该 Section 下已有的业务键集合，用于在创建后识别新增记录。
        previous_keys: set[tuple[str, str]] = set()
        for row_data in target_section.iter_rows(self.current_package):
            previous_keys.add(row_data.user_data)

        created = target_section.create_item(self, self.current_package)
        print(
            "[COMBAT-PRESETS] 调用 Section.create_item 结束：",
            f"section_key={section_key_repr!r}, result={created!r}, "
            f"previous_count={len(previous_keys)}",
        )
        if not created:
            return

        # 新建后再次扫描该 Section，找出新增的 user_data 作为首选选中目标。
        new_key: Optional[tuple[str, str]] = None
        current_keys: set[tuple[str, str]] = set()
        for row_data in target_section.iter_rows(self.current_package):
            current_keys.add(row_data.user_data)
        added_keys = current_keys - previous_keys
        print(
            "[COMBAT-PRESETS] 新建后 Section 键变化：",
            f"section_key={section_key_repr!r}, before_count={len(previous_keys)}, "
            f"after_count={len(current_keys)}, added_keys_count={len(added_keys)}",
        )
        if len(added_keys) == 1:
            new_key = next(iter(added_keys))

        self._refresh_items(preferred_key=new_key)

        if new_key is not None:
            new_section_key, new_item_id = new_key
            event = LibraryChangeEvent(
                kind="combat",
                id=new_item_id,
                operation="create",
                context={
                    "section_key": new_section_key,
                    "scope": describe_resource_view_scope(self.current_package),
                },
            )
            self.data_changed.emit(event)

    def _duplicate_item(self) -> None:
        """复制当前选中的战斗预设（浅复制）。"""
        if not self.current_package:
            self.show_warning("警告", "请先选择或创建存档")
            return

        current_item = self.item_list.currentItem()
        user_data = self._get_item_user_data(current_item)
        if not user_data:
            self.show_warning("提示", "请先选择要复制的战斗预设")
            return

        section_key, item_id = user_data
        section = SECTION_MAP.get(section_key)
        if section is None:
            self.show_warning("警告", f"未知的战斗预设分类：{section_key}")
            return

        spec = self._SECTION_SPECS.get(section_key)
        if spec is None:
            self.show_warning("警告", f"当前分类不支持复制：{section_key}")
            return
        bucket_key, id_field, name_field, id_prefix, resource_type = spec

        combat_presets_view = getattr(self.current_package, "combat_presets", None)
        if combat_presets_view is None:
            self.show_warning("警告", "当前视图未提供 combat_presets 数据，无法复制")
            return

        bucket_mapping_any = getattr(combat_presets_view, bucket_key, None)
        if not isinstance(bucket_mapping_any, dict):
            self.show_warning("警告", f"战斗预设数据结构异常：{bucket_key} 不是字典")
            return
        bucket_mapping: dict[str, dict] = bucket_mapping_any  # type: ignore[assignment]

        source_payload_any = bucket_mapping.get(item_id)
        if not isinstance(source_payload_any, dict):
            self.show_warning("警告", "战斗预设数据异常：条目内容不是字典")
            return
        source_payload: dict = source_payload_any

        new_item_id = generate_prefixed_id(id_prefix)
        new_payload: dict = copy.deepcopy(source_payload)

        # 规范化 ID 字段
        new_payload["id"] = new_item_id
        new_payload[id_field] = new_item_id

        # 名称字段
        raw_name = new_payload.get(name_field)
        base_name = str(raw_name).strip() if isinstance(raw_name, str) else ""
        if not base_name and current_item is not None:
            base_name = str(current_item.text() or "").strip()
        new_payload[name_field] = f"{base_name or new_item_id} - 副本"

        new_payload["last_modified"] = BaseCombatPresetSection._current_timestamp()

        bucket_mapping[new_item_id] = new_payload

        # 立即落盘资源文件：保持与“新建”一致的目录落点语义（PackageView→当前项目存档根；GlobalResourceView→共享根）。
        section._save_resource_for_package(  # type: ignore[attr-defined]
            self.current_package,
            resource_type,
            new_item_id,
            dict(new_payload),
        )

        self._refresh_items(preferred_key=(section_key, new_item_id))

        ToastNotification.show_message(
            self,
            f"已复制{getattr(section, 'type_name', '战斗预设')}：{new_payload.get(name_field, new_item_id)}",
            "success",
        )
        event = LibraryChangeEvent(
            kind="combat",
            id=new_item_id,
            operation="create",
            context={
                "section_key": section_key,
                "scope": describe_resource_view_scope(self.current_package),
                "source": "duplicate",
            },
        )
        self.data_changed.emit(event)

    def _rename_item(self) -> None:
        """重命名当前选中的战斗预设（仅修改 name 字段）。"""
        if not self.current_package:
            self.show_warning("警告", "请先选择或创建存档")
            return

        current_item = self.item_list.currentItem()
        user_data = self._get_item_user_data(current_item)
        if not user_data:
            self.show_warning("提示", "请先选择要重命名的战斗预设")
            return
        section_key, item_id = user_data

        spec = self._SECTION_SPECS.get(section_key)
        if spec is None:
            self.show_warning("警告", f"当前分类不支持重命名：{section_key}")
            return
        bucket_key, _id_field, name_field, _id_prefix, resource_type = spec

        combat_presets_view = getattr(self.current_package, "combat_presets", None)
        if combat_presets_view is None:
            self.show_warning("警告", "当前视图未提供 combat_presets 数据，无法重命名")
            return

        bucket_mapping_any = getattr(combat_presets_view, bucket_key, None)
        if not isinstance(bucket_mapping_any, dict):
            self.show_warning("警告", f"战斗预设数据结构异常：{bucket_key} 不是字典")
            return
        bucket_mapping = bucket_mapping_any

        payload_any = bucket_mapping.get(item_id)
        if not isinstance(payload_any, dict):
            self.show_warning("警告", "战斗预设数据异常：条目内容不是字典")
            return
        payload = payload_any

        old_name_any = payload.get(name_field)
        old_name = str(old_name_any).strip() if isinstance(old_name_any, str) else ""
        if not old_name and current_item is not None:
            old_name = str(current_item.text() or "").strip()
        if not old_name:
            old_name = item_id

        new_name = input_dialogs.prompt_text(
            self,
            "重命名战斗预设",
            "请输入新的名称:",
            text=old_name,
        )
        if not new_name:
            return
        new_name = str(new_name).strip()
        if not new_name or new_name == old_name:
            return

        payload[name_field] = new_name
        payload["last_modified"] = BaseCombatPresetSection._current_timestamp()

        section = SECTION_MAP.get(section_key)
        if section is not None:
            section._save_resource_for_package(  # type: ignore[attr-defined]
                self.current_package,
                resource_type,
                item_id,
                dict(payload),
            )

        self._refresh_items(preferred_key=(section_key, item_id))
        event = LibraryChangeEvent(
            kind="combat",
            id=item_id,
            operation="update",
            context={
                "section_key": section_key,
                "scope": describe_resource_view_scope(self.current_package),
                "action": "rename",
            },
        )
        self.data_changed.emit(event)
        ToastNotification.show_message(self, f"已重命名：{new_name}", "info")

    def _change_selected_item_owner(self) -> None:
        """修改当前选中战斗预设的归属位置（共享 / 某个项目存档目录）。"""
        if not self.current_package:
            self.show_warning("警告", "请先选择或创建存档")
            return

        current_item = self.item_list.currentItem()
        user_data = self._get_item_user_data(current_item)
        if not user_data:
            self.show_warning("提示", "请先选择要移动的战斗预设")
            return
        section_key, item_id = user_data

        spec = self._SECTION_SPECS.get(section_key)
        if spec is None:
            self.show_warning("警告", f"当前分类不支持移动：{section_key}")
            return
        bucket_key, _id_field, _name_field, _id_prefix, _resource_type = spec
        resource_type_text = f"combat_{bucket_key}"

        window = self.window()
        app_state = getattr(window, "app_state", None) if window is not None else None
        package_index_manager = getattr(app_state, "package_index_manager", None) if app_state is not None else None
        if not isinstance(package_index_manager, PackageIndexManager):
            self.show_warning("警告", "无法移动：PackageIndexManager 不可用。")
            return

        previous_owner = package_index_manager.get_resource_owner_root_id(
            resource_type=resource_type_text,
            resource_id=item_id,
        )

        packages = package_index_manager.list_packages()
        choice_labels: list[str] = ["🌐 共享（shared）"]
        label_to_root_id: dict[str, str] = {"🌐 共享（shared）": "shared"}
        for pkg in packages:
            package_id = pkg.get("package_id")
            if not isinstance(package_id, str) or not package_id:
                continue
            display_name = str(pkg.get("name") or package_id).strip() or package_id
            label = f"{display_name}（{package_id}）"
            choice_labels.append(label)
            label_to_root_id[label] = package_id

        current_index = 0
        if previous_owner == "shared":
            current_index = 0
        elif isinstance(previous_owner, str) and previous_owner:
            for idx, label in enumerate(choice_labels):
                if label_to_root_id.get(label) == previous_owner:
                    current_index = idx
                    break

        selected_label = input_dialogs.prompt_item(
            self,
            "移动战斗预设（所属存档）",
            "请选择目标归属位置:",
            choice_labels,
            current_index=current_index,
            editable=False,
        )
        if not selected_label:
            return

        target_root_id = label_to_root_id.get(selected_label, "")
        if not target_root_id:
            return
        if target_root_id == previous_owner:
            return

        previous_label = "🌐 共享" if previous_owner == "shared" else (previous_owner or "(未知)")
        next_label = "🌐 共享" if target_root_id == "shared" else target_root_id
        if not self.confirm(
            "确认切换所属存档",
            f"即将把战斗预设 '{item_id}' 的归属从「{previous_label}」切换到「{next_label}」。\n\n确定要继续吗？",
        ):
            return

        move_method = getattr(window, "_move_resource_to_owner_root_and_sync_current", None) if window is not None else None
        if callable(move_method):
            moved_ok = bool(
                move_method(
                    resource_type=resource_type_text,
                    resource_id=item_id,
                    target_owner_root_id=target_root_id,
                )
            )
            if not moved_ok:
                self.show_warning("警告", "移动失败：未找到资源文件或目标目录不可用。")
                return
        else:
            moved_ok = package_index_manager.move_resource_to_root(target_root_id, resource_type_text, item_id)
            if not moved_ok:
                self.show_warning("警告", "移动失败：未找到资源文件或目标目录不可用。")
                return

        if hasattr(self.current_package, "clear_cache"):
            self.current_package.clear_cache()
        self._refresh_items()
        ToastNotification.show_message(self, "归属已更新。", "info")

    def _locate_issues_for_selected_item(self) -> None:
        """打开验证面板并定位到与当前战斗预设相关的问题（若存在）。"""
        current_item = self.item_list.currentItem()
        user_data = self._get_item_user_data(current_item)
        if not user_data:
            self.show_warning("提示", "请先选择要定位问题的战斗预设")
            return
        _section_key, item_id = user_data
        window = self.window()
        locate = getattr(window, "_locate_issues_for_resource_id", None) if window is not None else None
        if callable(locate):
            locate(item_id)

    @staticmethod
    def _payload_mentions_id(payload: object, target_id: str) -> bool:
        """简单引用探测：递归检查 payload 内是否出现等于 target_id 的字符串值。"""
        if isinstance(payload, str):
            return payload == target_id
        if isinstance(payload, dict):
            for value in payload.values():
                if CombatPresetsWidget._payload_mentions_id(value, target_id):
                    return True
            return False
        if isinstance(payload, (list, tuple, set)):
            for value in payload:
                if CombatPresetsWidget._payload_mentions_id(value, target_id):
                    return True
            return False
        return False

    def _collect_combat_preset_reference_lines(self, target_id: str) -> list[str]:
        """返回“哪些战斗预设条目引用了 target_id”的提示行列表（用于删除确认）。"""
        if not self.current_package:
            return []

        combat_presets_view = getattr(self.current_package, "combat_presets", None)
        if combat_presets_view is None:
            return []

        lines: list[str] = []
        for section_key, (bucket_key, _id_field, name_field, _id_prefix, _resource_type) in self._SECTION_SPECS.items():
            bucket_mapping_any = getattr(combat_presets_view, bucket_key, None)
            if not isinstance(bucket_mapping_any, dict):
                continue
            bucket_mapping = bucket_mapping_any

            section = SECTION_MAP.get(section_key)
            type_name = getattr(section, "type_name", section_key) if section is not None else section_key

            for preset_id, payload_any in bucket_mapping.items():
                if not isinstance(preset_id, str) or not preset_id:
                    continue
                if preset_id == target_id:
                    continue
                if not isinstance(payload_any, dict):
                    continue
                if not self._payload_mentions_id(payload_any, target_id):
                    continue
                raw_name = payload_any.get(name_field)
                name_text = str(raw_name).strip() if isinstance(raw_name, str) else ""
                if not name_text:
                    name_text = preset_id
                lines.append(f"{type_name}: {name_text}（{preset_id}）")

        lines.sort(key=lambda text: text.casefold())
        return lines

    def _resolve_target_section(self) -> Optional[BaseCombatPresetSection]:
        """根据当前分类或用户选择确定 Section。"""
        if self.current_category == "all":
            selection_label = input_dialogs.prompt_item(
                self,
                "选择类型",
                "请选择要创建的战斗预设类型:",
                list(SECTION_SELECTION_LABELS),
                current_index=0,
                editable=False,
            )
            if not selection_label:
                return None
            return get_section_by_selection_label(selection_label)

        return SECTION_MAP.get(self.current_category)

    def _delete_item(self) -> None:
        """删除项目"""
        if not self.current_package:
            return

        current_item = self.item_list.currentItem()
        user_data = self._get_item_user_data(current_item)
        if not user_data:
            self.show_warning("警告", "请先选择要删除的项目")
            return
        section_key, item_id = user_data
        section = SECTION_MAP.get(section_key)
        if not section:
            return

        if current_item is None:
            return

        item_display_name = current_item.text()

        spec = self._SECTION_SPECS.get(section_key)
        if spec is None:
            self.show_warning("警告", f"当前分类不支持删除：{section_key}")
            return
        bucket_key, _id_field, _name_field, _id_prefix, resource_type = spec

        referencing_lines = self._collect_combat_preset_reference_lines(item_id)
        reference_hint = ""
        if referencing_lines:
            preview = referencing_lines[:10]
            more_count = max(0, len(referencing_lines) - len(preview))
            reference_hint = "\n\n⚠️ 检测到以下战斗预设条目引用了该资源（节选）：\n" + "\n".join(
                f"- {line}" for line in preview
            )
            if more_count:
                reference_hint += f"\n- ... 另有 {more_count} 个引用未展开"

        if isinstance(self.current_package, PackageView):
            if not self.confirm(
                "确认删除",
                (
                    f"将把战斗预设 '{item_display_name}' 从当前存档中移出（移动到默认归档项目），"
                    "不会物理删除资源文件。"
                    f"{reference_hint}\n\n"
                    "确定要继续吗？"
                ),
            ):
                return

            window = self.window()
            package_index_manager_candidate = (
                getattr(window, "package_index_manager", None) if window is not None else None
            )
            if not isinstance(package_index_manager_candidate, PackageIndexManager):
                self.show_warning("警告", "无法删除：未找到 PackageIndexManager（无法执行文件移动）。")
                return

            moved_ok = package_index_manager_candidate.remove_resource_from_package(
                self.current_package.package_id,
                f"combat_{bucket_key}",
                item_id,
            )
            if not moved_ok:
                self.show_warning("警告", "无法删除：资源文件未找到或移动失败。")
                return

        elif isinstance(self.current_package, GlobalResourceView):
            if not self.confirm(
                "确认全局删除",
                (
                    f"将从共享资源中彻底删除战斗预设 '{item_display_name}'（ID: {item_id}）。\n\n"
                    f"{reference_hint}\n\n"
                    "此操作不可撤销，确定要继续吗？"
                ),
            ):
                return

            resource_manager_candidate = getattr(self.current_package, "resource_manager", None)
            if not isinstance(resource_manager_candidate, ResourceManager):
                self.show_warning("警告", "当前视图不支持删除：resource_manager 不可用。")
                return
            resource_manager_candidate.delete_resource(resource_type, item_id)

        if section.delete_item(self.current_package, item_id):
            self._refresh_items()
            ToastNotification.show_message(
                self,
                f"已删除战斗预设 '{item_display_name}'。",
                "success",
            )
            event = LibraryChangeEvent(
                kind="combat",
                id=item_id,
                operation="delete",
                context={
                    "section_key": section_key,
                    "scope": describe_resource_view_scope(self.current_package),
                },
            )
            self.data_changed.emit(event)

    # === 玩家模板选中辅助 ===

    def _select_first_player_item(self) -> None:
        """选中当前列表中的第一个玩家模板条目，并触发选中信号。"""
        for row_index in range(self.item_list.count()):
            item = self.item_list.item(row_index)
            user_data = self._get_item_user_data(item)
            if not user_data:
                continue
            section_key, _ = user_data
            if section_key == "player_template":
                self.item_list.setCurrentItem(item)
                break

    def switch_to_player_editor(self) -> None:
        """聚焦到玩家模板分类，并在需要时选中一个模板。"""
        if not self.current_package:
            return

        # 定位并选中左侧“玩家模板”分类
        for index in range(self.category_tree.topLevelItemCount()):
            tree_item = self.category_tree.topLevelItem(index)
            if tree_item is None:
                continue
            category_key = tree_item.data(0, QtCore.Qt.ItemDataRole.UserRole)
            if category_key == "player_template":
                self.category_tree.setCurrentItem(tree_item)
                break

        self.current_category = "player_template"
        self._refresh_items()
        if self.item_list.currentRow() < 0:
            self._select_first_player_item()
