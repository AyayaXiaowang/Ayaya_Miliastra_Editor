"""实体摆放组件 - 文件列表形式"""

import types
from PyQt6 import QtCore, QtWidgets, QtGui
from typing import Any, Optional, Union

from ui.foundation.theme_manager import Sizes
from ui.foundation.id_generator import generate_prefixed_id
from ui.foundation.toast_notification import ToastNotification
from ui.graph.library_mixins import (
    ConfirmDialogMixin,
    SearchFilterMixin,
    ToolbarMixin,
    rebuild_list_with_preserved_selection,
)
from ui.forms.schema_dialog import FormDialogBuilder
from engine.resources.package_view import PackageView
from engine.resources.global_resource_view import GlobalResourceView
from engine.resources.unclassified_resource_view import UnclassifiedResourceView
from engine.graph.models.package_model import InstanceConfig, VariableConfig, TemplateConfig
from engine.graph.models.entity_templates import (
    get_entity_type_info,
    get_template_library_entity_types,
)
from ui.graph.library_pages.category_tree_mixin import EntityCategoryTreeMixin
from ui.graph.library_pages.library_scaffold import (
    DualPaneLibraryScaffold,
    LibraryChangeEvent,
    LibraryPageMixin,
    LibrarySelection,
)

INSTANCE_ID_ROLE = QtCore.Qt.ItemDataRole.UserRole
ENTITY_TYPE_ROLE = QtCore.Qt.ItemDataRole.UserRole + 1
SEARCH_TEXT_ROLE = QtCore.Qt.ItemDataRole.UserRole + 2

# 关卡实体在“实体分类”树与“实体列表”中应使用统一的图标，避免左右两侧语义不一致。
LEVEL_ENTITY_ICON = "📍"
LEVEL_ENTITY_LABEL_TEXT = "关卡实体"


