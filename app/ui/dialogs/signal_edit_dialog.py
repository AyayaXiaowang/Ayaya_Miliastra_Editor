"""信号编辑对话框"""

from typing import Optional, List

from PyQt6 import QtCore, QtGui, QtWidgets

from engine.graph.models.package_model import SignalConfig, SignalParameterConfig
from engine.graph.models.entity_templates import get_all_variable_types
from app.ui.dialogs.struct_definition_value_editors import ClickToEditLineEdit
from app.ui.dialogs.table_edit_helpers import (
    wrap_click_to_edit_line_edit_for_table_cell,
)
from app.ui.foundation.base_widgets import BaseDialog
from app.ui.foundation.theme_manager import Sizes, ThemeManager
from app.ui.foundation import dialog_utils
from app.ui.widgets.inline_table_editor_widget import (
    InlineTableColumnSpec,
    InlineTableEditorWidget,
)


def _get_signal_supported_types() -> List[str]:
    """返回信号参数可选的数据类型列表。

    数据源统一复用实体/节点图变量的全局变量类型列表，仅保留信号系统当前
    支持的基础类型及其列表类型，避免与节点端口类型、结构体字段类型串名发散，
    并保持与变量编辑对话框中相同的展示顺序。
    """
    variable_types = list(get_all_variable_types())

    # 目前信号只支持这几类基础类型及其列表形式（若存在于变量类型枚举中）
    allowed_base_types = [
        "整数",
        "浮点数",
        "字符串",
        "三维向量",
        "布尔值",
        "GUID",
        "实体",
        "配置ID",
        "元件ID",
    ]
    allowed_names = set(allowed_base_types)
    allowed_names.update(f"{base}列表" for base in allowed_base_types)

    filtered: List[str] = [type_name for type_name in variable_types if type_name in allowed_names]

    # 兜底：如果外部配置发生变更导致过滤后为空，至少保留基础类型列表
    if not filtered:
        return allowed_base_types

    return filtered


SIGNAL_PARAMETER_TYPES: List[str] = _get_signal_supported_types()

ALIAS_TO_CANONICAL_SIGNAL_TYPE = {
    "向量3": "三维向量",
    "颜色": "三维向量",
}


def normalize_signal_parameter_type(raw_type_name: str) -> str:
    """将旧的参数类型别名映射为规范类型字符串。

    - 兼容旧工程中使用的“向量3”“颜色”等别名；
    - 对于未知类型回退为第一个可用类型（通常为“整数”）。
    """
    if not SIGNAL_PARAMETER_TYPES:
        return "整数"

    if not raw_type_name:
        return SIGNAL_PARAMETER_TYPES[0]

    if raw_type_name in ALIAS_TO_CANONICAL_SIGNAL_TYPE:
        return ALIAS_TO_CANONICAL_SIGNAL_TYPE[raw_type_name]

    if raw_type_name in SIGNAL_PARAMETER_TYPES:
        return raw_type_name

    return SIGNAL_PARAMETER_TYPES[0]


