from __future__ import annotations

from .management_sections_base import *


class LightSourcesSection(BaseManagementSection):
    """光源管理 Section（对应 `ManagementData.light_sources`）。"""

    section_key = "light_sources"
    tree_label = "💡 光源管理"
    type_name = "光源"

    def iter_rows(self, package: ManagementPackage) -> Iterable[ManagementRowData]:
        for light_id, light_payload in package.management.light_sources.items():
            light_name_value = str(light_payload.get("light_name", ""))
            light_type_value = str(light_payload.get("light_type", "point"))
            color_value = str(light_payload.get("color", "#FFFFFF"))
            intensity_value = light_payload.get("intensity", 1.0)
            range_value = light_payload.get("range_distance", 10.0)
            description_value = str(light_payload.get("description", ""))

            yield ManagementRowData(
                name=light_name_value or light_id,
                type_name=self.type_name,
                attr1=f"类型: {light_type_value}",
                attr2=f"颜色: {color_value}",
                attr3=f"强度: {intensity_value}，半径: {range_value}",
                description=description_value,
                last_modified=self._get_last_modified_text(light_payload),
                user_data=(self.section_key, light_id),
            )

    @staticmethod
    def _normalize_position(raw_position: Any) -> Tuple[float, float, float]:
        if not isinstance(raw_position, (list, tuple)):
            return 0.0, 0.0, 0.0
        extended = list(raw_position) + [0.0, 0.0, 0.0]
        return float(extended[0]), float(extended[1]), float(extended[2])

    def _build_form(
        self,
        parent_widget: QtWidgets.QWidget,
        *,
        title: str,
        is_edit: bool,
        existing_ids: Sequence[str],
        initial: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        initial_values: Dict[str, Any] = {
            "light_id": "",
            "light_name": "",
            "light_type": "point",
            "color": "#FFFFFF",
            "intensity": 1.0,
            "range_distance": 10.0,
            "cast_shadows": True,
            "pos_x": 0.0,
            "pos_y": 0.0,
            "pos_z": 0.0,
            "description": "",
        }
        if initial:
            initial_values.update(initial)

        builder = FormDialogBuilder(parent_widget, title, fixed_size=(480, 520))

        light_id_widget = builder.add_line_edit(
            "光源ID:",
            str(initial_values.get("light_id", "")),
            None,
            read_only=is_edit,
        )
        name_widget = builder.add_line_edit(
            "光源名称:",
            str(initial_values.get("light_name", "")),
        )
        type_widget = builder.add_combo_box(
            "光源类型:",
            ["point", "spot"],
            current_text=str(initial_values.get("light_type", "point")),
        )
        color_widget = builder.add_color_picker(
            "颜色:",
            str(initial_values.get("color", "#FFFFFF")),
        )
        intensity_widget = builder.add_double_spin_box(
            "强度:",
            minimum=0.0,
            maximum=10.0,
            value=float(initial_values.get("intensity", 1.0)),
            decimals=2,
            single_step=0.1,
        )
        range_widget = builder.add_double_spin_box(
            "半径（照射范围）:",
            minimum=0.1,
            maximum=100.0,
            value=float(initial_values.get("range_distance", 10.0)),
            decimals=2,
            single_step=0.5,
        )
        cast_shadows_widget = builder.add_check_box(
            "投射阴影",
            bool(initial_values.get("cast_shadows", True)),
        )

        position_sequence: Sequence[float] = [
            float(initial_values.get("pos_x", 0.0)),
            float(initial_values.get("pos_y", 0.0)),
            float(initial_values.get("pos_z", 0.0)),
        ]
        pos_x_widget, pos_y_widget, pos_z_widget = builder.add_vector3_editor(
            "位置:",
            position_sequence,
        )

        description_widget = builder.add_plain_text_edit(
            "描述:",
            str(initial_values.get("description", "")),
            min_height=80,
            max_height=200,
        )

        def _validate(dialog_self: QtWidgets.QDialog) -> bool:
            from ui.foundation import dialog_utils

            light_id_text = light_id_widget.text().strip()
            if not light_id_text:
                dialog_utils.show_warning_dialog(
                    dialog_self,
                    "提示",
                    "光源 ID 不能为空",
                )
                return False
            if (not is_edit) and light_id_text in existing_ids:
                dialog_utils.show_warning_dialog(
                    dialog_self,
                    "提示",
                    "该光源 ID 已存在",
                )
                return False
            return True

        builder.dialog.validate = types.MethodType(_validate, builder.dialog)

        if not builder.exec():
            return None

        return {
            "light_id": light_id_widget.text().strip(),
            "light_name": name_widget.text().strip(),
            "light_type": str(type_widget.currentText()),
            "color": color_widget.text().strip(),
            "intensity": float(intensity_widget.value()),
            "range_distance": float(range_widget.value()),
            "cast_shadows": bool(cast_shadows_widget.isChecked()),
            "pos_x": float(pos_x_widget.value()),
            "pos_y": float(pos_y_widget.value()),
            "pos_z": float(pos_z_widget.value()),
            "description": description_widget.toPlainText().strip(),
        }

    def create_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
    ) -> bool:
        _ = parent_widget

        lights_mapping = package.management.light_sources
        if not isinstance(lights_mapping, dict):
            lights_mapping = {}
            package.management.light_sources = lights_mapping

        existing_ids = set(lights_mapping.keys())
        light_id_value = generate_prefixed_id("light")
        while light_id_value in existing_ids:
            light_id_value = generate_prefixed_id("light")

        default_index = len(lights_mapping) + 1
        light_name = f"光源{default_index}"

        light_config = LightSourceConfig(
            light_id=light_id_value,
            light_name=light_name,
        )
        lights_mapping[light_id_value] = light_config.serialize()
        return True

    def edit_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
    ) -> bool:
        light_payload = package.management.light_sources.get(item_id)
        if light_payload is None:
            return False

        pos_x_value, pos_y_value, pos_z_value = self._normalize_position(
            light_payload.get("position", [0.0, 0.0, 0.0]),
        )
        initial_values = {
            "light_id": item_id,
            "light_name": light_payload.get("light_name", ""),
            "light_type": light_payload.get("light_type", "point"),
            "color": light_payload.get("color", "#FFFFFF"),
            "intensity": light_payload.get("intensity", 1.0),
            "range_distance": light_payload.get("range_distance", 10.0),
            "cast_shadows": light_payload.get("cast_shadows", True),
            "pos_x": pos_x_value,
            "pos_y": pos_y_value,
            "pos_z": pos_z_value,
            "description": light_payload.get("description", ""),
        }
        existing_ids = list(package.management.light_sources.keys())
        dialog_data = self._build_form(
            parent_widget,
            title="编辑光源",
            is_edit=True,
            existing_ids=existing_ids,
            initial=initial_values,
        )
        if dialog_data is None:
            return False

        light_payload["light_name"] = dialog_data["light_name"]
        light_payload["light_type"] = dialog_data["light_type"]
        light_payload["color"] = dialog_data["color"]
        light_payload["intensity"] = dialog_data["intensity"]
        light_payload["range_distance"] = dialog_data["range_distance"]
        light_payload["cast_shadows"] = dialog_data["cast_shadows"]
        light_payload["position"] = [
            float(dialog_data["pos_x"]),
            float(dialog_data["pos_y"]),
            float(dialog_data["pos_z"]),
        ]
        light_payload["description"] = dialog_data["description"]
        return True

    def delete_item(self, package: ManagementPackage, item_id: str) -> bool:
        if item_id not in package.management.light_sources:
            return False
        package.management.light_sources.pop(item_id, None)
        return True

    def build_inline_edit_form(
        self,
        *,
        parent: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
        on_changed: Callable[[], None],
    ) -> Optional[Tuple[str, str, Callable[[QtWidgets.QFormLayout], None]]]:
        """在右侧属性面板中编辑光源的全部主要字段。"""
        lights_mapping = getattr(package.management, "light_sources", None)
        if not isinstance(lights_mapping, dict):
            return None
        light_payload_any = lights_mapping.get(item_id)
        if not isinstance(light_payload_any, dict):
            return None

        light_payload = light_payload_any

        def build_form(form_layout: QtWidgets.QFormLayout) -> None:
            light_name_value = str(light_payload.get("light_name", ""))
            light_type_value = str(light_payload.get("light_type", "point"))
            color_value = str(light_payload.get("color", "#FFFFFF"))
            intensity_any = light_payload.get("intensity", 1.0)
            if isinstance(intensity_any, (int, float)):
                intensity_value = float(intensity_any)
            else:
                intensity_value = 1.0
            range_any = light_payload.get("range_distance", 10.0)
            if isinstance(range_any, (int, float)):
                range_value = float(range_any)
            else:
                range_value = 10.0
            cast_shadows_value = bool(light_payload.get("cast_shadows", True))

            pos_x_value, pos_y_value, pos_z_value = self._normalize_position(
                light_payload.get("position", [0.0, 0.0, 0.0]),
            )
            description_value = str(light_payload.get("description", ""))

            name_edit = QtWidgets.QLineEdit(light_name_value)

            type_widget = QtWidgets.QComboBox()
            type_widget.addItems(["point", "spot"])
            if light_type_value:
                type_widget.setCurrentText(light_type_value)

            color_edit = QtWidgets.QLineEdit(color_value)

            intensity_spin = QtWidgets.QDoubleSpinBox()
            intensity_spin.setRange(0.0, 10.0)
            intensity_spin.setDecimals(2)
            intensity_spin.setSingleStep(0.1)
            intensity_spin.setValue(intensity_value)

            range_spin = QtWidgets.QDoubleSpinBox()
            range_spin.setRange(0.1, 100.0)
            range_spin.setDecimals(2)
            range_spin.setSingleStep(0.5)
            range_spin.setValue(range_value)

            cast_shadows_widget = QtWidgets.QCheckBox("投射阴影")
            cast_shadows_widget.setChecked(cast_shadows_value)

            pos_x_widget = QtWidgets.QDoubleSpinBox()
            pos_y_widget = QtWidgets.QDoubleSpinBox()
            pos_z_widget = QtWidgets.QDoubleSpinBox()
            for editor in (pos_x_widget, pos_y_widget, pos_z_widget):
                editor.setRange(-99999.0, 99999.0)
                editor.setDecimals(2)
            pos_x_widget.setValue(pos_x_value)
            pos_y_widget.setValue(pos_y_value)
            pos_z_widget.setValue(pos_z_value)

            description_edit = QtWidgets.QTextEdit()
            description_edit.setPlainText(description_value)
            description_edit.setMinimumHeight(80)
            description_edit.setMaximumHeight(200)

            def apply_changes() -> None:
                normalized_name = name_edit.text().strip()
                if normalized_name:
                    light_payload["light_name"] = normalized_name
                else:
                    light_payload["light_name"] = item_id
                light_payload["light_type"] = str(type_widget.currentText())
                light_payload["color"] = color_edit.text().strip() or "#FFFFFF"
                light_payload["intensity"] = float(intensity_spin.value())
                light_payload["range_distance"] = float(range_spin.value())
                light_payload["cast_shadows"] = bool(cast_shadows_widget.isChecked())
                light_payload["position"] = [
                    float(pos_x_widget.value()),
                    float(pos_y_widget.value()),
                    float(pos_z_widget.value()),
                ]
                light_payload["description"] = description_edit.toPlainText().strip()
                on_changed()

            name_edit.editingFinished.connect(apply_changes)
            type_widget.currentIndexChanged.connect(lambda _index: apply_changes())
            color_edit.editingFinished.connect(apply_changes)
            intensity_spin.editingFinished.connect(apply_changes)
            range_spin.editingFinished.connect(apply_changes)
            cast_shadows_widget.stateChanged.connect(lambda _state: apply_changes())
            pos_x_widget.editingFinished.connect(apply_changes)
            pos_y_widget.editingFinished.connect(apply_changes)
            pos_z_widget.editingFinished.connect(apply_changes)
            description_edit.textChanged.connect(lambda: apply_changes())

            pos_container = QtWidgets.QWidget()
            pos_layout = QtWidgets.QHBoxLayout(pos_container)
            pos_layout.setContentsMargins(0, 0, 0, 0)
            pos_layout.setSpacing(4)
            pos_layout.addWidget(pos_x_widget)
            pos_layout.addWidget(pos_y_widget)
            pos_layout.addWidget(pos_z_widget)

            form_layout.addRow("光源ID", QtWidgets.QLabel(item_id))
            form_layout.addRow("光源名称", name_edit)
            form_layout.addRow("光源类型", type_widget)
            form_layout.addRow("颜色", color_edit)
            form_layout.addRow("强度", intensity_spin)
            form_layout.addRow("半径（照射范围）", range_spin)
            form_layout.addRow("投射阴影", cast_shadows_widget)
            form_layout.addRow("位置", pos_container)
            form_layout.addRow("描述", description_edit)

        display_name_value = str(light_payload.get("light_name", "")).strip()
        display_name = display_name_value or item_id

        title = f"光源详情：{display_name}"
        description = "在右侧直接修改光源名称、类型、颜色、强度、半径、位置与描述等属性，修改会立即保存到当前视图。"
        return title, description, build_form