class EntityPlacementWidget(
    DualPaneLibraryScaffold,
    LibraryPageMixin,
    SearchFilterMixin,
    ToolbarMixin,
    EntityCategoryTreeMixin,
    ConfirmDialogMixin,
):
    """实体摆放界面 - 文件列表形式"""

    instance_selected = QtCore.pyqtSignal(str)  # instance_id
    level_entity_selected = QtCore.pyqtSignal()  # 关卡实体被选中
    # 当实例被新增/删除/位置修改等造成持久化状态改变时发射，用于通知上层立即保存存档索引
    data_changed = QtCore.pyqtSignal(LibraryChangeEvent)
    
    def __init__(self, parent=None):
        super().__init__(
            parent,
            title="实体摆放",
            description="浏览与管理元件实体，支持分类筛选与快速定位。",
        )
        self.current_package: Optional[
            Union[PackageView, GlobalResourceView, UnclassifiedResourceView]
        ] = None
        self.current_category: str = "all"  # 当前分类
        self._category_items: dict[str, QtWidgets.QTreeWidgetItem] = {}
        self._setup_ui()
        self.apply_list_widget_style()
    
    def _setup_ui(self) -> None:
        """设置UI"""
        # 顶部：标题右侧放搜索框，作为实体全局过滤入口
        self.search_edit = QtWidgets.QLineEdit(self)
        self.search_edit.setPlaceholderText("搜索实体...")
        self.search_edit.setMinimumHeight(Sizes.INPUT_HEIGHT)
        self.add_action_widget(self.search_edit)

        # 标题下方：仅保留“添加/删除”等主操作按钮
        toolbar_container = QtWidgets.QWidget()
        top_toolbar = QtWidgets.QHBoxLayout(toolbar_container)
        top_toolbar.setContentsMargins(0, 0, 0, 0)
        self.init_toolbar(top_toolbar)
        self.add_instance_btn = QtWidgets.QPushButton("+ 添加实体", self)
        self.delete_instance_btn = QtWidgets.QPushButton("删除", self)
        toolbar_buttons = [
            self.add_instance_btn,
            self.delete_instance_btn,
        ]
        # 工具栏行只放操作按钮，搜索栏统一放在标题行右侧
        self.setup_toolbar_with_search(top_toolbar, toolbar_buttons, None)
        self.set_status_widget(toolbar_container)

        self.category_tree = QtWidgets.QTreeWidget()
        self.category_tree.setHeaderLabel("实体分类")
        self.category_tree.setObjectName("leftPanel")
        self.category_tree.setFixedWidth(Sizes.LEFT_PANEL_WIDTH)

        right_widget = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # 右侧：使用列表视图展示实体，风格与元件库保持一致
        self.entity_list = QtWidgets.QListWidget()
        self.entity_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.entity_list.setObjectName("entityInstanceList")
        right_layout.addWidget(self.entity_list)

        self.build_dual_pane(
            self.category_tree,
            right_widget,
            left_title="实体分类",
            left_description="按实体类型过滤实体",
            right_title="实体列表",
            right_description="支持搜索与筛选，选中后在右侧属性面板中编辑详细属性",
        )
        
        # 初始化分类树
        self._init_category_tree()
        
        # 连接信号
        self.category_tree.itemClicked.connect(self._on_category_clicked)
        self.add_instance_btn.clicked.connect(self._add_from_template)
        self.delete_instance_btn.clicked.connect(self._delete_instance)
        self.entity_list.itemSelectionChanged.connect(self._on_selection_changed)
        self.connect_search(self.search_edit, self._on_search_text_changed, placeholder="搜索...")
    
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
        package: Union[PackageView, GlobalResourceView, UnclassifiedResourceView],
    ) -> None:
        """设置当前存档或资源视图并刷新列表（统一库页入口）。

        关卡实体不再仅限于具体存档视图，在全局/未分类视图下同样允许选中，
        具体归属由右侧属性面板中的“所属存档”单选下拉控制。
        """
        self.current_package = package

        # 始终允许点击“关卡实体”分类，只根据视图类型调整提示文案
        is_global_view = isinstance(package, (GlobalResourceView, UnclassifiedResourceView))
        level_item = self._category_items.get("level_entity")
        if level_item:
            level_item.setDisabled(False)
            if is_global_view:
                level_item.setToolTip(
                    0,
                    "关卡实体在全局/未分类视图下用于统一编辑本体，具体归属由属性页中的“所属存档”控制（每个存档最多一个）。",
                )
            else:
                level_item.setToolTip(
                    0,
                    "关卡实体（唯一，承载关卡逻辑），可通过属性页中的“所属存档”与当前存档建立或解除绑定。",
                )

        self._rebuild_instances()

    def set_package(
        self,
        package: Union[PackageView, GlobalResourceView, UnclassifiedResourceView],
    ) -> None:
        """兼容旧接口，内部委托给 set_context。"""
        self.set_context(package)

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
                    context={"scope": self._describe_current_scope()},
                )
            return None

        kind = "level_entity" if self._is_level_entity_instance_id(instance_id) else "instance"
        return LibrarySelection(
            kind=kind,
            id=instance_id,
            context={"scope": self._describe_current_scope()},
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
                    self.level_entity_selected.emit()
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
            self.level_entity_selected.emit()
            return

        self.current_category = category or "all"
        self._rebuild_instances()
    
    def _rebuild_instances(self) -> None:
        """刷新实体列表"""
        previously_selected_id = self._current_instance_id()

        self.entity_list.clear()

        if not self.current_package:
            return

        effective_category = self.current_category or "all"

        if effective_category == "level_entity":
            self._rebuild_level_entity_view(previously_selected_id)
            return

        allowed_types = set(get_template_library_entity_types())

        def build_items() -> None:
            displayed_instance_ids: set[str] = set()

            for instance_id, instance in self.current_package.instances.items():
                template = self.current_package.get_template(instance.template_id)
                if not template or template.entity_type not in allowed_types:
                    continue

                if (
                    effective_category not in ("all", "")
                    and template.entity_type != effective_category
                ):
                    continue

                metadata = getattr(template, "metadata", {}) or {}
                template_category = ""
                if isinstance(metadata, dict):
                    category_value = metadata.get("template_category") or metadata.get(
                        "category"
                    )
                    if isinstance(category_value, str):
                        template_category = category_value

                if template_category in ("元件组", "掉落物"):
                    icon = get_entity_type_info(template_category).get("icon", "📦")
                    display_type = template_category
                else:
                    icon = get_entity_type_info(template.entity_type).get("icon", "📦")
                    display_type = template.entity_type

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

                display_text = f"{icon} {instance.name}"

                list_item = QtWidgets.QListWidgetItem(display_text)
                list_item.setData(INSTANCE_ID_ROLE, instance_id)
                list_item.setData(ENTITY_TYPE_ROLE, template.entity_type)

                tooltip_lines: list[str] = [
                    f"实体名称: {instance.name}",
                    f"实体类型: {display_type}",
                    f"元件: {template.name}",
                    f"位置: {position_text}",
                    f"旋转: {rotation_text}",
                ]
                if guid_text:
                    tooltip_lines.append(f"GUID: {guid_text}")
                list_item.setToolTip("\n".join(tooltip_lines))

                search_tokens = [
                    instance.name,
                    template.name,
                    display_type,
                    template.entity_type,
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
            if self._is_level_entity_instance_id(instance_id):
                self.level_entity_selected.emit()
            else:
                self.instance_selected.emit(instance_id)

        def emit_empty_selection() -> None:
            if not self.current_package:
                return
            if previously_selected_id:
                self.instance_selected.emit("")

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

    def _describe_current_scope(self) -> str:
        """根据当前资源视图返回简单 scope 标识，用于变更事件上下文。"""
        if isinstance(self.current_package, PackageView):
            return "package"
        if isinstance(self.current_package, GlobalResourceView):
            return "global"
        if isinstance(self.current_package, UnclassifiedResourceView):
            return "unclassified"
        return "unknown"

    def _on_search_text_changed(self, text: str) -> None:
        """搜索框文本变化"""
        def _get_search_text(item: QtWidgets.QListWidgetItem) -> str:
            value = item.data(SEARCH_TEXT_ROLE)
            return str(value) if value is not None else item.text()

        self.filter_list_items(self.entity_list, text, text_getter=_get_search_text)

    def _on_selection_changed(self) -> None:
        instance_id = self._current_instance_id()
        if not instance_id:
            return
        # 关卡实体在任意分类下都应通过专用信号驱动右侧面板，
        # 避免被当作普通实体实例处理。
        if self._is_level_entity_instance_id(instance_id):
            self.level_entity_selected.emit()
            return
        self.instance_selected.emit(instance_id)

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
        variables_group = builder.dialog.add_group_box("初始变量值")
        variables_layout = QtWidgets.QFormLayout(variables_group)
        variable_widgets: dict[str, tuple[QtWidgets.QWidget, str]] = {}
        variables_group.setVisible(False)
        selected_template: Optional[TemplateConfig] = None

        def rebuild_variables(template_obj: Optional[TemplateConfig]) -> None:
            while variables_layout.count():
                item = variables_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            variable_widgets.clear()
            if not template_obj or not template_obj.default_variables:
                variables_group.setVisible(False)
                return
            for var in template_obj.default_variables:
                widget = self._create_variable_widget(var)
                if widget:
                    variables_layout.addRow(f"{var.name}:", widget)
                    variable_widgets[var.name] = (widget, var.variable_type)
            variables_group.setVisible(True)

        def on_template_changed(index: int) -> None:
            nonlocal selected_template
            if index < 0:
                selected_template = None
                rebuild_variables(None)
                return
            template_id = template_combo.itemData(index)
            selected_template = self.current_package.get_template(template_id)
            if not selected_template:
                rebuild_variables(None)
                return
            instance_count = len(self.current_package.instances) + 1
            name_edit.setText(f"{selected_template.name}_{instance_count}")
            rebuild_variables(selected_template)

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
        for var_name, (widget, var_type) in variable_widgets.items():
            if var_type == "Boolean":
                value = str(widget.isChecked())
            elif var_type in ["Integer", "Float"]:
                value = str(widget.value())
            else:
                value = widget.text()
            var_config = VariableConfig(name=var_name, variable_type=var_type, default_value=value)
            instance.override_variables.append(var_config)
        return instance

    def _create_variable_widget(self, var: VariableConfig) -> QtWidgets.QWidget:
        """根据变量类型创建编辑控件。"""
        var_type = var.variable_type
        if var_type == "Boolean":
            widget = QtWidgets.QCheckBox()
            if var.default_value:
                widget.setChecked(str(var.default_value).lower() in {"true", "1", "yes"})
            return widget
        if var_type in {"Integer", "Float"}:
            widget = QtWidgets.QDoubleSpinBox() if var_type == "Float" else QtWidgets.QSpinBox()
            widget.setRange(-999999, 999999)
            if var.default_value:
                widget.setValue(float(var.default_value) if var_type == "Float" else int(var.default_value))
            return widget
        widget = QtWidgets.QLineEdit()
        if var.default_value:
            widget.setText(str(var.default_value))
        return widget

    def _add_from_template(self) -> None:
        """从元件添加实体（使用新对话框）"""
        if not self.current_package:
            self.show_warning("警告", "请先选择或创建存档")
            return

        # 关卡实体分类下，点击“添加实体”直接创建或聚焦关卡实体，不弹出元件选择窗口。
        if self.current_category == "level_entity":
            self._ensure_level_entity_exists()
            self._rebuild_instances()
            self.level_entity_selected.emit()
            # 通知上层：关卡实体已创建或绑定（需立即保存索引/资源）
            event = LibraryChangeEvent(
                kind="level_entity",
                id="",
                operation="update",
                context={"scope": self._describe_current_scope(), "action": "ensure_level_entity"},
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
                context={"scope": self._describe_current_scope()},
            )
            self.data_changed.emit(event)
    
    def _delete_instance(self) -> None:
        """删除实体"""
        instance_id = self._current_instance_id()
        if not instance_id:
            self.show_warning("警告", "请先选择要删除的实体")
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
            self.current_package.remove_instance(instance_id)
            self._rebuild_instances()
            # 通知上层：实体列表发生了持久化相关变更（需立即保存包索引）
            event = LibraryChangeEvent(
                kind="instance",
                id=instance_id,
                operation="delete",
                context={"scope": self._describe_current_scope()},
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
                # 关卡实体通过专用信号驱动右侧属性面板。
                if self.current_category == "level_entity":
                    self.level_entity_selected.emit()
                else:
                    self.instance_selected.emit(instance_id)
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
        self.level_entity_selected.emit()

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
        - 对于全局视图/未分类视图：
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

        # 全局视图/未分类视图：只需在资源库层面保证存在一个带 is_level_entity 标记的实例
        if isinstance(self.current_package, (GlobalResourceView, UnclassifiedResourceView)):
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
