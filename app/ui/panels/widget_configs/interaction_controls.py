from __future__ import annotations

from typing import cast

from PyQt6 import QtCore, QtWidgets

from .base import BaseWidgetConfigPanel, WidgetConfigForm


_ITEM_DISPLAY_KBM_CODE_CANDIDATES = [str(i) for i in range(1, 15)]
_ITEM_DISPLAY_GAMEPAD_CODE_CANDIDATES = [str(i) for i in range(1, 15)]

_ITEM_DISPLAY_KBM_CODE_TOOLTIP = "\n".join(
    [
        "键鼠按键码（奇匠按键）：",
        "1-10：数字 1-0（10 对应 0）",
        "11：U（奇匠按键11）",
        "12：Z（奇匠按键12）",
        "13：Y（奇匠按键13）",
        "14：G（奇匠按键14）",
        "",
        "注意：HTML 导入/写回默认要求键鼠/手柄按键码同号（1..14），因此不推荐使用 15（仅键鼠存在）。",
        "输入框内必须是纯数字码（例如 11），不要填字母本身。",
    ]
)

_ITEM_DISPLAY_GAMEPAD_CODE_TOOLTIP = "\n".join(
    [
        "手柄按键码（奇匠按键 1-14）：",
        "1：D-pad Up（十字键上）",
        "2：D-pad Down（十字键下）",
        "3：LT",
        "4：LB + Y",
        "5：LB + X",
        "6：LB + A",
        "7：LB + D-pad Up",
        "8：LB + D-pad Right",
        "9：LB + D-pad Down",
        "10：LB + D-pad Left",
        "11：LB + RB",
        "12：LB + LT",
        "13：LB + RT",
        "14：LB + LS（左摇杆按下）",
        "",
        "注意：输入框内必须是纯数字码（例如 4），不要填组合键文本。",
    ]
)


class InteractionButtonConfigPanel(BaseWidgetConfigPanel):
    """交互按钮配置面板"""

    def _setup_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        form = WidgetConfigForm(self)
        # 注意：WidgetConfigForm 在实例上覆写了 `layout` 属性（QFormLayout），与 QWidget.layout() 方法同名；
        # 这里用 cast 明确实际类型，避免类型检查误判为 MethodType。
        self._form_layout = cast(QtWidgets.QFormLayout, form.layout)
        layout.addWidget(form)

        self.key_mapping_fields = form.add_key_mapping_pair(
            "key_mapping",
            "gamepad_mapping",
            keyboard_placeholder="如: E, F, Space",
            gamepad_placeholder="如: A, B, X, Y",
        )

        self.button_size_combo = form.add_combo_box(
            "大小:",
            "button_size",
            ["大", "小"],
            default_text="小",
        )

        self.button_type_combo = form.add_combo_box(
            "类型:",
            "button_type",
            ["交互事件", "角色技能", "使用道具"],
            default_text="交互事件",
            default_index=0,
        )
        self.button_type_combo.currentTextChanged.connect(self._on_type_changed)

        self._skill_icon_row = QtWidgets.QWidget()
        icon_layout = QtWidgets.QHBoxLayout(self._skill_icon_row)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        self.icon_edit = QtWidgets.QLineEdit()
        self.icon_edit.setPlaceholderText("图标资源路径")
        icon_layout.addWidget(self.icon_edit)
        icon_browse_btn = QtWidgets.QPushButton("浏览...")
        icon_browse_btn.setFixedWidth(60)
        icon_browse_btn.clicked.connect(self._choose_icon)
        icon_layout.addWidget(icon_browse_btn)
        form.add_row_widget("技能图标:", self._skill_icon_row)
        self._bind_line_edit("icon", self.icon_edit)

        self.cooldown_spin = form.add_double_spin_box(
            "技能冷却时间:",
            "cooldown",
            minimum=0,
            maximum=999,
            step=0.5,
            suffix=" 秒",
            default=0.0,
        )

        self.use_limit_check = form.add_checkbox("use_limit", "启用次数限制", default=False)
        self.use_limit_check.stateChanged.connect(self._on_limit_changed)

        self.hide_when_empty_check = form.add_checkbox(
            "hide_when_empty",
            "无次数时隐藏",
            default=False,
        )

        self.count_var_selector = form.add_variable_selector(
            "次数变量:",
            "count_var",
            placeholder="选择玩家自定义变量",
        )

        # “使用道具”分支
        self.item_config_var_selector = form.add_variable_selector(
            "道具配置ID变量:",
            "item_config_var",
            placeholder="选择变量或输入固定值",
        )
        self.no_item_behavior_combo = form.add_combo_box(
            "无道具时表现:",
            "no_item_behavior",
            ["图标置灰", "隐藏"],
            default_text="图标置灰",
        )

    def _on_type_changed(self, type_name: str) -> None:
        self._apply_type_state(type_name)

    def _on_limit_changed(self, state: int) -> None:
        enabled = state == QtCore.Qt.CheckState.Checked.value
        self._apply_limit_state(enabled)

    def _set_form_row_visible(self, field: QtWidgets.QWidget, visible: bool) -> None:
        label = self._form_layout.labelForField(field)
        if label is not None:
            label.setVisible(visible)
        field.setVisible(visible)

    def _apply_type_state(self, type_name: str) -> None:
        is_skill = type_name == "角色技能"
        is_use_item = type_name == "使用道具"

        # 技能分支
        self._set_form_row_visible(self._skill_icon_row, is_skill)
        self._set_form_row_visible(self.cooldown_spin, is_skill)
        self._set_form_row_visible(self.use_limit_check, is_skill)
        if is_skill:
            self._apply_limit_state(self.use_limit_check.isChecked())
        else:
            self._apply_limit_state(False)

        # 道具分支
        self._set_form_row_visible(self.item_config_var_selector, is_use_item)
        self._set_form_row_visible(self.no_item_behavior_combo, is_use_item)

    def _apply_limit_state(self, enabled: bool) -> None:
        self._set_form_row_visible(self.hide_when_empty_check, enabled)
        self._set_form_row_visible(self.count_var_selector, enabled)

    def _update_ui_from_config(self) -> None:
        super()._update_ui_from_config()
        self._apply_type_state(self.button_type_combo.currentText())

    def _choose_icon(self) -> None:
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "选择图标资源",
            "",
            "Images (*.png *.jpg *.jpeg *.svg);;All Files (*.*)",
        )
        if file_path:
            self.icon_edit.setText(file_path)


