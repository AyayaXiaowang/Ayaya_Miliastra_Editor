"""实体摆放组件 - 文件列表形式"""

import copy
import types
from pathlib import Path
from PyQt6 import QtCore, QtWidgets, QtGui
from typing import Any, Optional, Union

from app.ui.foundation.theme_manager import Sizes
from app.ui.foundation.shared_resource_badge_delegate import (
    SHARED_RESOURCE_BADGE_ROLE,
    install_shared_resource_badge_delegate,
)
from app.ui.foundation.id_generator import generate_prefixed_id
from app.ui.foundation.toast_notification import ToastNotification
from app.ui.foundation import input_dialogs
from app.ui.foundation.context_menu_builder import ContextMenuBuilder
from app.ui.foundation.keymap_store import KeymapStore
from app.ui.graph.library_mixins import (
    ConfirmDialogMixin,
    SearchFilterMixin,
    ToolbarMixin,
    rebuild_list_with_preserved_selection,
)
from app.ui.forms.schema_dialog import FormDialogBuilder
from engine.resources.package_view import PackageView
from engine.resources.global_resource_view import GlobalResourceView
from engine.resources.package_index_manager import PackageIndexManager
from engine.graph.models.package_model import InstanceConfig, TemplateConfig
from engine.graph.models.entity_templates import (
    get_entity_type_info,
    get_template_library_entity_types,
)
from app.ui.graph.library_pages.category_tree_mixin import EntityCategoryTreeMixin
from app.ui.graph.library_pages.library_scaffold import (
    DualPaneLibraryScaffold,
    LibraryChangeEvent,
    LibraryPageMixin,
    LibrarySelection,
)
from app.ui.graph.library_pages.library_view_scope import describe_resource_view_scope
from app.ui.graph.library_pages.standard_dual_pane_list_page import StandardDualPaneListPage
from engine.configs.resource_types import ResourceType
from engine.resources.resource_manager import ResourceManager

INSTANCE_ID_ROLE = QtCore.Qt.ItemDataRole.UserRole
ENTITY_TYPE_ROLE = QtCore.Qt.ItemDataRole.UserRole + 1
SEARCH_TEXT_ROLE = QtCore.Qt.ItemDataRole.UserRole + 2
IS_SHARED_INSTANCE_ROLE = QtCore.Qt.ItemDataRole.UserRole + 3

# 关卡实体在“实体分类”树与“实体列表”中应使用统一的图标，避免左右两侧语义不一致。
LEVEL_ENTITY_ICON = "📍"
LEVEL_ENTITY_LABEL_TEXT = "关卡实体"


