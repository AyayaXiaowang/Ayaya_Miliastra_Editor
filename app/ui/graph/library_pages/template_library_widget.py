"""元件库组件"""

import copy
import json
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union, Dict, Any, List

from PyQt6 import QtCore, QtGui, QtWidgets

from app.ui.foundation.theme_manager import Sizes
from app.ui.foundation.shared_resource_badge_delegate import (
    SHARED_RESOURCE_BADGE_ROLE,
    install_shared_resource_badge_delegate,
)
from app.ui.foundation.toast_notification import ToastNotification
from app.ui.foundation.id_generator import generate_prefixed_id
from app.ui.foundation import input_dialogs
from app.ui.foundation.context_menu_builder import ContextMenuBuilder
from app.ui.foundation.keymap_store import KeymapStore
from app.common.decorations_merge import merge_template_decorations
from app.ui.graph.library_mixins import (
    ConfirmDialogMixin,
    SearchFilterMixin,
    ToolbarMixin,
    rebuild_list_with_preserved_selection,
)
from app.ui.forms.schema_dialog import FormDialogBuilder
from engine.configs.resource_types import ResourceType
from engine.resources.package_view import PackageView
from engine.resources.global_resource_view import GlobalResourceView
from engine.resources.resource_manager import ResourceManager
from engine.resources.package_index_manager import PackageIndexManager
from engine.graph.models.package_model import TemplateConfig, ComponentConfig
from engine.graph.models.entity_templates import (
    get_entity_type_info,
    get_template_library_entity_types,
)
from engine.configs.entities.creature_models import get_creature_model_display_pairs, get_creature_model_category_for_name
from engine.utils.resource_library_layout import discover_package_resource_roots, get_shared_root_dir, get_packages_root_dir
from engine.resources.custom_variable_file_refs import normalize_custom_variable_file_refs
from app.ui.graph.library_pages.library_scaffold import (
    DualPaneLibraryScaffold,
    LibraryChangeEvent,
    LibraryPageMixin,
    LibrarySelection,
)
from app.ui.graph.library_pages.library_view_scope import describe_resource_view_scope
from app.ui.graph.library_pages.category_tree_mixin import EntityCategoryTreeMixin
from app.ui.graph.library_pages.standard_dual_pane_list_page import StandardDualPaneListPage
from app.ui.graph.library_pages.merge_decorations_dialog import (
    MergeDecorationsDialog,
    MergeDecorationsDialogItem,
)
from app.ui.graph.library_pages.template_library_widget_delete_utils import (
    build_template_delete_confirmation_message,
    collect_template_referencing_instances,
    collect_template_referencing_package_ids,
)


TEMPLATE_ID_ROLE = QtCore.Qt.ItemDataRole.UserRole
IS_SHARED_TEMPLATE_ROLE = QtCore.Qt.ItemDataRole.UserRole + 1


@dataclass(frozen=True)
class TemplateDialogConfig:
    """新建模板对话框的静态配置。"""

    title: str
    is_drop_category: bool
    default_entity_type: Optional[str]
    name_label: str
    description_label: str


