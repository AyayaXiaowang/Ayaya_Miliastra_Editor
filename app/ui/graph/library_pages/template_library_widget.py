"""元件库组件"""

import types
from dataclasses import dataclass
from typing import Optional, Union, Dict, Any, List

from PyQt6 import QtCore, QtGui, QtWidgets

from app.ui.foundation.theme_manager import Sizes
from app.ui.foundation.toast_notification import ToastNotification
from app.ui.foundation.id_generator import generate_prefixed_id
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
from engine.resources.unclassified_resource_view import UnclassifiedResourceView
from engine.resources.resource_manager import ResourceManager
from engine.resources.package_index_manager import PackageIndexManager
from engine.graph.models.package_model import TemplateConfig, ComponentConfig
from engine.graph.models.entity_templates import (
    get_entity_type_info,
    get_template_library_entity_types,
)
from engine.configs.entities.creature_models import get_creature_model_display_pairs, get_creature_model_category_for_name
from app.ui.graph.library_pages.library_scaffold import (
    DualPaneLibraryScaffold,
    LibraryChangeEvent,
    LibraryPageMixin,
    LibrarySelection,
)
from app.ui.graph.library_pages.category_tree_mixin import EntityCategoryTreeMixin


@dataclass(frozen=True)
class TemplateDialogConfig:
    """新建模板对话框的静态配置。"""

    title: str
    is_drop_category: bool
    default_entity_type: Optional[str]
    name_label: str
    description_label: str


