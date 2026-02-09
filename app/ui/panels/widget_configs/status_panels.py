from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from app.ui.foundation.theme_manager import Colors
from engine.configs.specialized.ui_widget_configs import (
    PROGRESSBAR_COLOR_GREEN_HEX,
    PROGRESSBAR_COLOR_OPTIONS,
)
from .base import BaseWidgetConfigPanel, VariableSelector, WidgetConfigForm


class ProgressBarConfigPanel(BaseWidgetConfigPanel):
    """进度条配置面板"""

    # 进度条颜色：固定枚举（与真源 `.gil` color_code 对齐的五色）
    _COLOR_OPTIONS: list[tuple[str, str]] = list(PROGRESSBAR_COLOR_OPTIONS)
    _ALLOWED_COLOR_HEX: set[str] = {value for _label, value in PROGRESSBAR_COLOR_OPTIONS}

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

        self.color_combo = QtWidgets.QComboBox()
        for label, value in self._COLOR_OPTIONS:
            self.color_combo.addItem(label, value)
        self.color_combo.setCurrentIndex(1)  # 默认：绿色 (Green)
        color_layout.addWidget(self.color_combo)

        self.color_preview = QtWidgets.QLabel()
        self.color_preview.setFixedSize(18, 18)
        self._sync_color_preview_from_combo()
        color_layout.addWidget(self.color_preview)
        color_layout.addStretch()

        form.add_row_widget("颜色:", color_widget)
        self._register_binding(
            "color",
            getter=self._get_selected_color_value,
            setter=self._set_selected_color_value,
            signal=self.color_combo.currentTextChanged,
        )
        self.color_combo.currentIndexChanged.connect(self._sync_color_preview_from_combo)

        form.add_variable_selector("当前进度值:", "current_var", placeholder="选择变量")
        form.add_variable_selector("最小值:", "min_var", placeholder="选择变量或输入固定值")
        form.add_variable_selector("最大值:", "max_var", placeholder="选择变量或输入固定值")

    def _get_selected_color_value(self) -> str:
        value = self.color_combo.currentData()
        return str(value) if value is not None else PROGRESSBAR_COLOR_GREEN_HEX

    def _set_selected_color_value(self, value) -> None:
        raw = str(value or "").strip()
        normalized = self._normalize_color_value(raw)
        index = self.color_combo.findData(normalized, role=QtCore.Qt.ItemDataRole.UserRole)
        if index >= 0:
            self.color_combo.setCurrentIndex(index)
        else:
            self.color_combo.setCurrentIndex(1)  # 绿色 (Green)
        self._sync_color_preview_from_combo()

    def _normalize_color_value(self, raw: str) -> str:
        text = str(raw or "").strip()
        if not text.startswith("#"):
            return ""
        upper = text.upper()
        return upper if upper in self._ALLOWED_COLOR_HEX else ""

    def _sync_color_preview_from_combo(self, _index: int | None = None) -> None:
        color_value = self._get_selected_color_value()
        self.color_preview.setStyleSheet(
            f"border: 1px solid {Colors.BORDER_DARK}; border-radius: 3px; background-color: {color_value};"
        )


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
        self._player_bindings: list[str] = []
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

        players_group = QtWidgets.QGroupBox("玩家数据绑定")
        players_layout = QtWidgets.QVBoxLayout(players_group)

        self.players_table = QtWidgets.QTableWidget()
        self.players_table.setColumnCount(2)
        self.players_table.setHorizontalHeaderLabels(["Player", "变量"])
        vertical_header = self.players_table.verticalHeader()
        if vertical_header is not None:
            vertical_header.setVisible(False)
        self.players_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.players_table.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
        )
        horizontal_header = self.players_table.horizontalHeader()
        if horizontal_header is not None:
            horizontal_header.setStretchLastSection(True)
        self.players_table.setMinimumHeight(180)
        players_layout.addWidget(self.players_table)

        toolbar = QtWidgets.QHBoxLayout()
        add_btn = QtWidgets.QPushButton("+ 新增行")
        add_btn.clicked.connect(self._add_player_row)
        remove_btn = QtWidgets.QPushButton("删除当前行")
        remove_btn.clicked.connect(self._remove_current_player_row)
        toolbar.addWidget(add_btn)
        toolbar.addWidget(remove_btn)
        toolbar.addStretch()
        players_layout.addLayout(toolbar)

        form.add_section_widget(players_group)

    def _on_type_changed(self, type_name: str) -> None:
        is_personal = type_name == "个人"
        self.show_faction_check.setEnabled(is_personal)
        self.show_name_check.setEnabled(is_personal)
        self.show_avatar_check.setEnabled(is_personal)

    def _add_player_row(self) -> None:
        self._player_bindings.append("")
        self._append_player_row("")
        self._persist_player_bindings()

    def _remove_current_player_row(self) -> None:
        row = self.players_table.currentRow()
        if row < 0 or row >= len(self._player_bindings):
            return
        del self._player_bindings[row]

        selector = self.players_table.cellWidget(row, 1)
        if isinstance(selector, VariableSelector) and selector in self._variable_selectors:
            self._variable_selectors.remove(selector)
        self.players_table.removeRow(row)
        self._refresh_player_labels()
        self._persist_player_bindings()

    def _sync_player_table_from_bindings(self) -> None:
        self.players_table.setRowCount(0)
        for index, raw_value in enumerate(self._player_bindings):
            self._append_player_row(raw_value, index=index)
        self.players_table.resizeColumnToContents(0)

    def _append_player_row(self, raw_value: str, *, index: int | None = None) -> None:
        row = self.players_table.rowCount()
        self.players_table.insertRow(row)

        display_index = (index + 1) if index is not None else (row + 1)
        label_item = QtWidgets.QTableWidgetItem(f"Player {display_index}")
        label_item.setFlags(label_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
        self.players_table.setItem(row, 0, label_item)

        selector = VariableSelector("选择变量或输入固定值", self.players_table)
        self._register_variable_selector(selector)
        selector.set_value(raw_value)
        selector.value_selected.connect(self._on_player_selector_changed)
        self.players_table.setCellWidget(row, 1, selector)

    def _refresh_player_labels(self) -> None:
        for row in range(self.players_table.rowCount()):
            item = self.players_table.item(row, 0)
            if item is None:
                continue
            item.setText(f"Player {row + 1}")

    def _on_player_selector_changed(self, value: str) -> None:
        sender = self.sender()
        if not isinstance(sender, VariableSelector):
            return
        row_index = -1
        for row in range(self.players_table.rowCount()):
            if self.players_table.cellWidget(row, 1) is sender:
                row_index = row
                break
        if row_index < 0 or row_index >= len(self._player_bindings):
            return
        self._player_bindings[row_index] = str(value or "").strip()
        self._persist_player_bindings()

    def _persist_player_bindings(self) -> None:
        self._settings()["player_bindings"] = list(self._player_bindings)
        self._emit_changed()

    def _update_ui_from_config(self) -> None:
        super()._update_ui_from_config()
        settings = self._settings()
        raw_list = settings.get("player_bindings", [])
        self._player_bindings = [str(value or "").strip() for value in raw_list if value is not None]
        self._sync_player_table_from_bindings()
        self._on_type_changed(self.board_type_combo.currentText())