class ItemDisplayConfigPanel(BaseWidgetConfigPanel):
    """道具展示配置面板"""

    def _setup_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        form = WidgetConfigForm(self)
        layout.addWidget(form)

        # 注意：道具展示的写回需要“完整变量引用”（组名.变量名），因此这里不使用 VariableSelector（它只返回变量名）。
        # 变量引用格式：玩家自身.xxx / 关卡.xxx / lv.xxx / '.'(不绑定)

        self.interactive_check = form.add_checkbox("can_interact", "可交互", default=False)
        self.interactive_check.stateChanged.connect(self._on_interactive_changed)

        self.keybind_fields = form.add_key_mapping_pair(
            "keybind_kbm_code",
            "keybind_gamepad_code",
            keyboard_label="按键码(键鼠):",
            gamepad_label="按键码(手柄):",
            keyboard_placeholder="如: 1 / 2 / 3 / 9 / 11(U)",
            gamepad_placeholder="如: 1 / 4 / 5 / 9",
        )
        # 道具展示使用“数字按键码”（而非键名）。为避免把描述文本写入配置，这里仅对数字码做补全，
        # 详细映射通过 tooltip 提示（让用户知道各 code 对应的真实按键/组合键）。
        kbm_completer = QtWidgets.QCompleter(_ITEM_DISPLAY_KBM_CODE_CANDIDATES, self.keybind_fields.keyboard)
        kbm_completer.setCaseSensitivity(QtCore.Qt.CaseSensitivity.CaseInsensitive)
        self.keybind_fields.keyboard.setCompleter(kbm_completer)
        self.keybind_fields.keyboard.setToolTip(_ITEM_DISPLAY_KBM_CODE_TOOLTIP)
        if self.keybind_fields.gamepad is not None:
            pad_completer = QtWidgets.QCompleter(
                _ITEM_DISPLAY_GAMEPAD_CODE_CANDIDATES, self.keybind_fields.gamepad
            )
            pad_completer.setCaseSensitivity(QtCore.Qt.CaseSensitivity.CaseInsensitive)
            self.keybind_fields.gamepad.setCompleter(pad_completer)
            self.keybind_fields.gamepad.setToolTip(_ITEM_DISPLAY_GAMEPAD_CODE_TOOLTIP)

        self.display_type_combo = form.add_combo_box(
            "类型:",
            "display_type",
            ["玩家当前装备", "模板道具", "背包内道具"],
            default_text="玩家当前装备",
        )
        self.display_type_combo.currentTextChanged.connect(self._on_type_changed)

        self.config_id_var_edit = form.add_line_edit(
            "道具配置ID变量:",
            "config_id_variable",
            placeholder="玩家自身.xxx / 关卡.xxx / lv.xxx / .",
            default=".",
        )

        # no_equipment_behavior_code：存储为 int（2/3），UI 显示为中文选项
        self.no_equipment_behavior_combo = QtWidgets.QComboBox()
        self.no_equipment_behavior_combo.addItem("显示空白槽位", 2)
        self.no_equipment_behavior_combo.addItem("隐藏", 3)
        form.add_row_widget("无装备时表现:", self.no_equipment_behavior_combo)

        def _get_no_equipment_behavior_code() -> int:
            data = self.no_equipment_behavior_combo.currentData()
            return int(data) if isinstance(data, int) else 2

        def _set_no_equipment_behavior_code(value) -> None:
            normalized: int = 2
            if isinstance(value, bool):
                normalized = 2
            elif isinstance(value, int):
                normalized = int(value)
            elif isinstance(value, float):
                normalized = int(value)
            elif isinstance(value, str) and value.strip().isdigit():
                normalized = int(value.strip())
            # 仅支持 2/3；其它值回退到默认（2）
            if normalized not in {2, 3}:
                normalized = 2
            index = self.no_equipment_behavior_combo.findData(normalized, role=QtCore.Qt.ItemDataRole.UserRole)
            self.no_equipment_behavior_combo.setCurrentIndex(index if index >= 0 else 0)

        self._register_binding(
            "no_equipment_behavior_code",
            getter=_get_no_equipment_behavior_code,
            setter=_set_no_equipment_behavior_code,
            signal=self.no_equipment_behavior_combo.currentIndexChanged,
        )

        self.cooldown_var_edit = form.add_line_edit(
            "栏位冷却时间变量:",
            "cooldown_seconds_variable",
            placeholder="玩家自身.xxx / 关卡.xxx / lv.xxx / .",
            default=".",
        )

        # 次数相关
        self.use_count_enabled_check = form.add_checkbox("use_count_enabled", "启用栏位使用次数", default=False)
        self.use_count_enabled_check.stateChanged.connect(self._on_use_count_enabled_changed)

        self.hide_when_empty_count_check = form.add_checkbox(
            "hide_when_empty_count",
            "无次数时隐藏",
            default=False,
        )
        self.use_count_var_edit = form.add_line_edit(
            "栏位使用次数变量:",
            "use_count_variable",
            placeholder="玩家自身.xxx / 关卡.xxx / lv.xxx / .",
            default=".",
        )

        # 数量相关（模板道具）
        self.show_quantity_check = form.add_checkbox("show_quantity", "显示道具数量", default=False)
        self.hide_when_zero_check = form.add_checkbox("hide_when_zero", "数量为零时隐藏", default=False)
        self.show_quantity_check.stateChanged.connect(self._on_show_quantity_changed)

        self.quantity_var_edit = form.add_line_edit(
            "道具数量变量:",
            "quantity_variable",
            placeholder="玩家自身.xxx / 关卡.xxx / lv.xxx / .",
            default=".",
        )

    def _on_interactive_changed(self, state: int) -> None:
        enabled = state == QtCore.Qt.CheckState.Checked.value
        self.keybind_fields.keyboard.setEnabled(enabled)
        if self.keybind_fields.gamepad:
            self.keybind_fields.gamepad.setEnabled(enabled)

    def _on_use_count_enabled_changed(self, state: int) -> None:
        enabled = state == QtCore.Qt.CheckState.Checked.value
        self._apply_use_count_state(enabled)

    def _apply_use_count_state(self, enabled: bool) -> None:
        self.hide_when_empty_count_check.setEnabled(enabled)
        self.use_count_var_edit.setEnabled(enabled)

    def _on_show_quantity_changed(self, state: int) -> None:
        enabled = state == QtCore.Qt.CheckState.Checked.value
        self._apply_quantity_state(enabled)

    def _apply_quantity_state(self, enabled: bool) -> None:
        self.hide_when_zero_check.setEnabled(enabled)
        self.quantity_var_edit.setEnabled(enabled)

    def _on_type_changed(self, type_name: str) -> None:
        is_template_item = type_name == "模板道具"
        # 数量显示目前只在“模板道具”样本中出现；非模板道具禁用这些字段以避免误解。
        self.show_quantity_check.setEnabled(is_template_item)
        self.hide_when_zero_check.setEnabled(is_template_item and self.show_quantity_check.isChecked())
        self.quantity_var_edit.setEnabled(is_template_item and self.show_quantity_check.isChecked())

    def _update_ui_from_config(self) -> None:
        super()._update_ui_from_config()
        self._on_interactive_changed(
            QtCore.Qt.CheckState.Checked.value if self.interactive_check.isChecked() else QtCore.Qt.CheckState.Unchecked.value
        )
        self._on_type_changed(self.display_type_combo.currentText())
        self._apply_use_count_state(self.use_count_enabled_check.isChecked())
        self._apply_quantity_state(self.show_quantity_check.isChecked())

