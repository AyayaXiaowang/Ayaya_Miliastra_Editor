from __future__ import annotations

from .management_sections_base import *
from ui.forms.schema_dialog import FormDialogBuilder


class EquipmentDataSection(BaseManagementSection):
    """装备数据管理 Section（对应 `ManagementData.equipment_data`）。"""

    section_key = "equipment_data"
    tree_label = "⚔️ 装备数据管理"
    type_name = "装备"

    def iter_rows(self, package: ManagementPackage) -> Iterable[ManagementRowData]:
        equipment_map = package.management.equipment_data
        if not isinstance(equipment_map, dict):
            return

        for equipment_id, equipment_payload in equipment_map.items():
            if not isinstance(equipment_payload, dict):
                continue

            name_value = str(equipment_payload.get("equipment_name", "")) or equipment_id
            slot_value = str(equipment_payload.get("equipment_slot", "weapon"))
            rarity_value = str(equipment_payload.get("rarity", "common"))
            level_requirement = int(equipment_payload.get("level_requirement", 1))
            description_value = str(equipment_payload.get("description", ""))

            attr1_text = f"槽位: {slot_value}"
            attr2_text = f"稀有度: {rarity_value}"
            attr3_text = f"等级需求: {level_requirement}"

            yield ManagementRowData(
                name=name_value,
                type_name=self.type_name,
                attr1=attr1_text,
                attr2=attr2_text,
                attr3=attr3_text,
                description=description_value,
                last_modified=self._get_last_modified_text(equipment_payload),
                user_data=(self.section_key, equipment_id),
            )

    def _build_form(
        self,
        parent_widget: QtWidgets.QWidget,
        *,
        title: str,
        initial: Optional[Dict[str, Any]] = None,
        is_edit: bool,
        existing_ids: Sequence[str],
    ) -> Optional[Dict[str, Any]]:
        initial_values: Dict[str, Any] = {
            "equipment_id": "",
            "equipment_name": "",
            "equipment_slot": "weapon",
            "rarity": "common",
            "level_requirement": 1,
            "icon": "",
            "model": "",
            "description": "",
        }
        if initial:
            initial_values.update(initial)

        existing_id_set = {str(value) for value in existing_ids}

        builder = FormDialogBuilder(parent_widget, title, fixed_size=(480, 460))

        equipment_id_edit = builder.add_line_edit(
            "装备ID:",
            str(initial_values.get("equipment_id", "")),
            "唯一标识，例如 sword_001",
            read_only=is_edit,
        )
        if is_edit:
            equipment_id_edit.setStyleSheet(ThemeManager.readonly_input_style())

        name_edit = builder.add_line_edit(
            "装备名称:",
            str(initial_values.get("equipment_name", "")),
        )
        slot_combo = builder.add_combo_box(
            "装备槽位:",
            ["weapon", "head", "body", "legs", "feet", "shield", "accessory"],
            current_text=str(initial_values.get("equipment_slot", "weapon")),
        )
        rarity_combo = builder.add_combo_box(
            "稀有度:",
            ["common", "uncommon", "rare", "epic", "legendary"],
            current_text=str(initial_values.get("rarity", "common")),
        )
        level_spin = builder.add_spin_box(
            "等级需求:",
            minimum=1,
            maximum=120,
            value=int(initial_values.get("level_requirement", 1)),
        )
        icon_edit = builder.add_line_edit(
            "图标:",
            str(initial_values.get("icon", "")),
        )
        model_edit = builder.add_line_edit(
            "模型:",
            str(initial_values.get("model", "")),
        )
        description_edit = builder.add_plain_text_edit(
            "描述:",
            str(initial_values.get("description", "")),
            min_height=80,
            max_height=200,
        )

        def _validate(dialog_self: QtWidgets.QDialog) -> bool:
            from ui.foundation import dialog_utils

            equipment_id_text = equipment_id_edit.text().strip()
            if not equipment_id_text:
                dialog_utils.show_warning_dialog(
                    dialog_self,
                    "提示",
                    "请输入装备ID",
                )
                return False
            if not is_edit and equipment_id_text in existing_id_set:
                dialog_utils.show_warning_dialog(
                    dialog_self,
                    "提示",
                    "该装备ID 已存在",
                )
                return False
            if not name_edit.text().strip():
                dialog_utils.show_warning_dialog(
                    dialog_self,
                    "提示",
                    "请输入装备名称",
                )
                return False
            return True

        builder.dialog.validate = types.MethodType(_validate, builder.dialog)

        if not builder.exec():
            return None

        return {
            "equipment_id": equipment_id_edit.text().strip(),
            "equipment_name": name_edit.text().strip(),
            "equipment_slot": str(slot_combo.currentText()),
            "rarity": str(rarity_combo.currentText()),
            "level_requirement": int(level_spin.value()),
            "icon": icon_edit.text().strip(),
            "model": model_edit.text().strip(),
            "description": description_edit.toPlainText().strip(),
        }

    def create_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
    ) -> bool:
        _ = parent_widget

        equipment_map = package.management.equipment_data
        if not isinstance(equipment_map, dict):
            equipment_map = {}
            package.management.equipment_data = equipment_map

        existing_ids = set(equipment_map.keys())
        equipment_id_value = generate_prefixed_id("equipment")
        while equipment_id_value in existing_ids:
            equipment_id_value = generate_prefixed_id("equipment")

        default_index = len(equipment_map) + 1
        equipment_name_value = f"装备{default_index}"

        equipment_config = EquipmentDataConfig(
            equipment_id=equipment_id_value,
            equipment_name=equipment_name_value,
            equipment_slot="weapon",
        )
        payload = equipment_config.serialize()
        equipment_map[equipment_id_value] = payload
        return True

    def edit_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
    ) -> bool:
        equipment_map = package.management.equipment_data
        if not isinstance(equipment_map, dict):
            return False

        equipment_payload = equipment_map.get(item_id)
        if not isinstance(equipment_payload, dict):
            return False

        initial_values = {
            "equipment_id": item_id,
            "equipment_name": equipment_payload.get("equipment_name", ""),
            "equipment_slot": equipment_payload.get("equipment_slot", "weapon"),
            "rarity": equipment_payload.get("rarity", "common"),
            "level_requirement": equipment_payload.get("level_requirement", 1),
            "icon": equipment_payload.get("icon", ""),
            "model": equipment_payload.get("model", ""),
            "description": equipment_payload.get("description", ""),
        }
        existing_ids: Sequence[str] = list(equipment_map.keys())
        dialog_data = self._build_form(
            parent_widget,
            title="编辑装备",
            initial=initial_values,
            is_edit=True,
            existing_ids=existing_ids,
        )
        if dialog_data is None:
            return False

        equipment_payload["equipment_name"] = dialog_data["equipment_name"]
        equipment_payload["equipment_slot"] = dialog_data["equipment_slot"]
        equipment_payload["rarity"] = dialog_data["rarity"]
        equipment_payload["level_requirement"] = dialog_data["level_requirement"]
        equipment_payload["icon"] = dialog_data["icon"]
        equipment_payload["model"] = dialog_data["model"]
        equipment_payload["description"] = dialog_data["description"]
        return True

    def delete_item(self, package: ManagementPackage, item_id: str) -> bool:
        equipment_map = package.management.equipment_data
        if not isinstance(equipment_map, dict):
            return False
        if item_id not in equipment_map:
            return False
        equipment_map.pop(item_id, None)
        return True

    def build_inline_edit_form(
        self,
        *,
        parent: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
        on_changed: Callable[[], None],
    ) -> Optional[Tuple[str, str, Callable[[QtWidgets.QFormLayout], None]]]:
        """在右侧属性面板中编辑装备的全部主要字段。"""
        equipment_map = getattr(package.management, "equipment_data", None)
        if not isinstance(equipment_map, dict):
            return None
        equipment_payload_any = equipment_map.get(item_id)
        if not isinstance(equipment_payload_any, dict):
            return None

        equipment_payload = equipment_payload_any

        def build_form(form_layout: QtWidgets.QFormLayout) -> None:
            equipment_name_value = str(equipment_payload.get("equipment_name", ""))
            equipment_slot_value = str(equipment_payload.get("equipment_slot", "weapon"))
            rarity_value = str(equipment_payload.get("rarity", "common"))
            level_requirement_any = equipment_payload.get("level_requirement", 1)
            if isinstance(level_requirement_any, int):
                level_requirement_value = level_requirement_any
            else:
                level_requirement_value = 1
            icon_value = str(equipment_payload.get("icon", ""))
            model_value = str(equipment_payload.get("model", ""))
            description_value = str(equipment_payload.get("description", ""))

            name_edit = QtWidgets.QLineEdit(equipment_name_value)

            slot_combo = QtWidgets.QComboBox()
            slot_combo.addItems(
                ["weapon", "head", "body", "legs", "feet", "shield", "accessory"],
            )
            if equipment_slot_value:
                slot_combo.setCurrentText(equipment_slot_value)

            rarity_combo = QtWidgets.QComboBox()
            rarity_combo.addItems(
                ["common", "uncommon", "rare", "epic", "legendary"],
            )
            if rarity_value:
                rarity_combo.setCurrentText(rarity_value)

            level_spin = QtWidgets.QSpinBox()
            level_spin.setRange(1, 120)
            level_spin.setValue(level_requirement_value)

            icon_edit = QtWidgets.QLineEdit(icon_value)
            model_edit = QtWidgets.QLineEdit(model_value)

            description_edit = QtWidgets.QTextEdit()
            description_edit.setPlainText(description_value)
            description_edit.setMinimumHeight(80)
            description_edit.setMaximumHeight(200)

            def apply_changes() -> None:
                normalized_name = name_edit.text().strip()
                if normalized_name:
                    equipment_payload["equipment_name"] = normalized_name
                else:
                    equipment_payload["equipment_name"] = item_id
                equipment_payload["equipment_slot"] = str(slot_combo.currentText())
                equipment_payload["rarity"] = str(rarity_combo.currentText())
                equipment_payload["level_requirement"] = int(level_spin.value())
                equipment_payload["icon"] = icon_edit.text().strip()
                equipment_payload["model"] = model_edit.text().strip()
                equipment_payload["description"] = description_edit.toPlainText().strip()
                on_changed()

            name_edit.editingFinished.connect(apply_changes)
            slot_combo.currentIndexChanged.connect(lambda _index: apply_changes())
            rarity_combo.currentIndexChanged.connect(lambda _index: apply_changes())
            level_spin.editingFinished.connect(apply_changes)
            icon_edit.editingFinished.connect(apply_changes)
            model_edit.editingFinished.connect(apply_changes)
            description_edit.textChanged.connect(lambda: apply_changes())

            form_layout.addRow("装备ID", QtWidgets.QLabel(item_id))
            form_layout.addRow("装备名称", name_edit)
            form_layout.addRow("装备槽位", slot_combo)
            form_layout.addRow("稀有度", rarity_combo)
            form_layout.addRow("等级需求", level_spin)
            form_layout.addRow("图标", icon_edit)
            form_layout.addRow("模型", model_edit)
            form_layout.addRow("描述", description_edit)

        display_name_value = str(equipment_payload.get("equipment_name", "")).strip()
        display_name = display_name_value or item_id

        title = f"装备数据详情：{display_name}"
        description = "在右侧直接修改装备名称与描述，修改会立即保存到当前视图。"
        return title, description, build_form