class SignalEditorWidget(QtWidgets.QWidget):
    """信号编辑核心组件。

    提供“信号名 + 描述 + 参数列表”的编辑 UI，可用于弹窗或嵌入右侧属性面板。
    """

    signal_changed = QtCore.pyqtSignal()

    def __init__(
        self,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._is_read_only: bool = False
        self._params_row_height: Optional[int] = (
            Sizes.INPUT_HEIGHT + Sizes.PADDING_SMALL
        )
        self._is_loading: bool = False

        self.name_edit: QtWidgets.QLineEdit
        self.desc_edit: QtWidgets.QTextEdit
        self.params_editor: InlineTableEditorWidget
        self.params_table: QtWidgets.QTableWidget

        self._setup_ui()

    # ------------------------------------------------------------------
    # UI 组装
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        # 外层边距由父容器控制，这里保持 0，便于复用在对话框和右侧面板中
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Sizes.SPACING_MEDIUM)

        form_layout = QtWidgets.QFormLayout()
        form_layout.setLabelAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        form_layout.setFormAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop
        )
        form_layout.setHorizontalSpacing(Sizes.SPACING_MEDIUM)
        form_layout.setVerticalSpacing(Sizes.SPACING_SMALL)

        self.name_edit = QtWidgets.QLineEdit(self)
        self.name_edit.setPlaceholderText("例如：机关触发信号")
        form_layout.addRow("信号名*:", self.name_edit)

        self.desc_edit = QtWidgets.QTextEdit(self)
        self.desc_edit.setPlaceholderText("描述信号的用途...")
        self.desc_edit.setMinimumHeight(80)
        self.desc_edit.setMaximumHeight(200)
        form_layout.addRow("描述:", self.desc_edit)

        layout.addLayout(form_layout)

        params_label = QtWidgets.QLabel("信号参数")
        params_label.setFont(
            QtGui.QFont("Microsoft YaHei UI", 10, QtGui.QFont.Weight.Bold)
        )
        params_label.setStyleSheet(ThemeManager.heading(4))
        layout.addWidget(params_label)

        column_specs = [
            InlineTableColumnSpec(
                title="参数名",
                resize_mode=QtWidgets.QHeaderView.ResizeMode.Stretch,
            ),
            InlineTableColumnSpec(
                title="数据类型",
                resize_mode=QtWidgets.QHeaderView.ResizeMode.Interactive,
                initial_width=230,
            ),
            InlineTableColumnSpec(
                title="描述",
                resize_mode=QtWidgets.QHeaderView.ResizeMode.Stretch,
            ),
        ]
        self.params_editor = InlineTableEditorWidget(
            parent=self,
            columns=column_specs,
            add_button_text="+ 添加参数",
            delete_button_text="- 删除参数",
            delete_action_text="删除参数",
        )
        self.params_table = self.params_editor.table
        layout.addWidget(self.params_editor)

        self.params_editor.row_add_requested.connect(self._add_parameter)
        self.params_editor.row_delete_requested.connect(self._remove_parameter_at_row)

        self.name_edit.editingFinished.connect(self._on_editor_changed)
        self.desc_edit.textChanged.connect(self._on_description_text_changed)

        # 初始时根据内容计算描述高度和参数表格高度
        self._update_description_height()

    # ------------------------------------------------------------------
    # 加载与行操作
    # ------------------------------------------------------------------

    def clear(self) -> None:
        self._is_loading = True
        self.name_edit.clear()
        self.desc_edit.clear()
        self.params_table.setRowCount(0)
        self._update_description_height()
        self._update_params_table_height()
        self._is_loading = False

    # ------------------------------------------------------------------
    # 描述高度自适应
    # ------------------------------------------------------------------

    def _update_description_height(self) -> None:
        """根据文本内容调整描述编辑框高度（保留最大高度限制）。"""
        document = self.desc_edit.document()
        layout = document.documentLayout()
        if layout is not None:
            document_size = layout.documentSize()
            document_height = document_size.height()
        else:
            document_height = document.size().height()

        contents_margins = self.desc_edit.contentsMargins()
        frame_height = self.desc_edit.frameWidth() * 2
        raw_height = int(document_height) + contents_margins.top() + contents_margins.bottom() + frame_height

        minimum_height = 60
        maximum_height = 200
        clamped_height = max(minimum_height, min(raw_height, maximum_height))

        self.desc_edit.setMinimumHeight(clamped_height)
        self.desc_edit.setMaximumHeight(clamped_height)

    def _on_description_text_changed(self) -> None:
        self._update_description_height()
        self._on_editor_changed()

    # ------------------------------------------------------------------
    # 只读模式控制
    # ------------------------------------------------------------------

    def set_read_only(self, read_only: bool) -> None:
        """切换编辑器的只读状态。

        - 只读模式下禁用名称与描述输入框及参数表格的增删改，但仍允许滚动浏览；
        - 对话框等需要完整编辑能力的场景不应启用该模式。
        """
        self._is_read_only = bool(read_only)

        self.name_edit.setReadOnly(self._is_read_only)
        self.desc_edit.setReadOnly(self._is_read_only)

        if self._is_read_only:
            self.name_edit.setStyleSheet(ThemeManager.readonly_input_style())
            self.desc_edit.setStyleSheet(ThemeManager.readonly_input_style())
        else:
            # 交由外层主题统一控制非只读样式
            self.name_edit.setStyleSheet("")
            self.desc_edit.setStyleSheet("")

        # 只读模式下禁用“添加/删除参数”按钮，但保留表格滚动与查看能力。
        self.params_editor.add_button.setEnabled(not self._is_read_only)
        if self.params_editor.delete_button is not None:
            self.params_editor.delete_button.setEnabled(not self._is_read_only)

    def load_from_config(self, signal_config: Optional[SignalConfig]) -> None:
        """从 SignalConfig 加载信号定义。"""
        self._is_loading = True
        self.params_table.setRowCount(0)
        if signal_config is None:
            self.name_edit.clear()
            self.desc_edit.clear()
            self._update_description_height()
            self._update_params_table_height()
            self._is_loading = False
            return

        self.name_edit.setText(signal_config.signal_name)
        self.desc_edit.setPlainText(signal_config.description)

        for parameter_config in signal_config.parameters:
            self._add_parameter_row(
                parameter_config.name,
                parameter_config.parameter_type,
                parameter_config.description,
            )

        self._update_description_height()
        self._update_params_table_height()
        self._is_loading = False

    def _add_parameter(self) -> None:
        """添加新参数"""
        default_type = SIGNAL_PARAMETER_TYPES[0] if SIGNAL_PARAMETER_TYPES else "整数"
        self._add_parameter_row("参数名", default_type, "")
        self._on_editor_changed()

    def _add_parameter_row(
        self,
        name: str = "",
        param_type: str = "整数",
        description: str = "",
    ) -> None:
        """添加参数行"""
        row_index = self.params_table.rowCount()
        self.params_table.insertRow(row_index)

        header = self.params_table.verticalHeader()
        if self._params_row_height is not None:
            row_height = self._params_row_height
        elif header is not None:
            row_height = header.defaultSectionSize()
        else:
            row_height = Sizes.INPUT_HEIGHT + Sizes.PADDING_SMALL

        name_edit = ClickToEditLineEdit(name, self.params_table)
        name_edit.setPlaceholderText("参数名")
        name_edit.setClearButtonEnabled(True)
        name_edit.setMinimumWidth(80)
        name_edit.setFrame(False)
        name_edit.setFixedHeight(Sizes.INPUT_HEIGHT)
        name_edit.editingFinished.connect(self._on_editor_changed)
        self.params_editor.attach_context_menu_forwarding(name_edit)
        name_container = wrap_click_to_edit_line_edit_for_table_cell(
            self.params_table,
            name_edit,
        )
        self.params_editor.attach_context_menu_forwarding(name_container)
        self.params_table.setCellWidget(row_index, 0, name_container)

        normalized_type = normalize_signal_parameter_type(param_type)
        type_combo = QtWidgets.QComboBox(self.params_table)
        type_combo.addItems(SIGNAL_PARAMETER_TYPES)
        type_combo.setCurrentText(normalized_type)
        type_combo.setFrame(False)
        type_combo.setFixedHeight(Sizes.INPUT_HEIGHT)
        type_combo.setStyleSheet(
            "QComboBox {"
            "  border: none;"
            "  background: transparent;"
            "  padding: 0px;"
            "}"
            "QComboBox::drop-down {"
            "  border: none;"
            "  width: 14px;"
            "}"
        )
        type_combo.currentTextChanged.connect(self._on_editor_changed)
        self.params_editor.attach_context_menu_forwarding(type_combo)
        self.params_table.setCellWidget(row_index, 1, type_combo)

        desc_edit = ClickToEditLineEdit(description, self.params_table)
        desc_edit.setPlaceholderText("描述该参数的用途（可选）")
        desc_edit.setClearButtonEnabled(True)
        desc_edit.setFrame(False)
        desc_edit.setFixedHeight(Sizes.INPUT_HEIGHT)
        desc_edit.editingFinished.connect(self._on_editor_changed)
        self.params_editor.attach_context_menu_forwarding(desc_edit)
        desc_container = wrap_click_to_edit_line_edit_for_table_cell(
            self.params_table,
            desc_edit,
        )
        self.params_editor.attach_context_menu_forwarding(desc_container)
        self.params_table.setCellWidget(row_index, 2, desc_container)

    def _remove_parameter(self) -> None:
        """删除选中的参数"""
        current_row = self.params_table.currentRow()
        if current_row >= 0:
            self._remove_parameter_at_row(current_row)

    def _remove_parameter_at_row(self, row_index: int) -> None:
        """按行索引删除参数（供通用表格模板的删除信号复用）。"""
        if row_index < 0 or row_index >= self.params_table.rowCount():
            return
        self.params_table.removeRow(row_index)
        self._update_params_table_height()
        self._on_editor_changed()

    # ------------------------------------------------------------------
    # 参数表格高度自适应（供嵌入式只读视图按需启用）
    # ------------------------------------------------------------------

    def _update_params_table_height(self) -> None:
        """根据当前行数调整参数表格高度，确保表格内容始终完整可见。"""
        if self.params_table is None:
            return

        row_count = self.params_table.rowCount()
        vertical_header = self.params_table.verticalHeader()
        if vertical_header is not None and row_count > 0:
            row_height = vertical_header.sectionSize(0)
        else:
            row_height = Sizes.INPUT_HEIGHT + Sizes.PADDING_SMALL

        horizontal_header = self.params_table.horizontalHeader()
        if horizontal_header is not None:
            header_height = horizontal_header.height()
        else:
            header_height = 0

        frame_height = self.params_table.frameWidth() * 2
        effective_rows = max(1, row_count)
        content_height = row_height * effective_rows
        extra_padding = Sizes.PADDING_SMALL

        total_height = header_height + frame_height + content_height + extra_padding
        self.params_table.setMinimumHeight(total_height)
        self.params_table.setMaximumHeight(total_height)

    def _on_editor_changed(self) -> None:
        if self._is_loading:
            return
        self.signal_changed.emit()

    # ------------------------------------------------------------------
    # 导出配置
    # ------------------------------------------------------------------

    def build_signal_config(self, signal_id: str) -> SignalConfig:
        """根据当前编辑内容构建 SignalConfig（不做对话框级校验）。"""
        signal_name = self.name_edit.text().strip()
        description = self.desc_edit.toPlainText().strip()

        parameters: List[SignalParameterConfig] = []
        for row_index in range(self.params_table.rowCount()):
            # 名称列：单元格内是包装过的 ClickToEditLineEdit，需要向下查找 QLineEdit
            name_container = self.params_table.cellWidget(row_index, 0)
            name_edit: Optional[QtWidgets.QLineEdit] = None
            if isinstance(name_container, QtWidgets.QLineEdit):
                name_edit = name_container
            elif isinstance(name_container, QtWidgets.QWidget):
                name_edit = name_container.findChild(QtWidgets.QLineEdit)

            if name_edit is not None:
                parameter_name = name_edit.text().strip()
            else:
                name_item = self.params_table.item(row_index, 0)
                parameter_name = name_item.text().strip() if name_item else ""
            if not parameter_name:
                continue

            type_widget = self.params_table.cellWidget(row_index, 1)
            if isinstance(type_widget, QtWidgets.QComboBox):
                raw_type_name = type_widget.currentText()
            else:
                raw_type_name = "整数"
            normalized_type_name = normalize_signal_parameter_type(raw_type_name)

            desc_container = self.params_table.cellWidget(row_index, 2)
            desc_edit: Optional[QtWidgets.QLineEdit] = None
            if isinstance(desc_container, QtWidgets.QLineEdit):
                desc_edit = desc_container
            elif isinstance(desc_container, QtWidgets.QWidget):
                desc_edit = desc_container.findChild(QtWidgets.QLineEdit)

            if desc_edit is not None:
                parameter_description = desc_edit.text().strip()
            else:
                desc_item = self.params_table.item(row_index, 2)
                parameter_description = desc_item.text().strip() if desc_item else ""

            parameters.append(
                SignalParameterConfig(
                    name=parameter_name,
                    parameter_type=normalized_type_name,
                    description=parameter_description,
                )
            )

        return SignalConfig(
            signal_id=signal_id,
            signal_name=signal_name,
            parameters=parameters,
            description=description,
        )

    def validate_and_build_config(
        self,
        *,
        parent_for_message_box: Optional[QtWidgets.QWidget],
        existing_signal_id: str,
    ) -> Optional[SignalConfig]:
        """进行最小校验后返回配置，用于对话框模式下的确定按钮。"""
        parent = parent_for_message_box or self
        signal_name = self.name_edit.text().strip()
        if not signal_name:
            dialog_utils.show_warning_dialog(parent, "警告", "请输入信号名")
            return None
        return self.build_signal_config(existing_signal_id)
        

