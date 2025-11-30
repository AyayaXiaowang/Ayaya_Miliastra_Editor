from __future__ import annotations

from .management_sections_base import *


class VariableSection(BaseManagementSection):
    """关卡变量管理 Section（对应 `ManagementData.level_variables`）。"""

    section_key = "variable"
    tree_label = "📊 关卡变量"
    type_name = "关卡变量"

    def iter_rows(self, package: ManagementPackage) -> Iterable[ManagementRowData]:
        for variable_id, variable_data in package.management.level_variables.items():
            name_value = str(variable_data.get("variable_name", ""))
            data_type_value = str(variable_data.get("data_type", ""))
            default_value = variable_data.get("default_value", "")
            is_global_value = bool(variable_data.get("is_global", True))
            yield ManagementRowData(
                name=name_value or variable_id,
                type_name=self.type_name,
                attr1=f"类型: {data_type_value}",
                attr2=f"默认值: {default_value}",
                attr3=f"全局: {'是' if is_global_value else '否'}",
                description="",
                last_modified=self._get_last_modified_text(variable_data),
                user_data=(self.section_key, variable_id),
            )

    def _build_form(
        self,
        parent_widget: QtWidgets.QWidget,
        *,
        title: str,
        initial: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        from engine.graph.models.entity_templates import get_all_variable_types

        all_types = list(get_all_variable_types())
        if not all_types:
            all_types = ["整数", "浮点数", "字符串", "布尔值"]

        initial_values: Dict[str, Any] = {
            "variable_name": "",
            "data_type": all_types[0],
            "default_value": "",
            "is_global": True,
        }
        if initial:
            initial_values.update(initial)

        builder = FormDialogBuilder(parent_widget, title, fixed_size=(420, 260))

        name_edit = builder.add_line_edit(
            "变量名:",
            str(initial_values.get("variable_name", "")),
            "请输入变量名称",
        )
        type_combo = builder.add_combo_box("数据类型:", all_types, str(initial_values.get("data_type", "")))
        default_edit = builder.add_line_edit(
            "默认值:",
            str(initial_values.get("default_value", "")),
            "请输入默认值",
        )
        global_check = builder.add_check_box(
            "全局可访问",
            bool(initial_values.get("is_global", True)),
        )

        def _validate(dialog_self: QtWidgets.QDialog) -> bool:
            if not name_edit.text().strip():
                from ui.foundation import dialog_utils

                dialog_utils.show_warning_dialog(
                    dialog_self,
                    "提示",
                    "请输入变量名",
                )
                return False
            return True

        builder.dialog.validate = types.MethodType(_validate, builder.dialog)

        if not builder.exec():
            return None

        return {
            "variable_name": name_edit.text().strip(),
            "data_type": str(type_combo.currentText()),
            "default_value": default_edit.text(),
            "is_global": bool(global_check.isChecked()),
        }

    def create_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
    ) -> bool:
        _ = parent_widget

        variables_mapping = package.management.level_variables
        if not isinstance(variables_mapping, dict):
            variables_mapping = {}
            package.management.level_variables = variables_mapping

        variable_id = generate_prefixed_id("var")
        while variable_id in variables_mapping:
            variable_id = generate_prefixed_id("var")

        from engine.graph.models.entity_templates import get_all_variable_types

        all_types = list(get_all_variable_types())
        if not all_types:
            all_types = ["整数", "浮点数", "字符串", "布尔值"]
        default_type = all_types[0]

        default_index = len(variables_mapping) + 1
        variable_name = f"变量{default_index}"

        variable_config = LevelVariableConfig(
            variable_id=variable_id,
            variable_name=variable_name,
            data_type=default_type,
        )
        serialized = variable_config.serialize()
        serialized["default_value"] = ""
        serialized["is_global"] = True
        variables_mapping[variable_id] = serialized
        return True

    def edit_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
    ) -> bool:
        variable_data = package.management.level_variables.get(item_id)
        if variable_data is None:
            return False

        initial_values = {
            "variable_name": variable_data.get("variable_name", ""),
            "data_type": variable_data.get("data_type", ""),
            "default_value": variable_data.get("default_value", ""),
            "is_global": bool(variable_data.get("is_global", True)),
        }
        dialog_data = self._build_form(
            parent_widget,
            title="编辑变量",
            initial=initial_values,
        )
        if dialog_data is None:
            return False

        variable_data["variable_name"] = dialog_data["variable_name"]
        variable_data["data_type"] = dialog_data["data_type"]
        variable_data["default_value"] = dialog_data["default_value"]
        variable_data["is_global"] = dialog_data["is_global"]
        return True

    def delete_item(self, package: ManagementPackage, item_id: str) -> bool:
        if item_id not in package.management.level_variables:
            return False
        del package.management.level_variables[item_id]
        return True

    def build_inline_edit_form(
        self,
        *,
        parent: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
        on_changed: Callable[[], None],
    ) -> Optional[Tuple[str, str, Callable[[QtWidgets.QFormLayout], None]]]:
        """在右侧属性面板中编辑关卡变量的全部主要字段。"""
        variables_mapping = getattr(package.management, "level_variables", None)
        if not isinstance(variables_mapping, dict):
            return None
        variable_payload_any = variables_mapping.get(item_id)
        if not isinstance(variable_payload_any, dict):
            return None

        variable_payload = variable_payload_any

        def build_form(form_layout: QtWidgets.QFormLayout) -> None:
            from engine.graph.models.entity_templates import get_all_variable_types

            all_types = list(get_all_variable_types())
            if not all_types:
                all_types = ["整数", "浮点数", "字符串", "布尔值"]

            variable_name_value = str(variable_payload.get("variable_name", ""))
            data_type_value = str(variable_payload.get("data_type", ""))
            default_value_text = str(variable_payload.get("default_value", ""))
            is_global_value = bool(variable_payload.get("is_global", True))

            name_edit = QtWidgets.QLineEdit(variable_name_value)
            data_type_combo = QtWidgets.QComboBox()
            data_type_combo.addItems(all_types)
            if data_type_value and data_type_value in all_types:
                data_type_combo.setCurrentText(data_type_value)
            else:
                data_type_combo.setCurrentText(all_types[0])
            default_edit = QtWidgets.QLineEdit(default_value_text)
            is_global_checkbox = QtWidgets.QCheckBox("全局可访问")
            is_global_checkbox.setChecked(is_global_value)

            def apply_changes() -> None:
                normalized_name = name_edit.text().strip()
                if normalized_name:
                    variable_payload["variable_name"] = normalized_name
                else:
                    variable_payload["variable_name"] = item_id

                variable_payload["data_type"] = str(data_type_combo.currentText())
                variable_payload["default_value"] = default_edit.text()
                variable_payload["is_global"] = bool(is_global_checkbox.isChecked())
                on_changed()

            name_edit.editingFinished.connect(apply_changes)
            data_type_combo.currentIndexChanged.connect(lambda _index: apply_changes())
            default_edit.editingFinished.connect(apply_changes)
            is_global_checkbox.stateChanged.connect(lambda _state: apply_changes())

            form_layout.addRow("变量ID", QtWidgets.QLabel(item_id))
            form_layout.addRow("变量名", name_edit)
            form_layout.addRow("数据类型", data_type_combo)
            form_layout.addRow("默认值", default_edit)
            form_layout.addRow("", is_global_checkbox)

        display_name_value = str(variable_payload.get("variable_name", "")).strip()
        display_name = display_name_value or item_id

        title = f"关卡变量详情：{display_name}"
        description = "在右侧直接修改变量名称、默认值与是否全局可访问，修改会立即保存到当前视图。"
        return title, description, build_form



