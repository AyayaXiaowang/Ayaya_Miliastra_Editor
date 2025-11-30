"""通用的两行结构字段表格组件。

从结构体定义编辑器中抽取，提供统一的"点击才能编辑"交互逻辑：
- 每个字段占2行（主行 + 详情行）
- 输入控件用容器包装，点击单元格背景只选中行，不触发编辑
- 必须显式点击输入框本身才能获得焦点
- 列表/字典类型支持折叠展开
- 右键菜单删除
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from PyQt6 import QtCore, QtGui, QtWidgets

from ui.dialogs.struct_definition_types import (
    canonical_to_param_type,
    is_dict_type,
    is_list_type,
    is_struct_type,
    normalize_canonical_type_name,
    param_type_to_canonical,
)
from ui.dialogs.struct_definition_value_editors import (
    ClickToEditLineEdit,
    DictValueEditor,
    ListValueEditor,
    ScrollSafeComboBox,
)
from ui.dialogs.table_edit_helpers import (
    wrap_click_to_edit_line_edit_for_table_cell,
)
from ui.foundation.context_menu_builder import ContextMenuBuilder
from ui.foundation.theme_manager import Colors, Sizes, ThemeManager


class FieldTypeComboBox(ScrollSafeComboBox):
    """字段"数据类型"下拉框：在保持通用滚轮保护行为的基础上，用于两行字段表格。

    继承 `ScrollSafeComboBox` 的规则：只有在获得焦点后才响应滚轮事件，
    滚轮优先交给外层表格用于整体滚动，避免鼠标仅悬停+滚轮就误改类型。
    """


class TwoRowFieldTableWidget(QtWidgets.QWidget):
    """通用的两行结构字段表格组件。

    每个字段占2行：
    - 主行：序号 | 名字 | 数据类型 | 数据值摘要（或基础类型的值）
    - 详情行：仅在列表/字典类型展开时显示，左侧3列合并为灰色禁用区域

    核心交互逻辑：
    - 表格禁用Qt内建编辑（EditTriggers = NoEditTriggers）
    - 所有输入控件用容器包装，点击单元格背景只选中行
    - 必须显式点击输入框本身才能获得焦点并开始编辑
    - 类型下拉框未聚焦时忽略滚轮事件
    """

    field_changed = QtCore.pyqtSignal()
    field_added = QtCore.pyqtSignal()
    field_deleted = QtCore.pyqtSignal()

    def __init__(
        self,
        supported_types: Sequence[str],
        parent: Optional[QtWidgets.QWidget] = None,
        column_headers: Optional[Sequence[str]] = None,
    ) -> None:
        super().__init__(parent)
        self._supported_types: List[str] = list(supported_types) if supported_types else ["字符串"]
        self._is_loading: bool = False
        self._struct_id_options: List[str] = []
        # 可选的字典类型解析回调：用于根据字段上下文决定键/值类型的展示，
        # 例如为节点图变量读取 GraphVariableConfig 中的 dict_key_type/dict_value_type。
        # 签名：resolver(type_name, value_mapping) -> (key_type_name, value_type_name)
        self._dict_type_resolver: Optional[
            Callable[[str, Mapping[str, Any]], Tuple[str, str]]
        ] = None

        # 列标题：默认采用“序号 / 名字 / 数据类型 / 数据值”，允许调用方按需覆盖，
        # 但仍固定为 4 列结构以保持组件行为与样式的一致性。
        default_headers: List[str] = ["序号", "名字", "数据类型", "数据值"]
        if column_headers:
            normalized_headers: List[str] = [str(title) for title in column_headers]
            # 保证长度为 4：不足时填充空字符串，多余时截断。
            if len(normalized_headers) < 4:
                normalized_headers.extend([""] * (4 - len(normalized_headers)))
            self._column_headers: List[str] = normalized_headers[:4]
        else:
            self._column_headers = default_headers

        self.table: QtWidgets.QTableWidget = QtWidgets.QTableWidget(self)
        self._setup_table()

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Sizes.SPACING_SMALL)
        layout.addWidget(self.table)

    def _setup_table(self) -> None:
        """初始化表格：列配置、样式、交互模式。"""
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(self._column_headers)
        self.table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        # 禁用 QTableWidget 自身的内建编辑，所有编辑仅通过单元格内的控件触发
        self.table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.setContextMenuPolicy(
            QtCore.Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.table.customContextMenuRequested.connect(
            self._on_table_context_menu
        )
        self._configure_table()

    def _configure_table(self) -> None:
        """配置表格样式、列宽、行高、调色板。"""
        self.table.setAlternatingRowColors(True)
        vertical_header = self.table.verticalHeader()
        if vertical_header is not None:
            vertical_header.setVisible(False)
            vertical_header.setDefaultSectionSize(
                Sizes.INPUT_HEIGHT + Sizes.PADDING_SMALL
            )
        # 使用按像素滚动模式，避免当详情行很高时“每滚一下就跳一大块”，
        # 让展开列表/字典后的滚动更加细腻、易于观察中间部分。
        self.table.setVerticalScrollMode(
            QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        header = self.table.horizontalHeader()
        if header is not None:
            # 列宽策略：
            # - 序号列：按内容自动调整；
            # - 名字列：使用较窄的固定起始宽度，可交互调节；
            # - 数据类型列：使用较窄的固定起始宽度，可交互调节；
            # - 数据值列：拉伸占据剩余空间，作为主要编辑区域。
            header.setStretchLastSection(True)
            header.setSectionResizeMode(
                0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
            )
            header.setSectionResizeMode(
                1, QtWidgets.QHeaderView.ResizeMode.Interactive
            )
            header.setSectionResizeMode(
                2, QtWidgets.QHeaderView.ResizeMode.Interactive
            )
            header.setSectionResizeMode(
                3, QtWidgets.QHeaderView.ResizeMode.Stretch
            )
            # 收窄“名字”和“数据类型”列，为“数据值”列腾出更多空间
            header.resizeSection(1, 160)
            header.resizeSection(2, 140)

        palette = self.table.palette()
        palette.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor(Colors.BG_CARD))
        palette.setColor(
            QtGui.QPalette.ColorRole.AlternateBase,
            QtGui.QColor(Colors.BG_MAIN),
        )
        palette.setColor(
            QtGui.QPalette.ColorRole.Text,
            QtGui.QColor(Colors.TEXT_PRIMARY),
        )
        palette.setColor(
            QtGui.QPalette.ColorRole.Highlight,
            QtGui.QColor(Colors.BG_SELECTED),
        )
        palette.setColor(
            QtGui.QPalette.ColorRole.HighlightedText,
            QtGui.QColor(Colors.TEXT_PRIMARY),
        )
        self.table.setPalette(palette)
        # 复用全局表格样式，保证与管理面板/信号列表等表格组件的视觉一致性
        self.table.setStyleSheet(ThemeManager.table_style())

    # ------------------------------------------------------------------
    # 公开接口：增删改查
    # ------------------------------------------------------------------

    def set_struct_id_options(self, struct_ids: Sequence[str]) -> None:
        """配置可选的结构体 ID 列表，用于“结构体 / 结构体列表”类型的数据值下拉框。"""
        options: List[str] = []
        seen: set[str] = set()
        for raw_id in struct_ids:
            text = str(raw_id).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            options.append(text)
        self._struct_id_options = options

    def set_dict_type_resolver(
        self,
        resolver: Optional[Callable[[str, Mapping[str, Any]], Tuple[str, str]]],
    ) -> None:
        """为字典字段提供可选的“键/值类型”解析回调。

        当字段类型为字典且提供了回调时，会优先使用回调结果作为键/值类型的初始展示值；
        若未提供回调或回调未返回有效结果，则回退为默认的“字符串/字符串”。
        """
        self._dict_type_resolver = resolver

    def add_field_row(
        self,
        name: str,
        type_name: str,
        value: Any,
        readonly: bool = False,
        name_prefix: str = "",
        foreground: Optional[str] = None,
        background: Optional[str] = None,
    ) -> None:
        """添加一个字段（插入主行+详情行）。

        Args:
            name: 字段名
            type_name: 数据类型（中文）
            value: 默认值/数据值
            readonly: 是否只读
            name_prefix: 名字前缀（如"🔗 [继承] "）
            foreground: 前景色（如"#888"）
            background: 背景色（如"#F5F5F5"）
        """
        self._add_field_row_internal(
            name,
            type_name,
            value,
            readonly,
            name_prefix,
            foreground,
            background,
        )
        self.field_added.emit()

        # 用户显式“添加字段”后，自动滚动到新字段所在的主行，并将其设为当前选中行。
        # 注意：批量加载场景通过 `_add_field_row_internal` 直接插入行，不会触发此逻辑，
        # 以免初始化时强制滚动到表格底部。
        table = self.table
        row_count = table.rowCount()
        if row_count < 2:
            return

        main_row_index = row_count - 2
        index_item = table.item(main_row_index, 0)
        if index_item is not None:
            table.setCurrentItem(index_item)
            table.scrollToItem(
                index_item,
                QtWidgets.QAbstractItemView.ScrollHint.PositionAtCenter,
            )
        else:
            vertical_scroll_bar = table.verticalScrollBar()
            maximum_value = vertical_scroll_bar.maximum()
            vertical_scroll_bar.setValue(maximum_value)

    def remove_field_at_row(self, row_index: int) -> None:
        """删除字段（移除主行+详情行）。"""
        if row_index < 0:
            return
        # 字段使用"两行结构"，需要同时删除字段主行与其下方的详情行
        if row_index % 2 == 1:
            main_row_index = row_index - 1
        else:
            main_row_index = row_index
        detail_row_index = main_row_index + 1
        row_count = self.table.rowCount()
        if detail_row_index < row_count:
            self.table.removeRow(detail_row_index)
        self.table.removeRow(main_row_index)
        self._refresh_row_numbers()
        self._on_content_changed()
        self.field_deleted.emit()

    def get_all_fields(self) -> List[Dict[str, Any]]:
        """获取所有字段数据。

        返回格式：
        [
            {"name": str, "type_name": str, "value": Any},
            ...
        ]
        """
        fields: List[Dict[str, Any]] = []
        row = 0
        row_count = self.table.rowCount()
        while row < row_count:
            name_widget = self._get_cell_line_edit(row, 1)
            type_widget = self._get_cell_combo_box(row, 2)

            if isinstance(name_widget, QtWidgets.QLineEdit):
                field_name = name_widget.text().strip()
            else:
                field_name = ""
            if not field_name:
                row += 2
                continue

            if isinstance(type_widget, QtWidgets.QComboBox):
                canonical_type_name = type_widget.currentText().strip()
            else:
                canonical_type_name = ""
            if not canonical_type_name:
                row += 2
                continue

            normalized_type_name = normalize_canonical_type_name(canonical_type_name)
            if is_list_type(normalized_type_name) or is_dict_type(normalized_type_name):
                value_row_index = row + 1
            else:
                value_row_index = row

            # 集合类型的详情行子表格放在合并后的第 1 列，其余类型仍在第 3 列
            value_widget = self.table.cellWidget(value_row_index, 3)
            if value_widget is None:
                value_widget = self.table.cellWidget(value_row_index, 1)
            value = self._extract_value_from_widget(canonical_type_name, value_widget)

            fields.append({
                "name": field_name,
                "type_name": canonical_type_name,
                "value": value,
            })

            row += 2

        return fields

    def load_fields(self, fields: Sequence[Mapping[str, Any]]) -> None:
        """批量加载字段。

        fields 格式：
        [
            {
                "name": str,
                "type_name": str,
                "value": Any,
                "readonly": bool (可选),
                "name_prefix": str (可选),
                "foreground": str (可选),
                "background": str (可选),
            },
            ...
        ]
        """
        self._is_loading = True
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(0)

        for field in fields:
            name = str(field.get("name", ""))
            type_name = str(field.get("type_name", ""))
            value = field.get("value")
            readonly = bool(field.get("readonly", False))
            name_prefix = str(field.get("name_prefix", ""))
            foreground = field.get("foreground")
            background = field.get("background")
            foreground_str = str(foreground) if foreground else None
            background_str = str(background) if background else None

            self._add_field_row_internal(
                name,
                type_name,
                value,
                readonly,
                name_prefix,
                foreground_str,
                background_str,
            )

        # 当 fields 为空时保持表格完全空白，由调用方决定是否添加占位行，
        # 避免在无任何字段配置时给用户造成“已存在一个字段/变量”的误解。

        self._refresh_row_numbers()
        self._is_loading = False
        self.table.setUpdatesEnabled(True)

    def clear_fields(self) -> None:
        """清空所有字段。"""
        self.table.setRowCount(0)

    # ------------------------------------------------------------------
    # 内部实现：添加字段行
    # ------------------------------------------------------------------

    def _add_field_row_internal(
        self,
        field_name: str,
        type_name: str,
        value: Any,
        readonly: bool = False,
        name_prefix: str = "",
        foreground: Optional[str] = None,
        background: Optional[str] = None,
    ) -> None:
        """内部方法：添加字段（主行+详情行）。"""
        main_row_index = self.table.rowCount()
        detail_row_index = main_row_index + 1
        self.table.insertRow(main_row_index)
        self.table.insertRow(detail_row_index)

        # 详情行：保留第 0 列作为缩进留白，其余三列合并为一个更宽的子表格区域
        # 这样列表/字典等子表格可以占据除序号列外的整行宽度，提升可见区域。
        self.table.setSpan(detail_row_index, 1, 1, 3)

        # 序号列
        index_item = QtWidgets.QTableWidgetItem(str(main_row_index + 1))
        index_item.setFlags(
            QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsEnabled
        )
        self.table.setItem(main_row_index, 0, index_item)

        # 名字列
        display_name = f"{name_prefix}{field_name}" if name_prefix else field_name
        name_edit = ClickToEditLineEdit(display_name, self.table)
        name_edit.setPlaceholderText("字段名")
        name_edit.setClearButtonEnabled(True)
        name_edit.setFixedHeight(Sizes.INPUT_HEIGHT)
        name_edit.setReadOnly(readonly)
        if readonly:
            name_edit.setStyleSheet(ThemeManager.readonly_input_style())
        name_edit.editingFinished.connect(self._on_content_changed)
        self._attach_context_menu_forwarding(name_edit)
        name_container = wrap_click_to_edit_line_edit_for_table_cell(
            self.table,
            name_edit,
        )
        self.table.setCellWidget(main_row_index, 1, name_container)
        self._attach_context_menu_forwarding(name_container)

        # 类型列
        type_combo = FieldTypeComboBox(self.table)
        type_combo.addItems(self._supported_types)
        default_type_name = type_name if type_name in self._supported_types else ""
        if not default_type_name and self._supported_types:
            default_type_name = self._supported_types[0]
        if default_type_name:
            type_combo.blockSignals(True)
            type_combo.setCurrentText(default_type_name)
            type_combo.blockSignals(False)
        type_combo.setFixedHeight(Sizes.INPUT_HEIGHT)
        type_combo.setEnabled(not readonly)
        type_combo.currentTextChanged.connect(self._on_field_type_changed)
        type_container = QtWidgets.QWidget(self.table)
        type_layout = QtWidgets.QVBoxLayout(type_container)
        type_layout.setContentsMargins(0, 0, 0, 0)
        type_layout.setSpacing(0)
        type_layout.addWidget(type_combo)
        type_layout.addStretch(1)
        self.table.setCellWidget(main_row_index, 2, type_container)
        self._attach_context_menu_forwarding(type_container)

        # 默认隐藏详情行
        self.table.setRowHidden(detail_row_index, True)

        # 数据值列
        current_type_name = type_combo.currentText()
        self._set_value_editor_for_field_row(
            main_row_index,
            current_type_name,
            value,
            readonly,
        )

        # 应用行样式：
        # - 状态色（继承/覆写/额外变量）仅用于"序号"列的背景色，作为整行状态的紧凑提示；
        # - 其余列保持统一的表格底色，避免在嵌套了输入框/子表格的单元格中出现“只铺一小块”的底色块。
        if foreground or background:
            index_item = self.table.item(main_row_index, 0)
            if index_item is not None:
                if foreground:
                    index_item.setForeground(QtGui.QColor(foreground))
                if background:
                    index_item.setBackground(QtGui.QColor(background))

            # 若调用方传入前景色，则尽量让其它列的文本也继承该颜色；
            # 不额外对单元格内控件设置 background-color，交由主题与只读样式统一管理。
            if foreground:
                for col in range(1, 4):
                    item = self.table.item(main_row_index, col)
                    if item is not None:
                        item.setForeground(QtGui.QColor(foreground))

        if not self._is_loading:
            self._refresh_row_numbers()

    def _refresh_row_numbers(self) -> None:
        """重新编号主行的序号列。"""
        display_index = 1
        row = 0
        row_count = self.table.rowCount()
        while row < row_count:
            item = self.table.item(row, 0)
            if item is None:
                item = QtWidgets.QTableWidgetItem()
                item.setFlags(
                    QtCore.Qt.ItemFlag.ItemIsSelectable
                    | QtCore.Qt.ItemFlag.ItemIsEnabled
                )
                self.table.setItem(row, 0, item)
            item.setText(str(display_index))

            detail_row = row + 1
            if detail_row < row_count:
                detail_item = self.table.item(detail_row, 0)
                if detail_item is None:
                    detail_item = QtWidgets.QTableWidgetItem()
                    self.table.setItem(detail_row, 0, detail_item)
                detail_item.setText("")
                detail_item.setFlags(QtCore.Qt.ItemFlag.NoItemFlags)
                detail_item.setBackground(QtGui.QColor(Colors.BG_DISABLED))

            display_index += 1
            row += 2

    # ------------------------------------------------------------------
    # 数据值编辑器
    # ------------------------------------------------------------------

    def _set_value_editor_for_field_row(
        self,
        main_row_index: int,
        type_name: str,
        value: Any,
        readonly: bool = False,
    ) -> None:
        """根据字段类型为"两行结构"设置合适的数据值编辑控件。"""
        detail_row_index = main_row_index + 1
        row_count = self.table.rowCount()
        if detail_row_index >= row_count:
            return

        # 清理旧的编辑控件
        old_main_widget = self.table.cellWidget(main_row_index, 3)
        if old_main_widget is not None:
            self.table.removeCellWidget(main_row_index, 3)
        old_detail_widget = self.table.cellWidget(detail_row_index, 3)
        if old_detail_widget is not None:
            self.table.removeCellWidget(detail_row_index, 3)
        alt_detail_widget = self.table.cellWidget(detail_row_index, 1)
        if alt_detail_widget is not None and alt_detail_widget is not old_detail_widget:
            self.table.removeCellWidget(detail_row_index, 1)

        value_widget = self._create_value_cell_widget(type_name, value, readonly)

        if isinstance(value_widget, (ListValueEditor, DictValueEditor)):
            # 集合型字段：
            # - 主行用于展示"折叠按钮 + 摘要"（仍放在数据值列中）；
            # - 详情行承载真正的子表格区域，占用除序号列外的整行宽度。
            header_container = value_widget.create_header_proxy(self.table)
            self.table.setCellWidget(main_row_index, 3, header_container)
            self.table.setCellWidget(detail_row_index, 1, value_widget)
            self._attach_context_menu_forwarding(header_container)
            self._attach_context_menu_forwarding(value_widget)
            self.table.setRowHidden(detail_row_index, False)
            self._adjust_row_height_for_value_widget(detail_row_index, value_widget)

            default_row_height = Sizes.INPUT_HEIGHT + Sizes.PADDING_SMALL
            self.table.setRowHeight(main_row_index, default_row_height)
        else:
            # 基础/结构体类型：单行结构，详情行保持隐藏
            self.table.setCellWidget(main_row_index, 3, value_widget)
            self._attach_context_menu_forwarding(value_widget)
            self.table.setRowHidden(detail_row_index, True)
            self._adjust_row_height_for_value_widget(main_row_index, value_widget)

    def _create_value_cell_widget(
        self,
        type_name: str,
        value: Any,
        readonly: bool = False,
    ) -> QtWidgets.QWidget:
        """创建值编辑控件（基础/列表/字典/结构体）。"""
        canonical_type_name = normalize_canonical_type_name(type_name or "")
        if not canonical_type_name:
            line_edit = ClickToEditLineEdit("", self.table)
            line_edit.setPlaceholderText("无初始值")
            line_edit.setClearButtonEnabled(True)
            line_edit.setMinimumHeight(Sizes.INPUT_HEIGHT)
            line_edit.setReadOnly(readonly)
            if readonly:
                line_edit.setStyleSheet(ThemeManager.readonly_input_style())
            line_edit.editingFinished.connect(self._on_content_changed)
            return self._wrap_line_edit_in_value_cell(line_edit)

        # 列表类型
        if is_list_type(canonical_type_name):
            list_values: List[str] = []
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                for element in value:
                    list_values.append(str(element))
            editor = ListValueEditor(
                canonical_type_name,
                list_values,
                parent=self.table,
            )
            editor.value_changed.connect(self._on_content_changed)
            if readonly:
                # 只读模式下移除子表格末尾的“新增占位行”，避免出现伪“新建”入口。
                editor.set_read_only(True)
            return editor

        # 字典类型
        if is_dict_type(canonical_type_name):
            key_type_name = "字符串"
            value_type_name = "字符串"
            entries: List[Tuple[str, str]] = []
            if isinstance(value, Mapping):
                # 若上层提供了键/值类型解析回调，则优先使用回调结果
                if self._dict_type_resolver is not None:
                    resolved = self._dict_type_resolver(
                        type_name,
                        value,
                    )
                    if (
                        isinstance(resolved, tuple)
                        and len(resolved) == 2
                        and isinstance(resolved[0], str)
                        and isinstance(resolved[1], str)
                    ):
                        resolved_key_type = resolved[0].strip()
                        resolved_value_type = resolved[1].strip()
                        if resolved_key_type:
                            key_type_name = resolved_key_type
                        if resolved_value_type:
                            value_type_name = resolved_value_type

                for key, val in value.items():
                    entries.append((str(key), str(val)))
            base_type_options = self._get_base_types()
            # 确保当前字段的键/值类型出现在下拉选项中，即便它们本身是列表类型等派生类型，
            # 以便在节点图变量等场景下正确展示如“GUID列表”之类的值类型。
            normalized_options: List[str] = list(base_type_options)
            if key_type_name not in normalized_options:
                normalized_options.insert(0, key_type_name)
            if value_type_name not in normalized_options:
                normalized_options.append(value_type_name)
            editor = DictValueEditor(
                key_type_name,
                value_type_name,
                entries,
                base_type_options=normalized_options,
                parent=self.table,
            )
            editor.value_changed.connect(self._on_content_changed)
            if readonly:
                # 只读模式下移除子表格末尾的“新增占位行”，避免出现伪“新建”入口。
                editor.set_read_only(True)
            return editor

        # 结构体 / 结构体列表
        if is_struct_type(canonical_type_name):
            struct_id_text = ""
            if isinstance(value, str):
                struct_id_text = value.strip()

            # 若未配置结构体列表，则退化为手动输入模式
            if not self._struct_id_options:
                editor = ClickToEditLineEdit(struct_id_text, self.table)
                editor.setPlaceholderText("结构体ID（可选）")
                editor.setMinimumHeight(Sizes.INPUT_HEIGHT)
                editor.setReadOnly(readonly)
                if readonly:
                    editor.setStyleSheet(ThemeManager.readonly_input_style())
                editor.editingFinished.connect(self._on_content_changed)
                return self._wrap_line_edit_in_value_cell(editor)

            # 使用下拉框选择结构体 ID（首项为空表示“未选择”）
            combo = ScrollSafeComboBox(self.table)
            combo.setMinimumHeight(Sizes.INPUT_HEIGHT)
            combo.setEditable(False)
            combo.addItem("（未选择）", "")

            # 保持传入顺序并去重
            seen_ids: set[str] = set()
            for struct_id in self._struct_id_options:
                text = str(struct_id).strip()
                if not text or text in seen_ids:
                    continue
                seen_ids.add(text)
                combo.addItem(text, text)

            if struct_id_text:
                index = combo.findData(struct_id_text)
                if index < 0:
                    combo.addItem(struct_id_text, struct_id_text)
                    index = combo.findData(struct_id_text)
                if index >= 0:
                    combo.setCurrentIndex(index)
            else:
                combo.setCurrentIndex(0)

            combo.setEnabled(not readonly)
            if readonly:
                combo.setStyleSheet(ThemeManager.readonly_input_style())
            combo.currentIndexChanged.connect(lambda _index: self._on_content_changed())

            container = QtWidgets.QWidget(self.table)
            layout = QtWidgets.QVBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            layout.addWidget(combo)
            layout.addStretch(1)

            self._attach_context_menu_forwarding(combo)
            self._attach_context_menu_forwarding(container)
            return container

        # 其余基础类型
        value_text = str(value) if value is not None else ""
        line_edit = ClickToEditLineEdit(value_text, self.table)
        line_edit.setPlaceholderText("无初始值")
        line_edit.setClearButtonEnabled(True)
        line_edit.setMinimumHeight(Sizes.INPUT_HEIGHT)
        line_edit.setReadOnly(readonly)
        if readonly:
            line_edit.setStyleSheet(ThemeManager.readonly_input_style())
        line_edit.editingFinished.connect(self._on_content_changed)
        return self._wrap_line_edit_in_value_cell(line_edit)

    def _extract_value_from_widget(
        self,
        type_name: str,
        value_widget: Optional[QtWidgets.QWidget],
    ) -> Any:
        """从值编辑控件中提取数据。"""
        normalized_type_name = normalize_canonical_type_name(type_name)

        # 列表类型
        if is_list_type(normalized_type_name):
            if isinstance(value_widget, ListValueEditor):
                return value_widget.get_values()
            return []

        # 字典类型
        if is_dict_type(normalized_type_name):
            if isinstance(value_widget, DictValueEditor):
                state = value_widget.get_dict_state()
                raw_entries: List[Tuple[str, str]] = state.get("entries", [])
                mapping: Dict[str, str] = {}
                for key_text, value_text in raw_entries:
                    key_normalized = key_text.strip()
                    if not key_normalized and not value_text:
                        continue
                    mapping[key_normalized] = value_text
                return mapping
            return {}

        # 结构体 / 结构体列表
        if is_struct_type(normalized_type_name):
            if isinstance(value_widget, QtWidgets.QComboBox):
                current_data = value_widget.currentData()
                if isinstance(current_data, str):
                    return current_data
                return value_widget.currentText()
            if isinstance(value_widget, QtWidgets.QWidget):
                combo = value_widget.findChild(QtWidgets.QComboBox)
                if isinstance(combo, QtWidgets.QComboBox):
                    current_data = combo.currentData()
                    if isinstance(current_data, str):
                        return current_data
                    return combo.currentText()

            # 退化为从文本编辑框读取
            value_text = ""
            if isinstance(value_widget, QtWidgets.QLineEdit):
                value_text = value_widget.text()
            elif isinstance(value_widget, QtWidgets.QWidget):
                inner_editor = value_widget.findChild(QtWidgets.QLineEdit)
                if isinstance(inner_editor, QtWidgets.QLineEdit):
                    value_text = inner_editor.text()
            return value_text

        # 其余基础类型
        value_text = ""
        if isinstance(value_widget, QtWidgets.QLineEdit):
            value_text = value_widget.text()
        elif isinstance(value_widget, QtWidgets.QWidget):
            inner_editor = value_widget.findChild(QtWidgets.QLineEdit)
            if isinstance(inner_editor, QtWidgets.QLineEdit):
                value_text = inner_editor.text()
        return value_text

    def _wrap_line_edit_in_value_cell(
        self,
        line_edit: QtWidgets.QLineEdit,
    ) -> QtWidgets.QWidget:
        """为"数据值"列的单行编辑框提供容器包装。"""
        container = wrap_click_to_edit_line_edit_for_table_cell(
            self.table,
            line_edit,
        )
        self._attach_context_menu_forwarding(line_edit)
        self._attach_context_menu_forwarding(container)
        return container

    def _get_base_types(self) -> List[str]:
        """供字典编辑对话框选择键/值类型使用的"基础类型"集合。"""
        base_types: List[str] = []
        for type_name in self._supported_types:
            normalized = normalize_canonical_type_name(type_name)
            if (
                not is_list_type(normalized)
                and not is_dict_type(normalized)
                and not is_struct_type(normalized)
            ):
                base_types.append(normalized)
        if not base_types:
            base_types.append("字符串")
        # 去重但保持顺序
        seen: set[str] = set()
        result: List[str] = []
        for name in base_types:
            if name in seen:
                continue
            seen.add(name)
            result.append(name)
        return result

    def _adjust_row_height_for_value_widget(
        self,
        row_index: int,
        value_widget: QtWidgets.QWidget,
    ) -> None:
        """根据"数据值"单元格实际内容调整行高。"""
        default_row_height = Sizes.INPUT_HEIGHT + Sizes.PADDING_SMALL

        if isinstance(value_widget, (ListValueEditor, DictValueEditor)):
            is_collapsed_getter = getattr(value_widget, "is_collapsed", None)
            is_collapsed = (
                bool(is_collapsed_getter())
                if callable(is_collapsed_getter)
                else False
            )

            if is_collapsed:
                self.table.setRowHidden(row_index, True)
                return

            self.table.setRowHidden(row_index, False)

            # 直接根据集合编辑器整体的 sizeHint 计算行高，
            # 其中已经包含“键/值类型行（若有）+ 工具栏 + 子表格”在内的总高度。
            value_widget.updateGeometry()
            widget_height = value_widget.sizeHint().height()
            target_height = max(default_row_height * 2, widget_height)
        else:
            value_widget.updateGeometry()
            widget_height = value_widget.sizeHint().height()
            target_height = max(default_row_height, widget_height)

        self.table.setRowHeight(row_index, int(target_height))

        # 调试：输出父表格行高与集合编辑器类型，便于与子表格高度对齐排查
        kind = "其他"
        if isinstance(value_widget, ListValueEditor):
            kind = "列表"
        elif isinstance(value_widget, DictValueEditor):
            kind = "字典"
        actual_height = self.table.rowHeight(row_index)
        hint_height = value_widget.sizeHint().height()
        print(
            "[UI调试/TwoRowField]",
            f"kind={kind}",
            f"row_index={row_index}",
            f"hint_height={hint_height}",
            f"target_height={int(target_height)}",
            f"actual_height={actual_height}",
        )

    # ------------------------------------------------------------------
    # 事件处理
    # ------------------------------------------------------------------

    def _on_field_type_changed(self, _new_text: str) -> None:
        """类型下拉框变化时重建值编辑器。"""
        sender = self.sender()
        if not isinstance(sender, QtWidgets.QComboBox):
            return
        for row in range(self.table.rowCount()):
            type_widget = self._get_cell_combo_box(row, 2)
            if type_widget is sender:
                current_type_name = sender.currentText()
                self._set_value_editor_for_field_row(
                    row,
                    current_type_name,
                    None,
                )
                break
        self._on_content_changed()

    def _on_content_changed(self) -> None:
        """内容变化时重新调整行高并发射信号。"""
        if self._is_loading:
            return
        row_index = 0
        row_count = self.table.rowCount()
        while row_index < row_count:
            value_widget_main = self.table.cellWidget(row_index, 3)
            value_widget_detail = None
            detail_row_index = row_index + 1
            if detail_row_index < row_count:
                value_widget_detail = self.table.cellWidget(detail_row_index, 3)
                if value_widget_detail is None:
                    # 集合类型的详情行子表格被放在合并后的第 1 列
                    value_widget_detail = self.table.cellWidget(detail_row_index, 1)

            if isinstance(value_widget_detail, (ListValueEditor, DictValueEditor)):
                self._adjust_row_height_for_value_widget(
                    detail_row_index, value_widget_detail
                )
            elif value_widget_main is not None:
                self._adjust_row_height_for_value_widget(row_index, value_widget_main)

            row_index += 2
        self.field_changed.emit()

    def _on_table_context_menu(self, pos: QtCore.QPoint) -> None:
        """右键菜单：删除字段。"""
        index = self.table.indexAt(pos)
        row_index = index.row()
        if row_index < 0:
            return
        builder = ContextMenuBuilder(self)
        builder.add_action("删除字段", lambda: self.remove_field_at_row(row_index))
        builder.exec_for(self.table, pos)

    def _attach_context_menu_forwarding(self, widget: QtWidgets.QWidget) -> None:
        """为嵌入表格的子控件接入统一的右键菜单转发逻辑。"""
        widget.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        widget.customContextMenuRequested.connect(self._on_cell_widget_context_menu)

    def _on_cell_widget_context_menu(self, pos: QtCore.QPoint) -> None:
        """将单元格内控件的右键菜单事件转发给表格。"""
        sender_widget = self.sender()
        if not isinstance(sender_widget, QtWidgets.QWidget):
            return
        if not isinstance(self.table, QtWidgets.QTableWidget):
            return

        global_pos = sender_widget.mapToGlobal(pos)
        viewport_pos = self.table.viewport().mapFromGlobal(global_pos)
        self._on_table_context_menu(viewport_pos)

    def _get_cell_line_edit(self, row: int, column: int) -> Optional[QtWidgets.QLineEdit]:
        """获取指定单元格内的 QLineEdit。"""
        widget = self.table.cellWidget(row, column)
        if isinstance(widget, QtWidgets.QLineEdit):
            return widget
        if isinstance(widget, QtWidgets.QWidget):
            return widget.findChild(QtWidgets.QLineEdit)
        return None

    def _get_cell_combo_box(
        self,
        row: int,
        column: int,
    ) -> Optional[QtWidgets.QComboBox]:
        """获取指定单元格内的 QComboBox。"""
        widget = self.table.cellWidget(row, column)
        if isinstance(widget, QtWidgets.QComboBox):
            return widget
        if isinstance(widget, QtWidgets.QWidget):
            return widget.findChild(QtWidgets.QComboBox)
        return None


__all__ = ["TwoRowFieldTableWidget", "FieldTypeComboBox"]

