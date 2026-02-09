"""“铭牌”通用组件表单。"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from PyQt6 import QtWidgets

from app.ui.dialogs.graph_selection_dialog import GraphSelectionDialog
from app.ui.foundation import dialog_utils, prompt_text
from app.ui.forms.schema_bound_form import FormComboOption, FormFieldSpec, SchemaBoundForm


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
        on_settings_changed: Optional[Callable[[], None]] = None,
        resource_manager: Optional[object] = None,
        package_index_manager: Optional[object] = None,
    ) -> None:
        super().__init__(parent)
        self._settings: Dict[str, object] = settings
        self._on_settings_changed = on_settings_changed
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

        def _get_current_config() -> Optional[Dict[str, Any]]:
            return self._get_current_config_dict()

        def _set_current_config_value(key: str, value: Any) -> None:
            config_dict = _get_current_config()
            if config_dict is None:
                return
            config_dict[key] = value
            if self._on_settings_changed is not None:
                self._on_settings_changed()

        def _update_current_combo_item_text() -> None:
            if self._current_config_index < 0:
                return
            if self._current_config_index >= self._config_combo.count():
                return
            config_dict = _get_current_config()
            if config_dict is None:
                return
            display_text = str(config_dict.get("名称") or config_dict.get("配置ID") or "未命名配置")
            previous_block_state = self._config_combo.blockSignals(True)
            self._config_combo.setItemText(self._current_config_index, display_text)
            self._config_combo.blockSignals(previous_block_state)

        self._nameplate_basic_schema_form = SchemaBoundForm(
            basic_group,
            [
                FormFieldSpec(
                    key="配置ID",
                    label="配置ID:",
                    kind="line_edit",
                    default="",
                    placeholder="自动生成，例如 铭牌配置ID1",
                    read_only=True,
                    get_value=lambda _model: str((self._get_current_config_dict() or {}).get("配置ID", "")),
                    set_value=lambda _model, _value: None,
                ),
                FormFieldSpec(
                    key="名称",
                    label="显示名称:",
                    kind="line_edit",
                    default="",
                    placeholder="用于区分用途的名称，例如“路牌名称”",
                    get_value=lambda _model: str((self._get_current_config_dict() or {}).get("名称", "")),
                    set_value=lambda _model, value: (
                        _set_current_config_value("名称", str(value).strip()),
                        _update_current_combo_item_text(),
                    ),
                ),
                FormFieldSpec(
                    key="选择挂点",
                    label="选择挂点:",
                    kind="line_edit",
                    default="GI_RootNode",
                    placeholder="例如 GI_RootNode",
                    get_value=lambda _model: str((self._get_current_config_dict() or {}).get("选择挂点", "GI_RootNode")),
                    set_value=lambda _model, value: _set_current_config_value(
                        "选择挂点",
                        str(value).strip() or "GI_RootNode",
                    ),
                ),
                FormFieldSpec(
                    key="可见半径",
                    label="可见半径(m):",
                    kind="double_spin",
                    default=5.0,
                    minimum_float=0.0,
                    maximum_float=1000.0,
                    single_step_float=1.0,
                    get_value=lambda _model: float((self._get_current_config_dict() or {}).get("可见半径", 5.0)),
                    set_value=lambda _model, value: _set_current_config_value("可见半径", float(value)),
                ),
                FormFieldSpec(
                    key="本地过滤器",
                    label="本地过滤器:",
                    kind="combo",
                    default="",
                    combo_options=[
                        FormComboOption("无", ""),
                        FormComboOption("布尔过滤器", "布尔过滤器"),
                    ],
                    get_value=lambda _model: str((self._get_current_config_dict() or {}).get("本地过滤器", "")),
                    set_value=lambda _model, value: _set_current_config_value("本地过滤器", str(value)),
                ),
            ],
            self._settings,  # 占位模型：实际读写通过 get_value/set_value 回调完成
        )
        self._nameplate_basic_schema_form.build_into(basic_form)
        self._config_id_edit = self._nameplate_basic_schema_form.widgets["配置ID"]  # type: ignore[assignment]
        self._display_name_edit = self._nameplate_basic_schema_form.widgets["名称"]  # type: ignore[assignment]
        self._attach_point_edit = self._nameplate_basic_schema_form.widgets["选择挂点"]  # type: ignore[assignment]
        self._visible_radius_spin_box = self._nameplate_basic_schema_form.widgets["可见半径"]  # type: ignore[assignment]
        self._local_filter_combo = self._nameplate_basic_schema_form.widgets["本地过滤器"]  # type: ignore[assignment]

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

        self._initial_active_schema_form = SchemaBoundForm(
            basic_group,
            [
                FormFieldSpec(
                    key="初始生效",
                    label="初始生效:",
                    kind="bool",
                    default=True,
                    use_toggle_switch=True,
                    get_value=lambda _model: (self._get_current_config_dict() or {}).get("初始生效", True) is True,
                    set_value=lambda _model, value: (
                        _set_current_config_value("初始生效", value is True),
                        self._sync_initial_active_ids(),
                    ),
                )
            ],
            self._settings,
        )
        self._initial_active_schema_form.build_into(basic_form)
        self._initial_active_switch = self._initial_active_schema_form.widgets["初始生效"]  # type: ignore[assignment]

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

        def _get_current_content() -> Dict[str, Any]:
            config_dict = self._get_current_config_dict()
            if config_dict is None:
                return {}
            return self._get_current_content_dict(config_dict)

        def _set_current_content_value(key: str, value: Any) -> None:
            config_dict = self._get_current_config_dict()
            if config_dict is None:
                return
            content_dict = self._get_current_content_dict(config_dict)
            content_dict[key] = value
            if self._on_settings_changed is not None:
                self._on_settings_changed()

        self._nameplate_content_schema_form = SchemaBoundForm(
            content_group,
            [
                FormFieldSpec(
                    key="背景颜色",
                    label="背景颜色:",
                    kind="line_edit",
                    default="",
                    placeholder="背景颜色，例如 #RRGGBBAA，留空表示“无”",
                    get_value=lambda _model: str(_get_current_content().get("背景颜色", "")),
                    set_value=lambda _model, value: _set_current_content_value("背景颜色", str(value).strip()),
                ),
                FormFieldSpec(
                    key="字号",
                    label="字号:",
                    kind="int_spin",
                    default=18,
                    minimum_int=6,
                    maximum_int=200,
                    get_value=lambda _model: int(_get_current_content().get("字号", 18)),
                    set_value=lambda _model, value: _set_current_content_value("字号", int(value)),
                ),
                FormFieldSpec(
                    key="对齐",
                    label="对齐:",
                    kind="combo",
                    default="居中",
                    combo_options=[
                        FormComboOption("左对齐", "左对齐"),
                        FormComboOption("居中", "居中"),
                        FormComboOption("右对齐", "右对齐"),
                    ],
                    get_value=lambda _model: str(_get_current_content().get("对齐", "居中")),
                    set_value=lambda _model, value: _set_current_content_value("对齐", str(value)),
                ),
                FormFieldSpec(
                    key="文本内容",
                    label="文本内容:",
                    kind="plain_text",
                    default="",
                    placeholder="文本内容，可插入变量占位符，例如 {1:s.当前路标名字}",
                    max_height=120,
                    get_value=lambda _model: str(_get_current_content().get("文本内容", "")),
                    set_value=lambda _model, value: _set_current_content_value("文本内容", str(value)),
                ),
            ],
            self._settings,
        )
        self._nameplate_content_schema_form.build_into(content_form)
        self._background_color_edit = self._nameplate_content_schema_form.widgets["背景颜色"]  # type: ignore[assignment]
        self._font_size_spin_box = self._nameplate_content_schema_form.widgets["字号"]  # type: ignore[assignment]
        self._text_align_combo = self._nameplate_content_schema_form.widgets["对齐"]  # type: ignore[assignment]
        self._text_content_edit = self._nameplate_content_schema_form.widgets["文本内容"]  # type: ignore[assignment]

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

        if hasattr(self, "_nameplate_basic_schema_form"):
            self._nameplate_basic_schema_form.load_from_model()
        filter_graph_id_raw = config_dict.get("过滤器节点图", "")
        filter_graph_id_value = (
            str(filter_graph_id_raw) if isinstance(filter_graph_id_raw, str) else ""
        )
        self._set_line_edit_text(self._filter_graph_edit, filter_graph_id_value)
        if hasattr(self, "_initial_active_schema_form"):
            self._initial_active_schema_form.load_from_model()

        # 内容字段
        select_type_value_raw = content_dict.get("选择类型", "文本框")
        select_type_value = (
            str(select_type_value_raw)
            if isinstance(select_type_value_raw, str)
            else "文本框"
        )
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

        if hasattr(self, "_nameplate_content_schema_form"):
            self._nameplate_content_schema_form.load_from_model()

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
        if self._on_settings_changed is not None:
            self._on_settings_changed()

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
        if self._on_settings_changed is not None:
            self._on_settings_changed()

    # ------------------------------------------------------------------ 信号槽：基础设置

    def _on_filter_graph_changed(self, text: str) -> None:
        config_dict = self._get_current_config_dict()
        if config_dict is None:
            return
        config_dict["过滤器节点图"] = text.strip()
        if self._on_settings_changed is not None:
            self._on_settings_changed()

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

    # ------------------------------------------------------------------ 信号槽：内容设置

    def _on_content_type_changed(self, index: int) -> None:
        del index
        config_dict = self._get_current_config_dict()
        if config_dict is None:
            return
        content_dict = self._get_current_content_dict(config_dict)
        content_dict["选择类型"] = "文本框"
        if self._on_settings_changed is not None:
            self._on_settings_changed()

    def _on_offset_changed(self, _: float) -> None:
        config_dict = self._get_current_config_dict()
        if config_dict is None:
            return
        content_dict = self._get_current_content_dict(config_dict)
        content_dict["偏移"] = [
            float(self._offset_x_spin_box.value()),
            float(self._offset_y_spin_box.value()),
        ]
        if self._on_settings_changed is not None:
            self._on_settings_changed()

    def _on_size_changed(self, _: float) -> None:
        config_dict = self._get_current_config_dict()
        if config_dict is None:
            return
        content_dict = self._get_current_content_dict(config_dict)
        content_dict["大小"] = [
            float(self._size_width_spin_box.value()),
            float(self._size_height_spin_box.value()),
        ]
        if self._on_settings_changed is not None:
            self._on_settings_changed()

    def _on_insert_variable_clicked(self) -> None:
        variable_expression = prompt_text(self, "插入变量", "变量占位符（例如 1:s.当前路标名字）:")
        if not variable_expression:
            return
        cursor = self._text_content_edit.textCursor()
        cursor.insertText(f"{{{variable_expression}}}")
        self._text_content_edit.setTextCursor(cursor)
        if self._on_settings_changed is not None:
            self._on_settings_changed()


__all__ = ["NameplateConfigForm"]