class EntityPlacementWidget(
    StandardDualPaneListPage,
    LibraryPageMixin,
    SearchFilterMixin,
    ToolbarMixin,
    EntityCategoryTreeMixin,
    ConfirmDialogMixin,
):
    """实体摆放界面 - 文件列表形式"""

    # 统一库页选中事件：发射 LibrarySelection（或 None 表示无有效选中）。
    selection_changed = QtCore.pyqtSignal(object)
    # 当实例被新增/删除/位置修改等造成持久化状态改变时发射，用于通知上层立即保存存档索引
    data_changed = QtCore.pyqtSignal(LibraryChangeEvent)
    
    def __init__(self, parent=None):
        super().__init__(
            parent,
            title="实体摆放",
            description="浏览与管理元件实体，支持分类筛选与快速定位。",
        )
        self._standard_shortcuts: list[QtGui.QShortcut] = []
        self.current_package: Optional[
            Union[PackageView, GlobalResourceView]
        ] = None
        self.current_category: str = "all"  # 当前分类
        self._category_items: dict[str, QtWidgets.QTreeWidgetItem] = {}
        self._setup_ui()
        self.apply_list_widget_style()
    
    def _setup_ui(self) -> None:
        """设置UI"""
        self.add_instance_btn = QtWidgets.QPushButton("+ 添加实体", self)
        self.duplicate_instance_btn = QtWidgets.QPushButton("复制", self)
        self.delete_instance_btn = QtWidgets.QPushButton("删除", self)
        widgets = self.build_standard_dual_pane_list_ui(
            search_placeholder="搜索实体...",
            toolbar_buttons=[self.add_instance_btn, self.duplicate_instance_btn, self.delete_instance_btn],
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

        # 与节点图库一致：共享资源使用徽章标注（避免在名称里拼接共享文本前缀）。
        install_shared_resource_badge_delegate(self.entity_list)
        
        # 初始化分类树
        self._init_category_tree()
        
        # 连接信号
        self.category_tree.itemClicked.connect(self._on_category_clicked)
        self.add_instance_btn.clicked.connect(self._add_from_template)
        self.duplicate_instance_btn.clicked.connect(self._duplicate_instance)
        self.delete_instance_btn.clicked.connect(self._delete_instance)
        self.entity_list.itemSelectionChanged.connect(self._on_selection_changed)
        self.entity_list.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.entity_list.customContextMenuRequested.connect(self._show_instance_context_menu)
        self.connect_search(self.search_edit, self._on_search_text_changed, placeholder="搜索...")

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
        """初始化分类树"""
        self._category_items = self.build_entity_category_tree(
            self.category_tree,
            all_label="📁 全部实体",
            entity_label_suffix="实体",
            include_level_entity=True,
            level_entity_label=f"{LEVEL_ENTITY_ICON} {LEVEL_ENTITY_LABEL_TEXT}",
        )
        self.category_tree.setCurrentItem(self._category_items["all"])
    
    # === LibraryPage 协议实现 ===

    def set_context(
        self,
        package: Union[PackageView, GlobalResourceView],
    ) -> None:
        """设置当前存档或资源视图并刷新列表（统一库页入口）。

        关卡实体不再仅限于具体存档视图，在全局视图下同样允许选中，
        具体归属由右侧属性面板中的“所属存档”单选下拉控制。
        """
        self.current_package = package

        # 始终允许点击“关卡实体”分类，只根据视图类型调整提示文案
        is_global_view = isinstance(package, GlobalResourceView)
        level_item = self._category_items.get("level_entity")
        if level_item:
            level_item.setDisabled(False)
            if is_global_view:
                level_item.setToolTip(
                    0,
                    "关卡实体在全局视图下用于统一编辑本体，具体归属由属性页中的“所属存档”控制（每个存档最多一个）。",
                )
            else:
                level_item.setToolTip(
                    0,
                    "关卡实体（唯一，承载关卡逻辑），可通过属性页中的“所属存档”与当前存档建立或解除绑定。",
                )

        self._rebuild_instances()

    def reload(self) -> None:
        """在当前上下文下全量刷新实体列表并负责选中恢复。"""
        self._rebuild_instances()

    def get_selection(self) -> Optional[LibrarySelection]:
        """返回当前选中的实体/关卡实体（若存在）。"""
        instance_id = self._current_instance_id()
        if not instance_id:
            # 若当前分类为关卡实体且存在 level_entity，则统一使用 level_entity 表示
            if self.current_category == "level_entity" and getattr(
                self.current_package, "level_entity", None
            ) is not None:
                level_instance = getattr(self.current_package, "level_entity")
                level_id = getattr(level_instance, "instance_id", "")
                value = level_id if isinstance(level_id, str) else ""
                return LibrarySelection(
                    kind="level_entity",
                    id=value,
                    context={"scope": describe_resource_view_scope(self.current_package)},
                )
            return None

        kind = "level_entity" if self._is_level_entity_instance_id(instance_id) else "instance"
        return LibrarySelection(
            kind=kind,
            id=instance_id,
            context={"scope": describe_resource_view_scope(self.current_package)},
        )

    def set_selection(self, selection: Optional[LibrarySelection]) -> None:
        """根据 LibrarySelection 恢复实体或关卡实体选中状态。"""
        if selection is None:
            self.entity_list.setCurrentItem(None)
            return
        if selection.kind == "level_entity":
            # 确保关卡实体存在，并切换到关卡实体分类后选中
            self._ensure_level_entity_exists()
            self.current_category = "level_entity"
            self._rebuild_instances()
            level_id = selection.id
            if level_id:
                self.select_instance(level_id)
            else:
                # 无具体 ID 时默认选中关卡实体视图中的唯一条目
                if self.entity_list.count() > 0:
                    self.entity_list.setCurrentRow(0)
                    self._emit_current_selection_or_clear()
            return

        if selection.kind != "instance":
            return
        if not selection.id:
            return
        self.select_instance(selection.id)
    
    def _on_category_clicked(self, item: QtWidgets.QTreeWidgetItem, column: int) -> None:
        """分类点击"""
        category = item.data(0, QtCore.Qt.ItemDataRole.UserRole)

        if category == "level_entity":
            # 特殊处理：关卡实体
            self.current_category = "level_entity"
            self._rebuild_instances()
            self._emit_current_selection_or_clear()
            return

        self.current_category = category or "all"
        self._rebuild_instances()
    
    def _rebuild_instances(self) -> None:
        """刷新实体列表"""
        previously_selected_id = self._current_instance_id()
        if not self.current_package:
            self.entity_list.clear()
            return

        effective_category = self.current_category or "all"

        if effective_category == "level_entity":
            self.entity_list.clear()
            self._rebuild_level_entity_view(previously_selected_id)
            return

        allowed_types = set(get_template_library_entity_types())

        def build_items() -> None:
            displayed_instance_ids: set[str] = set()

            shared_instance_ids: set[str] = set()
            resource_manager_candidate = getattr(self.current_package, "resource_manager", None)
            if isinstance(resource_manager_candidate, ResourceManager):
                resource_library_dir = getattr(resource_manager_candidate, "resource_library_dir", None)
                if isinstance(resource_library_dir, Path):
                    shared_root_dir = (resource_library_dir / "共享").resolve()
                    instance_paths = resource_manager_candidate.list_resource_file_paths(ResourceType.INSTANCE)
                    for resource_id, file_path in instance_paths.items():
                        if not isinstance(resource_id, str) or not resource_id:
                            continue
                        if not isinstance(file_path, Path):
                            continue
                        resolved_file = file_path.resolve()
                        if hasattr(resolved_file, "is_relative_to"):
                            if resolved_file.is_relative_to(shared_root_dir):  # type: ignore[attr-defined]
                                shared_instance_ids.add(resource_id)
                        else:
                            shared_parts = shared_root_dir.parts
                            file_parts = resolved_file.parts
                            if len(file_parts) >= len(shared_parts) and file_parts[: len(shared_parts)] == shared_parts:
                                shared_instance_ids.add(resource_id)

            for instance_id, instance in self.current_package.instances.items():
                template = self.current_package.get_template(instance.template_id)

                # 设计约定：
                # - 实体摆放（InstanceConfig）允许“未绑定/找不到元件（TemplateConfig）”的情况；
                # - UI 列表应仍然展示这些实例，并尽可能从实例 metadata 中回退推导实体类型。
                resolved_entity_type = ""
                template_category = ""
                template_name = ""

                if template is not None:
                    template_name = str(getattr(template, "name", "") or "").strip()
                    resolved_entity_type = str(getattr(template, "entity_type", "") or "").strip()
                    template_metadata = getattr(template, "metadata", {}) or {}
                    if isinstance(template_metadata, dict):
                        category_value = template_metadata.get("template_category") or template_metadata.get(
                            "category"
                        )
                        if isinstance(category_value, str):
                            template_category = category_value.strip()
                else:
                    instance_metadata = getattr(instance, "metadata", {}) or {}
                    if isinstance(instance_metadata, dict):
                        entity_type_value = instance_metadata.get("entity_type")
                        if isinstance(entity_type_value, str):
                            resolved_entity_type = entity_type_value.strip()
                        category_value = instance_metadata.get("template_category") or instance_metadata.get(
                            "category"
                        )
                        if isinstance(category_value, str):
                            template_category = category_value.strip()

                # 仅过滤“明确不属于元件库实体类型”的条目：当无法推导类型时，保留在“全部实体”中展示。
                if resolved_entity_type and resolved_entity_type not in allowed_types:
                    continue

                if (
                    effective_category not in ("all", "")
                    and resolved_entity_type != effective_category
                ):
                    continue

                if template_category in ("元件组", "掉落物"):
                    icon = get_entity_type_info(template_category).get("icon", "📦")
                    display_type = template_category
                else:
                    icon = get_entity_type_info(resolved_entity_type).get("icon", "📦")
                    display_type = resolved_entity_type or "未知"

                guid_text = ""
                instance_metadata = getattr(instance, "metadata", {}) or {}
                if isinstance(instance_metadata, dict):
                    raw_guid = instance_metadata.get("guid")
                    if raw_guid is not None:
                        guid_text = str(raw_guid)

                position_text = (
                    f"({instance.position[0]:.1f}, "
                    f"{instance.position[1]:.1f}, "
                    f"{instance.position[2]:.1f})"
                )
                rotation_text = (
                    f"({instance.rotation[0]:.1f}, "
                    f"{instance.rotation[1]:.1f}, "
                    f"{instance.rotation[2]:.1f})"
                )

                is_shared_instance = instance_id in shared_instance_ids
                display_text = f"{icon} {instance.name}"

                list_item = QtWidgets.QListWidgetItem(display_text)
                list_item.setData(INSTANCE_ID_ROLE, instance_id)
                list_item.setData(ENTITY_TYPE_ROLE, resolved_entity_type)
                list_item.setData(IS_SHARED_INSTANCE_ROLE, bool(is_shared_instance))
                list_item.setData(SHARED_RESOURCE_BADGE_ROLE, bool(is_shared_instance))

                template_line = template_name if template_name else "(未绑定元件)"

                tooltip_lines: list[str] = [
                    f"实体名称: {instance.name}",
                    f"实体类型: {display_type}",
                    f"元件: {template_line}",
                    f"位置: {position_text}",
                    f"旋转: {rotation_text}",
                ]
                if is_shared_instance:
                    tooltip_lines.insert(0, "归属: 共享（所有存档可见）")
                if not template_name and getattr(instance, "template_id", ""):
                    tooltip_lines.append(f"元件ID: {instance.template_id}")
                if guid_text:
                    tooltip_lines.append(f"GUID: {guid_text}")
                list_item.setToolTip("\n".join(tooltip_lines))

                search_tokens = [
                    instance.name,
                    template_name,
                    display_type,
                    resolved_entity_type,
                    str(getattr(instance, "template_id", "") or "").strip(),
                    guid_text,
                    position_text,
                    rotation_text,
                ]
                search_value = " ".join(token for token in search_tokens if token)
                list_item.setData(SEARCH_TEXT_ROLE, search_value.lower())

                self.entity_list.addItem(list_item)
                displayed_instance_ids.add(instance_id)

            if effective_category == "all":
                self._append_level_entity_in_all_category(displayed_instance_ids)

        def get_item_key(list_item: QtWidgets.QListWidgetItem) -> Optional[str]:
            value = list_item.data(INSTANCE_ID_ROLE)
            if isinstance(value, str):
                return value
            return None

        def emit_for_instance(instance_id: Any) -> None:
            if not isinstance(instance_id, str) or not instance_id:
                return
            self._emit_current_selection_or_clear()

        def emit_empty_selection() -> None:
            if previously_selected_id:
                self.notify_selection_state(False, context={"source": "instance"})
                self.selection_changed.emit(None)

        rebuild_list_with_preserved_selection(
            self.entity_list,
            previous_key=previously_selected_id,
            had_selection_before_refresh=bool(previously_selected_id),
            build_items=build_items,
            key_getter=get_item_key,
            on_restored_selection=emit_for_instance,
            on_first_selection=emit_for_instance,
            on_cleared_selection=emit_empty_selection,
        )

    def _on_search_text_changed(self, text: str) -> None:
        """搜索框文本变化"""
        def _get_search_text(item: QtWidgets.QListWidgetItem) -> str:
            value = item.data(SEARCH_TEXT_ROLE)
            return str(value) if value is not None else item.text()

        self.filter_list_items(self.entity_list, text, text_getter=_get_search_text)

    def _on_selection_changed(self) -> None:
        self._emit_current_selection_or_clear()

    def _emit_current_selection_or_clear(self) -> None:
        """根据当前 QListWidget 选中项发射统一的 selection_changed 事件。"""
        selection = self.get_selection()
        if selection is None:
            self.notify_selection_state(False, context={"source": "instance"})
            self.selection_changed.emit(None)
            return
        self.notify_selection_state(True, context={"source": "instance"})
        self.selection_changed.emit(selection)

    def _current_instance_id(self) -> Optional[str]:
        """获取当前选中的实体 ID。"""
        current_item = self.entity_list.currentItem()
        if current_item is None:
            return None
        instance_id = current_item.data(INSTANCE_ID_ROLE)
        if not isinstance(instance_id, str):
            return None
        return instance_id

    def _is_level_entity_instance_id(self, instance_id: str) -> bool:
        """判断给定 ID 是否为当前视图下的关卡实体实例。"""
        if not self.current_package:
            return False
        level_entity = getattr(self.current_package, "level_entity", None)
        if not level_entity:
            return False
        level_instance_id = getattr(level_entity, "instance_id", "")
        return isinstance(level_instance_id, str) and level_instance_id == instance_id
    
    def _prompt_new_instance(self) -> Optional[InstanceConfig]:
        """使用 FormDialogBuilder 统一收集新实体信息。"""
        if not self.current_package:
            return None
        builder = FormDialogBuilder(self, "新建实体", fixed_size=(520, 640))
        allowed_types = set(get_template_library_entity_types())
        templates = [
            template
            for template in self.current_package.templates.values()
            if template.entity_type in allowed_types
        ]
        template_combo = builder.add_combo_box(
            "选择元件:",
            [f"{template.name} ({template.entity_type})" for template in templates] or [],
        )
        for index, template in enumerate(templates):
            template_combo.setItemData(index, template.template_id)
        name_edit = builder.add_line_edit("实体名称:", "")
        pos_editors = builder.add_vector3_editor("位置", [0.0, 0.0, 0.0], minimum=-10000, maximum=10000)
        rot_editors = builder.add_vector3_editor("旋转", [0.0, 0.0, 0.0], minimum=-360, maximum=360)
        selected_template: Optional[TemplateConfig] = None

        def on_template_changed(index: int) -> None:
            nonlocal selected_template
            if index < 0:
                selected_template = None
                return
            template_id = template_combo.itemData(index)
            selected_template = self.current_package.get_template(template_id)
            if not selected_template:
                return
            instance_count = len(self.current_package.instances) + 1
            name_edit.setText(f"{selected_template.name}_{instance_count}")

        template_combo.currentIndexChanged.connect(on_template_changed)
        if template_combo.count() > 0:
            on_template_changed(template_combo.currentIndex())

        def _validate(dialog_self):
            template_id = template_combo.itemData(template_combo.currentIndex())
            if not template_id:
                dialog_self.show_error("请选择元件")
                return False
            if not name_edit.text().strip():
                dialog_self.show_error("请输入实体名称")
                return False
            return True

        builder.dialog.validate = types.MethodType(_validate, builder.dialog)
        if not builder.exec():
            return None
        template_id = template_combo.itemData(template_combo.currentIndex())
        if not template_id:
            return None
        template = self.current_package.get_template(template_id)
        if not template:
            return None

        instance = InstanceConfig(
            instance_id=generate_prefixed_id("instance"),
            name=name_edit.text().strip(),
            template_id=template.template_id,
            position=[editor.value() for editor in pos_editors],
            rotation=[editor.value() for editor in rot_editors],
        )
        return instance

    def _add_from_template(self) -> None:
        """从元件添加实体（使用新对话框）"""
        if not self.current_package:
            self.show_warning("警告", "请先选择或创建存档")
            return

        # 关卡实体分类下，点击“添加实体”直接创建或聚焦关卡实体，不弹出元件选择窗口。
        if self.current_category == "level_entity":
            self._ensure_level_entity_exists()
            self._rebuild_instances()
            self._emit_current_selection_or_clear()
            # 通知上层：关卡实体已创建或绑定（需立即保存索引/资源）
            event = LibraryChangeEvent(
                kind="level_entity",
                id="",
                operation="update",
                context={"scope": describe_resource_view_scope(self.current_package), "action": "ensure_level_entity"},
            )
            self.data_changed.emit(event)
            return

        # 检查是否有可用的元件
        allowed_types = set(get_template_library_entity_types())
        available_templates = [t for t in self.current_package.templates.values() if t.entity_type in allowed_types]
        
        if not available_templates:
            self.show_warning("警告", "请先在元件库中创建元件")
            return
        
        instance = self._prompt_new_instance()
        if instance:
            self.current_package.add_instance(instance)
            self._rebuild_instances()
            self.show_info("成功", f"已添加实体: {instance.name}")
            # 通知上层：实体列表发生了持久化相关变更（需立即保存包索引）
            event = LibraryChangeEvent(
                kind="instance",
                id=instance.instance_id,
                operation="create",
                context={"scope": describe_resource_view_scope(self.current_package)},
            )
            self.data_changed.emit(event)

    def _duplicate_instance(self) -> None:
        """复制当前选中的实体（浅复制）。"""
        if not self.current_package:
            self.show_warning("警告", "请先选择或创建存档")
            return

        instance_id = self._current_instance_id()
        if not instance_id:
            self.show_warning("提示", "请先选择要复制的实体")
            return

        instance = self.current_package.get_instance(instance_id)
        if instance is None:
            self._rebuild_instances()
            return

        metadata = getattr(instance, "metadata", {}) or {}
        if isinstance(metadata, dict) and metadata.get("is_level_entity"):
            self.show_warning("提示", "关卡实体不支持复制（每个存档仅允许一个）。")
            return

        new_instance_id = generate_prefixed_id("instance")
        new_name = f"{instance.name} - 副本"

        new_metadata = copy.deepcopy(metadata) if isinstance(metadata, dict) else {}
        if isinstance(new_metadata, dict):
            # GUID 需要保持唯一，复制时默认清空，交由用户在属性面板中重新分配/填写。
            new_metadata.pop("guid", None)
            new_metadata.pop("is_level_entity", None)

        new_instance = InstanceConfig(
            instance_id=new_instance_id,
            name=new_name,
            template_id=str(getattr(instance, "template_id", "") or ""),
            position=list(getattr(instance, "position", [0.0, 0.0, 0.0]) or [0.0, 0.0, 0.0]),
            rotation=list(getattr(instance, "rotation", [0.0, 0.0, 0.0]) or [0.0, 0.0, 0.0]),
            override_variables=copy.deepcopy(getattr(instance, "override_variables", []) or []),
            additional_graphs=list(getattr(instance, "additional_graphs", []) or []),
            additional_components=copy.deepcopy(getattr(instance, "additional_components", []) or []),
            metadata=new_metadata if isinstance(new_metadata, dict) else {},
            graph_variable_overrides=copy.deepcopy(getattr(instance, "graph_variable_overrides", {}) or {}),
        )

        self.current_package.add_instance(new_instance)
        self._rebuild_instances()
        self.select_instance(new_instance_id)

        event = LibraryChangeEvent(
            kind="instance",
            id=new_instance_id,
            operation="create",
            context={
                "scope": describe_resource_view_scope(self.current_package),
                "source": "duplicate",
            },
        )
        self.data_changed.emit(event)
        ToastNotification.show_message(self, f"已复制实体：{new_name}", "success")

    def _rename_instance(self) -> None:
        """重命名当前选中的实体（仅修改 name 字段）。"""
        if not self.current_package:
            self.show_warning("警告", "请先选择或创建存档")
            return

        instance_id = self._current_instance_id()
        if not instance_id:
            self.show_warning("提示", "请先选择要重命名的实体")
            return

        instance = self.current_package.get_instance(instance_id)
        if instance is None:
            self._rebuild_instances()
            return

        old_name = str(getattr(instance, "name", "") or "").strip() or instance_id
        new_name = input_dialogs.prompt_text(
            self,
            "重命名实体",
            "请输入新的实体名称:",
            text=old_name,
        )
        if not new_name:
            return
        new_name = str(new_name).strip()
        if not new_name or new_name == old_name:
            return

        instance.name = new_name
        self._rebuild_instances()
        self.select_instance(instance_id)

        event = LibraryChangeEvent(
            kind="instance",
            id=instance_id,
            operation="update",
            context={
                "scope": describe_resource_view_scope(self.current_package),
                "action": "rename",
            },
        )
        self.data_changed.emit(event)
        ToastNotification.show_message(self, f"已重命名实体：{new_name}", "info")

    def _change_selected_instance_owner(self) -> None:
        """修改当前选中实体的归属位置（共享 / 某个项目存档目录）。"""
        if not self.current_package:
            self.show_warning("警告", "请先选择或创建存档")
            return

        instance_id = self._current_instance_id()
        if not instance_id:
            self.show_warning("提示", "请先选择要移动的实体")
            return

        if self._is_level_entity_instance_id(instance_id):
            self.show_warning("提示", "关卡实体请在右侧属性面板中修改“所属存档/归属位置”。")
            return

        window = self.window()
        app_state = getattr(window, "app_state", None) if window is not None else None
        package_index_manager = getattr(app_state, "package_index_manager", None) if app_state is not None else None
        if not isinstance(package_index_manager, PackageIndexManager):
            self.show_warning("警告", "无法移动：PackageIndexManager 不可用。")
            return

        previous_owner = package_index_manager.get_resource_owner_root_id(
            resource_type="instance",
            resource_id=instance_id,
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
            "移动实体（所属存档）",
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
            f"即将把实体 '{instance_id}' 的归属从「{previous_label}」切换到「{next_label}」。\n\n确定要继续吗？",
        ):
            return

        handler = getattr(window, "_on_instance_package_membership_changed", None) if window is not None else None
        if callable(handler):
            handler(instance_id, target_root_id, True)
        else:
            moved = package_index_manager.move_resource_to_root(target_root_id, "instance", instance_id)
            if not moved:
                self.show_warning("警告", "移动失败：未找到资源文件或目标目录不可用。")
                return
            if hasattr(self.current_package, "clear_cache"):
                self.current_package.clear_cache()
            self._rebuild_instances()

        ToastNotification.show_message(self, "归属已更新。", "info")

    def _locate_issues_for_selected_instance(self) -> None:
        """打开验证面板并定位到与当前实体相关的问题（若存在）。"""
        instance_id = self._current_instance_id()
        if not instance_id:
            self.show_warning("提示", "请先选择要定位问题的实体")
            return
        window = self.window()
        locate = getattr(window, "_locate_issues_for_resource_id", None) if window is not None else None
        if callable(locate):
            locate(instance_id)
    
    def _delete_instance(self) -> None:
        """删除实体。

        语义澄清（目录即项目存档模式）：
        - PackageView：从当前项目存档中移除实体 = 移动该实例 JSON 文件到默认归档项目（不做物理删除）；
        - GlobalResourceView：删除共享实体 = 物理删除共享根目录下的实例 JSON 文件。
        """
        instance_id = self._current_instance_id()
        if not instance_id:
            self.show_warning("警告", "请先选择要删除的实体")
            return

        current_item = self.entity_list.currentItem()
        is_shared_instance = bool(current_item.data(IS_SHARED_INSTANCE_ROLE)) if current_item is not None else False
        if isinstance(self.current_package, PackageView) and is_shared_instance:
            self.show_warning(
                "提示",
                "该实体属于【共享】资源，无法在“具体存档”视图下删除。\n\n"
                "如需删除共享实体，请切换到 <全部资源> 视图执行全局删除；\n"
                "如需让实体仅属于当前存档，请在右侧属性面板中修改其“所属存档/归属位置”。",
            )
            return
        instance = self.current_package.get_instance(instance_id)
        
        if not instance:
            return

        # 关卡实体通过索引约束为只读对象，不允许从实体摆放页面删除。
        metadata = getattr(instance, "metadata", {}) or {}
        if isinstance(metadata, dict) and metadata.get("is_level_entity"):
            self.show_warning("警告", "关卡实体不允许在此处删除，请通过存档管理与索引工具维护。")
            return

        if self.confirm("确认删除", f"确定要删除实体 '{instance.name}' 吗？"):
            # ===== 目录模式下的删除语义：按视图区分“移除归属”与“物理删除” =====
            if isinstance(self.current_package, PackageView):
                window = self.window()
                package_index_manager_candidate = (
                    getattr(window, "package_index_manager", None) if window is not None else None
                )
                if not isinstance(package_index_manager_candidate, PackageIndexManager):
                    self.show_warning(
                        "警告",
                        "无法从当前存档移除实体：未找到 PackageIndexManager（无法执行文件移动）。",
                    )
                    return

                moved_ok = package_index_manager_candidate.remove_resource_from_package(
                    self.current_package.package_id,
                    "instance",
                    instance_id,
                )
                if not moved_ok:
                    self.show_warning(
                        "警告",
                        "无法从当前存档移除实体：资源文件未找到或移动失败。",
                    )
                    return

                # 同步当前视图的内存快照与缓存（用于 UI 立即反馈）。
                self.current_package.remove_instance(instance_id)
                if hasattr(self.current_package, "clear_cache"):
                    self.current_package.clear_cache()

            elif isinstance(self.current_package, GlobalResourceView):
                resource_manager_candidate = getattr(self.current_package, "resource_manager", None)
                if not isinstance(resource_manager_candidate, ResourceManager):
                    self.show_warning("警告", "当前视图不支持删除实体：resource_manager 不可用。")
                    return

                resource_manager_candidate.delete_resource(ResourceType.INSTANCE, instance_id)
                # 清理当前视图缓存，避免列表刷新仍使用旧实例数据。
                self.current_package.remove_instance(instance_id)
                if hasattr(self.current_package, "clear_cache"):
                    self.current_package.clear_cache()

            self._rebuild_instances()
            # 通知上层：实体列表发生了持久化相关变更（需立即保存包索引）
            event = LibraryChangeEvent(
                kind="instance",
                id=instance_id,
                operation="delete",
                context={"scope": describe_resource_view_scope(self.current_package)},
            )
            self.data_changed.emit(event)
            ToastNotification.show_message(self, f"已删除实体 '{instance.name}'。", "success")
    
    def select_instance(self, instance_id: str) -> None:
        """选中指定实体"""
        for row in range(self.entity_list.count()):
            item = self.entity_list.item(row)
            if item and item.data(INSTANCE_ID_ROLE) == instance_id:
                self.entity_list.setCurrentRow(row)
                self.entity_list.scrollToItem(
                    item, QtWidgets.QAbstractItemView.ScrollHint.PositionAtCenter
                )
                self._emit_current_selection_or_clear()
                break

    # 对外刷新入口 -------------------------------------------------------------
    def refresh_instances(self) -> None:
        """刷新实体列表（供主窗口在属性面板数据更新后调用）。"""
        self._rebuild_instances()

    # 关卡实体专用视图与创建逻辑 ---------------------------------------------
    def _rebuild_level_entity_view(self, previously_selected_id: Optional[str]) -> None:
        """在“关卡实体”分类下重建右侧列表，仅展示关卡实体本体。"""
        level_entity = getattr(self.current_package, "level_entity", None) if self.current_package else None
        if not level_entity:
            # 无关卡实体时保持列表为空，由“添加实体”按钮负责创建。
            return

        level_entity_item = self._create_level_entity_item(level_entity)
        self.entity_list.addItem(level_entity_item)

        # 无论之前是否选中，关卡实体视图下始终选中唯一条目并触发专用信号。
        self.entity_list.setCurrentRow(0)
        self._emit_current_selection_or_clear()

    def _append_level_entity_in_all_category(self, displayed_instance_ids: set[str]) -> None:
        """在“全部实体”分类下，将关卡实体本体追加到列表中（若存在且尚未显示）。"""
        if not self.current_package:
            return

        level_entity = getattr(self.current_package, "level_entity", None)
        if not level_entity:
            return

        if not isinstance(level_entity.instance_id, str):
            return
        if level_entity.instance_id in displayed_instance_ids:
            return

        level_entity_item = self._create_level_entity_item(level_entity)
        self.entity_list.addItem(level_entity_item)
        displayed_instance_ids.add(level_entity.instance_id)

    def _create_level_entity_item(self, level_entity: InstanceConfig) -> QtWidgets.QListWidgetItem:
        """构造关卡实体在列表中的展示项与搜索信息。"""
        metadata = getattr(level_entity, "metadata", {}) or {}
        guid_text = ""
        if isinstance(metadata, dict):
            raw_guid = metadata.get("guid")
            if raw_guid is not None:
                guid_text = str(raw_guid)

        position_text = f"({level_entity.position[0]:.1f}, {level_entity.position[1]:.1f}, {level_entity.position[2]:.1f})"
        rotation_text = f"({level_entity.rotation[0]:.1f}, {level_entity.rotation[1]:.1f}, {level_entity.rotation[2]:.1f})"

        # 使用与左侧“关卡实体”分类一致的图标，保证实体列表与分类树的视觉语义统一。
        display_text = f"{LEVEL_ENTITY_ICON} {level_entity.name}"

        item = QtWidgets.QListWidgetItem(display_text)
        item.setData(INSTANCE_ID_ROLE, level_entity.instance_id)
        item.setData(ENTITY_TYPE_ROLE, "关卡")

        tooltip_lines: list[str] = [
            f"实体名称: {level_entity.name}",
            "实体类型: 关卡实体",
            f"位置: {position_text}",
            f"旋转: {rotation_text}",
        ]
        if guid_text:
            tooltip_lines.append(f"GUID: {guid_text}")
        item.setToolTip("\n".join(tooltip_lines))

        search_tokens = [
            level_entity.name,
            "关卡实体",
            "关卡",
            guid_text,
            position_text,
            rotation_text,
        ]
        search_value = " ".join(token for token in search_tokens if token)
        item.setData(SEARCH_TEXT_ROLE, search_value.lower())

        return item

    def _ensure_level_entity_exists(self) -> None:
        """确保当前视图下存在关卡实体。

        - 对于具体存档视图（PackageView）：
          - 若索引中已有 level_entity_id，直接复用；
          - 若不存在但实例中存在带 is_level_entity 标记的实体，则补写索引；
          - 否则创建新的关卡实体实例并写入索引与资源库。
        - 对于全局视图：
          - 若已存在带 is_level_entity 标记的实例则复用；
          - 否则创建新的关卡实体实例，仅写入资源库，不修改任何存档索引。
        """
        if not self.current_package:
            return

        # 已有关卡实体则无需重复创建
        level_entity = getattr(self.current_package, "level_entity", None)
        if level_entity:
            return

        # 具体存档视图
        if isinstance(self.current_package, PackageView):
            # 若已有带 is_level_entity 标记的实例，优先复用
            existing: Optional[InstanceConfig] = None
            for instance in self.current_package.instances.values():
                metadata = getattr(instance, "metadata", {}) or {}
                if isinstance(metadata, dict) and metadata.get("is_level_entity"):
                    existing = instance
                    break

            index = self.current_package.package_index

            if existing:
                index.level_entity_id = existing.instance_id
                if existing.instance_id not in index.resources.instances:
                    index.add_instance(existing.instance_id)
                # 更新视图缓存并持久化
                self.current_package.update_level_entity(existing)
                return

            # 创建新的关卡实体实例
            package_id = getattr(self.current_package, "package_id", "")
            instance_id = f"level_{package_id}" if package_id else generate_prefixed_id("level")
            new_level = InstanceConfig(
                instance_id=instance_id,
                name="关卡实体",
                template_id=instance_id,
                position=[0.0, 0.0, 0.0],
                rotation=[0.0, 0.0, 0.0],
                metadata={"is_level_entity": True, "entity_type": "关卡"},
            )

            index.level_entity_id = instance_id
            index.add_instance(instance_id)
            self.current_package.update_level_entity(new_level)
            return

        # 全局视图：只需在资源库层面保证存在一个带 is_level_entity 标记的实例
        if isinstance(self.current_package, GlobalResourceView):
            # level_entity 属性已在开头检查为 None，这里直接创建
            instance_id = generate_prefixed_id("level")
            new_level = InstanceConfig(
                instance_id=instance_id,
                name="关卡实体",
                template_id=instance_id,
                position=[0.0, 0.0, 0.0],
                rotation=[0.0, 0.0, 0.0],
                metadata={"is_level_entity": True, "entity_type": "关卡"},
            )
            self.current_package.add_instance(new_level)
