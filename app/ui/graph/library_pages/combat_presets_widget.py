"""战斗预设组件 - 文件列表形式"""

from PyQt6 import QtCore, QtWidgets
from typing import Optional, Union, Tuple

from engine.resources.global_resource_view import GlobalResourceView
from engine.resources.package_view import PackageView
from ui.foundation import input_dialogs
from ui.foundation.theme_manager import Sizes
from ui.foundation.toast_notification import ToastNotification
from ui.graph.library_mixins import (
    ConfirmDialogMixin,
    SearchFilterMixin,
    ToolbarMixin,
    rebuild_list_with_preserved_selection,
)
from ui.graph.library_pages.combat_presets import (
    BaseCombatPresetSection,
    TableRowData,
    SECTION_SEQUENCE,
    SECTION_MAP,
    SECTION_SELECTION_LABELS,
    get_section_by_key,
    get_section_by_selection_label,
)
from ui.graph.library_pages.library_scaffold import (
    DualPaneLibraryScaffold,
    LibraryChangeEvent,
    LibraryPageMixin,
    LibrarySelection,
)
from app.models.view_modes import ViewMode


class CombatPresetsWidget(
    DualPaneLibraryScaffold,
    LibraryPageMixin,
    SearchFilterMixin,
    ToolbarMixin,
    ConfirmDialogMixin,
):
    """战斗预设界面 - 文件列表形式"""

    # 当玩家模板被选中时发射，参数为 template_id
    player_template_selected = QtCore.pyqtSignal(str)
    # 当职业被选中时发射，参数为 class_id
    player_class_selected = QtCore.pyqtSignal(str)
    # 当技能被选中时发射，参数为 skill_id
    skill_selected = QtCore.pyqtSignal(str)
    # 当道具被选中时发射，参数为 item_id
    item_selected = QtCore.pyqtSignal(str)
    # 当任意战斗预设完成增删改操作时发射，用于上层触发保存或刷新其它视图
    data_changed = QtCore.pyqtSignal(LibraryChangeEvent)

    def __init__(self, parent=None):
        super().__init__(
            parent,
            title="战斗预设",
            description="浏览、筛选与管理战斗预设资源，支持分类定位与搜索。",
        )
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
        self.delete_btn = QtWidgets.QPushButton("删除", self)
        # 工具栏行只放操作按钮，搜索栏统一放在标题行右侧
        self.setup_toolbar_with_search(top_toolbar, [self.add_btn, self.delete_btn], None)
        self.set_status_widget(toolbar_container)

        # 左侧：战斗预设分类树
        self.category_tree = QtWidgets.QTreeWidget()
        self.category_tree.setHeaderLabel("战斗预设分类")
        self.category_tree.setObjectName("leftPanel")
        self.category_tree.setFixedWidth(Sizes.LEFT_PANEL_WIDTH)

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

        self._init_category_tree()

        self.category_tree.itemClicked.connect(self._on_category_clicked)
        self.add_btn.clicked.connect(self._add_item)
        self.delete_btn.clicked.connect(self._delete_item)
        # 选中变化用于处理程序化刷新；点击事件用于保证“已选中条目首次点击”同样能驱动右侧面板。
        self.item_list.itemSelectionChanged.connect(self._on_item_selection_changed)
        self.item_list.itemClicked.connect(self._on_item_clicked)
        self.connect_search(self.search_edit, self._filter_items, placeholder="搜索战斗预设...")

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
        # 初次加载时仅在战斗预设模式下才默认选中玩家模板，避免后台模式触发无谓处理
        if self.item_list.currentRow() < 0 and self._is_combat_mode_active():
            self._select_first_player_item()

    def set_package(self, package: Union[PackageView, GlobalResourceView]) -> None:
        """兼容旧接口，内部委托给 set_context。"""
        self.set_context(package)

    def ensure_default_selection(self) -> None:
        """在战斗预设模式下确保存在一个默认选中项，用于同步右侧详情。"""
        if self.item_list.currentRow() >= 0:
            return
        self._select_first_player_item()

    def _is_combat_mode_active(self) -> bool:
        """判断宿主窗口当前是否处于战斗预设视图模式。"""
        main_window = self.window()
        if main_window is None:
            return False
        central_stack = getattr(main_window, "central_stack", None)
        if central_stack is None:
            return False
        current_index = central_stack.currentIndex()
        current_mode = ViewMode.from_index(current_index)
        return current_mode == ViewMode.COMBAT

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
            context={"section_key": section_key, "scope": self._describe_current_scope()},
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

    def get_current_selection(self) -> Optional[Tuple[str, str]]:
        """返回当前列表中选中的 (section_key, item_id)（兼容旧接口）。

        无选中条目或条目未绑定有效业务键时返回 None。
        """
        selection = self.get_selection()
        if selection is None:
            return None
        section_key = ""
        if isinstance(selection.context, dict):
            raw_key = selection.context.get("section_key")
            if isinstance(raw_key, str):
                section_key = raw_key
        if not section_key:
            return None
        return section_key, selection.id

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
            if previous_section_key == "player_template":
                self.player_template_selected.emit("")
            elif previous_section_key == "player_class":
                self.player_class_selected.emit("")
            elif previous_section_key == "skill":
                self.skill_selected.emit("")
            elif previous_section_key == "item":
                self.item_selected.emit("")

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
            self.player_template_selected.emit("")
            return

        if self.current_category in ("all", "player_template"):
            current_item = self.item_list.currentItem()
            current_user_data = self._get_item_user_data(current_item)
            if not current_user_data or current_user_data[0] != "player_template":
                self._select_first_player_item()

    def _describe_current_scope(self) -> str:
        """根据当前资源视图返回简单 scope 标识，用于变更事件上下文。"""
        if isinstance(self.current_package, PackageView):
            return "package"
        if isinstance(self.current_package, GlobalResourceView):
            return "global"
        return "unknown"

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
            print("[COMBAT-PRESETS] selection changed: <none>")
            self.notify_selection_state(False, context={"source": "combat", "section_key": None})
            # 清空所有战斗详情上下文
            self.player_template_selected.emit("")
            self.player_class_selected.emit("")
            self.skill_selected.emit("")
            self.item_selected.emit("")
            return
        section_key, item_id = user_data
        print(
            "[COMBAT-PRESETS] selection changed:",
            f"section_key={section_key!r}, item_id={item_id!r}",
        )

        def clear_other_combat_contexts(selected_section_key: str) -> None:
            """先清空非当前分类的上下文，避免空 ID 触发的重置盖掉新选中。"""
            if selected_section_key != "player_template":
                self.player_template_selected.emit("")
            if selected_section_key != "player_class":
                self.player_class_selected.emit("")
            if selected_section_key != "skill":
                self.skill_selected.emit("")
            if selected_section_key != "item":
                self.item_selected.emit("")

        if section_key == "player_template" and item_id:
            clear_other_combat_contexts("player_template")
            self.player_template_selected.emit(item_id)
        elif section_key == "player_class" and item_id:
            clear_other_combat_contexts("player_class")
            self.player_class_selected.emit(item_id)
        elif section_key == "skill" and item_id:
            clear_other_combat_contexts("skill")
            self.skill_selected.emit(item_id)
        elif section_key == "item" and item_id:
            clear_other_combat_contexts("item")
            self.item_selected.emit(item_id)

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
                context={"section_key": new_section_key, "scope": self._describe_current_scope()},
            )
            self.data_changed.emit(event)

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

        if self.confirm("确认删除", f"确定要删除 '{item_display_name}' 吗？"):
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
                        "scope": self._describe_current_scope(),
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