class SignalEditDialog(BaseDialog):
    """信号编辑对话框"""
    
    def __init__(
        self,
        signal_config: Optional[SignalConfig] = None,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        self.signal_config = signal_config
        self.is_edit_mode = signal_config is not None
        self._result_config: Optional[SignalConfig] = None

        dialog_title = "编辑信号" if self.is_edit_mode else "新建信号"
        super().__init__(
            title=dialog_title,
            width=600,
            height=500,
            parent=parent,
        )

        self._build_content()

        if self.signal_config:
            self.editor.load_from_config(self.signal_config)
    
    def _build_content(self) -> None:
        """构建对话框主体内容。"""
        layout = self.content_layout
        layout.setContentsMargins(
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
        )
        layout.setSpacing(Sizes.SPACING_MEDIUM)
        
        self.editor = SignalEditorWidget(self)
        layout.addWidget(self.editor, 1)
    
    def _apply_styles(self) -> None:
        """应用统一对话框与表格样式。"""
        self.setStyleSheet(
            ThemeManager.dialog_surface_style(
                include_inputs=True,
                include_tables=True,
                include_scrollbars=True,
            )
        )

    def validate(self) -> bool:
        """确认前校验并构建信号配置。"""
        existing_signal_id = self.signal_config.signal_id if self.signal_config else ""
        result = self.editor.validate_and_build_config(
            parent_for_message_box=self,
            existing_signal_id=existing_signal_id,
        )
        if result is None:
            return False
        self._result_config = result
        return True

    def get_signal_config(self) -> Optional[SignalConfig]:
        """获取信号配置"""
        if self._result_config is not None:
            return self._result_config

        existing_signal_id = self.signal_config.signal_id if self.signal_config else ""
        config = self.editor.build_signal_config(existing_signal_id)
        if not config.signal_name:
            return None
        return config
