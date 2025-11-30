from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from .base import BaseWidgetConfigPanel, WidgetConfigForm


class InteractionButtonConfigPanel(BaseWidgetConfigPanel):
    """交互按钮配置面板"""

    def _setup_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        form = WidgetConfigForm(self)
        layout.addWidget(form)

        self.key_mapping_fields = form.add_key_mapping_pair(
            "key_mapping",
            "gamepad_mapping",
            keyboard_placeholder="如: E, F, Space",
            gamepad_placeholder="如: A, B, X, Y",
        )

        self.button_type_combo = form.add_combo_box(
            "类型:",
            "button_type",
            ["角色技能", "交互事件"],
            default_text="交互事件",
            default_index=1,
        )
        self.button_type_combo.currentTextChanged.connect(self._on_type_changed)

        icon_widget = QtWidgets.QWidget()
        icon_layout = QtWidgets.QHBoxLayout(icon_widget)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        self.icon_edit = QtWidgets.QLineEdit()
        self.icon_edit.setPlaceholderText("图标资源路径")
        icon_layout.addWidget(self.icon_edit)
        icon_browse_btn = QtWidgets.QPushButton("浏览...")
        icon_browse_btn.setFixedWidth(60)
        icon_browse_btn.clicked.connect(self._choose_icon)
        icon_layout.addWidget(icon_browse_btn)
        form.add_row_widget("技能图标:", icon_widget)
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

    def _on_type_changed(self, type_name: str) -> None:
        self._apply_type_state(type_name)

    def _on_limit_changed(self, state: int) -> None:
        enabled = state == QtCore.Qt.CheckState.Checked.value
        self._apply_limit_state(enabled)

    def _apply_type_state(self, type_name: str) -> None:
        is_skill = type_name == "角色技能"
        self.icon_edit.setEnabled(is_skill)
        self.cooldown_spin.setEnabled(is_skill)
        self.use_limit_check.setEnabled(is_skill)
        if not is_skill:
            self.hide_when_empty_check.setEnabled(False)
            self.count_var_selector.setEnabled(False)
        else:
            self._apply_limit_state(self.use_limit_check.isChecked())

    def _apply_limit_state(self, enabled: bool) -> None:
        self.hide_when_empty_check.setEnabled(enabled)
        self.count_var_selector.setEnabled(enabled)

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

        self.interactive_check = form.add_checkbox("interactive", "可交互", default=False)
        self.interactive_check.stateChanged.connect(self._on_interactive_changed)

        self.key_mapping_fields = form.add_key_mapping_pair(
            "key_mapping",
            "gamepad_mapping",
        )

        self.display_type_combo = form.add_combo_box(
            "类型:",
            "display_type",
            ["玩家当前装备", "模板道具", "背包内道具"],
            default_text="玩家当前装备",
        )
        self.display_type_combo.currentTextChanged.connect(self._on_type_changed)

        self.equip_var_selector = form.add_variable_selector(
            "装备配置ID变量:",
            "equip_config_var",
            placeholder="选择玩家自定义变量",
        )

        self.empty_behavior_combo = form.add_combo_box(
            "无装备时表现:",
            "empty_behavior",
            ["显示空白槽位", "隐藏"],
            default_text="显示空白槽位",
        )

        self.slot_cooldown_selector = form.add_variable_selector(
            "栏位冷却时间变量:",
            "slot_cooldown_var",
            placeholder="绑定冷却变量",
        )

        self.show_count_check = form.add_checkbox("show_count", "显示道具数量", default=False)
        self.hide_when_zero_check = form.add_checkbox("hide_when_zero", "数量为零时隐藏", default=False)

        self.count_var_selector = form.add_variable_selector(
            "道具数量变量:",
            "count_var",
            placeholder="绑定数量变量",
        )

    def _on_interactive_changed(self, state: int) -> None:
        enabled = state == QtCore.Qt.CheckState.Checked.value
        self.key_mapping_fields.keyboard.setEnabled(enabled)
        if self.key_mapping_fields.gamepad:
            self.key_mapping_fields.gamepad.setEnabled(enabled)

    def _on_type_changed(self, type_name: str) -> None:
        need_equip = type_name in ["玩家当前装备", "模板道具"]
        self.equip_var_selector.setEnabled(need_equip)

    def _update_ui_from_config(self) -> None:
        super()._update_ui_from_config()
        self._on_interactive_changed(
            QtCore.Qt.CheckState.Checked.value if self.interactive_check.isChecked() else QtCore.Qt.CheckState.Unchecked.value
        )
        self._on_type_changed(self.display_type_combo.currentText())

