"""挂接点编辑器（Sockets Editor）。

用于维护主物体上的挂接点数据结构：
- 系统/单位挂接点（Unit Sockets）：只读展示（来自 `common_inspector.model.mountPoints`）
- 自定义挂接点（Custom Sockets）：可编辑（写入 `common_inspector.model.attachmentPoints`）

注意：本项目当前未接入 3D 视口，因此“预览/显示坐标轴”仅作为数据标记写回，
由后续渲染侧决定如何展示。
"""

from __future__ import annotations

import copy
from typing import Any, Optional

from PyQt6 import QtCore, QtWidgets

from app.ui.foundation import dialog_utils
from app.ui.foundation.base_widgets import BaseDialog
from app.ui.foundation.theme_manager import Colors, Sizes, ThemeManager
from app.ui.foundation.toggle_switch import ToggleSwitch
from app.ui.panels.template_instance.vector3_editor import Vector3Editor


ROOT_SOCKET_NAME = "GI_RootNode"


def _safe_str(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _safe_bool(value: object, default: bool) -> bool:
    return bool(value) if isinstance(value, bool) else bool(default)


def _safe_vector3_dict(value: object, *, default: tuple[float, float, float]) -> dict[str, float]:
    if isinstance(value, dict):
        x = value.get("x")
        y = value.get("y")
        z = value.get("z")
        out = {
            "x": float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else float(default[0]),
            "y": float(y) if isinstance(y, (int, float)) and not isinstance(y, bool) else float(default[1]),
            "z": float(z) if isinstance(z, (int, float)) and not isinstance(z, bool) else float(default[2]),
        }
        return out
    return {"x": float(default[0]), "y": float(default[1]), "z": float(default[2])}


class SocketEditorDialog(BaseDialog):
    """挂接点编辑对话框（单位挂接点只读 + 自定义挂接点编辑）。"""

    def __init__(
        self,
        *,
        unit_sockets: list[str],
        attachment_points: list[dict[str, object]],
        unit_socket_previews: list[str],
        parent: Optional[QtWidgets.QWidget] = None,
        title: str = "挂接点编辑",
    ) -> None:
        self._unit_sockets: list[str] = []
        for raw in unit_sockets:
            name = _safe_str(raw)
            if name:
                self._unit_sockets.append(name)
        if ROOT_SOCKET_NAME not in self._unit_sockets:
            self._unit_sockets.insert(0, ROOT_SOCKET_NAME)

        self._unit_socket_preview_set: set[str] = set(
            _safe_str(x) for x in unit_socket_previews if _safe_str(x)
        )

        self._attachment_points: list[dict[str, object]] = []
        for raw in attachment_points:
            if not isinstance(raw, dict):
                continue
            self._attachment_points.append(self._normalize_attachment_point(raw))

        self._selected_index: int = -1
        self._updating_ui: bool = False

        super().__init__(
            title=title,
            width=880,
            height=560,
            parent=parent,
        )

        self._build_content()
        self._populate_unit_sockets_table()
        self._populate_custom_socket_list()

    # ------------------------------------------------------------------ UI

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            ThemeManager.dialog_surface_style(
                include_inputs=True,
                include_tables=True,
                include_scrollbars=True,
            )
        )

    def _build_content(self) -> None:
        layout = self.content_layout
        layout.setContentsMargins(
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
        )
        layout.setSpacing(Sizes.SPACING_MEDIUM)

        hint = QtWidgets.QLabel(
            "挂接点用于定义主物体上的锚点（Sockets），供装饰物等子物体选择父节点/骨骼。\n"
            "系统/单位挂接点来自主模型骨骼/预设点（此处只读展示）；自定义挂接点可在下方维护偏移与旋转。",
            self,
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(ThemeManager.hint_text_style())
        layout.addWidget(hint)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal, self)
        splitter.setHandleWidth(2)
        layout.addWidget(splitter, 1)

        # Left -----------------------------------------------------------
        left_root = QtWidgets.QWidget(splitter)
        left_layout = QtWidgets.QVBoxLayout(left_root)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(Sizes.SPACING_MEDIUM)

        unit_group = QtWidgets.QGroupBox("系统/单位挂接点（只读）", left_root)
        unit_layout = QtWidgets.QVBoxLayout(unit_group)
        unit_layout.setContentsMargins(
            Sizes.PADDING_SMALL,
            Sizes.PADDING_SMALL,
            Sizes.PADDING_SMALL,
            Sizes.PADDING_SMALL,
        )
        unit_layout.setSpacing(Sizes.SPACING_SMALL)

        self._unit_table = QtWidgets.QTableWidget(unit_group)
        self._unit_table.setColumnCount(3)
        self._unit_table.setHorizontalHeaderLabels(("挂接点", "复制", "预览"))
        self._unit_table.verticalHeader().setVisible(False)
        self._unit_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self._unit_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self._unit_table.horizontalHeader().setStretchLastSection(False)
        self._unit_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self._unit_table.setColumnWidth(1, 54)
        self._unit_table.setColumnWidth(2, 60)
        unit_layout.addWidget(self._unit_table)

        left_layout.addWidget(unit_group, 1)

        custom_group = QtWidgets.QGroupBox("自定义挂接点", left_root)
        custom_layout = QtWidgets.QVBoxLayout(custom_group)
        custom_layout.setContentsMargins(
            Sizes.PADDING_SMALL,
            Sizes.PADDING_SMALL,
            Sizes.PADDING_SMALL,
            Sizes.PADDING_SMALL,
        )
        custom_layout.setSpacing(Sizes.SPACING_SMALL)

        self._custom_list = QtWidgets.QListWidget(custom_group)
        self._custom_list.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
        )
        self._custom_list.currentRowChanged.connect(self._on_custom_socket_selected)
        custom_layout.addWidget(self._custom_list, 1)

        buttons_row = QtWidgets.QWidget(custom_group)
        buttons_layout = QtWidgets.QHBoxLayout(buttons_row)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(Sizes.SPACING_SMALL)

        self._add_btn = QtWidgets.QPushButton("+ 添加", buttons_row)
        self._add_btn.setStyleSheet(ThemeManager.button_style())
        self._add_btn.clicked.connect(self._add_custom_socket)
        buttons_layout.addWidget(self._add_btn)

        self._duplicate_btn = QtWidgets.QPushButton("复制", buttons_row)
        self._duplicate_btn.setStyleSheet(ThemeManager.button_style())
        self._duplicate_btn.clicked.connect(self._duplicate_custom_socket)
        buttons_layout.addWidget(self._duplicate_btn)

        self._remove_btn = QtWidgets.QPushButton("删除", buttons_row)
        self._remove_btn.setStyleSheet(ThemeManager.button_style())
        self._remove_btn.clicked.connect(self._remove_custom_socket)
        buttons_layout.addWidget(self._remove_btn)

        buttons_layout.addStretch(1)
        custom_layout.addWidget(buttons_row)

        left_layout.addWidget(custom_group, 2)

        # Right ----------------------------------------------------------
        right_root = QtWidgets.QWidget(splitter)
        right_layout = QtWidgets.QVBoxLayout(right_root)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(Sizes.SPACING_MEDIUM)

        editor_group = QtWidgets.QGroupBox("挂接点属性", right_root)
        form = QtWidgets.QFormLayout(editor_group)
        form.setContentsMargins(
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
        )
        form.setHorizontalSpacing(Sizes.SPACING_MEDIUM)
        form.setVerticalSpacing(Sizes.SPACING_MEDIUM)

        self._name_edit = QtWidgets.QLineEdit(editor_group)
        self._name_edit.setStyleSheet(ThemeManager.input_style())
        self._name_edit.textEdited.connect(self._on_name_changed)

        self._parent_combo = QtWidgets.QComboBox(editor_group)
        self._parent_combo.setStyleSheet(ThemeManager.combo_box_style())
        self._parent_combo.currentIndexChanged.connect(self._on_parent_changed)

        self._offset_editor = Vector3Editor(
            minimum=-10000.0,
            maximum=10000.0,
            decimals=2,
            single_step=0.1,
            parent=editor_group,
        )
        self._offset_editor.value_changed.connect(self._on_offset_changed)

        self._rotation_editor = Vector3Editor(
            minimum=-360.0,
            maximum=360.0,
            decimals=2,
            single_step=1.0,
            parent=editor_group,
        )
        self._rotation_editor.value_changed.connect(self._on_rotation_changed)

        self._preview_switch = ToggleSwitch(editor_group)
        self._preview_switch.toggled.connect(self._on_preview_toggled)

        form.addRow("名称*", self._name_edit)
        form.addRow("父节点/骨骼", self._parent_combo)
        form.addRow("偏移 Offset", self._offset_editor)
        form.addRow("旋转 Rotation", self._rotation_editor)
        form.addRow("预览坐标轴", self._preview_switch)

        right_layout.addWidget(editor_group, 1)

        self._empty_hint = QtWidgets.QLabel("在左侧选择一个自定义挂接点以编辑。", right_root)
        self._empty_hint.setWordWrap(True)
        self._empty_hint.setStyleSheet(f"color: {Colors.TEXT_HINT};")
        right_layout.addWidget(self._empty_hint)

        splitter.addWidget(left_root)
        splitter.addWidget(right_root)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([340, 520])

        self._refresh_editor_enabled_state()

    # ------------------------------------------------------------------ Data normalize

    @staticmethod
    def _normalize_attachment_point(raw: dict[str, object]) -> dict[str, object]:
        name = _safe_str(raw.get("name") or raw.get("socketName") or raw.get("id"))
        parent_id = _safe_str(raw.get("parentId") or ROOT_SOCKET_NAME) or ROOT_SOCKET_NAME
        offset = _safe_vector3_dict(raw.get("offset"), default=(0.0, 0.0, 0.0))
        rotation = _safe_vector3_dict(raw.get("rotation"), default=(0.0, 0.0, 0.0))
        show_preview = _safe_bool(raw.get("showPreview"), False)
        return {
            "name": name,
            "parentId": parent_id,
            "offset": offset,
            "rotation": rotation,
            "showPreview": show_preview,
        }

    # ------------------------------------------------------------------ Unit sockets table

    def _populate_unit_sockets_table(self) -> None:
        table = self._unit_table
        table.setRowCount(len(self._unit_sockets))
        for row, socket_name in enumerate(self._unit_sockets):
            name_item = QtWidgets.QTableWidgetItem(socket_name)
            table.setItem(row, 0, name_item)

            copy_btn = QtWidgets.QToolButton(table)
            copy_btn.setText("复制")
            copy_btn.setAutoRaise(True)
            copy_btn.clicked.connect(lambda _=False, text=socket_name: self._copy_text(text))
            table.setCellWidget(row, 1, copy_btn)

            preview_box = QtWidgets.QCheckBox(table)
            preview_box.setChecked(socket_name in self._unit_socket_preview_set)
            preview_box.setToolTip("在预览中显示坐标轴辅助线。")
            preview_box.stateChanged.connect(
                lambda state, name=socket_name: self._on_unit_preview_changed(name, state)
            )
            preview_box.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
            table.setCellWidget(row, 2, preview_box)

        table.resizeRowsToContents()

    def _on_unit_preview_changed(self, socket_name: str, state: int) -> None:
        checked = state == QtCore.Qt.CheckState.Checked.value
        if checked:
            self._unit_socket_preview_set.add(socket_name)
        else:
            self._unit_socket_preview_set.discard(socket_name)

    @staticmethod
    def _copy_text(text: str) -> None:
        clipboard = QtWidgets.QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(str(text or ""))

    # ------------------------------------------------------------------ Custom sockets list

    def _populate_custom_socket_list(self) -> None:
        self._custom_list.clear()
        for ap in self._attachment_points:
            name = _safe_str(ap.get("name"))
            label = name if name else "(未命名挂接点)"
            item = QtWidgets.QListWidgetItem(f"🔩 {label}")
            self._custom_list.addItem(item)

        has_any = len(self._attachment_points) > 0
        self._duplicate_btn.setEnabled(has_any)
        self._remove_btn.setEnabled(has_any)

        if has_any:
            self._custom_list.setCurrentRow(0)
        else:
            self._selected_index = -1
            self._refresh_editor_enabled_state()

    def _on_custom_socket_selected(self, row: int) -> None:
        if self._updating_ui:
            return
        self._selected_index = int(row)
        self._load_selected_socket_to_editor()

    # ------------------------------------------------------------------ Editor wiring

    def _refresh_parent_combo(self, *, current_value: str) -> None:
        self._parent_combo.blockSignals(True)
        self._parent_combo.clear()
        options = list(self._unit_sockets)
        if current_value and current_value not in options:
            options.insert(0, current_value)
        for name in options:
            self._parent_combo.addItem(name)
        if current_value:
            idx = self._parent_combo.findText(current_value)
            if idx >= 0:
                self._parent_combo.setCurrentIndex(idx)
        self._parent_combo.blockSignals(False)

    def _refresh_editor_enabled_state(self) -> None:
        has_selection = 0 <= self._selected_index < len(self._attachment_points)
        self._name_edit.setEnabled(has_selection)
        self._parent_combo.setEnabled(has_selection)
        self._offset_editor.setEnabled(has_selection)
        self._rotation_editor.setEnabled(has_selection)
        self._preview_switch.setEnabled(has_selection)
        self._empty_hint.setVisible(not has_selection)

    def _load_selected_socket_to_editor(self) -> None:
        self._updating_ui = True
        try:
            has_selection = 0 <= self._selected_index < len(self._attachment_points)
            self._refresh_editor_enabled_state()
            if not has_selection:
                self._name_edit.setText("")
                self._refresh_parent_combo(current_value=ROOT_SOCKET_NAME)
                self._offset_editor.set_values([0.0, 0.0, 0.0])
                self._rotation_editor.set_values([0.0, 0.0, 0.0])
                self._preview_switch.setChecked(False)
                return

            ap = self._attachment_points[self._selected_index]
            name = _safe_str(ap.get("name"))
            parent_id = _safe_str(ap.get("parentId")) or ROOT_SOCKET_NAME
            offset = _safe_vector3_dict(ap.get("offset"), default=(0.0, 0.0, 0.0))
            rotation = _safe_vector3_dict(ap.get("rotation"), default=(0.0, 0.0, 0.0))
            show_preview = _safe_bool(ap.get("showPreview"), False)

            self._name_edit.setText(name)
            self._refresh_parent_combo(current_value=parent_id)
            self._offset_editor.set_values([offset["x"], offset["y"], offset["z"]])
            self._rotation_editor.set_values([rotation["x"], rotation["y"], rotation["z"]])
            self._preview_switch.setChecked(bool(show_preview))
        finally:
            self._updating_ui = False

    def _on_name_changed(self, text: str) -> None:
        if self._updating_ui:
            return
        if not (0 <= self._selected_index < len(self._attachment_points)):
            return
        name = _safe_str(text)
        self._attachment_points[self._selected_index]["name"] = name
        item = self._custom_list.item(self._selected_index)
        if item is not None:
            item.setText(f"🔩 {name if name else '(未命名挂接点)'}")

    def _on_parent_changed(self, index: int) -> None:
        if self._updating_ui:
            return
        if not (0 <= self._selected_index < len(self._attachment_points)):
            return
        parent_id = _safe_str(self._parent_combo.itemText(index)) or ROOT_SOCKET_NAME
        self._attachment_points[self._selected_index]["parentId"] = parent_id

    def _on_offset_changed(self) -> None:
        if self._updating_ui:
            return
        if not (0 <= self._selected_index < len(self._attachment_points)):
            return
        x, y, z = self._offset_editor.get_values()
        self._attachment_points[self._selected_index]["offset"] = {"x": x, "y": y, "z": z}

    def _on_rotation_changed(self) -> None:
        if self._updating_ui:
            return
        if not (0 <= self._selected_index < len(self._attachment_points)):
            return
        x, y, z = self._rotation_editor.get_values()
        self._attachment_points[self._selected_index]["rotation"] = {"x": x, "y": y, "z": z}

    def _on_preview_toggled(self, checked: bool) -> None:
        if self._updating_ui:
            return
        if not (0 <= self._selected_index < len(self._attachment_points)):
            return
        self._attachment_points[self._selected_index]["showPreview"] = bool(checked)

    # ------------------------------------------------------------------ CRUD

    def _next_unique_socket_name(self) -> str:
        existing = {ROOT_SOCKET_NAME}
        existing.update(self._unit_sockets)
        for ap in self._attachment_points:
            name = _safe_str(ap.get("name"))
            if name:
                existing.add(name)
        base = "Socket"
        idx = 1
        while True:
            candidate = f"{base}_{idx}"
            if candidate not in existing:
                return candidate
            idx += 1

    def _add_custom_socket(self) -> None:
        name = self._next_unique_socket_name()
        ap = {
            "name": name,
            "parentId": ROOT_SOCKET_NAME,
            "offset": {"x": 0.0, "y": 0.0, "z": 0.0},
            "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
            "showPreview": False,
        }
        self._attachment_points.append(ap)
        self._populate_custom_socket_list()
        self._custom_list.setCurrentRow(len(self._attachment_points) - 1)

    def _duplicate_custom_socket(self) -> None:
        if not (0 <= self._selected_index < len(self._attachment_points)):
            return
        raw = self._attachment_points[self._selected_index]
        cloned = copy.deepcopy(raw)
        cloned["name"] = self._next_unique_socket_name()
        self._attachment_points.append(cloned)
        self._populate_custom_socket_list()
        self._custom_list.setCurrentRow(len(self._attachment_points) - 1)

    def _remove_custom_socket(self) -> None:
        if not (0 <= self._selected_index < len(self._attachment_points)):
            return
        ap = self._attachment_points[self._selected_index]
        name = _safe_str(ap.get("name")) or "(未命名挂接点)"
        ok = dialog_utils.ask_yes_no_dialog(
            self,
            "确认删除",
            f"确定要删除自定义挂接点：{name}？",
            default_yes=False,
        )
        if not ok:
            return
        self._attachment_points.pop(self._selected_index)
        self._populate_custom_socket_list()

    # ------------------------------------------------------------------ Validate / Output

    def validate(self) -> bool:
        names: list[str] = []
        for ap in self._attachment_points:
            name = _safe_str(ap.get("name"))
            if not name:
                dialog_utils.show_warning_dialog(self, "提示", "存在未命名的自定义挂接点，请填写名称。")
                return False
            names.append(name)

        if len(set(names)) != len(names):
            dialog_utils.show_warning_dialog(self, "提示", "自定义挂接点名称不能重复。")
            return False

        reserved = set(self._unit_sockets)
        reserved.add(ROOT_SOCKET_NAME)
        for name in names:
            if name in reserved:
                dialog_utils.show_warning_dialog(
                    self,
                    "提示",
                    f"自定义挂接点名称与系统挂接点重复：{name}\n请改名以避免引用歧义。",
                )
                return False
        return True

    def get_attachment_points(self) -> list[dict[str, object]]:
        return [dict(item) for item in self._attachment_points]

    def get_unit_socket_previews(self) -> list[str]:
        result = [name for name in self._unit_sockets if name in self._unit_socket_preview_set]
        return result


__all__ = ["SocketEditorDialog", "ROOT_SOCKET_NAME"]


