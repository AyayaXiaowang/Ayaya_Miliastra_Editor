from __future__ import annotations

from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from PyQt6 import QtCore, QtGui, QtWidgets

from engine.configs.specialized.node_graph_configs import (
    STRUCT_TYPE_BASIC,
)
from app.ui.dialogs.struct_definition_types import (
    is_dict_type,
    is_list_type,
    is_struct_type,
    normalize_canonical_type_name,
)
from app.ui.dialogs.struct_definition_value_editors import ClickToEditLineEdit
from app.ui.foundation.base_widgets import BaseDialog
from app.ui.foundation import fonts as ui_fonts
from app.ui.foundation.theme_manager import Sizes, ThemeManager
from app.ui.foundation import dialog_utils
from app.ui.widgets.two_row_field_table_widget import TwoRowFieldTableWidget


class StructDefinitionEditorWidget(QtWidgets.QWidget):
    """结构体定义编辑核心组件。

    提供"结构体名 + 字段表格"的编辑 UI，可用于弹窗或嵌入右侧属性面板。
    内部使用 TwoRowFieldTableWidget 通用组件实现字段表格。
    """

    struct_changed = QtCore.pyqtSignal()

    def __init__(
        self,
        *,
        parent: Optional[QtWidgets.QWidget] = None,
        supported_types: Sequence[str] | None = None,
        struct_type: str = STRUCT_TYPE_BASIC,
    ) -> None:
        super().__init__(parent)
        self._supported_types: List[str] = list(supported_types) if supported_types else ["字符串"]
        self._allow_edit_name: bool = True
        self._struct_type: str = struct_type or STRUCT_TYPE_BASIC
        self._is_read_only: bool = False

        self.struct_name_edit: QtWidgets.QLineEdit
        self.fields_table_widget: TwoRowFieldTableWidget
        self.add_field_button: QtWidgets.QPushButton

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

        self.struct_name_edit = ClickToEditLineEdit(self)
        self.struct_name_edit.setPlaceholderText("结构体名称，例如：武器数据")
        form_layout.addRow("结构体名*:", self.struct_name_edit)

        layout.addLayout(form_layout)

        fields_label = QtWidgets.QLabel("字段列表")
        fields_label.setFont(
            ui_fonts.ui_font(10, bold=True)
        )
        fields_label.setStyleSheet(ThemeManager.heading(4))
        layout.addWidget(fields_label)

        toolbar_layout = QtWidgets.QHBoxLayout()
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(Sizes.SPACING_SMALL)
        self.add_field_button = QtWidgets.QPushButton("+ 添加字段", self)
        toolbar_layout.addWidget(self.add_field_button)
        toolbar_layout.addStretch()
        layout.addLayout(toolbar_layout)

        # 使用通用的两行结构字段表格组件
        self.fields_table_widget = TwoRowFieldTableWidget(
            self._supported_types, parent=self
        )
        layout.addWidget(self.fields_table_widget)

        # 连接信号
        self.struct_name_edit.editingFinished.connect(self._on_editor_content_changed)
        self.add_field_button.clicked.connect(self._on_add_field)
        self.fields_table_widget.field_changed.connect(self._on_editor_content_changed)

    # ------------------------------------------------------------------
    # 加载与字段表格操作
    # ------------------------------------------------------------------

    def load_struct(
        self,
        *,
        struct_name: str,
        fields: Sequence[Mapping[str, object]],
        allow_edit_name: bool,
    ) -> None:
        """从解析后的字段列表加载结构体定义。

        fields 中的每一项应包含 name/type_name/value_node 三个键。
        """
        self._allow_edit_name = allow_edit_name

        self.struct_name_edit.setText(struct_name)
        # 是否允许编辑名称由 allow_edit_name 与只读状态共同决定
        is_name_read_only = (not allow_edit_name) or self._is_read_only
        self.struct_name_edit.setReadOnly(is_name_read_only)
        if is_name_read_only:
            self.struct_name_edit.setStyleSheet(ThemeManager.readonly_input_style())
        else:
            # 清除只读样式，回退为主题默认输入框样式
            self.struct_name_edit.setStyleSheet("")

        # 根据结构体类型切换值列展示模式与含义：
        # - 基础结构体：值列仍展示/编辑默认数据值；
        # - 局内存档结构体：值列改为展示列表长度等元信息（lenth），不再展示默认数据值。
        from engine.configs.specialized.node_graph_configs import STRUCT_TYPE_INGAME_SAVE

        is_ingame_save_struct = self._struct_type == STRUCT_TYPE_INGAME_SAVE
        if is_ingame_save_struct:
            # 局内存档结构体：第四列展示“列表长度”，不再展示“数据值”
            self.fields_table_widget.set_column_headers(["序号", "字段名", "数据类型", "列表长度"])
            self.fields_table_widget.set_value_mode("metadata")
        else:
            # 基础结构体：保持原有的“数据值”列语义
            self.fields_table_widget.set_column_headers(["序号", "名字", "数据类型", "数据值"])
            self.fields_table_widget.set_value_mode("value")

        # 转换为通用组件所需的字段格式
        converted_fields: List[Dict[str, object]] = []
        for field in fields:
            field_name_value = field.get("name")
            type_name_value = field.get("type_name")
            value_node = field.get("value_node")
            name_text = str(field_name_value) if isinstance(field_name_value, str) else ""
            type_name = str(type_name_value) if isinstance(type_name_value, str) else ""

            if is_ingame_save_struct:
                # 局内存档结构体：值列展示 lenth 元数据（如存在）
                length_value = field.get("lenth")
                if isinstance(length_value, (int, float)):
                    value = int(length_value)
                else:
                    value = ""
            else:
                # 基础结构体：从 value_node 提取默认数据值
                value = self._extract_value_from_value_node(type_name, value_node)

            converted_fields.append(
                {
                    "name": name_text,
                    "type_name": type_name,
                    "value": value,
                    # 在只读模式下，字段级别标记为只读，仍允许表格滚动与展开详情。
                    "readonly": self._is_read_only,
                }
            )

        if not converted_fields:
            converted_fields.append(
                {
                    "name": "",
                    "type_name": "",
                    "value": None,
                    "readonly": self._is_read_only,
                }
            )

        self.fields_table_widget.load_fields(converted_fields)

    def _extract_value_from_value_node(
        self,
        type_name: str,
        value_node: Optional[object],
    ) -> object:
        """从value_node中提取值，适配通用组件格式。"""
        if not isinstance(value_node, Mapping):
            return None
            
        normalized_type = normalize_canonical_type_name(type_name or "")
        
        # 列表类型
        if is_list_type(normalized_type):
            items = value_node.get("value")
            if isinstance(items, Sequence) and not isinstance(items, (str, bytes)):
                return [str(element) for element in items]
            return []
        
        # 字典类型
        if is_dict_type(normalized_type):
            inner_value = value_node.get("value")
            if isinstance(inner_value, Mapping):
                raw_entries = inner_value.get("value")
                if isinstance(raw_entries, Sequence):
                    result = {}
                    for entry in raw_entries:
                        if not isinstance(entry, Mapping):
                            continue
                        key_node = entry.get("key")
                        value_node_inner = entry.get("value")
                        key_text = ""
                        value_text = ""
                        if isinstance(key_node, Mapping):
                            key_inner_value = key_node.get("value")
                            if isinstance(key_inner_value, str):
                                key_text = key_inner_value
                        if isinstance(value_node_inner, Mapping):
                            value_inner_value = value_node_inner.get("value")
                            if isinstance(value_inner_value, str):
                                value_text = value_inner_value
                        if key_text or value_text:
                            result[key_text] = value_text
                    return result
            return {}
        
        # 结构体类型
        if is_struct_type(normalized_type):
            inner_struct = value_node.get("value")
            if isinstance(inner_struct, Mapping):
                struct_id_value = inner_struct.get("structId")
                if isinstance(struct_id_value, str):
                    return struct_id_value
            return ""
        
        # 基础类型
        inner_value = value_node.get("value")
        if isinstance(inner_value, str):
            return inner_value
        return ""

    def _on_add_field(self) -> None:
        self.fields_table_widget.add_field_row("", "", None)
        self._on_editor_content_changed()

    # ------------------------------------------------------------------
    # 校验与导出
    # ------------------------------------------------------------------

    def build_struct_data(self) -> Dict[str, object]:
        """导出符合 test.json 规范的结构体定义 JSON 片段（不含资源 id 等元信息）。"""
        struct_name = self.struct_name_edit.text().strip()
        value_entries: List[Dict[str, object]] = []

        # 从通用组件获取所有字段
        fields = self.fields_table_widget.get_all_fields()
        for field in fields:
            field_name = field.get("name", "").strip()
            if not field_name:
                continue
                
            canonical_type_name = field.get("type_name", "").strip()
            if not canonical_type_name:
                continue

            # 直接使用中文类型名作为 param_type，不再转换成英文
            value = field.get("value")

            # 对于局内存档结构体，仅输出结构信息与元数据，不再写入字段默认值
            from engine.configs.specialized.node_graph_configs import STRUCT_TYPE_INGAME_SAVE

            if self._struct_type == STRUCT_TYPE_INGAME_SAVE:
                entry: Dict[str, object] = {
                    "key": field_name,
                    "param_type": canonical_type_name,
                }
                # 若值列被用于编辑 lenth（列表长度），则将其写回字段元数据
                if canonical_type_name.endswith("列表") and canonical_type_name != "结构体列表":
                    if isinstance(value, (int, float)):
                        entry["lenth"] = int(value)
                value_entries.append(entry)
            else:
                # 基础结构体仍按原有方式写入默认数据值
                value_node = self._build_value_node(
                    canonical_type_name, canonical_type_name, value
                )
                value_entries.append(
                    {
                        "key": field_name,
                        "param_type": canonical_type_name,
                        "value": value_node,
                    }
                )

        struct_data: Dict[str, object] = {
            "type": "结构体",
            "struct_ype": self._struct_type,
            "name": struct_name,
            "value": value_entries,
        }
        return struct_data

    def validate_and_build(
        self,
        *,
        parent_for_message_box: Optional[QtWidgets.QWidget] = None,
    ) -> Optional[Dict[str, object]]:
        """校验当前输入并在通过时返回结构体定义数据。

        若校验失败，会弹出 MessageBox 并返回 None。
        """
        parent = parent_for_message_box or self
        struct_name = self.struct_name_edit.text().strip()
        if not struct_name:
            dialog_utils.show_warning_dialog(parent, "警告", "结构体名不能为空")
            return None

        fields = self.fields_table_widget.get_all_fields()
        has_at_least_one_field = any(f.get("name", "").strip() for f in fields)
        if not has_at_least_one_field:
            dialog_utils.show_warning_dialog(parent, "警告", "至少需要定义一个字段")
            return None

        return self.build_struct_data()
    
    def _on_editor_content_changed(self) -> None:
        """内容变化时发射信号。"""
        self.struct_changed.emit()

    # ------------------------------------------------------------------
    # 只读模式控制
    # ------------------------------------------------------------------

    def set_read_only(self, read_only: bool) -> None:
        """切换编辑器的只读状态。

        - 只读模式下禁用名称输入、字段新增与字段表格编辑，但仍允许滚动浏览；
        - 对话框等需要完整编辑能力的场景不应启用该模式。
        """
        self._is_read_only = bool(read_only)

        is_name_read_only = (not self._allow_edit_name) or self._is_read_only
        self.struct_name_edit.setReadOnly(is_name_read_only)
        if is_name_read_only:
            self.struct_name_edit.setStyleSheet(ThemeManager.readonly_input_style())
        else:
            self.struct_name_edit.setStyleSheet("")

        # 只读模式下禁用“添加字段”按钮，但保留表格滚动与展开/折叠能力；
        # 字段本身的可编辑性通过 load_struct 中的 readonly 标记控制。
        self.add_field_button.setEnabled(not self._is_read_only)

    def _build_value_node(
        self,
        canonical_type_name: str,
        param_type_name: str,
        value: Any,
    ) -> Dict[str, object]:
        """根据字段类型与值导出对应的 value 节点。

        返回值直接写入字段对象的 `"value"` 字段。
        """
        normalized_type_name = normalize_canonical_type_name(canonical_type_name)

        # 结构体 / 结构体列表
        if is_struct_type(normalized_type_name):
            struct_id_text = str(value) if value else ""

            if normalized_type_name == "结构体":
                inner_value = {
                    "structId": struct_id_text,
                    "type": "Struct",
                    "value": [],
                }
                return {
                    "param_type": "结构体",
                    "value": inner_value,
                }

            # 结构体列表
            inner_list_value = {
                "structId": struct_id_text,
                "value": [],
            }
            return {
                "param_type": "结构体列表",
                "value": inner_list_value,
            }

        # 字典
        if is_dict_type(normalized_type_name):
            if isinstance(value, Mapping):
                entries = [(k, v) for k, v in value.items()]
            else:
                entries = []

            # 使用中文类型名
            key_type_name = "字符串"
            value_type_name = "字符串"

            dict_entries: List[Dict[str, object]] = []
            for key_text, value_text in entries:
                dict_entries.append(
                    {
                        "key": {
                            "param_type": key_type_name,
                            "value": str(key_text),
                        },
                        "value": {
                            "param_type": value_type_name,
                            "value": str(value_text),
                        },
                    }
                )

            inner_value = {
                "type": "Dict",
                "key_type": key_type_name,
                "value_type": value_type_name,
                "value": dict_entries,
            }
            return {
                "param_type": "字典",
                "value": inner_value,
            }

        # 列表
        if is_list_type(normalized_type_name):
            list_values: List[str] = []
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                list_values = [str(v) for v in value]
            return {
                "param_type": param_type_name,
                "value": list_values,
            }

        # 其余基础类型
        value_text = str(value) if value is not None else ""
        return {
            "param_type": param_type_name,
            "value": value_text,
        }
        
        
