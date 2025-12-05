"""通用组件表单工厂。

本模块根据组件类型为通用组件标签页构建配置表单区域：
- 针对少量常用组件（如“背包”“铭牌”）提供结构化表单；
- 其它暂未接入自动表单的组件统一展示只读占位说明，避免误导为“不可配置”。

后续可以在此模块中按组件类型逐步扩展更完整的表单定义。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PyQt6 import QtWidgets

from ui.dialogs.graph_selection_dialog import GraphSelectionDialog
from ui.foundation import dialog_utils
from ui.foundation.toggle_switch import ToggleSwitch


class NameplateConfigForm(QtWidgets.QWidget):
    """“铭牌”组件配置表单。

    设计目标：
    - 支持在同一组件下维护多条“铭牌配置”，配置 ID 从 1 开始递增；
    - 为每条配置提供“初始生效”开关，用于写回 `初始生效配置ID列表`；
    - 字段命名与 `engine.configs.components.ui_configs.NameplateConfig` 的 `to_dict` 输出保持一致。
    """

    def __init__(
        self,
        settings: Dict[str, object],
        parent: QtWidgets.QWidget,
        *,
        resource_manager: Optional[object] = None,
        package_index_manager: Optional[object] = None,
    ) -> None:
        super().__init__(parent)
        self._settings: Dict[str, object] = settings
        self._resource_manager = resource_manager
        self._package_index_manager = package_index_manager
        self._nameplate_dicts: List[Dict[str, Any]] = []
        self._current_config_index: int = -1

        self._init_base_structure()
        self._build_ui()
        self._rebuild_config_list()

    # ------------------------------------------------------------------ 基础结构与加载

    def _init_base_structure(self) -> None:
        """确保 settings 中存在铭牌所需的基础字段。"""
        raw_list = self._settings.get("铭牌配置列表")
        if isinstance(raw_list, list):
            self._nameplate_dicts = [
                item if isinstance(item, dict) else {}
                for item in raw_list
            ]
        else:
            self._nameplate_dicts = []
        self._settings["铭牌配置列表"] = self._nameplate_dicts

        initial_active_ids = self._settings.get("初始生效配置ID列表")
        if not isinstance(initial_active_ids, list):
            self._settings["初始生效配置ID列表"] = []

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(6)

        # 顶部：配置选择与增删
        selector_layout = QtWidgets.QHBoxLayout()
        selector_label = QtWidgets.QLabel("铭牌配置：", self)
        selector_layout.addWidget(selector_label)

        self._config_combo = QtWidgets.QComboBox(self)
        self._config_combo.currentIndexChanged.connect(self._on_config_combo_changed)
        selector_layout.addWidget(self._config_combo, 1)

        add_button = QtWidgets.QPushButton("+ 新增配置", self)
        add_button.clicked.connect(self._on_add_config_clicked)
        selector_layout.addWidget(add_button)

        remove_button = QtWidgets.QPushButton("删除当前配置", self)
        remove_button.clicked.connect(self._on_remove_config_clicked)
        selector_layout.addWidget(remove_button)

        layout.addLayout(selector_layout)

        # 基础设置分组
        basic_group = QtWidgets.QGroupBox("基础设置", self)
        basic_form = QtWidgets.QFormLayout(basic_group)
        basic_form.setContentsMargins(0, 6, 0, 6)
        basic_form.setSpacing(4)

        self._config_id_edit = QtWidgets.QLineEdit(basic_group)
        self._config_id_edit.setReadOnly(True)
        self._config_id_edit.setPlaceholderText("自动生成，例如 铭牌配置ID1")
        basic_form.addRow("配置ID:", self._config_id_edit)

        self._display_name_edit = QtWidgets.QLineEdit(basic_group)
        self._display_name_edit.setPlaceholderText("用于区分用途的名称，例如“路牌名称”")
        self._display_name_edit.textChanged.connect(self._on_display_name_changed)
        basic_form.addRow("显示名称:", self._display_name_edit)

        self._attach_point_edit = QtWidgets.QLineEdit(basic_group)
        self._attach_point_edit.setPlaceholderText("例如 GI_RootNode")
        self._attach_point_edit.textChanged.connect(self._on_attach_point_changed)
        basic_form.addRow("选择挂点:", self._attach_point_edit)

        self._visible_radius_spin_box = QtWidgets.QDoubleSpinBox(basic_group)
        self._visible_radius_spin_box.setDecimals(2)
        self._visible_radius_spin_box.setRange(0.0, 1000.0)
        self._visible_radius_spin_box.setSingleStep(1.0)
        self._visible_radius_spin_box.valueChanged.connect(self._on_visible_radius_changed)
        basic_form.addRow("可见半径(m):", self._visible_radius_spin_box)

        self._local_filter_combo = QtWidgets.QComboBox(basic_group)
        self._local_filter_combo.addItem("无", "")
        self._local_filter_combo.addItem("布尔过滤器", "布尔过滤器")
        self._local_filter_combo.currentIndexChanged.connect(self._on_local_filter_changed)
        basic_form.addRow("本地过滤器:", self._local_filter_combo)

        filter_graph_row = QtWidgets.QWidget(basic_group)
        filter_graph_layout = QtWidgets.QHBoxLayout(filter_graph_row)
        filter_graph_layout.setContentsMargins(0, 0, 0, 0)
        filter_graph_layout.setSpacing(4)

        self._filter_graph_edit = QtWidgets.QLineEdit(filter_graph_row)
        self._filter_graph_edit.setPlaceholderText("点击右侧按钮选择节点图，或手动输入ID")
        self._filter_graph_edit.textChanged.connect(self._on_filter_graph_changed)
        filter_graph_layout.addWidget(self._filter_graph_edit, 1)

        filter_graph_button = QtWidgets.QPushButton("点击选择", filter_graph_row)
        filter_graph_button.clicked.connect(self._on_select_filter_graph_clicked)
        filter_graph_layout.addWidget(filter_graph_button)

        basic_form.addRow("过滤器节点图:", filter_graph_row)

        self._initial_active_switch = ToggleSwitch(basic_group)
        self._initial_active_switch.stateChanged.connect(self._on_initial_active_changed)
        basic_form.addRow("初始生效:", self._initial_active_switch)

        layout.addWidget(basic_group)

        # 铭牌内容分组（当前实现为“单条文本框内容”）
        content_group = QtWidgets.QGroupBox("铭牌内容", self)
        content_form = QtWidgets.QFormLayout(content_group)
        content_form.setContentsMargins(0, 6, 0, 6)
        content_form.setSpacing(4)

        self._content_type_combo = QtWidgets.QComboBox(content_group)
        self._content_type_combo.addItem("文本框")
        self._content_type_combo.currentIndexChanged.connect(self._on_content_type_changed)
        content_form.addRow("选择类型:", self._content_type_combo)

        offset_row = QtWidgets.QWidget(content_group)
        offset_layout = QtWidgets.QHBoxLayout(offset_row)
        offset_layout.setContentsMargins(0, 0, 0, 0)
        offset_layout.setSpacing(4)
        offset_label_x = QtWidgets.QLabel("X:", offset_row)
        self._offset_x_spin_box = QtWidgets.QDoubleSpinBox(offset_row)
        self._offset_x_spin_box.setDecimals(2)
        self._offset_x_spin_box.setRange(-10000.0, 10000.0)
        self._offset_x_spin_box.valueChanged.connect(self._on_offset_changed)
        offset_label_y = QtWidgets.QLabel("Y:", offset_row)
        self._offset_y_spin_box = QtWidgets.QDoubleSpinBox(offset_row)
        self._offset_y_spin_box.setDecimals(2)
        self._offset_y_spin_box.setRange(-10000.0, 10000.0)
        self._offset_y_spin_box.valueChanged.connect(self._on_offset_changed)
        offset_layout.addWidget(offset_label_x)
        offset_layout.addWidget(self._offset_x_spin_box)
        offset_layout.addWidget(offset_label_y)
        offset_layout.addWidget(self._offset_y_spin_box)
        content_form.addRow("偏移:", offset_row)

        size_row = QtWidgets.QWidget(content_group)
        size_layout = QtWidgets.QHBoxLayout(size_row)
        size_layout.setContentsMargins(0, 0, 0, 0)
        size_layout.setSpacing(4)
        size_label_width = QtWidgets.QLabel("W:", size_row)
        self._size_width_spin_box = QtWidgets.QDoubleSpinBox(size_row)
        self._size_width_spin_box.setDecimals(2)
        self._size_width_spin_box.setRange(0.0, 10000.0)
        self._size_width_spin_box.valueChanged.connect(self._on_size_changed)
        size_label_height = QtWidgets.QLabel("H:", size_row)
        self._size_height_spin_box = QtWidgets.QDoubleSpinBox(size_row)
        self._size_height_spin_box.setDecimals(2)
        self._size_height_spin_box.setRange(0.0, 10000.0)
        self._size_height_spin_box.valueChanged.connect(self._on_size_changed)
        size_layout.addWidget(size_label_width)
        size_layout.addWidget(self._size_width_spin_box)
        size_layout.addWidget(size_label_height)
        size_layout.addWidget(self._size_height_spin_box)
        content_form.addRow("大小:", size_row)

        self._background_color_edit = QtWidgets.QLineEdit(content_group)
        self._background_color_edit.setPlaceholderText("背景颜色，例如 #RRGGBBAA，留空表示“无”")
        self._background_color_edit.textChanged.connect(self._on_background_color_changed)
        content_form.addRow("背景颜色:", self._background_color_edit)

        self._font_size_spin_box = QtWidgets.QSpinBox(content_group)
        self._font_size_spin_box.setRange(6, 200)
        self._font_size_spin_box.valueChanged.connect(self._on_font_size_changed)
        content_form.addRow("字号:", self._font_size_spin_box)

        self._text_align_combo = QtWidgets.QComboBox(content_group)
        self._text_align_combo.addItems(["左对齐", "居中", "右对齐"])
        self._text_align_combo.currentIndexChanged.connect(self._on_text_align_changed)
        content_form.addRow("对齐:", self._text_align_combo)

        self._text_content_edit = QtWidgets.QPlainTextEdit(content_group)
        self._text_content_edit.setPlaceholderText("文本内容，可插入变量占位符，例如 {1:s.当前路标名字}")
        self._text_content_edit.setMaximumHeight(120)
        self._text_content_edit.textChanged.connect(self._on_text_content_changed)
        content_form.addRow("文本内容:", self._text_content_edit)

        insert_variable_button = QtWidgets.QPushButton("插入变量...", content_group)
        insert_variable_button.setFixedWidth(100)
        insert_variable_button.clicked.connect(self._on_insert_variable_clicked)
        content_form.addRow("", insert_variable_button)

        layout.addWidget(content_group)
        layout.addStretch(1)

    # ------------------------------------------------------------------ 配置列表管理

    def _rebuild_config_list(self) -> None:
        if not self._nameplate_dicts:
            self._nameplate_dicts.append(self._create_default_config(len(self._nameplate_dicts)))

        self._renumber_configs()
        self._refresh_config_combo_and_widgets()

    def _create_default_config(self, existing_count: int) -> Dict[str, Any]:
        config_index = existing_count + 1
        config_id = f"铭牌配置ID{config_index}"
        content_dict = self._create_default_content()
        return {
            "配置序号": config_index,
            "配置ID": config_id,
            "名称": f"铭牌配置{config_index}",
            "选择挂点": "GI_RootNode",
            "可见半径": 5.0,
            "本地过滤器": "",
            "过滤器节点图": "",
            "初始生效": True,
            "铭牌内容": [content_dict],
        }

    def _create_default_content(self) -> Dict[str, Any]:
        return {
            "内容序号": 1,
            "选择类型": "文本框",
            "偏移": [0.0, 0.0],
            "大小": [100.0, 30.0],
            "背景颜色": "",
            "字号": 18,
            "对齐": "居中",
            "文本内容": "",
        }

    def _renumber_configs(self) -> None:
        for index, config_dict in enumerate(self._nameplate_dicts, start=1):
            if not isinstance(config_dict, dict):
                continue
            config_dict["配置序号"] = index
            config_id_raw = config_dict.get("配置ID")
            if not isinstance(config_id_raw, str) or not config_id_raw.strip():
                config_dict["配置ID"] = f"铭牌配置ID{index}"
            name_raw = config_dict.get("名称")
            if not isinstance(name_raw, str) or not name_raw.strip():
                config_dict["名称"] = f"铭牌配置{index}"
        self._sync_initial_active_ids()

    def _refresh_config_combo_and_widgets(self) -> None:
        if not self._nameplate_dicts:
            self._current_config_index = -1
            self._config_combo.blockSignals(True)
            self._config_combo.clear()
            self._config_combo.blockSignals(False)
            self._clear_form_fields()
            return

        if self._current_config_index < 0 or self._current_config_index >= len(self._nameplate_dicts):
            self._current_config_index = 0

        self._config_combo.blockSignals(True)
        self._config_combo.clear()
        for config_dict in self._nameplate_dicts:
            if not isinstance(config_dict, dict):
                self._config_combo.addItem("未命名配置")
                continue
            display_name_value = str(config_dict.get("名称") or config_dict.get("配置ID") or "未命名配置")
            self._config_combo.addItem(display_name_value)
        self._config_combo.setCurrentIndex(self._current_config_index)
        self._config_combo.blockSignals(False)

        self._load_config_into_form(self._current_config_index)

    def _clear_form_fields(self) -> None:
        self._set_line_edit_text(self._config_id_edit, "")
        self._set_line_edit_text(self._display_name_edit, "")
        self._set_line_edit_text(self._attach_point_edit, "")
        self._set_double_spin_value(self._visible_radius_spin_box, 0.0)
        self._set_combo_by_value(self._local_filter_combo, "")
        self._set_line_edit_text(self._filter_graph_edit, "")
        self._initial_active_switch.setChecked(False)

        self._content_type_combo.setCurrentIndex(0)
        self._set_double_spin_value(self._offset_x_spin_box, 0.0)
        self._set_double_spin_value(self._offset_y_spin_box, 0.0)
        self._set_double_spin_value(self._size_width_spin_box, 0.0)
        self._set_double_spin_value(self._size_height_spin_box, 0.0)
        self._set_line_edit_text(self._background_color_edit, "")
        self._set_spin_value(self._font_size_spin_box, 18)
        self._text_align_combo.setCurrentIndex(1)
        self._set_plain_text(self._text_content_edit, "")

    # ------------------------------------------------------------------ 工具：控件赋值

    def _set_line_edit_text(self, editor: QtWidgets.QLineEdit, text: str) -> None:
        previous_block_state = editor.blockSignals(True)
        editor.setText(text)
        editor.blockSignals(previous_block_state)

    def _set_plain_text(self, editor: QtWidgets.QPlainTextEdit, text: str) -> None:
        previous_block_state = editor.blockSignals(True)
        editor.setPlainText(text)
        editor.blockSignals(previous_block_state)

    def _set_double_spin_value(self, spin_box: QtWidgets.QDoubleSpinBox, value: float) -> None:
        previous_block_state = spin_box.blockSignals(True)
        spin_box.setValue(value)
        spin_box.blockSignals(previous_block_state)

    def _set_spin_value(self, spin_box: QtWidgets.QSpinBox, value: int) -> None:
        previous_block_state = spin_box.blockSignals(True)
        spin_box.setValue(value)
        spin_box.blockSignals(previous_block_state)

    def _set_combo_by_value(self, combo_box: QtWidgets.QComboBox, target_value: str) -> None:
        previous_block_state = combo_box.blockSignals(True)
        target_index = 0
        for index in range(combo_box.count()):
            data_value = combo_box.itemData(index)
            if isinstance(data_value, str) and data_value == target_value:
                target_index = index
                break
        combo_box.setCurrentIndex(target_index)
        combo_box.blockSignals(previous_block_state)

    # ------------------------------------------------------------------ 从配置填充到表单

    def _get_current_config_dict(self) -> Optional[Dict[str, Any]]:
        if self._current_config_index < 0:
            return None
        if self._current_config_index >= len(self._nameplate_dicts):
            return None
        raw_dict = self._nameplate_dicts[self._current_config_index]
        if not isinstance(raw_dict, dict):
            empty_dict: Dict[str, Any] = {}
            self._nameplate_dicts[self._current_config_index] = empty_dict
            return empty_dict
        return raw_dict

    def _get_current_content_dict(self, config_dict: Dict[str, Any]) -> Dict[str, Any]:
        raw_contents = config_dict.get("铭牌内容")
        if isinstance(raw_contents, list) and raw_contents:
            first_item = raw_contents[0]
            if isinstance(first_item, dict):
                return first_item
        default_content = self._create_default_content()
        config_dict["铭牌内容"] = [default_content]
        return default_content

    def _load_config_into_form(self, index: int) -> None:
        self._current_config_index = index

        config_dict = self._get_current_config_dict()
        if config_dict is None:
            self._clear_form_fields()
            return

        self._ensure_config_defaults(config_dict, index)
        content_dict = self._get_current_content_dict(config_dict)
        self._ensure_content_defaults(content_dict)

        config_id_value = str(config_dict.get("配置ID"))
        self._set_line_edit_text(self._config_id_edit, config_id_value)

        display_name_value = str(config_dict.get("名称"))
        self._set_line_edit_text(self._display_name_edit, display_name_value)

        attach_point_value = str(config_dict.get("选择挂点"))
        self._set_line_edit_text(self._attach_point_edit, attach_point_value)

        visible_radius_value_raw = config_dict.get("可见半径", 5.0)
        visible_radius_value = float(visible_radius_value_raw) if isinstance(visible_radius_value_raw, (int, float)) else 5.0
        self._set_double_spin_value(self._visible_radius_spin_box, visible_radius_value)

        local_filter_value_raw = config_dict.get("本地过滤器", "")
        local_filter_value = str(local_filter_value_raw) if isinstance(local_filter_value_raw, str) else ""
        self._set_combo_by_value(self._local_filter_combo, local_filter_value)

        filter_graph_id_raw = config_dict.get("过滤器节点图", "")
        filter_graph_id_value = str(filter_graph_id_raw) if isinstance(filter_graph_id_raw, str) else ""
        self._set_line_edit_text(self._filter_graph_edit, filter_graph_id_value)

        initially_active_value = config_dict.get("初始生效", True) is True
        self._initial_active_switch.setChecked(initially_active_value)

        # 内容字段
        select_type_value_raw = content_dict.get("选择类型", "文本框")
        select_type_value = str(select_type_value_raw) if isinstance(select_type_value_raw, str) else "文本框"
        previous_block_state = self._content_type_combo.blockSignals(True)
        if select_type_value == "文本框":
            self._content_type_combo.setCurrentIndex(0)
        else:
            self._content_type_combo.setCurrentIndex(0)
        self._content_type_combo.blockSignals(previous_block_state)

        offset_raw = content_dict.get("偏移", [0.0, 0.0])
        if isinstance(offset_raw, list) and len(offset_raw) >= 2:
            offset_x_raw = offset_raw[0]
            offset_y_raw = offset_raw[1]
        else:
            offset_x_raw = 0.0
            offset_y_raw = 0.0
        offset_x_value = float(offset_x_raw) if isinstance(offset_x_raw, (int, float)) else 0.0
        offset_y_value = float(offset_y_raw) if isinstance(offset_y_raw, (int, float)) else 0.0
        self._set_double_spin_value(self._offset_x_spin_box, offset_x_value)
        self._set_double_spin_value(self._offset_y_spin_box, offset_y_value)

        size_raw = content_dict.get("大小", [100.0, 30.0])
        if isinstance(size_raw, list) and len(size_raw) >= 2:
            size_width_raw = size_raw[0]
            size_height_raw = size_raw[1]
        else:
            size_width_raw = 100.0
            size_height_raw = 30.0
        size_width_value = float(size_width_raw) if isinstance(size_width_raw, (int, float)) else 100.0
        size_height_value = float(size_height_raw) if isinstance(size_height_raw, (int, float)) else 30.0
        self._set_double_spin_value(self._size_width_spin_box, size_width_value)
        self._set_double_spin_value(self._size_height_spin_box, size_height_value)

        background_color_value_raw = content_dict.get("背景颜色", "")
        background_color_value = str(background_color_value_raw) if isinstance(background_color_value_raw, str) else ""
        self._set_line_edit_text(self._background_color_edit, background_color_value)

        font_size_value_raw = content_dict.get("字号", 18)
        font_size_value = int(font_size_value_raw) if isinstance(font_size_value_raw, int) else 18
        self._set_spin_value(self._font_size_spin_box, font_size_value)

        text_align_value_raw = content_dict.get("对齐", "居中")
        text_align_value = str(text_align_value_raw) if isinstance(text_align_value_raw, str) else "居中"
        align_index = 1
        if text_align_value == "左对齐":
            align_index = 0
        elif text_align_value == "居中":
            align_index = 1
        elif text_align_value == "右对齐":
            align_index = 2
        previous_block_state_align = self._text_align_combo.blockSignals(True)
        self._text_align_combo.setCurrentIndex(align_index)
        self._text_align_combo.blockSignals(previous_block_state_align)

        text_content_value_raw = content_dict.get("文本内容", "")
        text_content_value = str(text_content_value_raw) if isinstance(text_content_value_raw, str) else ""
        self._set_plain_text(self._text_content_edit, text_content_value)

    def _ensure_config_defaults(self, config_dict: Dict[str, Any], index: int) -> None:
        if "配置序号" not in config_dict:
            config_dict["配置序号"] = index + 1
        config_id_raw = config_dict.get("配置ID")
        if not isinstance(config_id_raw, str) or not config_id_raw.strip():
            config_dict["配置ID"] = f"铭牌配置ID{index + 1}"
        if "名称" not in config_dict or not isinstance(config_dict["名称"], str):
            config_dict["名称"] = f"铭牌配置{index + 1}"
        if "选择挂点" not in config_dict or not isinstance(config_dict["选择挂点"], str):
            config_dict["选择挂点"] = "GI_RootNode"
        if "可见半径" not in config_dict:
            config_dict["可见半径"] = 5.0
        if "本地过滤器" not in config_dict or not isinstance(config_dict["本地过滤器"], str):
            config_dict["本地过滤器"] = ""
        if "过滤器节点图" not in config_dict or not isinstance(config_dict["过滤器节点图"], str):
            config_dict["过滤器节点图"] = ""
        if "初始生效" not in config_dict:
            config_dict["初始生效"] = True

    def _ensure_content_defaults(self, content_dict: Dict[str, Any]) -> None:
        if "内容序号" not in content_dict:
            content_dict["内容序号"] = 1
        if "选择类型" not in content_dict or not isinstance(content_dict["选择类型"], str):
            content_dict["选择类型"] = "文本框"
        offset_raw = content_dict.get("偏移")
        if not isinstance(offset_raw, list) or len(offset_raw) < 2:
            content_dict["偏移"] = [0.0, 0.0]
        size_raw = content_dict.get("大小")
        if not isinstance(size_raw, list) or len(size_raw) < 2:
            content_dict["大小"] = [100.0, 30.0]
        if "背景颜色" not in content_dict or not isinstance(content_dict["背景颜色"], str):
            content_dict["背景颜色"] = ""
        if "字号" not in content_dict:
            content_dict["字号"] = 18
        if "对齐" not in content_dict or not isinstance(content_dict["对齐"], str):
            content_dict["对齐"] = "居中"
        if "文本内容" not in content_dict or not isinstance(content_dict["文本内容"], str):
            content_dict["文本内容"] = ""

    def _sync_initial_active_ids(self) -> None:
        active_ids: List[str] = []
        for config_dict in self._nameplate_dicts:
            if not isinstance(config_dict, dict):
                continue
            is_active = config_dict.get("初始生效", True) is True
            config_id_raw = config_dict.get("配置ID")
            if is_active and isinstance(config_id_raw, str) and config_id_raw.strip():
                active_ids.append(config_id_raw.strip())
        self._settings["初始生效配置ID列表"] = active_ids

    # ------------------------------------------------------------------ 信号槽：配置列表

    def _on_config_combo_changed(self, index: int) -> None:
        if index < 0 or index >= len(self._nameplate_dicts):
            return
        self._load_config_into_form(index)

    def _on_add_config_clicked(self) -> None:
        new_config = self._create_default_config(len(self._nameplate_dicts))
        self._nameplate_dicts.append(new_config)
        self._current_config_index = len(self._nameplate_dicts) - 1
        self._renumber_configs()
        self._refresh_config_combo_and_widgets()

    def _on_remove_config_clicked(self) -> None:
        if not self._nameplate_dicts:
            return
        if len(self._nameplate_dicts) == 1:
            dialog_utils.show_warning_dialog(self, "无法删除", "至少需要保留一条铭牌配置。")
            return
        if self._current_config_index < 0 or self._current_config_index >= len(self._nameplate_dicts):
            return
        self._nameplate_dicts.pop(self._current_config_index)
        if self._current_config_index >= len(self._nameplate_dicts):
            self._current_config_index = len(self._nameplate_dicts) - 1
        self._renumber_configs()
        self._refresh_config_combo_and_widgets()

    # ------------------------------------------------------------------ 信号槽：基础设置

    def _on_display_name_changed(self, text: str) -> None:
        config_dict = self._get_current_config_dict()
        if config_dict is None:
            return
        config_dict["名称"] = text.strip()
        # 更新下拉显示名称
        self._refresh_config_combo_and_widgets()

    def _on_attach_point_changed(self, text: str) -> None:
        config_dict = self._get_current_config_dict()
        if config_dict is None:
            return
        config_dict["选择挂点"] = text.strip() or "GI_RootNode"

    def _on_visible_radius_changed(self, value: float) -> None:
        config_dict = self._get_current_config_dict()
        if config_dict is None:
            return
        config_dict["可见半径"] = float(value)

    def _on_local_filter_changed(self, index: int) -> None:
        del index
        config_dict = self._get_current_config_dict()
        if config_dict is None:
            return
        selected_value = self._local_filter_combo.currentData()
        if isinstance(selected_value, str):
            config_dict["本地过滤器"] = selected_value
        else:
            config_dict["本地过滤器"] = ""

    def _on_filter_graph_changed(self, text: str) -> None:
        config_dict = self._get_current_config_dict()
        if config_dict is None:
            return
        config_dict["过滤器节点图"] = text.strip()

    def _on_select_filter_graph_clicked(self) -> None:
        if not self._resource_manager or not self._package_index_manager:
            dialog_utils.show_warning_dialog(self, "未配置", "当前环境未提供节点图库资源管理器。")
            return
        dialog = GraphSelectionDialog(
            resource_manager=self._resource_manager,
            package_index_manager=self._package_index_manager,
            parent=self,
        )
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        graph_id = dialog.get_selected_graph_id()
        if not graph_id:
            return
        self._filter_graph_edit.setText(graph_id)
        self._on_filter_graph_changed(graph_id)

    def _on_initial_active_changed(self, state: int) -> None:
        del state
        config_dict = self._get_current_config_dict()
        if config_dict is None:
            return
        config_dict["初始生效"] = self._initial_active_switch.isChecked()
        self._sync_initial_active_ids()

    # ------------------------------------------------------------------ 信号槽：内容设置

    def _on_content_type_changed(self, index: int) -> None:
        del index
        config_dict = self._get_current_config_dict()
        if config_dict is None:
            return
        content_dict = self._get_current_content_dict(config_dict)
        content_dict["选择类型"] = "文本框"

    def _on_offset_changed(self, _: float) -> None:
        config_dict = self._get_current_config_dict()
        if config_dict is None:
            return
        content_dict = self._get_current_content_dict(config_dict)
        content_dict["偏移"] = [
            float(self._offset_x_spin_box.value()),
            float(self._offset_y_spin_box.value()),
        ]

    def _on_size_changed(self, _: float) -> None:
        config_dict = self._get_current_config_dict()
        if config_dict is None:
            return
        content_dict = self._get_current_content_dict(config_dict)
        content_dict["大小"] = [
            float(self._size_width_spin_box.value()),
            float(self._size_height_spin_box.value()),
        ]

    def _on_background_color_changed(self, text: str) -> None:
        config_dict = self._get_current_config_dict()
        if config_dict is None:
            return
        content_dict = self._get_current_content_dict(config_dict)
        content_dict["背景颜色"] = text.strip()

    def _on_font_size_changed(self, value: int) -> None:
        config_dict = self._get_current_config_dict()
        if config_dict is None:
            return
        content_dict = self._get_current_content_dict(config_dict)
        content_dict["字号"] = int(value)

    def _on_text_align_changed(self, index: int) -> None:
        config_dict = self._get_current_config_dict()
        if config_dict is None:
            return
        content_dict = self._get_current_content_dict(config_dict)
        if index == 0:
            content_dict["对齐"] = "左对齐"
        elif index == 1:
            content_dict["对齐"] = "居中"
        else:
            content_dict["对齐"] = "右对齐"

    def _on_text_content_changed(self) -> None:
        config_dict = self._get_current_config_dict()
        if config_dict is None:
            return
        content_dict = self._get_current_content_dict(config_dict)
        content_dict["文本内容"] = self._text_content_edit.toPlainText()

    def _on_insert_variable_clicked(self) -> None:
        variable_expression = dialog_utils.prompt_text(self, "插入变量", "变量占位符（例如 1:s.当前路标名字）:")
        if not variable_expression:
            return
        cursor = self._text_content_edit.textCursor()
        cursor.insertText(f"{{{variable_expression}}}")
        self._text_content_edit.setTextCursor(cursor)


class TabConfigForm(QtWidgets.QWidget):
    """“选项卡”组件配置表单。

    对应通用组件中的“选项卡”配置，可为同一个造物实体配置多个选项卡：
    - 每个选项卡有独立的序号、初始生效开关与排序等级；
    - 每个选项卡可以挂接一个本地过滤器节点图（客户端），用于判定“对谁显示/对谁不显示”。

    settings 结构与 `engine.configs.components.tab_configs.TabComponentConfig.to_dict()` 对齐：
    - settings["选项卡列表"] -> 若干 {选项序号, 选项卡图标, 初始生效, 排序等级, 本地过滤器, 过滤器节点图}
    - settings["初始生效选项卡"] -> 初始生效选项卡序号列表
    - settings["触发区域"]       -> 触发区域字典列表（当前表单仅保持原状，不提供编辑 UI）
    """

    def __init__(
        self,
        settings: Dict[str, object],
        parent: QtWidgets.QWidget,
        *,
        resource_manager: Optional[object] = None,
        package_index_manager: Optional[object] = None,
    ) -> None:
        super().__init__(parent)
        self._settings: Dict[str, object] = settings
        self._resource_manager = resource_manager
        self._package_index_manager = package_index_manager
        self._tab_dicts: List[Dict[str, Any]] = []
        self._cards_layout: Optional[QtWidgets.QVBoxLayout] = None

        self._init_base_structure()
        self._build_ui()
        self._rebuild_cards()

    # ------------------------------------------------------------------ 基础结构与加载

    def _init_base_structure(self) -> None:
        """确保 settings 中存在选项卡所需的基础字段。"""
        raw_list = self._settings.get("选项卡列表")
        if isinstance(raw_list, list):
            self._tab_dicts = [
                item if isinstance(item, dict) else {}
                for item in raw_list
            ]
        else:
            self._tab_dicts = []
        self._settings["选项卡列表"] = self._tab_dicts

        initial_active_tabs = self._settings.get("初始生效选项卡")
        if not isinstance(initial_active_tabs, list):
            self._settings["初始生效选项卡"] = []

        raw_trigger_areas = self._settings.get("触发区域")
        if isinstance(raw_trigger_areas, list):
            self._settings["触发区域"] = list(raw_trigger_areas)
        else:
            self._settings["触发区域"] = []

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(6)

        hint_label = QtWidgets.QLabel(
            "为当前造物配置多个选项卡，每个选项卡可以绑定一个本地过滤器节点图（客户端），"
            "用于按玩家条件决定“对谁显示/对谁不显示”。",
            self,
        )
        hint_label.setWordWrap(True)
        from ui.foundation.theme_manager import Colors
        hint_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        layout.addWidget(hint_label)

        toolbar_layout = QtWidgets.QHBoxLayout()
        add_button = QtWidgets.QPushButton("+ 添加选项卡", self)
        add_button.clicked.connect(self._on_add_tab_clicked)
        toolbar_layout.addWidget(add_button)
        toolbar_layout.addStretch(1)
        layout.addLayout(toolbar_layout)

        container = QtWidgets.QWidget(self)
        cards_layout = QtWidgets.QVBoxLayout(container)
        cards_layout.setContentsMargins(0, 4, 0, 0)
        cards_layout.setSpacing(6)
        layout.addWidget(container)

        self._cards_layout = cards_layout

    def _clear_cards(self) -> None:
        if self._cards_layout is None:
            return
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _rebuild_cards(self) -> None:
        if self._cards_layout is None:
            return

        self._clear_cards()

        if not self._tab_dicts:
            self._tab_dicts.append(self._create_default_tab(len(self._tab_dicts)))

        self._renumber_tabs()

        for index, tab_dict in enumerate(self._tab_dicts, start=1):
            card = self._create_card_widget(index, tab_dict)
            self._cards_layout.addWidget(card)

        self._cards_layout.addStretch(1)

    def _create_default_tab(self, existing_count: int) -> Dict[str, Any]:
        tab_index = existing_count + 1
        return {
            "选项序号": tab_index,
            "选项卡图标": "",
            "初始生效": tab_index == 1,
            "排序等级": 1,
            "本地过滤器": "",
            "过滤器节点图": "",
        }

    def _renumber_tabs(self) -> None:
        for index, tab_dict in enumerate(self._tab_dicts, start=1):
            if not isinstance(tab_dict, dict):
                continue
            tab_dict["选项序号"] = index
            if "排序等级" not in tab_dict:
                tab_dict["排序等级"] = 1
            if "选项卡图标" not in tab_dict or not isinstance(tab_dict["选项卡图标"], str):
                tab_dict["选项卡图标"] = ""
            if "本地过滤器" not in tab_dict or not isinstance(tab_dict["本地过滤器"], str):
                tab_dict["本地过滤器"] = ""
            if "过滤器节点图" not in tab_dict or not isinstance(tab_dict["过滤器节点图"], str):
                tab_dict["过滤器节点图"] = ""
            if "初始生效" not in tab_dict:
                tab_dict["初始生效"] = False

        self._sync_initial_active_indices()

    def _sync_initial_active_indices(self) -> None:
        active_indices: List[int] = []
        for tab_dict in self._tab_dicts:
            if not isinstance(tab_dict, dict):
                continue
            is_active = tab_dict.get("初始生效", False) is True
            index_raw = tab_dict.get("选项序号")
            if is_active and isinstance(index_raw, int):
                active_indices.append(index_raw)
        self._settings["初始生效选项卡"] = active_indices

    # ------------------------------------------------------------------ 卡片与字段绑定

    def _create_card_widget(self, index: int, tab_dict: Dict[str, Any]) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox(f"选项卡 序号: {index}", self)

        main_layout = QtWidgets.QVBoxLayout(group)
        main_layout.setContentsMargins(8, 6, 8, 8)
        main_layout.setSpacing(4)

        header_layout = QtWidgets.QHBoxLayout()
        title_label = QtWidgets.QLabel("选项卡", group)
        header_layout.addWidget(title_label)
        header_layout.addStretch(1)

        remove_button = QtWidgets.QPushButton("删除此选项卡", group)
        remove_button.clicked.connect(lambda: self._on_remove_tab_clicked(tab_dict))
        header_layout.addWidget(remove_button)

        main_layout.addLayout(header_layout)

        form_layout = QtWidgets.QFormLayout()
        form_layout.setContentsMargins(0, 4, 0, 0)
        form_layout.setSpacing(4)

        index_label = QtWidgets.QLabel(str(index), group)
        form_layout.addRow("选项序号:", index_label)

        icon_edit = QtWidgets.QLineEdit(group)
        icon_value_raw = tab_dict.get("选项卡图标", "")
        icon_edit.setText(str(icon_value_raw) if isinstance(icon_value_raw, str) else "")
        icon_edit.setPlaceholderText("可选：图标资源 ID 或名称")
        icon_edit.textChanged.connect(lambda text: self._on_icon_changed(tab_dict, text))
        form_layout.addRow("选项卡图标:", icon_edit)

        sort_spin = QtWidgets.QSpinBox(group)
        sort_spin.setRange(-9999, 9999)
        sort_value_raw = tab_dict.get("排序等级", 1)
        sort_value = int(sort_value_raw) if isinstance(sort_value_raw, int) else 1
        sort_spin.setValue(sort_value)
        sort_spin.valueChanged.connect(lambda value: self._on_sort_level_changed(tab_dict, value))
        form_layout.addRow("排序等级:", sort_spin)

        initial_switch = ToggleSwitch(group)
        initial_switch.setChecked(tab_dict.get("初始生效", False) is True)
        initial_switch.stateChanged.connect(
            lambda _state: self._on_initial_active_changed(tab_dict, initial_switch)
        )
        form_layout.addRow("初始生效:", initial_switch)

        local_filter_combo = QtWidgets.QComboBox(group)
        local_filter_combo.addItem("无", "")
        local_filter_combo.addItem("布尔过滤器", "布尔过滤器")
        local_filter_value_raw = tab_dict.get("本地过滤器", "")
        local_filter_value = (
            str(local_filter_value_raw) if isinstance(local_filter_value_raw, str) else ""
        )
        target_index = 0
        for combo_index in range(local_filter_combo.count()):
            data_value = local_filter_combo.itemData(combo_index)
            if isinstance(data_value, str) and data_value == local_filter_value:
                target_index = combo_index
                break
        local_filter_combo.setCurrentIndex(target_index)
        local_filter_combo.currentIndexChanged.connect(
            lambda _index: self._on_local_filter_changed(tab_dict, local_filter_combo)
        )
        form_layout.addRow("本地过滤器:", local_filter_combo)

        filter_graph_row = QtWidgets.QWidget(group)
        filter_graph_layout = QtWidgets.QHBoxLayout(filter_graph_row)
        filter_graph_layout.setContentsMargins(0, 0, 0, 0)
        filter_graph_layout.setSpacing(4)

        filter_graph_edit = QtWidgets.QLineEdit(filter_graph_row)
        filter_graph_edit.setPlaceholderText("点击右侧按钮选择节点图，或手动输入ID")
        filter_graph_value_raw = tab_dict.get("过滤器节点图", "")
        filter_graph_value = (
            str(filter_graph_value_raw) if isinstance(filter_graph_value_raw, str) else ""
        )
        filter_graph_edit.setText(filter_graph_value)
        filter_graph_edit.textChanged.connect(
            lambda text: self._on_filter_graph_changed(tab_dict, text)
        )
        filter_graph_layout.addWidget(filter_graph_edit, 1)

        filter_graph_button = QtWidgets.QPushButton("点击选择", filter_graph_row)
        filter_graph_button.clicked.connect(
            lambda: self._on_select_filter_graph_clicked(tab_dict, filter_graph_edit)
        )
        filter_graph_layout.addWidget(filter_graph_button)

        form_layout.addRow("过滤器节点图:", filter_graph_row)

        main_layout.addLayout(form_layout)

        return group

    # ------------------------------------------------------------------ 事件处理

    def _on_add_tab_clicked(self) -> None:
        new_tab = self._create_default_tab(len(self._tab_dicts))
        self._tab_dicts.append(new_tab)
        self._renumber_tabs()
        self._rebuild_cards()

    def _on_remove_tab_clicked(self, tab_dict: Dict[str, Any]) -> None:
        if not self._tab_dicts:
            return
        if len(self._tab_dicts) == 1:
            dialog_utils.show_warning_dialog(self, "无法删除", "至少需要保留一个选项卡。")
            return
        if tab_dict not in self._tab_dicts:
            return
        self._tab_dicts.remove(tab_dict)
        self._renumber_tabs()
        self._rebuild_cards()

    def _on_icon_changed(self, tab_dict: Dict[str, Any], text: str) -> None:
        tab_dict["选项卡图标"] = text.strip()

    def _on_sort_level_changed(self, tab_dict: Dict[str, Any], value: int) -> None:
        tab_dict["排序等级"] = int(value)

    def _on_initial_active_changed(
        self,
        tab_dict: Dict[str, Any],
        switch: ToggleSwitch,
    ) -> None:
        tab_dict["初始生效"] = switch.isChecked()
        self._sync_initial_active_indices()

    def _on_local_filter_changed(
        self,
        tab_dict: Dict[str, Any],
        combo_box: QtWidgets.QComboBox,
    ) -> None:
        selected_value = combo_box.currentData()
        if isinstance(selected_value, str):
            tab_dict["本地过滤器"] = selected_value
        else:
            tab_dict["本地过滤器"] = ""

    def _on_filter_graph_changed(self, tab_dict: Dict[str, Any], text: str) -> None:
        tab_dict["过滤器节点图"] = text.strip()

    def _on_select_filter_graph_clicked(
        self,
        tab_dict: Dict[str, Any],
        line_edit: QtWidgets.QLineEdit,
    ) -> None:
        if not self._resource_manager or not self._package_index_manager:
            dialog_utils.show_warning_dialog(self, "未配置", "当前环境未提供节点图库资源管理器。")
            return
        dialog = GraphSelectionDialog(
            resource_manager=self._resource_manager,
            package_index_manager=self._package_index_manager,
            parent=self,
            allowed_graph_type="client",
            allowed_folder_prefix="本地过滤器节点图",
        )
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        graph_id = dialog.get_selected_graph_id()
        if not graph_id:
            return
        line_edit.setText(graph_id)
        self._on_filter_graph_changed(tab_dict, graph_id)


def _create_backpack_form(settings: Dict[str, object], parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    """为“背包”组件创建简单表单，只暴露背包容量字段。

    说明：
    - 使用 settings["背包容量"] 作为单一配置项，默认值为 20。
    - 该设置与引擎侧 BackpackComponentConfig.to_dict() 的字段名称保持一致。
    """
    container = QtWidgets.QWidget(parent)
    layout = QtWidgets.QFormLayout(container)
    layout.setContentsMargins(0, 4, 0, 0)
    layout.setSpacing(4)

    capacity_spin = QtWidgets.QSpinBox(container)
    capacity_spin.setRange(0, 9999)
    capacity_value_raw = settings.get("背包容量", 20)
    if isinstance(capacity_value_raw, int):
        capacity_value = capacity_value_raw
    else:
        capacity_value = 20
    capacity_spin.setValue(capacity_value)

    def on_capacity_changed(value: int) -> None:
        settings["背包容量"] = int(value)

    capacity_spin.valueChanged.connect(on_capacity_changed)
    layout.addRow("背包容量:", capacity_spin)
    return container


def create_component_form(
    component_type: str,
    settings: Dict[str, object],
    parent: QtWidgets.QWidget,
    *,
    resource_manager: Optional[object] = None,
    package_index_manager: Optional[object] = None,
) -> QtWidgets.QWidget | None:
    """根据组件类型创建通用组件的配置表单。

    当前仅对少量组件提供简单表单：
    - 背包：背包容量
    - 铭牌：铭牌配置列表（支持多个配置ID与“初始生效”开关）
    - 选项卡：多选项卡配置（序号、排序等级、本地过滤器与本地过滤器节点图 ID）

    其余组件返回 None，由调用方决定展示只读占位说明。
    """
    if component_type == "背包":
        return _create_backpack_form(settings, parent)
    if component_type == "铭牌":
        return NameplateConfigForm(
            settings,
            parent,
            resource_manager=resource_manager,
            package_index_manager=package_index_manager,
        )
    if component_type == "选项卡":
        return TabConfigForm(
            settings,
            parent,
            resource_manager=resource_manager,
            package_index_manager=package_index_manager,
        )
    return None


__all__ = ["create_component_form"]