class TemplateLibraryWidget(
    StandardDualPaneListPage,
    LibraryPageMixin,
    SearchFilterMixin,
    ToolbarMixin,
    EntityCategoryTreeMixin,
    ConfirmDialogMixin,
):
    """元件库界面"""

    # 统一库页选中事件：发射 LibrarySelection（或 None 表示无有效选中）。
    selection_changed = QtCore.pyqtSignal(object)
    # 当模板被新增/删除等造成持久化状态改变时发射，用于通知上层立即保存存档索引
    data_changed = QtCore.pyqtSignal(LibraryChangeEvent)
    
    def __init__(self, parent=None):
        super().__init__(
            parent,
            title="元件库",
            description="按实体类型管理可复用元件，支持快速新建、删除与搜索过滤。",
        )
        self._standard_shortcuts: list[QtGui.QShortcut] = []
        self.current_package: Optional[
            Union[PackageView, GlobalResourceView]
        ] = None
        # 当前左侧选中的分类 key（"all"、具体实体类型或扩展分类名）
        self._current_category_key: str = "all"
        # 根据当前分类推导出的“新建模板”默认实体类型（例如：掉落物/元件组 → 物件）
        self._default_entity_type_for_new: Optional[str] = None
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """设置UI"""
        self.add_template_btn = QtWidgets.QPushButton("+ 新建元件", self)
        self.duplicate_template_btn = QtWidgets.QPushButton("复制", self)
        self.merge_decorations_btn = QtWidgets.QPushButton("合并装饰物…", self)
        self.delete_template_btn = QtWidgets.QPushButton("删除", self)
        widgets = self.build_standard_dual_pane_list_ui(
            search_placeholder="搜索元件...",
            toolbar_buttons=[
                self.add_template_btn,
                self.duplicate_template_btn,
                self.merge_decorations_btn,
                self.delete_template_btn,
            ],
            left_header_label="元件分类",
            left_title="元件分类",
            left_description="按实体类型过滤元件",
            right_title="元件列表",
            right_description="双击可查看详情，支持按类型筛选",
            tree_indentation=Sizes.SPACING_MEDIUM,
            wrap_right_list=False,
        )
        self.search_edit = widgets.search_edit
        self.category_tree = widgets.category_tree
        self.template_list = widgets.list_widget

        # 与节点图库一致：共享资源使用徽章标注（避免在名称里拼接共享文本前缀）。
        install_shared_resource_badge_delegate(self.template_list)
        
        # 连接信号
        self.add_template_btn.clicked.connect(self._add_template)
        self.duplicate_template_btn.clicked.connect(self._duplicate_template)
        self.merge_decorations_btn.clicked.connect(self._merge_decorations_into_one_template)
        self.delete_template_btn.clicked.connect(self._delete_template)
        self.template_list.itemClicked.connect(self._on_template_clicked)
        self.template_list.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.template_list.customContextMenuRequested.connect(self._show_template_context_menu)
        self.connect_search(self.search_edit, self._filter_templates, placeholder="搜索元件...")

        self._install_standard_shortcuts()
        
        # 初始化分类树
        self._init_category_tree()

    def apply_keymap_shortcuts(self, keymap_store: object) -> None:
        """由主窗口调用：在快捷键配置变更后刷新本页快捷键绑定。"""
        self._install_standard_shortcuts(keymap_store=keymap_store)

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

    def _install_standard_shortcuts(self, *, keymap_store: object | None = None) -> None:
        """统一快捷键（尽量与其它库页一致）。"""
        resolved = keymap_store if keymap_store is not None else self._resolve_keymap_store()
        get_primary = getattr(resolved, "get_primary_shortcut", None) if resolved is not None else None

        def _primary(action_id: str) -> str:
            if callable(get_primary):
                return str(get_primary(action_id) or "")
            defaults = KeymapStore.get_default_shortcuts(action_id)
            return defaults[0] if defaults else ""

        self._clear_standard_shortcuts()

        # 新建：挂在页面自身（允许在搜索框聚焦时也能新建）
        shortcut_new = _primary("library.new")
        if shortcut_new:
            sc = QtGui.QShortcut(QtGui.QKeySequence(shortcut_new), self)
            sc.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(self._add_template)
            self._standard_shortcuts.append(sc)

        # 其余动作：尽量只在列表聚焦时触发，避免干扰输入框编辑
        shortcut_dup = _primary("library.duplicate")
        if shortcut_dup:
            sc = QtGui.QShortcut(QtGui.QKeySequence(shortcut_dup), self.template_list)
            sc.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(self._duplicate_template)
            self._standard_shortcuts.append(sc)

        shortcut_delete = _primary("library.delete")
        if shortcut_delete:
            sc = QtGui.QShortcut(QtGui.QKeySequence(shortcut_delete), self.template_list)
            sc.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(self._delete_template)
            self._standard_shortcuts.append(sc)

        shortcut_rename = _primary("library.rename")
        if shortcut_rename:
            sc = QtGui.QShortcut(QtGui.QKeySequence(shortcut_rename), self.template_list)
            sc.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(self._rename_template)
            self._standard_shortcuts.append(sc)

        shortcut_move = _primary("library.move")
        if shortcut_move:
            sc = QtGui.QShortcut(QtGui.QKeySequence(shortcut_move), self.template_list)
            sc.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(self._change_selected_template_owner)
            self._standard_shortcuts.append(sc)

        shortcut_locate = _primary("library.locate_issues")
        if shortcut_locate:
            sc = QtGui.QShortcut(QtGui.QKeySequence(shortcut_locate), self.template_list)
            sc.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(self._locate_issues_for_selected_template)
            self._standard_shortcuts.append(sc)

    def _show_template_context_menu(self, pos: QtCore.QPoint) -> None:
        """右键菜单：与实体摆放/战斗预设/节点图库保持一致的动作集合。"""
        has_item = self.template_list.itemAt(pos) is not None
        shortcut_new = self._primary_shortcut("library.new") or None
        shortcut_dup = self._primary_shortcut("library.duplicate") or None
        shortcut_rename = self._primary_shortcut("library.rename") or None
        shortcut_move = self._primary_shortcut("library.move") or None
        shortcut_locate = self._primary_shortcut("library.locate_issues") or None
        shortcut_delete = self._primary_shortcut("library.delete") or None
        builder = ContextMenuBuilder(self)
        builder.add_action("新建", self._add_template, shortcut=shortcut_new)
        builder.add_separator()
        builder.add_action("复制", self._duplicate_template, enabled=has_item, shortcut=shortcut_dup)
        builder.add_action("合并装饰物…", self._merge_decorations_into_one_template, enabled=has_item)
        builder.add_action("重命名", self._rename_template, enabled=has_item, shortcut=shortcut_rename)
        builder.add_action(
            "移动（所属存档）", self._change_selected_template_owner, enabled=has_item, shortcut=shortcut_move
        )
        builder.add_separator()
        builder.add_action(
            "定位问题", self._locate_issues_for_selected_template, enabled=has_item, shortcut=shortcut_locate
        )
        builder.add_separator()
        builder.add_action("删除", self._delete_template, enabled=has_item, shortcut=shortcut_delete)
        builder.exec_for(self.template_list, pos)
    
    def _init_category_tree(self) -> None:
        """初始化分类树"""
        items = self.build_entity_category_tree(
            self.category_tree,
            all_label="📁 全部元件",
            entity_label_suffix="",
            include_level_entity=False,
        )
        self._category_items = items
        self.category_tree.setCurrentItem(items["all"])
        self.category_tree.itemClicked.connect(self._on_category_clicked)
        # 初始化时同步一次“新建元件”按钮文案
        self._update_add_button_label("all")
    
    # === LibraryPage 协议实现 ===

    def set_context(
        self,
        package: Union[PackageView, GlobalResourceView],
    ) -> None:
        """设置当前资源视图并全量刷新列表（统一库页入口）。"""
        self.current_package = package
        self.refresh_templates()

    def reload(self) -> None:
        """在当前上下文下全量刷新列表并负责选中恢复。"""
        self.refresh_templates()

    def get_selection(self) -> Optional[LibrarySelection]:
        """返回当前选中的模板（若存在）。"""
        current_item = self.template_list.currentItem()
        if current_item is None:
            return None
        value = current_item.data(TEMPLATE_ID_ROLE)
        if not isinstance(value, str) or not value:
            return None
        return LibrarySelection(
            kind="template",
            id=value,
            context={"scope": describe_resource_view_scope(self.current_package)},
        )

    def set_selection(self, selection: Optional[LibrarySelection]) -> None:
        """根据 LibrarySelection 恢复模板选中状态。"""
        if selection is None:
            self.template_list.setCurrentItem(None)
            return
        if selection.kind != "template":
            return
        template_id = selection.id
        if not template_id:
            return
        self.select_template(template_id)
    
    def refresh_templates(self, filter_type: Optional[str] = None) -> None:
        """刷新模板列表。

        filter_type 为空时使用当前分类 key（_current_category_key）作为过滤条件，
        以便在属性面板修改后仍保持左侧分类选择一致。
        
        行为约定：
        - 若刷新前存在选中模板且该模板仍在当前过滤结果中，则恢复选中并发出选中信号；
        - 若刷新后当前列表中已不包含原选中模板，但列表中还有其他内容，则默认选中列表中的
          第一个模板，并发出对应的选中信号，让右侧属性面板自然切换到新的上下文；
        - 若刷新后当前列表为空且此前存在选中模板，则发出一个“空 ID”的选中信号，交由上层
          清空/隐藏右侧属性面板；
        - 若刷新前本就没有选中项，则在列表非空时同样默认选中第一个模板，以保持“有内容就有
          当前焦点”的体验。
        """
        current_item = self.template_list.currentItem()
        previously_selected_id = (
            current_item.data(TEMPLATE_ID_ROLE) if current_item is not None else None
        )

        def build_items() -> None:
            if not self.current_package:
                return

            shared_template_ids: set[str] = set()
            resource_manager_candidate = getattr(self.current_package, "resource_manager", None)
            if isinstance(resource_manager_candidate, ResourceManager):
                resource_library_dir = getattr(resource_manager_candidate, "resource_library_dir", None)
                if isinstance(resource_library_dir, Path):
                    shared_root_dir = get_shared_root_dir(resource_library_dir)
                    shared_root_abs = (
                        shared_root_dir if shared_root_dir.is_absolute() else shared_root_dir.absolute()
                    )
                    shared_parts = tuple(part.casefold() for part in shared_root_abs.parts)
                    template_paths = resource_manager_candidate.list_resource_file_paths(ResourceType.TEMPLATE)
                    for resource_id, file_path in template_paths.items():
                        if not isinstance(resource_id, str) or not resource_id:
                            continue
                        if not isinstance(file_path, Path):
                            continue
                        file_abs = file_path if file_path.is_absolute() else file_path.absolute()
                        if hasattr(file_abs, "is_relative_to"):
                            if file_abs.is_relative_to(shared_root_abs):  # type: ignore[attr-defined]
                                shared_template_ids.add(resource_id)
                        else:
                            file_parts = tuple(part.casefold() for part in file_abs.parts)
                            if len(file_parts) >= len(shared_parts) and file_parts[: len(shared_parts)] == shared_parts:
                                shared_template_ids.add(resource_id)

            effective_filter = (
                filter_type if filter_type is not None else self._current_category_key or "all"
            )

            allowed_types = set(get_template_library_entity_types())

            for template_id, template in self.current_package.templates.items():
                if template.entity_type not in allowed_types:
                    continue

                metadata = getattr(template, "metadata", {}) or {}
                category = ""
                if isinstance(metadata, dict):
                    category_value = metadata.get("template_category") or metadata.get("category")
                    if isinstance(category_value, str):
                        category = category_value

                if effective_filter != "all":
                    if effective_filter in allowed_types:
                        if template.entity_type != effective_filter:
                            continue
                        if category in ("元件组", "掉落物"):
                            continue
                    elif effective_filter in ("元件组", "掉落物"):
                        if category != effective_filter:
                            continue

                if category in ("元件组", "掉落物"):
                    icon = get_entity_type_info(category).get("icon", "📦")
                else:
                    icon = get_entity_type_info(template.entity_type).get("icon", "📦")

                is_shared_template = template_id in shared_template_ids
                list_item = QtWidgets.QListWidgetItem(f"{icon} {template.name}")
                list_item.setData(TEMPLATE_ID_ROLE, template_id)
                list_item.setData(IS_SHARED_TEMPLATE_ROLE, bool(is_shared_template))
                list_item.setData(SHARED_RESOURCE_BADGE_ROLE, bool(is_shared_template))

                tooltip_lines: list[str] = []
                if is_shared_template:
                    tooltip_lines.append("归属: 共享（所有存档可见）")
                tooltip_lines.append(f"类型: {template.entity_type}")
                if category != "掉落物":
                    tooltip_lines.append(
                        f"节点图: {len(getattr(template, 'default_graphs', []))}"
                    )
                variable_ref = ""
                if isinstance(metadata, dict):
                    refs = normalize_custom_variable_file_refs(metadata.get("custom_variable_file"))
                    variable_ref = " / ".join(refs)
                tooltip_lines.append(
                    f"变量文件: {variable_ref}" if variable_ref else "变量文件: 未配置"
                )
                tooltip_lines.append(
                    f"组件: {len(getattr(template, 'default_components', []))}"
                )
                list_item.setToolTip("\n".join(tooltip_lines))

                self.template_list.addItem(list_item)

        def get_item_key(list_item: QtWidgets.QListWidgetItem) -> Optional[str]:
            value = list_item.data(TEMPLATE_ID_ROLE)
            if isinstance(value, str):
                return value
            return None

        def emit_selection_for_template(template_id: Any) -> None:
            if not isinstance(template_id, str) or not template_id:
                return
            selection = LibrarySelection(
                kind="template",
                id=template_id,
                context={"scope": describe_resource_view_scope(self.current_package)},
            )
            self.notify_selection_state(True, context={"source": "template"})
            self.selection_changed.emit(selection)

        def emit_empty_selection() -> None:
            self.notify_selection_state(False, context={"source": "template"})
            self.selection_changed.emit(None)

        rebuild_list_with_preserved_selection(
            self.template_list,
            previous_key=previously_selected_id,
            had_selection_before_refresh=bool(previously_selected_id),
            build_items=build_items,
            key_getter=get_item_key,
            on_restored_selection=emit_selection_for_template,
            on_first_selection=emit_selection_for_template,
            on_cleared_selection=emit_empty_selection,
        )

    # === 内部辅助 ===

    def _on_category_clicked(self, item: QtWidgets.QTreeWidgetItem, column: int) -> None:
        """分类点击"""
        category = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not category:
            category = "all"
        self._current_category_key = category
        self._default_entity_type_for_new = self._resolve_default_entity_type_for_category(category)
        self._update_add_button_label(category)
        self.refresh_templates(category)

    def _resolve_default_entity_type_for_category(self, category: str) -> Optional[str]:
        """根据当前分类推导新建模板时的默认实体类型。

        - 物件/造物：直接对应同名实体类型
        - 元件组、掉落物：目前仍落在物件实体类型下
        - 其他或全部：返回 None，交给对话框使用默认顺序
        """
        if category in get_template_library_entity_types():
            return category
        if category in ("元件组", "掉落物"):
            return "物件"
        return None

    def _update_add_button_label(self, category: str) -> None:
        """根据当前分类更新“新建元件”按钮的文案。"""
        if category == "all":
            self.add_template_btn.setText("+ 新建元件")
            return
        if category == "造物":
            self.add_template_btn.setText("+ 新建造物元件")
            return
        if category == "物件":
            self.add_template_btn.setText("+ 新建物件元件")
            return
        if category == "掉落物":
            # 掉落物不再强调“模板”概念，直接以具体掉落物为单位管理
            self.add_template_btn.setText("+ 新建掉落物")
            return
        if category == "元件组":
            self.add_template_btn.setText("+ 新建元件组")
            return
        # 兜底：未知分类仍使用通用文案
        self.add_template_btn.setText("+ 新建元件")
    
    def _prompt_template_dialog(self) -> Optional[dict]:
        """使用通用 FormDialogBuilder 采集元件信息。

        该方法仅负责组织对话框流程，本体逻辑拆分为数个小型辅助方法，以降低单个方法的心智负担：
        - `_build_template_dialog_config()`：根据当前分类生成标题与标签配置；
        - `_build_name_and_description_fields()`：构建基础文本字段；
        - `_build_entity_type_combo()` 与 `_wire_entity_type_and_model_combos()`：负责实体类型与模型下拉联动；
        - `_build_drop_model_id_field()` 与 `_build_template_metadata()`：处理掉落物特有字段与 metadata 组装。
        """
        dialog_config = self._build_template_dialog_config()

        builder = FormDialogBuilder(self, dialog_config.title, fixed_size=(500, 460))

        # 名称与描述/备注字段
        name_edit, description_edit = self._build_name_and_description_fields(
            builder,
            dialog_config,
        )

        # 模型选择：
        # - 实体类型为“造物”时：从配置枚举中选择一个具体模型
        # - 实体类型为“物件”（含掉落物分类）：仅提供“空模型”这一选项
        creature_model_pairs = get_creature_model_display_pairs()
        model_combo = builder.add_combo_box("模型:", [""])

        entity_type_combo: Optional[QtWidgets.QComboBox]
        drop_model_id_edit: Optional[QtWidgets.QLineEdit]

        if dialog_config.is_drop_category:
            # 掉落物：实体类型隐含为“物件”，模型下拉固定为空模型，并追加模型 ID 字段。
            entity_type_combo = None
            self._configure_model_combo_for_drop_category(model_combo)
            drop_model_id_edit = self._build_drop_model_id_field(builder)
        else:
            entity_type_combo = self._build_entity_type_combo(
                builder,
                dialog_config.default_entity_type,
            )
            self._wire_entity_type_and_model_combos(
                entity_type_combo,
                model_combo,
                creature_model_pairs,
            )
            drop_model_id_edit = None

        self._attach_template_dialog_validation(
            builder,
            name_edit,
            dialog_config.is_drop_category,
        )

        if not builder.exec():
            return None

        entity_type_value = self._extract_entity_type_from_dialog(
            dialog_config.is_drop_category,
            entity_type_combo,
        )
        if entity_type_value is None:
            return None

        result: Dict[str, Any] = {
            "name": name_edit.text().strip(),
            "entity_type": entity_type_value,
            "description": description_edit.toPlainText().strip(),
        }

        metadata = self._build_template_metadata(
            entity_type_value=entity_type_value,
            is_drop_category=dialog_config.is_drop_category,
            model_combo=model_combo,
            drop_model_id_edit=drop_model_id_edit,
        )
        if metadata:
            result["metadata"] = metadata

        return result

    def _build_template_dialog_config(self) -> TemplateDialogConfig:
        """根据当前分类推导新建模板对话框的标题与基础标签配置。"""
        default_entity_type = self._default_entity_type_for_new
        is_drop_category = self._current_category_key == "掉落物"

        dialog_title = "新建元件"
        if is_drop_category:
            dialog_title = "新建掉落物"
        elif default_entity_type == "造物":
            dialog_title = "新建造物元件"
        elif default_entity_type == "物件":
            dialog_title = "新建物件元件"

        if is_drop_category:
            name_label = "掉落物名称*:"
            description_label = "备注"
        else:
            name_label = "元件名称*:"
            description_label = "描述"

        return TemplateDialogConfig(
            title=dialog_title,
            is_drop_category=is_drop_category,
            default_entity_type=default_entity_type,
            name_label=name_label,
            description_label=description_label,
        )

    def _build_name_and_description_fields(
        self,
        builder: FormDialogBuilder,
        dialog_config: TemplateDialogConfig,
    ) -> tuple[QtWidgets.QLineEdit, QtWidgets.QTextEdit]:
        """构建名称与描述/备注字段。"""
        name_edit = builder.add_line_edit(
            dialog_config.name_label,
            "",
            "例如：火焰陷阱",
        )
        description_edit = builder.add_plain_text_edit(
            dialog_config.description_label,
            "",
            min_height=120,
            max_height=200,
        )
        return name_edit, description_edit

    def _build_entity_type_combo(
        self,
        builder: FormDialogBuilder,
        default_entity_type: Optional[str],
    ) -> QtWidgets.QComboBox:
        """构建实体类型下拉框，并根据默认实体类型预选。"""
        entity_types = get_template_library_entity_types()
        display_labels: list[str] = []
        for entity_type in entity_types:
            icon = get_entity_type_info(entity_type).get("icon", "📦")
            display_labels.append(f"{icon} {entity_type}")
        entity_type_combo = builder.add_combo_box("实体类型*:", display_labels)
        for index, entity_type in enumerate(entity_types):
            entity_type_combo.setItemData(index, entity_type)
            if default_entity_type and entity_type == default_entity_type:
                entity_type_combo.setCurrentIndex(index)
        return entity_type_combo

    def _wire_entity_type_and_model_combos(
        self,
        entity_type_combo: QtWidgets.QComboBox,
        model_combo: QtWidgets.QComboBox,
        creature_model_pairs: list[tuple[str, str]],
    ) -> None:
        """根据实体类型刷新模型下拉框内容，并在初始化与变更时保持同步。"""

        def rebuild_model_items(entity_type_value: Optional[str]) -> None:
            model_combo.blockSignals(True)
            model_combo.clear()
            if entity_type_value == "造物":
                model_combo.addItem("请选择模型")
                model_combo.setItemData(0, None)
                for index, (display_label, model_name) in enumerate(
                    creature_model_pairs,
                    start=1,
                ):
                    model_combo.addItem(display_label)
                    model_combo.setItemData(index, model_name)
                model_combo.setEnabled(True)
                model_combo.setCurrentIndex(0)
            else:
                model_combo.addItem("空模型")
                model_combo.setItemData(0, "空模型")
                model_combo.setEnabled(False)
                model_combo.setCurrentIndex(0)
            model_combo.blockSignals(False)

        initial_index = entity_type_combo.currentIndex()
        initial_entity_type = (
            entity_type_combo.itemData(initial_index) if initial_index >= 0 else None
        )
        rebuild_model_items(initial_entity_type)

        def handle_entity_type_changed(index: int) -> None:
            entity_type_value = entity_type_combo.itemData(index) if index >= 0 else None
            rebuild_model_items(entity_type_value)

        entity_type_combo.currentIndexChanged.connect(handle_entity_type_changed)

    @staticmethod
    def _configure_model_combo_for_drop_category(model_combo: QtWidgets.QComboBox) -> None:
        """配置掉落物场景下的模型下拉框（固定为空模型）。"""
        model_combo.clear()
        model_combo.addItem("空模型")
        model_combo.setItemData(0, "空模型")
        model_combo.setEnabled(False)
        model_combo.setCurrentIndex(0)

    def _build_drop_model_id_field(
        self,
        builder: FormDialogBuilder,
    ) -> QtWidgets.QLineEdit:
        """构建掉落物专用的模型 ID 输入框。"""
        model_id_edit = builder.add_line_edit("模型ID:", "", "仅数字，例如：1001")
        model_id_edit.setValidator(QtGui.QIntValidator(0, 999999999, model_id_edit))
        return model_id_edit

    def _attach_template_dialog_validation(
        self,
        builder: FormDialogBuilder,
        name_edit: QtWidgets.QLineEdit,
        is_drop_category: bool,
    ) -> None:
        """为表单对话框绑定基础必填校验逻辑。"""

        def validate(dialog_self):
            if not name_edit.text().strip():
                if is_drop_category:
                    dialog_self.show_error("请输入掉落物名称")
                else:
                    dialog_self.show_error("请输入元件名称")
                return False
            return True

        builder.dialog.validate = types.MethodType(validate, builder.dialog)

    @staticmethod
    def _extract_entity_type_from_dialog(
        is_drop_category: bool,
        entity_type_combo: Optional[QtWidgets.QComboBox],
    ) -> Optional[str]:
        """从表单控件中解析实体类型，掉落物固定为“物件”。"""
        if is_drop_category:
            return "物件"
        if entity_type_combo is None:
            return None
        current_index = entity_type_combo.currentIndex()
        entity_type_value = (
            entity_type_combo.itemData(current_index) if current_index >= 0 else None
        )
        if not isinstance(entity_type_value, str) or not entity_type_value:
            return None
        return entity_type_value

    def _build_template_metadata(
        self,
        *,
        entity_type_value: str,
        is_drop_category: bool,
        model_combo: QtWidgets.QComboBox,
        drop_model_id_edit: Optional[QtWidgets.QLineEdit],
    ) -> Dict[str, Any]:
        """根据实体类型与对话框输入构造模板 metadata。"""
        metadata: Dict[str, Any] = {}

        model_index = model_combo.currentIndex()
        model_name = model_combo.itemData(model_index) if model_index >= 0 else None

        # 将造物/物件的模型信息写入 metadata，供后续持久化和逻辑使用
        if entity_type_value == "造物":
            if isinstance(model_name, str) and model_name:
                category_name = get_creature_model_category_for_name(model_name) or ""
                metadata["creature_model_name"] = model_name
                metadata["creature_model_category"] = category_name
        else:
            # 物件与掉落物当前只允许“空模型”，仍写入 metadata 便于后续逻辑判断
            if isinstance(model_name, str) and model_name:
                metadata["object_model_name"] = model_name

        # 掉落物标记与模型ID
        if is_drop_category:
            metadata["template_category"] = "掉落物"
            metadata["is_drop_item"] = True
            if drop_model_id_edit is not None:
                model_id_text = drop_model_id_edit.text().strip()
                if model_id_text:
                    metadata["drop_model_id"] = int(model_id_text)

        return metadata

    def _add_template(self) -> None:
        """添加模板"""
        if not self.current_package:
            self.show_warning("警告", "请先选择或创建存档")
            return
        
        dialog_result = self._prompt_template_dialog()
        if not dialog_result:
            return

        metadata = dialog_result.get("metadata", {}) or {}

        # 掉落物：初始自带“特效播放”和“战利品”两个组件
        default_components: list[ComponentConfig] = []
        if isinstance(metadata, dict) and metadata.get("template_category") == "掉落物":
            default_components = [
                ComponentConfig(component_type="特效播放"),
                ComponentConfig(component_type="战利品"),
            ]

        # 创建模板
        template_id = generate_prefixed_id("template")
        template = TemplateConfig(
            template_id=template_id,
            name=dialog_result["name"],
            entity_type=dialog_result["entity_type"],
            description=dialog_result["description"],
            default_components=default_components,
            metadata=metadata,
        )
        
        self.current_package.add_template(template)
        self.refresh_templates()
        
        # 选中新创建的模板
        for i in range(self.template_list.count()):
            item = self.template_list.item(i)
            if item.data(TEMPLATE_ID_ROLE) == template_id:
                self.template_list.setCurrentItem(item)
                selection = LibrarySelection(
                    kind="template",
                    id=template_id,
                    context={"scope": describe_resource_view_scope(self.current_package)},
                )
                self.notify_selection_state(True, context={"source": "template"})
                self.selection_changed.emit(selection)
                break

        # 通知上层：模板库发生了持久化相关变更（需立即保存包索引）
        event = LibraryChangeEvent(
            kind="template",
            id=template_id,
            operation="create",
            context={"scope": describe_resource_view_scope(self.current_package)},
        )
        self.data_changed.emit(event)

    def _duplicate_template(self) -> None:
        """复制当前选中的元件（浅复制）。

        复制规则：
        - 生成新的 template_id；
        - 名称追加“ - 副本”后缀；
        - 复制默认节点图引用/变量/组件/元数据等内容；
        - `metadata["guid"]` 默认清空（GUID 需要保持唯一）。
        """
        if not self.current_package:
            self.show_warning("警告", "请先选择或创建存档")
            return

        current_item = self.template_list.currentItem()
        if current_item is None:
            self.show_warning("提示", "请先选择要复制的元件")
            return

        template_id = current_item.data(TEMPLATE_ID_ROLE)
        if not isinstance(template_id, str) or not template_id:
            return

        template = self.current_package.get_template(template_id)  # type: ignore[call-arg]
        if template is None:
            self.refresh_templates()
            return

        new_template_id = generate_prefixed_id("template")
        new_name = f"{template.name} - 副本"

        new_metadata = copy.deepcopy(getattr(template, "metadata", {}) or {})
        if isinstance(new_metadata, dict):
            new_metadata.pop("guid", None)
        else:
            new_metadata = {}

        new_template = TemplateConfig(
            template_id=new_template_id,
            name=new_name,
            entity_type=str(getattr(template, "entity_type", "") or ""),
            description=str(getattr(template, "description", "") or ""),
            default_graphs=list(getattr(template, "default_graphs", []) or []),
            default_components=copy.deepcopy(getattr(template, "default_components", []) or []),
            entity_config=copy.deepcopy(getattr(template, "entity_config", {}) or {}),
            metadata=new_metadata,
            graph_variable_overrides=copy.deepcopy(getattr(template, "graph_variable_overrides", {}) or {}),
        )

        self.current_package.add_template(new_template)
        self.refresh_templates()
        self.select_template(new_template_id)

        event = LibraryChangeEvent(
            kind="template",
            id=new_template_id,
            operation="create",
            context={
                "scope": describe_resource_view_scope(self.current_package),
                "source": "duplicate",
            },
        )
        self.data_changed.emit(event)
        ToastNotification.show_message(self, f"已复制元件：{new_name}", "success")

    # ------------------------------------------------------------------ Decorations merge (project-level)

    def _merge_decorations_into_one_template(self) -> None:
        """将多个元件的 decorations 合并到同一个目标元件（项目资源级）。"""
        if not isinstance(self.current_package, PackageView):
            self.show_warning("提示", "请先切换到具体项目存档视图（非 <全部资源>）再使用“合并装饰物”。")
            return

        package = self.current_package
        package_id = str(getattr(package, "package_id", "") or "").strip()
        resource_manager = getattr(package, "resource_manager", None)
        if not isinstance(resource_manager, ResourceManager):
            self.show_warning("警告", "ResourceManager 不可用，无法执行合并。")
            return

        resource_library_dir = getattr(resource_manager, "resource_library_dir", None)
        if not isinstance(resource_library_dir, Path):
            self.show_warning("警告", "无法解析资源库根目录（resource_library_dir）。")
            return

        # 仅允许选择“当前项目存档目录”下的元件条目（不含共享根目录资源）。
        package_root_dir = get_packages_root_dir(resource_library_dir) / package_id
        package_root_abs = (
            package_root_dir if package_root_dir.is_absolute() else package_root_dir.absolute()
        )
        pkg_parts = tuple(part.casefold() for part in package_root_abs.parts)
        template_paths = resource_manager.list_resource_file_paths(ResourceType.TEMPLATE)

        items: list[MergeDecorationsDialogItem] = []
        for template_id, template in package.templates.items():
            if not isinstance(template_id, str) or not template_id:
                continue
            file_path = template_paths.get(template_id)
            if not isinstance(file_path, Path):
                continue

            file_abs = file_path if file_path.is_absolute() else file_path.absolute()
            if hasattr(file_abs, "is_relative_to"):
                if not file_abs.is_relative_to(package_root_abs):  # type: ignore[attr-defined]
                    continue
            else:
                f_parts = tuple(part.casefold() for part in file_abs.parts)
                if len(f_parts) < len(pkg_parts) or f_parts[: len(pkg_parts)] != pkg_parts:
                    continue

            # Decorations count from template.metadata
            deco_count = 0
            metadata = getattr(template, "metadata", {}) or {}
            if isinstance(metadata, dict):
                ci = metadata.get("common_inspector") if isinstance(metadata.get("common_inspector"), dict) else {}
                model = ci.get("model") if isinstance(ci.get("model"), dict) else {}
                decos = model.get("decorations")
                if isinstance(decos, list):
                    # Count dict entries + non-empty string entries (compat with legacy string list)
                    deco_count = int(
                        len([x for x in decos if isinstance(x, dict) or (isinstance(x, str) and x.strip())])
                    )

            category = ""
            if isinstance(metadata, dict):
                category_value = metadata.get("template_category") or metadata.get("category")
                if isinstance(category_value, str):
                    category = category_value.strip()

            if category in ("元件组", "掉落物"):
                icon = get_entity_type_info(category).get("icon", "📦")
            else:
                icon = get_entity_type_info(template.entity_type).get("icon", "📦")

            name_text = str(getattr(template, "name", "") or "").strip() or template_id
            display_text = f"{icon} {name_text}"
            search_text = " ".join(
                token
                for token in [
                    name_text,
                    template_id,
                    str(getattr(template, "entity_type", "") or "").strip(),
                    category,
                    str(deco_count),
                ]
                if token
            )
            items.append(
                MergeDecorationsDialogItem(
                    instance_id=template_id,
                    display_text=display_text,
                    search_text=search_text,
                    decorations_count=int(deco_count),
                )
            )

        if not items:
            self.show_warning("提示", "当前项目存档目录下没有可用的元件资源。")
            return

        items.sort(key=lambda it: it.display_text.casefold())

        dialog = MergeDecorationsDialog(
            items=items,
            package_id=package_id,
            source_kind_label="元件",
            target_kind_label="元件",
            default_new_name=f"装饰物合并元件_{package_id}" if package_id else "装饰物合并元件",
            show_center_policy=False,
            parent=self,
        )
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return

        source_ids = dialog.get_selected_source_instance_ids()
        target_choice_id = dialog.get_target_instance_id()

        op = "update"
        include_target_existing = True
        if target_choice_id == "__new__":
            new_template_id = generate_prefixed_id("template")
            target_template = TemplateConfig(
                template_id=new_template_id,
                name=dialog.get_new_instance_name(),
                entity_type="物件",
                description="由“合并装饰物”工具生成",
                default_graphs=[],
                default_components=[],
                entity_config={
                    "render": {"model_name": "空模型", "visible": True},
                },
                metadata={
                    "object_model_name": "空模型",
                },
                graph_variable_overrides={},
            )
            op = "create"
            include_target_existing = False
        else:
            target_template = package.get_template(target_choice_id)  # type: ignore[call-arg]
            if target_template is None:
                self.refresh_templates()
                self.show_warning("提示", "目标元件不存在或已被移除，请刷新后重试。")
                return

        # Build source templates list (exclude target itself to avoid duplication when keeping target existing).
        source_templates: list[TemplateConfig] = []
        target_id_text = str(getattr(target_template, "template_id", "") or "").strip()
        for sid in source_ids:
            if sid == target_id_text:
                continue
            tmpl = package.get_template(sid)  # type: ignore[call-arg]
            if tmpl is None:
                continue
            source_templates.append(tmpl)

        outcome = merge_template_decorations(
            source_templates=source_templates,
            target_template=target_template,
            include_target_existing=include_target_existing,
            center=dialog.should_center(),
            center_mode=dialog.get_center_mode(),
            center_axes=dialog.get_center_axes(),
        )

        updated_target = outcome.target_template
        package.add_template(updated_target)

        event = LibraryChangeEvent(
            kind="template",
            id=updated_target.template_id,
            operation=op,
            context={
                "scope": describe_resource_view_scope(package),
                "action": "merge_decorations",
            },
        )
        self.data_changed.emit(event)

        removed_ids: list[str] = []
        if dialog.should_remove_sources():
            window = self.window()
            app_state = getattr(window, "app_state", None) if window is not None else None
            package_index_manager = (
                getattr(app_state, "package_index_manager", None) if app_state is not None else None
            )
            if not isinstance(package_index_manager, PackageIndexManager):
                # 兼容旧别名（逐步迁移中）
                package_index_manager = getattr(window, "package_index_manager", None) if window is not None else None

            if not isinstance(package_index_manager, PackageIndexManager):
                self.show_warning("警告", "无法移除源元件：PackageIndexManager 不可用。")
            else:
                for sid in source_ids:
                    if sid == updated_target.template_id:
                        continue
                    moved_ok = package_index_manager.remove_resource_from_package(
                        package.package_id,
                        "template",
                        sid,
                    )
                    if not moved_ok:
                        continue
                    removed_ids.append(sid)
                    package.remove_template(sid)

                if removed_ids and hasattr(package, "clear_cache"):
                    package.clear_cache()

                for rid in removed_ids:
                    self.data_changed.emit(
                        LibraryChangeEvent(
                            kind="template",
                            id=rid,
                            operation="delete",
                            context={
                                "scope": describe_resource_view_scope(package),
                                "action": "merge_decorations_remove_sources",
                            },
                        )
                    )

        self.refresh_templates()
        self.select_template(updated_target.template_id)

        skipped = len(outcome.skipped_template_ids)
        removed = len(removed_ids)
        msg = f"已合并装饰物：{len(outcome.merged_decorations)} 个 → {updated_target.name}"
        if skipped:
            msg += f"（跳过 {skipped} 个无装饰物元件）"
        if removed:
            msg += f"（已移除 {removed} 个源元件）"
        ToastNotification.show_message(self, msg, "success")

    def _rename_template(self) -> None:
        """重命名当前选中的元件（仅修改 name 字段）。"""
        if not self.current_package:
            self.show_warning("警告", "请先选择或创建存档")
            return

        current_item = self.template_list.currentItem()
        if current_item is None:
            self.show_warning("提示", "请先选择要重命名的元件")
            return

        template_id = current_item.data(TEMPLATE_ID_ROLE)
        if not isinstance(template_id, str) or not template_id:
            return

        template = self.current_package.get_template(template_id)  # type: ignore[call-arg]
        if template is None:
            self.refresh_templates()
            return

        old_name = str(getattr(template, "name", "") or "").strip() or template_id
        new_name = input_dialogs.prompt_text(
            self,
            "重命名元件",
            "请输入新的元件名称:",
            text=old_name,
        )
        if not new_name:
            return
        new_name = str(new_name).strip()
        if not new_name or new_name == old_name:
            return

        template.name = new_name
        self.refresh_templates()
        self.select_template(template_id)

        event = LibraryChangeEvent(
            kind="template",
            id=template_id,
            operation="update",
            context={
                "scope": describe_resource_view_scope(self.current_package),
                "action": "rename",
            },
        )
        self.data_changed.emit(event)
        ToastNotification.show_message(self, f"已重命名元件：{new_name}", "info")

    def _change_selected_template_owner(self) -> None:
        """修改当前选中元件的归属位置（共享 / 某个项目存档目录）。"""
        if not self.current_package:
            self.show_warning("警告", "请先选择或创建存档")
            return

        current_item = self.template_list.currentItem()
        if current_item is None:
            self.show_warning("提示", "请先选择要移动的元件")
            return

        template_id = current_item.data(TEMPLATE_ID_ROLE)
        if not isinstance(template_id, str) or not template_id:
            return

        window = self.window()
        app_state = getattr(window, "app_state", None) if window is not None else None
        package_index_manager = getattr(app_state, "package_index_manager", None) if app_state is not None else None
        if not isinstance(package_index_manager, PackageIndexManager):
            self.show_warning("警告", "无法移动：PackageIndexManager 不可用。")
            return

        previous_owner = package_index_manager.get_resource_owner_root_id(
            resource_type="template",
            resource_id=template_id,
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
            "移动元件（所属存档）",
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
            f"即将把元件 '{template_id}' 的归属从「{previous_label}」切换到「{next_label}」。\n\n确定要继续吗？",
        ):
            return

        handler = getattr(window, "_on_template_package_membership_changed", None) if window is not None else None
        if callable(handler):
            handler(template_id, target_root_id, True)
        else:
            moved = package_index_manager.move_resource_to_root(target_root_id, "template", template_id)
            if not moved:
                self.show_warning("警告", "移动失败：未找到资源文件或目标目录不可用。")
                return
            if hasattr(self.current_package, "clear_cache"):
                self.current_package.clear_cache()
            self.refresh_templates()

        ToastNotification.show_message(self, "归属已更新。", "info")

    def _locate_issues_for_selected_template(self) -> None:
        """打开验证面板并定位到与当前元件相关的问题（若存在）。"""
        current_item = self.template_list.currentItem()
        if current_item is None:
            self.show_warning("提示", "请先选择要定位问题的元件")
            return
        template_id = current_item.data(TEMPLATE_ID_ROLE)
        if not isinstance(template_id, str) or not template_id:
            return
        window = self.window()
        locate = getattr(window, "_locate_issues_for_resource_id", None) if window is not None else None
        if callable(locate):
            locate(template_id)
    
    def _delete_template(self) -> None:
        """删除模板。

        语义区分：
        - 具体存档视图（PackageView，目录即存档）：
          - “从当前存档移除”本质是**改变资源归属**：将模板 JSON 文件从当前项目存档根目录移出
            （默认移动到“测试项目”等默认归档项目），而不是改写某个 pkg_*.json；
          - 不执行物理删除，避免误删后难以找回。
        - 全局视图（GlobalResourceView）：
          视为“硬删除”操作：
            - 在所有存档索引中移除对该模板的引用；
            - 物理删除资源库中的模板 JSON 文件。
        """
        current_item = self.template_list.currentItem()
        if not current_item:
            self.show_warning("警告", "请先选择要删除的模板")
            return

        if not self.current_package:
            self.show_warning("警告", "当前视图尚未加载任何资源上下文，无法删除模板")
            return

        template_id = current_item.data(TEMPLATE_ID_ROLE)
        is_shared_template = bool(current_item.data(IS_SHARED_TEMPLATE_ROLE))
        if isinstance(self.current_package, PackageView) and is_shared_template:
            self.show_warning(
                "提示",
                "该元件属于【共享】资源，无法在“具体存档”视图下执行“从当前存档移除引用”。\n\n"
                "如需删除共享元件，请切换到 <全部资源> 视图进行全局删除；\n"
                "如需让元件仅属于当前存档，请在右侧属性面板中修改其“所属存档/归属位置”。",
            )
            return
        template = self.current_package.get_template(template_id)  # type: ignore[call-arg]

        if not template:
            # 理论上不应发生，如出现说明索引与资源已不一致，直接刷新列表以兜底。
            self.refresh_templates()
            return

        # 按视图类型区分行为
        if isinstance(self.current_package, PackageView):
            # 引用影响分析：该元件若被当前存档中的实体引用，移出后实体将变为“未绑定元件”。
            referenced_instances: list[str] = []
            for instance_id, instance in self.current_package.instances.items():
                if str(getattr(instance, "template_id", "") or "") != str(template_id or ""):
                    continue
                instance_name = str(getattr(instance, "name", "") or "").strip() or instance_id
                referenced_instances.append(f"{instance_name}（{instance_id}）")
            referenced_instances.sort(key=lambda text: text.casefold())
            reference_hint = ""
            if referenced_instances:
                preview = referenced_instances[:12]
                more_count = max(0, len(referenced_instances) - len(preview))
                reference_hint = (
                    "\n\n⚠️ 该元件被以下实体引用，移出后这些实体会变为“未绑定元件”的状态：\n"
                    + "\n".join(f"- {line}" for line in preview)
                )
                if more_count:
                    reference_hint += f"\n- ... 另有 {more_count} 个引用未展开"

            # 目录模式下：从当前项目存档移除模板 = 移动文件归属（不物理删除）
            if not self.confirm(
                "确认删除",
                (
                    f"将把元件 '{template.name}' 从当前存档中移出（移动到默认归档项目），"
                    "不会物理删除资源文件。"
                    f"{reference_hint}\n\n"
                    "确定要继续吗？"
                ),
            ):
                return

            # 1) 先执行“归属移出”（物理移动文件），保证重启/重建索引后不会“删了又回来”。
            window = self.window()
            package_index_manager_candidate = (
                getattr(window, "package_index_manager", None) if window is not None else None
            )
            if isinstance(package_index_manager_candidate, PackageIndexManager):
                package_index_manager_candidate.remove_resource_from_package(
                    self.current_package.package_id,
                    "template",
                    template_id,
                )

            # 2) 同步当前视图的内存快照与缓存（用于 UI 立即反馈）。
            self.current_package.remove_template(template_id)
            if hasattr(self.current_package, "clear_cache"):
                self.current_package.clear_cache()
            self.refresh_templates()
            # 通知上层：模板库发生了持久化相关变更（需立即保存包索引）
            event = LibraryChangeEvent(
                kind="template",
                id=template_id,
                operation="update",
                context={
                    "scope": describe_resource_view_scope(self.current_package),
                    "action": "detach_from_package",
                },
            )
            self.data_changed.emit(event)
            return

        # 全局视图：执行全局删除（资源文件 + 所有存档引用）
        resource_manager_candidate = getattr(self.current_package, "resource_manager", None)
        if not isinstance(resource_manager_candidate, ResourceManager):
            self.show_warning("警告", "当前视图不支持删除模板，请切换到具体存档后重试")
            return
        resource_manager: ResourceManager = resource_manager_candidate

        # 收集仍引用该模板的存档ID（通过 PackageIndexManager 扫描）。
        window = self.window()
        package_index_manager_candidate = (
            getattr(window, "package_index_manager", None) if window is not None else None
        )
        if isinstance(package_index_manager_candidate, PackageIndexManager):
            package_index_manager: Optional[PackageIndexManager] = package_index_manager_candidate
        else:
            package_index_manager = None

        referencing_package_ids: List[str] = []
        referencing_package_ids = collect_template_referencing_package_ids(
            package_index_manager,
            template_id=str(template_id),
        )
        referencing_instance_lines = collect_template_referencing_instances(
            resource_manager,
            template_id=str(template_id),
        )
        message = build_template_delete_confirmation_message(
            template_name=str(template.name),
            template_id=str(template_id),
            referencing_package_ids=referencing_package_ids,
            referencing_instance_lines=referencing_instance_lines,
        )

        if not self.confirm("确认删除元件资源", message):
            return

        # 1. 先让当前视图的缓存失效，避免后续刷新仍使用旧缓存。
        #    GlobalResourceView 实现了 remove_template 以清理本地缓存。
        self.current_package.remove_template(template_id)  # type: ignore[call-arg]

        # 2. 若可用 PackageIndexManager，则从所有存档索引中移除该模板引用。
        if package_index_manager is not None and referencing_package_ids:
            for package_id in referencing_package_ids:
                package_index_manager.remove_resource_from_package(
                    package_id,
                    "template",
                    template_id,
                )

        # 3. 物理删除资源库中的模板 JSON 文件。
        resource_manager.delete_resource(ResourceType.TEMPLATE, template_id)

        # 4. 刷新当前列表视图。
        self.refresh_templates()

        # 5. 通知上层：模板库发生了持久化相关变更（包括资源库与索引），以便触发额外的保存/校验逻辑。
        event = LibraryChangeEvent(
            kind="template",
            id=template_id,
            operation="delete",
            context={
                "scope": describe_resource_view_scope(self.current_package),
                "referencing_packages": referencing_package_ids,
            },
        )
        self.data_changed.emit(event)
        
        ToastNotification.show_message(self, f"已从资源库中删除元件 '{template.name}'。", "success")
    
    def _on_template_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        """模板点击"""
        template_id = item.data(TEMPLATE_ID_ROLE)
        if not isinstance(template_id, str) or not template_id:
            self.notify_selection_state(False, context={"source": "template"})
            self.selection_changed.emit(None)
            return
        selection = LibrarySelection(
            kind="template",
            id=template_id,
            context={"scope": describe_resource_view_scope(self.current_package)},
        )
        self.notify_selection_state(True, context={"source": "template"})
        self.selection_changed.emit(selection)
    
    def _filter_templates(self, text: str) -> None:
        """过滤模板"""
        self.filter_list_items(self.template_list, text)
    
    def select_template(self, template_id: str) -> None:
        """选中指定模板"""
        for i in range(self.template_list.count()):
            item = self.template_list.item(i)
            if item.data(TEMPLATE_ID_ROLE) == template_id:
                self.template_list.setCurrentItem(item)
                selection = LibrarySelection(
                    kind="template",
                    id=template_id,
                    context={"scope": describe_resource_view_scope(self.current_package)},
                )
                self.notify_selection_state(True, context={"source": "template"})
                self.selection_changed.emit(selection)
                break

