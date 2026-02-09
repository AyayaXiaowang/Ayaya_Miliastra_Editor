"""装饰物编辑器（Decoration Editor）。

用于在主物体上维护 decorations 列表（列表-详情 Master-Detail），并写回到
`metadata["common_inspector"]["model"]["decorations"]`。

注意：当前项目未接入 3D 视口，故：
- “在场景选取 / Gizmo 拖拽回填”不做实际联动，仅提供数据字段与 UI 编辑能力；
- showPreview/lockTransform 等标记会落到数据结构中，渲染侧可在后续接入时复用。
"""

from __future__ import annotations

import copy
from typing import Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from app.ui.foundation import dialog_utils, input_dialogs
from app.ui.foundation.base_widgets import BaseDialog
from app.ui.foundation.theme_manager import Colors, Sizes, ThemeManager
from app.ui.foundation.toggle_switch import ToggleSwitch
from app.ui.panels.template_instance.vector3_editor import Vector3Editor


ROOT_SOCKET_NAME = "GI_RootNode"


def _safe_str(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _safe_bool(value: object, default: bool) -> bool:
    return bool(value) if isinstance(value, bool) else bool(default)


def _safe_int(value: object, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return int(value)
    if isinstance(value, float) and not isinstance(value, bool):
        return int(value)
    return int(default)


def _safe_vector3_dict(value: object, *, default: tuple[float, float, float]) -> dict[str, float]:
    if isinstance(value, dict):
        x = value.get("x")
        y = value.get("y")
        z = value.get("z")
        return {
            "x": float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else float(default[0]),
            "y": float(y) if isinstance(y, (int, float)) and not isinstance(y, bool) else float(default[1]),
            "z": float(z) if isinstance(z, (int, float)) and not isinstance(z, bool) else float(default[2]),
        }
    return {"x": float(default[0]), "y": float(default[1]), "z": float(default[2])}


def _vector_dict_from_editor(editor: Vector3Editor) -> dict[str, float]:
    x, y, z = editor.get_values()
    return {"x": float(x), "y": float(y), "z": float(z)}


def _vector_list_from_dict(value: object, default: tuple[float, float, float]) -> list[float]:
    d = _safe_vector3_dict(value, default=default)
    return [d["x"], d["y"], d["z"]]


class DecorationEditorDialog(BaseDialog):
    """装饰物编辑对话框（列表-详情）。"""

    def __init__(
        self,
        *,
        decorations: list[dict[str, object]],
        available_parent_sockets: list[str],
        parent: Optional[QtWidgets.QWidget] = None,
        title: str = "装饰物编辑",
    ) -> None:
        self._decorations: list[dict[str, object]] = []
        for raw in decorations:
            if not isinstance(raw, dict):
                continue
            self._decorations.append(self._normalize_decoration(raw))

        sockets: list[str] = []
        for raw in available_parent_sockets:
            name = _safe_str(raw)
            if name and name not in sockets:
                sockets.append(name)
        if ROOT_SOCKET_NAME not in sockets:
            sockets.insert(0, ROOT_SOCKET_NAME)
        self._available_sockets = sockets

        self._selected_index: int = -1
        self._updating_ui: bool = False
        self._updating_list: bool = False
        self._copied_decoration: Optional[dict[str, object]] = None

        super().__init__(
            title=title,
            width=980,
            height=660,
            parent=parent,
        )

        self._build_content()
        self._populate_list()

    # ------------------------------------------------------------------ UI

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            ThemeManager.dialog_surface_style(
                include_inputs=True,
                include_tables=False,
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
            "装饰物用于在主物体上挂载子物体实例，并配置其模型、父挂接点、变换与原生碰撞等属性。\n"
            "提示：当前项目未接入 3D 视口，因此“在场景选取 / Gizmo 拖拽”仅保留数据字段与 UI。"
            "后续接入渲染侧即可复用本数据结构。",
            self,
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(ThemeManager.hint_text_style())
        layout.addWidget(hint)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal, self)
        splitter.setHandleWidth(2)
        layout.addWidget(splitter, 1)

        # Left: list -----------------------------------------------------
        left_root = QtWidgets.QWidget(splitter)
        left_layout = QtWidgets.QVBoxLayout(left_root)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(Sizes.SPACING_SMALL)

        self._list_widget = QtWidgets.QListWidget(left_root)
        self._list_widget.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
        )
        self._list_widget.currentRowChanged.connect(self._on_selection_changed)
        self._list_widget.itemChanged.connect(self._on_item_changed)
        left_layout.addWidget(self._list_widget, 1)

        footer = QtWidgets.QWidget(left_root)
        footer_layout = QtWidgets.QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(Sizes.SPACING_SMALL)

        self._add_btn = QtWidgets.QPushButton("+ 添加", footer)
        self._add_btn.setStyleSheet(ThemeManager.button_style())
        self._add_btn.clicked.connect(self._add_decoration)
        footer_layout.addWidget(self._add_btn)

        self._duplicate_btn = QtWidgets.QPushButton("复制", footer)
        self._duplicate_btn.setStyleSheet(ThemeManager.button_style())
        self._duplicate_btn.clicked.connect(self._duplicate_decoration)
        footer_layout.addWidget(self._duplicate_btn)

        self._remove_btn = QtWidgets.QPushButton("删除", footer)
        self._remove_btn.setStyleSheet(ThemeManager.button_style())
        self._remove_btn.clicked.connect(self._remove_decoration)
        footer_layout.addWidget(self._remove_btn)

        footer_layout.addStretch(1)

        self._select_in_scene_btn = QtWidgets.QPushButton("在场景选取", footer)
        self._select_in_scene_btn.setStyleSheet(ThemeManager.button_style())
        self._select_in_scene_btn.setEnabled(False)
        self._select_in_scene_btn.setToolTip("当前项目未接入 3D 视口，暂不支持在场景中选取。")
        footer_layout.addWidget(self._select_in_scene_btn)

        left_layout.addWidget(footer)

        # Right: inspector ----------------------------------------------
        right_root = QtWidgets.QWidget(splitter)
        right_layout = QtWidgets.QVBoxLayout(right_root)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(Sizes.SPACING_MEDIUM)

        header = QtWidgets.QFrame(right_root)
        header.setObjectName("DecorationInspectorHeader")
        header.setStyleSheet(ThemeManager.card_style())
        header_layout = QtWidgets.QHBoxLayout(header)
        header_layout.setContentsMargins(
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
        )
        header_layout.setSpacing(Sizes.SPACING_SMALL)

        self._name_edit = QtWidgets.QLineEdit(header)
        self._name_edit.setStyleSheet(ThemeManager.input_style())
        self._name_edit.setPlaceholderText("装饰物名称")
        self._name_edit.textEdited.connect(self._on_name_edited)
        header_layout.addWidget(self._name_edit, 1)

        self._instance_id_label = QtWidgets.QLabel("ID: -", header)
        self._instance_id_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        header_layout.addWidget(self._instance_id_label)

        menu_btn = QtWidgets.QToolButton(header)
        menu_btn.setText("⋯")
        menu_btn.setAutoRaise(True)
        menu_btn.setToolTip("更多操作")
        menu_btn.clicked.connect(self._open_header_menu)
        header_layout.addWidget(menu_btn)

        right_layout.addWidget(header)

        self._empty_hint = QtWidgets.QLabel("在左侧选择一个装饰物以编辑。", right_root)
        self._empty_hint.setWordWrap(True)
        self._empty_hint.setStyleSheet(f"color: {Colors.TEXT_HINT};")
        right_layout.addWidget(self._empty_hint)

        self._inspector_container = QtWidgets.QWidget(right_root)
        inspector_layout = QtWidgets.QVBoxLayout(self._inspector_container)
        inspector_layout.setContentsMargins(0, 0, 0, 0)
        inspector_layout.setSpacing(Sizes.SPACING_MEDIUM)

        # Group 1: Model asset
        model_group = QtWidgets.QGroupBox("模型 (Model Asset)", self._inspector_container)
        model_form = QtWidgets.QFormLayout(model_group)
        model_form.setContentsMargins(
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
        )
        model_form.setHorizontalSpacing(Sizes.SPACING_MEDIUM)
        model_form.setVerticalSpacing(Sizes.SPACING_MEDIUM)

        self._asset_id_spin = QtWidgets.QSpinBox(model_group)
        self._asset_id_spin.setStyleSheet(ThemeManager.spin_box_style())
        self._asset_id_spin.setRange(0, 999_999_999)
        self._asset_id_spin.valueChanged.connect(self._on_asset_id_changed)

        asset_row = QtWidgets.QWidget(model_group)
        asset_row_layout = QtWidgets.QHBoxLayout(asset_row)
        asset_row_layout.setContentsMargins(0, 0, 0, 0)
        asset_row_layout.setSpacing(Sizes.SPACING_SMALL)
        asset_row_layout.addWidget(self._asset_id_spin, 1)

        pick_btn = QtWidgets.QPushButton("选择…", asset_row)
        pick_btn.setStyleSheet(ThemeManager.button_style())
        pick_btn.clicked.connect(self._pick_asset_id)
        asset_row_layout.addWidget(pick_btn)

        clear_btn = QtWidgets.QPushButton("清除", asset_row)
        clear_btn.setStyleSheet(ThemeManager.button_style())
        clear_btn.clicked.connect(self._clear_asset_id)
        asset_row_layout.addWidget(clear_btn)

        model_form.addRow("资源ID", asset_row)

        model_hint = QtWidgets.QLabel("资源ID=0 表示未设置模型。", model_group)
        model_hint.setStyleSheet(f"color: {Colors.TEXT_HINT};")
        model_form.addRow("", model_hint)

        inspector_layout.addWidget(model_group)

        # Group 2: Transform
        transform_group = QtWidgets.QGroupBox("变换 (Transform)", self._inspector_container)
        transform_form = QtWidgets.QFormLayout(transform_group)
        transform_form.setContentsMargins(
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
        )
        transform_form.setHorizontalSpacing(Sizes.SPACING_MEDIUM)
        transform_form.setVerticalSpacing(Sizes.SPACING_MEDIUM)

        self._parent_combo = QtWidgets.QComboBox(transform_group)
        self._parent_combo.setStyleSheet(ThemeManager.combo_box_style())
        self._parent_combo.currentIndexChanged.connect(self._on_parent_socket_changed)
        transform_form.addRow("父挂接点", self._parent_combo)

        self._lock_switch = ToggleSwitch(transform_group)
        self._lock_switch.toggled.connect(self._on_transform_lock_toggled)
        transform_form.addRow("锁定变换", self._lock_switch)

        self._pos_editor = Vector3Editor(
            minimum=-10000.0,
            maximum=10000.0,
            decimals=2,
            single_step=0.1,
            parent=transform_group,
        )
        self._pos_editor.value_changed.connect(self._on_transform_changed)
        transform_form.addRow("位置 Position", self._pos_editor)

        self._rot_editor = Vector3Editor(
            minimum=-360.0,
            maximum=360.0,
            decimals=2,
            single_step=1.0,
            parent=transform_group,
        )
        self._rot_editor.value_changed.connect(self._on_transform_changed)
        transform_form.addRow("旋转 Rotation", self._rot_editor)

        self._scale_editor = Vector3Editor(
            minimum=0.0,
            maximum=1000.0,
            decimals=2,
            single_step=0.1,
            parent=transform_group,
        )
        self._scale_editor.value_changed.connect(self._on_transform_changed)
        transform_form.addRow("缩放 Scale", self._scale_editor)

        inspector_layout.addWidget(transform_group)

        # Group 3: Physics
        physics_group = QtWidgets.QGroupBox("原生碰撞 (Physics)", self._inspector_container)
        physics_form = QtWidgets.QFormLayout(physics_group)
        physics_form.setContentsMargins(
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
        )
        physics_form.setHorizontalSpacing(Sizes.SPACING_MEDIUM)
        physics_form.setVerticalSpacing(Sizes.SPACING_MEDIUM)

        self._collision_switch = ToggleSwitch(physics_group)
        self._collision_switch.toggled.connect(self._on_physics_changed)
        physics_form.addRow("启用碰撞", self._collision_switch)

        self._climbable_switch = ToggleSwitch(physics_group)
        self._climbable_switch.toggled.connect(self._on_physics_changed)
        physics_form.addRow("是否可攀爬", self._climbable_switch)

        self._preview_switch = ToggleSwitch(physics_group)
        self._preview_switch.toggled.connect(self._on_physics_changed)
        physics_form.addRow("碰撞预览", self._preview_switch)

        inspector_layout.addWidget(physics_group)

        right_layout.addWidget(self._inspector_container, 1)

        splitter.addWidget(left_root)
        splitter.addWidget(right_root)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([360, 620])

        self._refresh_inspector_enabled_state()

    # ------------------------------------------------------------------ Data normalize

    @staticmethod
    def _normalize_decoration(raw: dict[str, object]) -> dict[str, object]:
        instance_id = _safe_str(raw.get("instanceId") or raw.get("id"))
        display_name = _safe_str(raw.get("displayName") or raw.get("name") or instance_id)

        is_visible = _safe_bool(raw.get("isVisible"), True)
        asset_id = _safe_int(raw.get("assetId"), 0)
        parent_id = _safe_str(raw.get("parentId") or ROOT_SOCKET_NAME) or ROOT_SOCKET_NAME

        transform_raw = raw.get("transform")
        transform = transform_raw if isinstance(transform_raw, dict) else {}
        pos = _safe_vector3_dict(transform.get("pos"), default=(0.0, 0.0, 0.0))
        rot = _safe_vector3_dict(transform.get("rot"), default=(0.0, 0.0, 0.0))
        scale = _safe_vector3_dict(transform.get("scale"), default=(1.0, 1.0, 1.0))
        locked = _safe_bool(transform.get("isLocked"), False)

        physics_raw = raw.get("physics")
        physics = physics_raw if isinstance(physics_raw, dict) else {}
        enable_collision = _safe_bool(physics.get("enableCollision"), True)
        is_climbable = _safe_bool(physics.get("isClimbable"), True)
        show_preview = _safe_bool(physics.get("showPreview"), False)

        return {
            "instanceId": instance_id,
            "displayName": display_name,
            "isVisible": is_visible,
            "assetId": asset_id,
            "parentId": parent_id,
            "transform": {
                "pos": pos,
                "rot": rot,
                "scale": scale,
                "isLocked": locked,
            },
            "physics": {
                "enableCollision": enable_collision,
                "isClimbable": is_climbable,
                "showPreview": show_preview,
            },
        }

    # ------------------------------------------------------------------ List helpers

    def _populate_list(self) -> None:
        self._updating_list = True
        self._list_widget.clear()

        for deco in self._decorations:
            item = self._build_list_item(deco)
            self._list_widget.addItem(item)

        self._updating_list = False
        has_any = len(self._decorations) > 0
        self._duplicate_btn.setEnabled(has_any)
        self._remove_btn.setEnabled(has_any)

        if has_any:
            self._list_widget.setCurrentRow(0)
        else:
            self._selected_index = -1
            self._refresh_inspector_enabled_state()

    def _build_list_item(self, deco: dict[str, object]) -> QtWidgets.QListWidgetItem:
        display_name = _safe_str(deco.get("displayName")) or "(未命名装饰物)"
        asset_id = _safe_int(deco.get("assetId"), 0)
        is_visible = _safe_bool(deco.get("isVisible"), True)
        text = f"{display_name}  (ID:{asset_id})"
        item = QtWidgets.QListWidgetItem(text)
        item.setFlags(
            item.flags()
            | QtCore.Qt.ItemFlag.ItemIsUserCheckable
            | QtCore.Qt.ItemFlag.ItemIsSelectable
            | QtCore.Qt.ItemFlag.ItemIsEnabled
        )
        item.setCheckState(
            QtCore.Qt.CheckState.Checked if is_visible else QtCore.Qt.CheckState.Unchecked
        )
        item.setData(QtCore.Qt.ItemDataRole.UserRole, _safe_str(deco.get("instanceId")))
        return item

    def _refresh_list_item_text(self, index: int) -> None:
        if not (0 <= index < len(self._decorations)):
            return
        item = self._list_widget.item(index)
        if item is None:
            return
        deco = self._decorations[index]
        display_name = _safe_str(deco.get("displayName")) or "(未命名装饰物)"
        asset_id = _safe_int(deco.get("assetId"), 0)
        item.setText(f"{display_name}  (ID:{asset_id})")

    # ------------------------------------------------------------------ Selection / sync

    def _on_selection_changed(self, row: int) -> None:
        if self._updating_ui:
            return
        self._selected_index = int(row)
        self._load_selected_to_inspector()

    def _on_item_changed(self, item: QtWidgets.QListWidgetItem) -> None:
        if self._updating_list:
            return
        row = self._list_widget.row(item)
        if not (0 <= row < len(self._decorations)):
            return
        self._decorations[row]["isVisible"] = (
            item.checkState() == QtCore.Qt.CheckState.Checked
        )
        if row == self._selected_index:
            self._load_selected_to_inspector()

    def _refresh_inspector_enabled_state(self) -> None:
        has_selection = 0 <= self._selected_index < len(self._decorations)
        self._empty_hint.setVisible(not has_selection)
        self._inspector_container.setVisible(has_selection)

        self._name_edit.setEnabled(has_selection)
        self._asset_id_spin.setEnabled(has_selection)
        self._parent_combo.setEnabled(has_selection)
        self._lock_switch.setEnabled(has_selection)
        self._pos_editor.setEnabled(has_selection)
        self._rot_editor.setEnabled(has_selection)
        self._scale_editor.setEnabled(has_selection)
        self._collision_switch.setEnabled(has_selection)
        self._climbable_switch.setEnabled(has_selection)
        self._preview_switch.setEnabled(has_selection)

    def _refresh_parent_combo(self, *, current_value: str) -> None:
        self._parent_combo.blockSignals(True)
        self._parent_combo.clear()
        options = list(self._available_sockets)
        if current_value and current_value not in options:
            options.insert(0, current_value)
        for name in options:
            self._parent_combo.addItem(name)
        if current_value:
            idx = self._parent_combo.findText(current_value)
            if idx >= 0:
                self._parent_combo.setCurrentIndex(idx)
        self._parent_combo.blockSignals(False)

    def _load_selected_to_inspector(self) -> None:
        self._updating_ui = True
        try:
            self._refresh_inspector_enabled_state()
            if not (0 <= self._selected_index < len(self._decorations)):
                self._name_edit.setText("")
                self._instance_id_label.setText("ID: -")
                return

            deco = self._decorations[self._selected_index]
            instance_id = _safe_str(deco.get("instanceId")) or "-"
            self._instance_id_label.setText(f"ID: {instance_id}")

            self._name_edit.setText(_safe_str(deco.get("displayName")))
            self._asset_id_spin.setValue(_safe_int(deco.get("assetId"), 0))

            parent_id = _safe_str(deco.get("parentId")) or ROOT_SOCKET_NAME
            self._refresh_parent_combo(current_value=parent_id)

            transform = deco.get("transform") if isinstance(deco.get("transform"), dict) else {}
            self._lock_switch.setChecked(_safe_bool(transform.get("isLocked"), False))
            self._pos_editor.set_values(_vector_list_from_dict(transform.get("pos"), (0.0, 0.0, 0.0)))
            self._rot_editor.set_values(_vector_list_from_dict(transform.get("rot"), (0.0, 0.0, 0.0)))
            self._scale_editor.set_values(_vector_list_from_dict(transform.get("scale"), (1.0, 1.0, 1.0)))
            self._apply_transform_lock_state()

            physics = deco.get("physics") if isinstance(deco.get("physics"), dict) else {}
            self._collision_switch.setChecked(_safe_bool(physics.get("enableCollision"), True))
            self._climbable_switch.setChecked(_safe_bool(physics.get("isClimbable"), True))
            self._preview_switch.setChecked(_safe_bool(physics.get("showPreview"), False))
        finally:
            self._updating_ui = False

    # ------------------------------------------------------------------ Header / menus

    def _open_header_menu(self) -> None:
        menu = QtWidgets.QMenu(self)
        menu.addAction("复制配置", self._copy_selected_decoration)
        menu.addAction("粘贴配置", self._paste_to_new_decoration)
        menu.addSeparator()
        menu.addAction("重置当前装饰物", self._reset_selected_decoration)
        menu.addSeparator()
        menu.addAction("删除当前装饰物", self._remove_decoration)
        menu.exec(QtGui.QCursor.pos())

    # ------------------------------------------------------------------ Inspector handlers

    def _on_name_edited(self, text: str) -> None:
        if self._updating_ui:
            return
        if not (0 <= self._selected_index < len(self._decorations)):
            return
        self._decorations[self._selected_index]["displayName"] = _safe_str(text)
        self._refresh_list_item_text(self._selected_index)

    def _on_asset_id_changed(self, value: int) -> None:
        if self._updating_ui:
            return
        if not (0 <= self._selected_index < len(self._decorations)):
            return
        self._decorations[self._selected_index]["assetId"] = int(value)
        self._refresh_list_item_text(self._selected_index)

    def _pick_asset_id(self) -> None:
        if not (0 <= self._selected_index < len(self._decorations)):
            return
        current = _safe_int(self._decorations[self._selected_index].get("assetId"), 0)
        picked = input_dialogs.prompt_int(
            self,
            "选择模型资产",
            "模型资源ID:",
            value=int(current),
            minimum=0,
            maximum=999_999_999,
            step=1,
        )
        if picked is None:
            return
        self._asset_id_spin.setValue(int(picked))

    def _clear_asset_id(self) -> None:
        self._asset_id_spin.setValue(0)

    def _on_parent_socket_changed(self, index: int) -> None:
        if self._updating_ui:
            return
        if not (0 <= self._selected_index < len(self._decorations)):
            return
        parent_id = _safe_str(self._parent_combo.itemText(index)) or ROOT_SOCKET_NAME
        self._decorations[self._selected_index]["parentId"] = parent_id

    def _on_transform_lock_toggled(self, checked: bool) -> None:
        if self._updating_ui:
            return
        if not (0 <= self._selected_index < len(self._decorations)):
            return
        deco = self._decorations[self._selected_index]
        transform = deco.get("transform")
        if not isinstance(transform, dict):
            transform = {}
            deco["transform"] = transform
        transform["isLocked"] = bool(checked)
        self._apply_transform_lock_state()

    def _apply_transform_lock_state(self) -> None:
        locked = bool(self._lock_switch.isChecked())
        editable = not locked
        self._pos_editor.set_editable(editable)
        self._rot_editor.set_editable(editable)
        self._scale_editor.set_editable(editable)

    def _on_transform_changed(self) -> None:
        if self._updating_ui:
            return
        if not (0 <= self._selected_index < len(self._decorations)):
            return
        deco = self._decorations[self._selected_index]
        transform = deco.get("transform")
        if not isinstance(transform, dict):
            transform = {}
            deco["transform"] = transform
        transform["pos"] = _vector_dict_from_editor(self._pos_editor)
        transform["rot"] = _vector_dict_from_editor(self._rot_editor)
        transform["scale"] = _vector_dict_from_editor(self._scale_editor)

    def _on_physics_changed(self, _checked: bool) -> None:
        if self._updating_ui:
            return
        if not (0 <= self._selected_index < len(self._decorations)):
            return
        deco = self._decorations[self._selected_index]
        physics = deco.get("physics")
        if not isinstance(physics, dict):
            physics = {}
            deco["physics"] = physics
        physics["enableCollision"] = bool(self._collision_switch.isChecked())
        physics["isClimbable"] = bool(self._climbable_switch.isChecked())
        physics["showPreview"] = bool(self._preview_switch.isChecked())

    # ------------------------------------------------------------------ CRUD

    def _next_display_name(self) -> str:
        existing = {_safe_str(d.get("displayName")) for d in self._decorations if _safe_str(d.get("displayName"))}
        idx = 1
        while True:
            candidate = f"装饰物_{idx}"
            if candidate not in existing:
                return candidate
            idx += 1

    def _new_decoration(self) -> dict[str, object]:
        return {
            "instanceId": generate_prefixed_id("deco"),
            "displayName": self._next_display_name(),
            "isVisible": True,
            "assetId": 0,
            "parentId": ROOT_SOCKET_NAME,
            "transform": {
                "pos": {"x": 0.0, "y": 0.0, "z": 0.0},
                "rot": {"x": 0.0, "y": 0.0, "z": 0.0},
                "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
                "isLocked": False,
            },
            "physics": {
                "enableCollision": True,
                "isClimbable": True,
                "showPreview": False,
            },
        }

    def _add_decoration(self) -> None:
        deco = self._new_decoration()
        self._decorations.append(deco)
        self._updating_list = True
        self._list_widget.addItem(self._build_list_item(deco))
        self._updating_list = False
        self._list_widget.setCurrentRow(len(self._decorations) - 1)
        self._duplicate_btn.setEnabled(True)
        self._remove_btn.setEnabled(True)

    def _duplicate_decoration(self) -> None:
        if not (0 <= self._selected_index < len(self._decorations)):
            return
        raw = self._decorations[self._selected_index]
        cloned = copy.deepcopy(raw)
        cloned["instanceId"] = generate_prefixed_id("deco")
        cloned["displayName"] = f"{_safe_str(raw.get('displayName'))} - 副本".strip()
        self._decorations.append(self._normalize_decoration(cloned))
        self._updating_list = True
        self._list_widget.addItem(self._build_list_item(self._decorations[-1]))
        self._updating_list = False
        self._list_widget.setCurrentRow(len(self._decorations) - 1)

    def _remove_decoration(self) -> None:
        if not (0 <= self._selected_index < len(self._decorations)):
            return
        deco = self._decorations[self._selected_index]
        name = _safe_str(deco.get("displayName")) or "(未命名装饰物)"
        ok = dialog_utils.ask_yes_no_dialog(
            self,
            "确认删除",
            f"确定要删除装饰物：{name}？",
            default_yes=False,
        )
        if not ok:
            return
        self._decorations.pop(self._selected_index)
        self._list_widget.takeItem(self._selected_index)
        if self._decorations:
            next_row = min(self._selected_index, len(self._decorations) - 1)
            self._list_widget.setCurrentRow(next_row)
        else:
            self._selected_index = -1
            self._refresh_inspector_enabled_state()
            self._duplicate_btn.setEnabled(False)
            self._remove_btn.setEnabled(False)

    def _reset_selected_decoration(self) -> None:
        if not (0 <= self._selected_index < len(self._decorations)):
            return
        deco = self._decorations[self._selected_index]
        deco["assetId"] = 0
        deco["parentId"] = ROOT_SOCKET_NAME
        deco["transform"] = {
            "pos": {"x": 0.0, "y": 0.0, "z": 0.0},
            "rot": {"x": 0.0, "y": 0.0, "z": 0.0},
            "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
            "isLocked": False,
        }
        deco["physics"] = {
            "enableCollision": True,
            "isClimbable": True,
            "showPreview": False,
        }
        deco["isVisible"] = True
        self._updating_list = True
        item = self._list_widget.item(self._selected_index)
        if item is not None:
            item.setCheckState(QtCore.Qt.CheckState.Checked)
        self._updating_list = False
        self._refresh_list_item_text(self._selected_index)
        self._load_selected_to_inspector()

    # ------------------------------------------------------------------ Copy / Paste (in-dialog buffer)

    def _copy_selected_decoration(self) -> None:
        if not (0 <= self._selected_index < len(self._decorations)):
            return
        self._copied_decoration = copy.deepcopy(self._decorations[self._selected_index])

    def _paste_to_new_decoration(self) -> None:
        if self._copied_decoration is None:
            dialog_utils.show_warning_dialog(self, "提示", "当前没有可粘贴的装饰物配置，请先复制。")
            return
        cloned = copy.deepcopy(self._copied_decoration)
        cloned["instanceId"] = generate_prefixed_id("deco")
        cloned["displayName"] = f"{_safe_str(cloned.get('displayName'))} - 粘贴".strip()
        self._decorations.append(self._normalize_decoration(cloned))
        self._updating_list = True
        self._list_widget.addItem(self._build_list_item(self._decorations[-1]))
        self._updating_list = False
        self._list_widget.setCurrentRow(len(self._decorations) - 1)
        self._duplicate_btn.setEnabled(True)
        self._remove_btn.setEnabled(True)

    # ------------------------------------------------------------------ Validate / Output

    def validate(self) -> bool:
        instance_ids: list[str] = []
        for deco in self._decorations:
            instance_id = _safe_str(deco.get("instanceId"))
            name = _safe_str(deco.get("displayName"))
            if not instance_id:
                dialog_utils.show_warning_dialog(self, "提示", "存在缺少 instanceId 的装饰物。")
                return False
            if not name:
                dialog_utils.show_warning_dialog(self, "提示", "存在未命名的装饰物，请填写名称。")
                return False
            instance_ids.append(instance_id)
        if len(set(instance_ids)) != len(instance_ids):
            dialog_utils.show_warning_dialog(self, "提示", "存在重复的 instanceId，请重新生成。")
            return False
        return True

    def get_decorations(self) -> list[dict[str, object]]:
        return [dict(item) for item in self._decorations]


def generate_prefixed_id(prefix: str) -> str:
    """对话框内部使用的轻量 ID 生成（避免引入外部资源 ID 生成语义）。"""
    from app.ui.foundation.id_generator import generate_prefixed_id as _gen

    return _gen(prefix)


__all__ = ["DecorationEditorDialog"]


