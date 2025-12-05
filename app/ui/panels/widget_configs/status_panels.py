from __future__ import annotations

from PyQt6 import QtWidgets

from ui.foundation.theme_manager import Colors
from .base import BaseWidgetConfigPanel, WidgetConfigForm


class ProgressBarConfigPanel(BaseWidgetConfigPanel):
    """进度条配置面板"""

    def _setup_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        form = WidgetConfigForm(self)
        layout.addWidget(form)

        self.shape_combo = form.add_combo_box(
            "形状:",
            "shape",
            ["横向", "纵向", "圆环"],
            default_text="横向",
        )
        self.style_combo = form.add_combo_box(
            "进度样式:",
            "style",
            ["不显示", "百分比", "真实比例", "当前值"],
            default_text="不显示",
        )

        color_widget = QtWidgets.QWidget()
        color_layout = QtWidgets.QHBoxLayout(color_widget)
        color_layout.setContentsMargins(0, 0, 0, 0)
        self.color_edit = QtWidgets.QLineEdit(Colors.SUCCESS)
        self.color_edit.setFixedWidth(100)
        color_layout.addWidget(self.color_edit)
        color_btn = QtWidgets.QPushButton("选择颜色...")
        color_btn.clicked.connect(self._choose_color)
        color_layout.addWidget(color_btn)
        color_layout.addStretch()
        form.add_row_widget("颜色:", color_widget)
        self._bind_line_edit("color", self.color_edit, default=Colors.SUCCESS)

        form.add_variable_selector("当前进度值:", "current_var", placeholder="选择变量")
        form.add_variable_selector("最小值:", "min_var", placeholder="选择变量或输入固定值")
        form.add_variable_selector("最大值:", "max_var", placeholder="选择变量或输入固定值")

    def _choose_color(self) -> None:
        color = QtWidgets.QColorDialog.getColor()
        if color.isValid():
            self.color_edit.setText(color.name())


class TimerConfigPanel(BaseWidgetConfigPanel):
    """计时器配置面板"""

    def _setup_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        form = WidgetConfigForm(self)
        layout.addWidget(form)

        self.timer_type_combo = form.add_combo_box(
            "类型:",
            "timer_type",
            ["正计时", "倒计时"],
            default_text="正计时",
        )

        self.timer_id_combo = QtWidgets.QComboBox()
        self.timer_id_combo.setEditable(True)
        self.timer_id_combo.setPlaceholderText("选择已定义的全局计时器")
        form.add_row_widget("指定计时器:", self.timer_id_combo)
        self._register_binding(
            "timer_id",
            getter=self.timer_id_combo.currentText,
            setter=lambda value: self.timer_id_combo.setCurrentText(value or ""),
            signal=self.timer_id_combo.currentTextChanged,
        )

        self.source_entity_combo = form.add_combo_box(
            "来源实体:",
            "source_entity",
            ["关卡实体", "玩家实体"],
            default_text="关卡实体",
        )


class ScoreboardConfigPanel(BaseWidgetConfigPanel):
    """计分板配置面板"""

    def _setup_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        form = WidgetConfigForm(self)
        layout.addWidget(form)

        form.add_key_mapping_pair(
            "key_mapping",
            gamepad_key=None,
            keyboard_label="按键映射(键鼠):",
            keyboard_placeholder="收起/展开按键",
        )

        self.sort_combo = form.add_combo_box(
            "排序:",
            "sort_order",
            ["升序", "降序"],
            default_text="升序",
        )

        self.board_type_combo = form.add_combo_box(
            "类型:",
            "board_type",
            ["个人", "阵营"],
            default_text="个人",
        )
        self.board_type_combo.currentTextChanged.connect(self._on_type_changed)

        style_group = QtWidgets.QGroupBox("样式设置")
        style_layout = QtWidgets.QVBoxLayout(style_group)
        self.show_rank_check = QtWidgets.QCheckBox("显示名次")
        self.show_score_check = QtWidgets.QCheckBox("显示分数")
        self.show_faction_check = QtWidgets.QCheckBox("显示阵营图标")
        self.show_name_check = QtWidgets.QCheckBox("显示玩家名称")
        self.show_avatar_check = QtWidgets.QCheckBox("显示玩家头像")

        for checkbox, key in [
            (self.show_rank_check, "show_rank"),
            (self.show_score_check, "show_score"),
            (self.show_faction_check, "show_faction"),
            (self.show_name_check, "show_name"),
            (self.show_avatar_check, "show_avatar"),
        ]:
            style_layout.addWidget(checkbox)
            self._bind_checkbox(key, checkbox, default=False)

        form.add_section_widget(style_group)
        form.add_variable_selector("分数变量:", "score_var", placeholder="选择分数变量")

    def _on_type_changed(self, type_name: str) -> None:
        is_personal = type_name == "个人"
        self.show_faction_check.setEnabled(is_personal)
        self.show_name_check.setEnabled(is_personal)
        self.show_avatar_check.setEnabled(is_personal)

    def _update_ui_from_config(self) -> None:
        super()._update_ui_from_config()
        self._on_type_changed(self.board_type_combo.currentText())