class TemplateLibraryWidget(
    DualPaneLibraryScaffold,
    LibraryPageMixin,
    SearchFilterMixin,
    ToolbarMixin,
    EntityCategoryTreeMixin,
    ConfirmDialogMixin,
):
    """元件库界面"""

    template_selected = QtCore.pyqtSignal(str)  # template_id
    # 当模板被新增/删除等造成持久化状态改变时发射，用于通知上层立即保存存档索引
    data_changed = QtCore.pyqtSignal(LibraryChangeEvent)
    
    def __init__(self, parent=None):
        super().__init__(
            parent,
            title="元件库",
            description="按实体类型管理可复用元件，支持快速新建、删除与搜索过滤。",
        )
        self.current_package: Optional[
            Union[PackageView, GlobalResourceView, UnclassifiedResourceView]
        ] = None
        # 当前左侧选中的分类 key（"all"、具体实体类型或扩展分类名）
        self._current_category_key: str = "all"
        # 根据当前分类推导出的“新建模板”默认实体类型（例如：掉落物/元件组 → 物件）
        self._default_entity_type_for_new: Optional[str] = None
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """设置UI"""
        # 顶部：标题右侧放搜索框，作为全局过滤入口
        self.search_edit = QtWidgets.QLineEdit(self)
        self.search_edit.setPlaceholderText("搜索元件...")
        self.search_edit.setMinimumHeight(Sizes.INPUT_HEIGHT)
        self.add_action_widget(self.search_edit)

        # 标题下方：仅保留“新建/删除”等主操作按钮
        toolbar_widget = QtWidgets.QWidget()
        toolbar_layout = QtWidgets.QHBoxLayout(toolbar_widget)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        self.init_toolbar(toolbar_layout)
        self.add_template_btn = QtWidgets.QPushButton("+ 新建元件", self)
        self.add_template_btn.setMinimumHeight(Sizes.BUTTON_HEIGHT)
        self.delete_template_btn = QtWidgets.QPushButton("删除", self)
        self.delete_template_btn.setMinimumHeight(Sizes.BUTTON_HEIGHT)
        toolbar_buttons = [self.add_template_btn, self.delete_template_btn]
        # 工具栏行只放操作按钮，搜索栏统一放在标题行右侧
        self.setup_toolbar_with_search(toolbar_layout, toolbar_buttons, None)
        self.set_status_widget(toolbar_widget)
        
        self.category_tree = QtWidgets.QTreeWidget()
        self.category_tree.setHeaderLabel("元件分类")
        self.category_tree.setObjectName("leftPanel")
        self.category_tree.setFixedWidth(Sizes.LEFT_PANEL_WIDTH)
        self.category_tree.setIndentation(Sizes.SPACING_MEDIUM)

        self.template_list = QtWidgets.QListWidget()

        self.build_dual_pane(
            self.category_tree,
            self.template_list,
            left_title="元件分类",
            left_description="按实体类型过滤元件",
            right_title="元件列表",
            right_description="双击可查看详情，支持按类型筛选",
        )
        
        # 连接信号
        self.add_template_btn.clicked.connect(self._add_template)
        self.delete_template_btn.clicked.connect(self._delete_template)
        self.template_list.itemClicked.connect(self._on_template_clicked)
        self.connect_search(self.search_edit, self._filter_templates, placeholder="搜索元件...")
        
        # 初始化分类树
        self._init_category_tree()
    
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
        package: Union[PackageView, GlobalResourceView, UnclassifiedResourceView],
    ) -> None:
        """设置当前资源视图并全量刷新列表（统一库页入口）。"""
        self.current_package = package
        self.refresh_templates()

    def set_package(
        self,
        package: Union[PackageView, GlobalResourceView, UnclassifiedResourceView],
    ) -> None:
        """兼容旧接口，内部委托给 set_context。"""
        self.set_context(package)

    def reload(self) -> None:
        """在当前上下文下全量刷新列表并负责选中恢复。"""
        self.refresh_templates()

    def get_selection(self) -> Optional[LibrarySelection]:
        """返回当前选中的模板（若存在）。"""
        current_item = self.template_list.currentItem()
        if current_item is None:
            return None
        value = current_item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(value, str) or not value:
            return None
        return LibrarySelection(
            kind="template",
            id=value,
            context={"scope": self._describe_current_scope()},
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
            current_item.data(QtCore.Qt.ItemDataRole.UserRole) if current_item is not None else None
        )

        def build_items() -> None:
            if not self.current_package:
                return

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
                list_item = QtWidgets.QListWidgetItem(f"{icon} {template.name}")
                list_item.setData(QtCore.Qt.ItemDataRole.UserRole, template_id)

                tooltip_lines: list[str] = [f"类型: {template.entity_type}"]
                if category != "掉落物":
                    tooltip_lines.append(
                        f"节点图: {len(getattr(template, 'default_graphs', []))}"
                    )
                tooltip_lines.append(f"变量: {len(getattr(template, 'default_variables', []))}")
                tooltip_lines.append(
                    f"组件: {len(getattr(template, 'default_components', []))}"
                )
                list_item.setToolTip("\n".join(tooltip_lines))

                self.template_list.addItem(list_item)

        def get_item_key(list_item: QtWidgets.QListWidgetItem) -> Optional[str]:
            value = list_item.data(QtCore.Qt.ItemDataRole.UserRole)
            if isinstance(value, str):
                return value
            return None

        def emit_selection_for_template(template_id: Any) -> None:
            if isinstance(template_id, str) and template_id:
                self.template_selected.emit(template_id)

        def emit_empty_selection() -> None:
            if not self.current_package:
                return
            self.notify_selection_state(False, context={"source": "template"})
            self.template_selected.emit("")

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

    def _describe_current_scope(self) -> str:
        """根据当前资源视图返回简单 scope 标识，用于变更事件上下文。"""
        if isinstance(self.current_package, PackageView):
            return "package"
        if isinstance(self.current_package, GlobalResourceView):
            return "global"
        if isinstance(self.current_package, UnclassifiedResourceView):
            return "unclassified"
        return "unknown"
    
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
            if item.data(QtCore.Qt.ItemDataRole.UserRole) == template_id:
                self.template_list.setCurrentItem(item)
                self.template_selected.emit(template_id)
                break

        # 通知上层：模板库发生了持久化相关变更（需立即保存包索引）
        event = LibraryChangeEvent(
            kind="template",
            id=template_id,
            operation="create",
            context={"scope": self._describe_current_scope()},
        )
        self.data_changed.emit(event)
    
    def _delete_template(self) -> None:
        """删除模板。

        语义区分：
        - 具体存档视图（PackageView）：仅从当前存档索引中移除该模板引用，不删除资源文件，
          以避免影响复用同一模板的其他存档。
        - 全局视图/未分类视图（GlobalResourceView/UnclassifiedResourceView）：
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

        template_id = current_item.data(QtCore.Qt.ItemDataRole.UserRole)
        template = self.current_package.get_template(template_id)  # type: ignore[call-arg]

        if not template:
            # 理论上不应发生，如出现说明索引与资源已不一致，直接刷新列表以兜底。
            self.refresh_templates()
            return

        # 按视图类型区分行为
        if isinstance(self.current_package, PackageView):
            # 仅移除当前存档中的引用，不删除底层资源文件
            if not self.confirm(
                "确认删除",
                (
                    f"将从当前存档中移除元件 '{template.name}' 的引用，"
                    "不会删除资源库中的模板文件，其他存档中对该元件的使用不受影响。\n\n"
                    "确定要继续吗？"
                ),
            ):
                return

            self.current_package.remove_template(template_id)
            self.refresh_templates()
            # 通知上层：模板库发生了持久化相关变更（需立即保存包索引）
            event = LibraryChangeEvent(
                kind="template",
                id=template_id,
                operation="update",
                context={
                    "scope": self._describe_current_scope(),
                    "action": "detach_from_package",
                },
            )
            self.data_changed.emit(event)
            return

        # 全局 / 未分类视图：执行全局删除（资源文件 + 所有存档引用）
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
        if package_index_manager is not None:
            for package_info in package_index_manager.list_packages():
                package_id_value = package_info.get("package_id")
                if not isinstance(package_id_value, str) or not package_id_value:
                    continue
                package_id = package_id_value
                package_index = package_index_manager.load_package_index(package_id)
                if not package_index:
                    continue
                if template_id in package_index.resources.templates:
                    referencing_package_ids.append(package_id)

        # 构建确认文案：提示该模板是否仍被某些存档纳入。
        if referencing_package_ids:
            # 仅在提示中展示少量 ID，避免对话框过长；详细排查可通过存档库页面完成。
            preview_count = min(len(referencing_package_ids), 5)
            preview_ids = ", ".join(referencing_package_ids[:preview_count])
            extra_tail = ""
            if len(referencing_package_ids) > preview_count:
                extra_tail = f" 等共 {len(referencing_package_ids)} 个存档"
            message = (
                f"将从资源库中彻底删除元件 '{template.name}'（ID: {template_id}），"
                "并从所有存档索引中移除对该元件的引用。\n\n"
                "当前仍有以下存档纳入了该元件：\n"
                f"- {preview_ids}{extra_tail}\n\n"
                "此操作无法撤销，可能导致这些存档中原本使用该元件的实体变为“悬空引用”。\n"
                "如需保留某些存档的使用，请先在对应存档中替换或移除相关实体，再执行删除。\n\n"
                "确定要继续执行全局删除吗？"
            )
        else:
            message = (
                f"将从资源库中彻底删除未被任何存档纳入的元件 '{template.name}'（ID: {template_id}）。\n\n"
                "此操作会删除元件 JSON 文件本身，且无法撤销。\n"
                "确定要继续吗？"
            )

        if not self.confirm("确认删除元件资源", message):
            return

        # 1. 先让当前视图的缓存失效，避免后续刷新仍使用旧缓存。
        #    GlobalResourceView/UnclassifiedResourceView 均实现了 remove_template 以清理本地缓存。
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
                "scope": self._describe_current_scope(),
                "referencing_packages": referencing_package_ids,
            },
        )
        self.data_changed.emit(event)
        
        ToastNotification.show_message(self, f"已从资源库中删除元件 '{template.name}'。", "success")
    
    def _on_template_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        """模板点击"""
        template_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
        self.template_selected.emit(template_id)
    
    def _filter_templates(self, text: str) -> None:
        """过滤模板"""
        self.filter_list_items(self.template_list, text)
    
    def select_template(self, template_id: str) -> None:
        """选中指定模板"""
        for i in range(self.template_list.count()):
            item = self.template_list.item(i)
            if item.data(QtCore.Qt.ItemDataRole.UserRole) == template_id:
                self.template_list.setCurrentItem(item)
                self.template_selected.emit(template_id)
                break