class StructDefinitionDialog(BaseDialog):
    """结构体定义编辑对话框。
    
    使用 `StructDefinitionEditorWidget` 提供字段编辑能力，并包装为标准的“确定/取消”对话框。
    """
    
    def __init__(
        self,
        *,
        title: str,
        parent: Optional[QtWidgets.QWidget],
        initial_name: str,
        initial_fields: Sequence[Mapping[str, object]],
        allow_edit_name: bool,
        supported_types: Sequence[str],
        struct_type: str = STRUCT_TYPE_BASIC,
    ) -> None:
        self._struct_data_cache: Optional[Dict[str, object]] = None
        
        super().__init__(
            title=title,
            width=640,
            height=520,
            parent=parent,
        )
        
        self.editor = StructDefinitionEditorWidget(
            parent=self,
            supported_types=supported_types,
            struct_type=struct_type,
        )

        self._build_content(
            initial_name=initial_name,
            initial_fields=initial_fields,
            allow_edit_name=allow_edit_name,
        )
    
    def _build_content(
        self,
        *,
        initial_name: str,
        initial_fields: Sequence[Mapping[str, object]],
        allow_edit_name: bool,
    ) -> None:
        layout = self.content_layout
        layout.setContentsMargins(
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
        )
        layout.setSpacing(Sizes.SPACING_MEDIUM)
        
        layout.addWidget(self.editor, 1)
        
        self.editor.load_struct(
            struct_name=initial_name,
            fields=initial_fields,
            allow_edit_name=allow_edit_name,
        )
    
    def _apply_styles(self) -> None:
        self.setStyleSheet(
            ThemeManager.dialog_surface_style(
                include_inputs=True,
                include_tables=True,
                include_scrollbars=True,
            )
        )
    
    # ------------------------------------------------------------------
    # 确认与数据导出
    # ------------------------------------------------------------------
    
    def validate(self) -> bool:
        result = self.editor.validate_and_build(parent_for_message_box=self)
        if result is None:
            return False
        self._struct_data_cache = result
        return True

    def get_struct_data(self) -> Dict[str, object]:
        """导出符合 test.json 规范的结构体定义 JSON 片段（不含资源 id 等元信息）。"""
        if self._struct_data_cache is not None:
            return dict(self._struct_data_cache)
        return self.editor.build_struct_data()


__all__ = ["StructDefinitionEditorWidget", "StructDefinitionDialog"]


