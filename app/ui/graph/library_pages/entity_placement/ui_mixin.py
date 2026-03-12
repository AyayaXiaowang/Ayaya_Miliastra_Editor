"""实体摆放页面 UI 装配与快捷键。"""

from __future__ import annotations

from PyQt6 import QtCore, QtWidgets, QtGui

from app.ui.foundation.context_menu_builder import ContextMenuBuilder
from app.ui.foundation.keymap_store import KeymapStore
from app.ui.foundation.shared_resource_badge_delegate import (
    install_shared_resource_badge_delegate,
)
from app.ui.graph.library_pages.entity_placement.constants import (
    CATEGORY_ALL,
    LEVEL_ENTITY_ICON,
    LEVEL_ENTITY_LABEL_TEXT,
)


class EntityPlacementUiMixin:
    """实体摆放页面 UI 装配与快捷键 mixin。"""

    def _setup_ui(self) -> None:
        """设置实体摆放页面 UI。"""
        self.add_instance_btn = QtWidgets.QPushButton("+ 添加实体", self)
        self.duplicate_instance_btn = QtWidgets.QPushButton("复制", self)
        self.merge_decorations_btn = QtWidgets.QPushButton("合并装饰物…", self)
        self.delete_instance_btn = QtWidgets.QPushButton("删除", self)

        widgets = self.build_standard_dual_pane_list_ui(
            search_placeholder="搜索实体...",
            toolbar_buttons=[
                self.add_instance_btn,
                self.duplicate_instance_btn,
                self.merge_decorations_btn,
                self.delete_instance_btn,
            ],
            left_header_label="实体分类",
            left_title="实体分类",
            left_description="按实体类型过滤实体",
            right_title="实体列表",
            right_description="支持搜索与筛选，选中后在右侧属性面板中编辑详细属性",
            list_object_name="entityInstanceList",
            wrap_right_list=True,
        )
        self.search_edit = widgets.search_edit
        self.category_tree = widgets.category_tree
        self.entity_list = widgets.list_widget

        install_shared_resource_badge_delegate(self.entity_list)
        self._init_category_tree()

        self.category_tree.itemClicked.connect(self._on_category_clicked)
        self.add_instance_btn.clicked.connect(self._add_from_template)
        self.duplicate_instance_btn.clicked.connect(self._duplicate_instance)
        self.merge_decorations_btn.clicked.connect(self._merge_decorations_into_one_instance)
        self.delete_instance_btn.clicked.connect(self._delete_instance)
        self.entity_list.itemSelectionChanged.connect(self._on_selection_changed)
        self.entity_list.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.entity_list.customContextMenuRequested.connect(self._show_instance_context_menu)
        self.connect_search(self.search_edit, self._on_search_text_changed, placeholder="搜索...")

        self._install_standard_shortcuts()

    def _install_standard_shortcuts(self) -> None:
        """统一安装页面内快捷键。"""
        self._install_standard_shortcuts_impl()

    def apply_keymap_shortcuts(self, keymap_store: object) -> None:
        """根据新的 keymap_store 刷新本页快捷键绑定。"""
        self._install_standard_shortcuts_impl(keymap_store=keymap_store)

    def _resolve_keymap_store(self) -> object | None:
        """从主窗口 app_state 解析 keymap_store。"""
        window_obj = self.window()
        app_state = getattr(window_obj, "app_state", None)
        return getattr(app_state, "keymap_store", None) if app_state is not None else None

    def _clear_standard_shortcuts(self) -> None:
        """清理并释放已安装的标准快捷键对象。"""
        for shortcut in list(self._standard_shortcuts):
            shortcut.setEnabled(False)
            shortcut.deleteLater()
        self._standard_shortcuts.clear()

    def _primary_shortcut(self, action_id: str) -> str:
        """返回给定 action_id 的主快捷键文本。"""
        keymap_store = self._resolve_keymap_store()
        get_primary = (
            getattr(keymap_store, "get_primary_shortcut", None) if keymap_store is not None else None
        )
        if callable(get_primary):
            return str(get_primary(action_id) or "")
        defaults = KeymapStore.get_default_shortcuts(action_id)
        return defaults[0] if defaults else ""

    def _install_standard_shortcuts_impl(self, *, keymap_store: object | None = None) -> None:
        """按当前 keymap 重新安装本页标准快捷键。"""
        resolved = keymap_store if keymap_store is not None else self._resolve_keymap_store()
        get_primary = getattr(resolved, "get_primary_shortcut", None) if resolved is not None else None

        def _primary(action_id: str) -> str:
            """返回 action_id 在当前 keymap 下的主快捷键文本。"""
            if callable(get_primary):
                return str(get_primary(action_id) or "")
            defaults = KeymapStore.get_default_shortcuts(action_id)
            return defaults[0] if defaults else ""

        self._clear_standard_shortcuts()

        shortcut_new = _primary("library.new")
        if shortcut_new:
            sc = QtGui.QShortcut(QtGui.QKeySequence(shortcut_new), self)
            sc.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(self._add_from_template)
            self._standard_shortcuts.append(sc)

        shortcut_dup = _primary("library.duplicate")
        if shortcut_dup:
            sc = QtGui.QShortcut(QtGui.QKeySequence(shortcut_dup), self.entity_list)
            sc.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(self._duplicate_instance)
            self._standard_shortcuts.append(sc)

        shortcut_delete = _primary("library.delete")
        if shortcut_delete:
            sc = QtGui.QShortcut(QtGui.QKeySequence(shortcut_delete), self.entity_list)
            sc.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(self._delete_instance)
            self._standard_shortcuts.append(sc)

        shortcut_rename = _primary("library.rename")
        if shortcut_rename:
            sc = QtGui.QShortcut(QtGui.QKeySequence(shortcut_rename), self.entity_list)
            sc.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(self._rename_instance)
            self._standard_shortcuts.append(sc)

        shortcut_move = _primary("library.move")
        if shortcut_move:
            sc = QtGui.QShortcut(QtGui.QKeySequence(shortcut_move), self.entity_list)
            sc.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(self._change_selected_instance_owner)
            self._standard_shortcuts.append(sc)

        shortcut_locate = _primary("library.locate_issues")
        if shortcut_locate:
            sc = QtGui.QShortcut(QtGui.QKeySequence(shortcut_locate), self.entity_list)
            sc.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(self._locate_issues_for_selected_instance)
            self._standard_shortcuts.append(sc)

    def _show_instance_context_menu(self, pos: QtCore.QPoint) -> None:
        """在右侧实体列表弹出上下文菜单。"""
        has_item = self.entity_list.itemAt(pos) is not None
        shortcut_new = self._primary_shortcut("library.new") or None
        shortcut_dup = self._primary_shortcut("library.duplicate") or None
        shortcut_rename = self._primary_shortcut("library.rename") or None
        shortcut_move = self._primary_shortcut("library.move") or None
        shortcut_locate = self._primary_shortcut("library.locate_issues") or None
        shortcut_delete = self._primary_shortcut("library.delete") or None

        builder = ContextMenuBuilder(self)
        builder.add_action("新建", self._add_from_template, shortcut=shortcut_new)
        builder.add_separator()
        builder.add_action("复制", self._duplicate_instance, enabled=has_item, shortcut=shortcut_dup)
        builder.add_action("合并装饰物…", self._merge_decorations_into_one_instance, enabled=has_item)
        builder.add_action("重命名", self._rename_instance, enabled=has_item, shortcut=shortcut_rename)
        builder.add_action(
            "移动（所属存档）", self._change_selected_instance_owner, enabled=has_item, shortcut=shortcut_move
        )
        builder.add_separator()
        builder.add_action(
            "定位问题", self._locate_issues_for_selected_instance, enabled=has_item, shortcut=shortcut_locate
        )
        builder.add_separator()
        builder.add_action("删除", self._delete_instance, enabled=has_item, shortcut=shortcut_delete)
        builder.exec_for(self.entity_list, pos)

    def _init_category_tree(self) -> None:
        """初始化实体分类树。"""
        self._category_items = self.build_entity_category_tree(
            self.category_tree,
            all_label="📁 全部实体",
            entity_label_suffix="实体",
            include_level_entity=True,
            level_entity_label=f"{LEVEL_ENTITY_ICON} {LEVEL_ENTITY_LABEL_TEXT}",
        )
        self.category_tree.setCurrentItem(self._category_items[CATEGORY_ALL])

