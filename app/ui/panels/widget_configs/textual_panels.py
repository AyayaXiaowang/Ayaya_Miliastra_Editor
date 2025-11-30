from __future__ import annotations

from typing import Optional

from PyQt6 import QtWidgets

from ui.foundation import input_dialogs
from ui.foundation.base_widgets import BaseDialog
from ui.foundation.context_menu_builder import ContextMenuBuilder
from .base import BaseWidgetConfigPanel, WidgetConfigForm


class TextBoxConfigPanel(BaseWidgetConfigPanel):
    """文本框配置面板"""

    def _setup_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        form = WidgetConfigForm(self)
        layout.addWidget(form)

        self.bg_color_combo = form.add_combo_box(
            "背景颜色:",
            "background_color",
            ["透明", "黑色半透明"],
            default_text="透明",
        )

        self.font_size_spin = form.add_spin_box("字号:", "font_size", minimum=8, maximum=72, default=16)

        self.content_edit = form.add_plain_text_edit(
            "文本内容:",
            "text_content",
            placeholder="输入文本内容，可插入变量",
            max_height=100,
        )

        insert_var_btn = QtWidgets.QPushButton("插入变量...")
        insert_var_btn.setFixedWidth(100)
        insert_var_btn.clicked.connect(self._insert_variable_placeholder)
        form.add_row_widget("", insert_var_btn)

        align_group = QtWidgets.QGroupBox("对齐方式")
        align_layout = QtWidgets.QVBoxLayout(align_group)

        h_align_layout = QtWidgets.QHBoxLayout()
        h_align_layout.addWidget(QtWidgets.QLabel("水平:"))
        self.h_align_combo = QtWidgets.QComboBox()
        self.h_align_combo.addItems(["左侧对齐", "水平居中", "右侧对齐"])
        h_align_layout.addWidget(self.h_align_combo)
        self._bind_combo_box("alignment_h", self.h_align_combo, default_text="左侧对齐")
        align_layout.addLayout(h_align_layout)

        v_align_layout = QtWidgets.QHBoxLayout()
        v_align_layout.addWidget(QtWidgets.QLabel("垂直:"))
        self.v_align_combo = QtWidgets.QComboBox()
        self.v_align_combo.addItems(["顶部对齐", "垂直居中", "底部对齐"])
        v_align_layout.addWidget(self.v_align_combo)
        self._bind_combo_box("alignment_v", self.v_align_combo, default_text="顶部对齐")
        align_layout.addLayout(v_align_layout)

        form.add_section_widget(align_group)

    def _insert_variable_placeholder(self) -> None:
        variable_name = input_dialogs.prompt_text(self, "插入变量", "变量名称:")
        if not variable_name:
            return
        cursor = self.content_edit.textCursor()
        cursor.insertText(f"{{{{{variable_name}}}}}")
        self.content_edit.setTextCursor(cursor)


class PopupConfigPanel(BaseWidgetConfigPanel):
    """弹窗配置面板"""

    def _setup_ui(self) -> None:
        self._buttons: list[dict[str, str]] = []
        layout = QtWidgets.QVBoxLayout(self)
        form = WidgetConfigForm(self)
        layout.addWidget(form)

        self.title_edit = form.add_line_edit("标题:", "title", placeholder="弹窗标题")
        self.content_edit = form.add_plain_text_edit(
            "文本内容:",
            "content",
            placeholder="弹窗内容，支持插入变量",
            max_height=120,
        )

        buttons_group = QtWidgets.QGroupBox("按钮配置")
        buttons_layout = QtWidgets.QVBoxLayout(buttons_group)
        self.buttons_list = QtWidgets.QListWidget()
        self.buttons_list.setMaximumHeight(100)
        self.buttons_list.itemDoubleClicked.connect(self._edit_button)
        self.buttons_list.setContextMenuPolicy(
            QtWidgets.Qt.ContextMenuPolicy.CustomContextMenu  # type: ignore[attr-defined]
        )
        self.buttons_list.customContextMenuRequested.connect(
            self._on_buttons_context_menu
        )
        buttons_layout.addWidget(self.buttons_list)

        btn_toolbar = QtWidgets.QHBoxLayout()
        add_btn = QtWidgets.QPushButton("添加按钮")
        add_btn.clicked.connect(self._add_button)
        remove_btn = QtWidgets.QPushButton("移除")
        remove_btn.clicked.connect(self._remove_button)
        btn_toolbar.addWidget(add_btn)
        btn_toolbar.addWidget(remove_btn)
        btn_toolbar.addStretch()
        buttons_layout.addLayout(btn_toolbar)

        form.add_section_widget(buttons_group)

    def _update_ui_from_config(self) -> None:
        super()._update_ui_from_config()
        settings = self._settings()
        raw_buttons = settings.get("buttons", [])
        self._buttons = [dict(entry) for entry in raw_buttons if isinstance(entry, dict)]
        self._refresh_button_list()

    def _add_button(self) -> None:
        button = self._prompt_button()
        if not button:
            return
        self._buttons.append(button)
        self._persist_buttons()

    def _edit_button(self, item: QtWidgets.QListWidgetItem) -> None:
        index = self.buttons_list.row(item)
        if index < 0:
            return
        updated = self._prompt_button(self._buttons[index])
        if not updated:
            return
        self._buttons[index] = updated
        self._persist_buttons()

    def _remove_button(self) -> None:
        index = self.buttons_list.currentRow()
        if index < 0:
            return
        del self._buttons[index]
        self._persist_buttons()

    def _on_buttons_context_menu(self, pos) -> None:
        item = self.buttons_list.itemAt(pos)
        if item is None:
            return
        builder = ContextMenuBuilder(self.buttons_list)
        builder.add_action("删除当前行", self._remove_button)
        builder.exec_for(self.buttons_list, pos)

    def _persist_buttons(self) -> None:
        self._settings()["buttons"] = list(self._buttons)
        self._refresh_button_list()
        self._emit_changed()

    def _refresh_button_list(self) -> None:
        self.buttons_list.clear()
        for button in self._buttons:
            label = button.get("label", "")
            action = button.get("action", "")
            text = f"{label} → {action}" if action else label
            self.buttons_list.addItem(text)

    def _prompt_button(self, button: Optional[dict] = None) -> Optional[dict]:
        dialog = BaseDialog(
            title="编辑按钮" if button else "添加按钮",
            width=360,
            height=180,
            parent=self,
        )

        form_layout = QtWidgets.QFormLayout()
        label_edit = QtWidgets.QLineEdit(button.get("label", "") if button else "")
        action_edit = QtWidgets.QLineEdit(button.get("action", "") if button else "")
        form_layout.addRow("按钮文本:", label_edit)
        form_layout.addRow("动作标识:", action_edit)
        dialog.add_layout(form_layout)

        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return None
        label = label_edit.text().strip()
        action = action_edit.text().strip()
        if not label:
            return None
        return {"label": label, "action": action}

