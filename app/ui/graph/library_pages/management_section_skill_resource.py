from __future__ import annotations

from .management_sections_base import *
from app.ui.forms.schema_dialog import FormDialogBuilder


class SkillResourceSection(BaseManagementSection):
    """技能资源管理 Section（对应 `ManagementData.skill_resources`）。"""

    section_key = "skill_resource"
    tree_label = "✨ 技能资源管理"
    type_name = "技能资源"

    def iter_rows(self, package: ManagementPackage) -> Iterable[ManagementRowData]:
        resources_mapping = package.management.skill_resources
        if not isinstance(resources_mapping, dict):
            return

        for resource_id, payload in resources_mapping.items():
            if not isinstance(payload, dict):
                continue

            name_value = str(payload.get("resource_name", "")) or resource_id
            growth_type_value = str(payload.get("growth_type", "无条件增长"))
            max_value = float(
                payload.get(
                    "max_obtainable_value",
                    payload.get("max_value", 100.0),
                ),
            )
            referenced_skills = payload.get("referenced_skills", [])
            referenced_count = (
                len(referenced_skills) if isinstance(referenced_skills, list) else 0
            )
            description_value = str(payload.get("description", ""))

            yield ManagementRowData(
                name=name_value,
                type_name=self.type_name,
                attr1=f"增长类型: {growth_type_value}",
                attr2=f"最大值: {max_value:g}",
                attr3=f"引用技能数: {referenced_count}",
                description=description_value,
                last_modified=self._get_last_modified_text(payload),
                user_data=(self.section_key, resource_id),
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
            "resource_id": "",
            "resource_name": "",
            "growth_type": "无条件增长",
            "max_obtainable_value": 100.0,
            "recovery_rate": 5.0,
            "description": "",
        }
        if initial:
            initial_values.update(initial)

        existing_id_set = {str(value) for value in existing_ids}

        builder = FormDialogBuilder(parent_widget, title, fixed_size=(460, 420))

        resource_id_edit = builder.add_line_edit(
            "配置ID:",
            str(initial_values.get("resource_id", "")),
            "用于节点图中引用该资源",
            read_only=is_edit,
        )
        resource_name_edit = builder.add_line_edit(
            "资源名称:",
            str(initial_values.get("resource_name", "")),
            "请输入资源名称",
        )
        growth_type_combo = builder.add_combo_box(
            "增长类型:",
            ["无条件增长", "跟随技能(保留值)", "跟随技能(不保留值)"],
            current_text=str(initial_values.get("growth_type", "无条件增长")),
        )
        max_value_spin = builder.add_double_spin_box(
            "可获取最大值:",
            minimum=1.0,
            maximum=99999.0,
            value=float(initial_values.get("max_obtainable_value", 100.0)),
            decimals=0,
            single_step=1.0,
        )
        recovery_rate_spin = builder.add_double_spin_box(
            "恢复速率(/秒):",
            minimum=0.0,
            maximum=9999.0,
            value=float(initial_values.get("recovery_rate", 5.0)),
            decimals=2,
            single_step=0.5,
        )
        description_edit = builder.add_plain_text_edit(
            "描述:",
            str(initial_values.get("description", "")),
            min_height=80,
            max_height=200,
        )

        def _validate(dialog_self: QtWidgets.QDialog) -> bool:
            from app.ui.foundation import dialog_utils

            resource_id_text = resource_id_edit.text().strip()
            if not resource_id_text:
                dialog_utils.show_warning_dialog(
                    dialog_self,
                    "提示",
                    "配置ID 不能为空",
                )
                return False
            if not is_edit and resource_id_text in existing_id_set:
                dialog_utils.show_warning_dialog(
                    dialog_self,
                    "提示",
                    "该配置ID 已存在",
                )
                return False
            if not resource_name_edit.text().strip():
                dialog_utils.show_warning_dialog(
                    dialog_self,
                    "提示",
                    "请输入资源名称",
                )
                return False
            return True

        builder.dialog.validate = types.MethodType(_validate, builder.dialog)

        if not builder.exec():
            return None

        return {
            "resource_id": resource_id_edit.text().strip(),
            "resource_name": resource_name_edit.text().strip(),
            "growth_type": str(growth_type_combo.currentText()),
            "max_obtainable_value": float(max_value_spin.value()),
            "recovery_rate": float(recovery_rate_spin.value()),
            "description": description_edit.toPlainText().strip(),
        }

    def create_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
    ) -> bool:
        _ = parent_widget

        resources_mapping = package.management.skill_resources
        if not isinstance(resources_mapping, dict):
            resources_mapping = {}
            package.management.skill_resources = resources_mapping

        existing_ids = set(resources_mapping.keys())
        resource_id_value = generate_prefixed_id("skill_resource")
        while resource_id_value in existing_ids:
            resource_id_value = generate_prefixed_id("skill_resource")

        default_index = len(resources_mapping) + 1
        resource_name_value = f"技能资源{default_index}"

        resource_config = SkillResourceConfig(
            resource_id=resource_id_value,
            resource_name=resource_name_value,
        )
        payload = resource_config.serialize()
        payload["growth_type"] = "无条件增长"
        payload["max_obtainable_value"] = 100.0
        payload["recovery_rate"] = 5.0
        payload["max_value"] = 100.0
        payload["description"] = ""
        resources_mapping[resource_config.resource_id] = payload
        return True

    def edit_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
    ) -> bool:
        resources_mapping = package.management.skill_resources
        if not isinstance(resources_mapping, dict):
            return False

        payload = resources_mapping.get(item_id)
        if not isinstance(payload, dict):
            return False

        initial_values = {
            "resource_id": item_id,
            "resource_name": payload.get("resource_name", ""),
            "growth_type": payload.get("growth_type", "无条件增长"),
            "max_obtainable_value": payload.get(
                "max_obtainable_value",
                payload.get("max_value", 100.0),
            ),
            "recovery_rate": payload.get("recovery_rate", 5.0),
            "description": payload.get("description", ""),
        }
        existing_ids: Sequence[str] = list(resources_mapping.keys())
        dialog_data = self._build_form(
            parent_widget,
            title="编辑技能资源",
            initial=initial_values,
            is_edit=True,
            existing_ids=existing_ids,
        )
        if dialog_data is None:
            return False

        payload["resource_name"] = dialog_data["resource_name"]
        payload["growth_type"] = dialog_data["growth_type"]
        payload["max_obtainable_value"] = dialog_data["max_obtainable_value"]
        payload["recovery_rate"] = dialog_data["recovery_rate"]
        payload["max_value"] = dialog_data["max_obtainable_value"]
        payload["description"] = dialog_data["description"]
        return True

    def delete_item(self, package: ManagementPackage, item_id: str) -> bool:
        resources_mapping = package.management.skill_resources
        if not isinstance(resources_mapping, dict):
            return False
        if item_id not in resources_mapping:
            return False
        del resources_mapping[item_id]
        return True

    def build_inline_edit_form(
        self,
        *,
        parent: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
        on_changed: Callable[[], None],
    ) -> Optional[Tuple[str, str, Callable[[QtWidgets.QFormLayout], None]]]:
        """在右侧属性面板中编辑技能资源的全部主要字段。"""
        resources_mapping = getattr(package.management, "skill_resources", None)
        if not isinstance(resources_mapping, dict):
            return None
        resource_payload_any = resources_mapping.get(item_id)
        if not isinstance(resource_payload_any, dict):
            return None

        resource_payload = resource_payload_any

        def build_form(form_layout: QtWidgets.QFormLayout) -> None:
            resource_name_value = str(resource_payload.get("resource_name", ""))
            growth_type_value = str(resource_payload.get("growth_type", "无条件增长"))
            max_value_any = resource_payload.get(
                "max_obtainable_value",
                resource_payload.get("max_value", 100.0),
            )
            if isinstance(max_value_any, (int, float)):
                max_value = float(max_value_any)
            else:
                max_value = 100.0
            recovery_rate_any = resource_payload.get("recovery_rate", 5.0)
            if isinstance(recovery_rate_any, (int, float)):
                recovery_rate_value = float(recovery_rate_any)
            else:
                recovery_rate_value = 5.0
            description_value = str(resource_payload.get("description", ""))

            name_edit = QtWidgets.QLineEdit(resource_name_value)

            growth_type_combo = QtWidgets.QComboBox()
            growth_type_combo.addItems(["无条件增长", "跟随技能(保留值)", "跟随技能(不保留值)"])
            if growth_type_value:
                growth_type_combo.setCurrentText(growth_type_value)

            max_value_spin = QtWidgets.QDoubleSpinBox()
            max_value_spin.setRange(1.0, 99999.0)
            max_value_spin.setDecimals(0)
            max_value_spin.setSingleStep(1.0)
            max_value_spin.setValue(max_value)

            recovery_rate_spin = QtWidgets.QDoubleSpinBox()
            recovery_rate_spin.setRange(0.0, 9999.0)
            recovery_rate_spin.setDecimals(2)
            recovery_rate_spin.setSingleStep(0.5)
            recovery_rate_spin.setValue(recovery_rate_value)

            description_edit = QtWidgets.QTextEdit()
            description_edit.setPlainText(description_value)
            description_edit.setMinimumHeight(80)
            description_edit.setMaximumHeight(200)

            def apply_changes() -> None:
                normalized_name = name_edit.text().strip()
                if normalized_name:
                    resource_payload["resource_name"] = normalized_name
                else:
                    resource_payload["resource_name"] = item_id
                resource_payload["growth_type"] = str(growth_type_combo.currentText())
                resource_payload["max_obtainable_value"] = float(max_value_spin.value())
                resource_payload["recovery_rate"] = float(recovery_rate_spin.value())
                resource_payload["max_value"] = float(max_value_spin.value())
                resource_payload["description"] = description_edit.toPlainText().strip()
                on_changed()

            name_edit.editingFinished.connect(apply_changes)
            growth_type_combo.currentIndexChanged.connect(lambda _index: apply_changes())
            max_value_spin.editingFinished.connect(apply_changes)
            recovery_rate_spin.editingFinished.connect(apply_changes)
            description_edit.textChanged.connect(lambda: apply_changes())

            form_layout.addRow("资源ID", QtWidgets.QLabel(item_id))
            form_layout.addRow("资源名称", name_edit)
            form_layout.addRow("增长类型", growth_type_combo)
            form_layout.addRow("可获取最大值", max_value_spin)
            form_layout.addRow("恢复速率(/秒)", recovery_rate_spin)
            form_layout.addRow("描述", description_edit)

        display_name_value = str(resource_payload.get("resource_name", "")).strip()
        display_name = display_name_value or item_id

        title = f"技能资源详情：{display_name}"
        description = "在右侧直接修改技能资源名称与描述，修改会立即保存到当前视图。"
        return title, description, build_form



