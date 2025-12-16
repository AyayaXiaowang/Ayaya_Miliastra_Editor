"""Reusable variable edit dialogs for entity and graph scopes."""

from __future__ import annotations

from typing import Optional, Sequence

from PyQt6 import QtWidgets

from engine.graph.models.entity_templates import get_all_variable_types
from engine.graph.models.package_model import GraphVariableConfig, VariableConfig
from app.ui.foundation.base_widgets import BaseDialog
from app.ui.foundation.theme_manager import Colors, ThemeManager
from app.ui.foundation import dialog_utils


class _BaseVariableDialog(BaseDialog):
    """提供通用的变量编辑表单骨架。"""

    TYPE_FIELD_LABEL = "数据类型*:"

    def __init__(self, *, title: str, type_items: Sequence[str], parent=None) -> None:
        self._type_items = list(type_items)
        super().__init__(
            title=title,
            width=500,
            height=340,
            parent=parent,
        )

        self._build_form()

    def _build_form(self) -> None:
        layout = self.content_layout
        self.form_layout = QtWidgets.QFormLayout()

        self.name_edit = QtWidgets.QLineEdit(self)
        self.name_edit.setPlaceholderText("请输入变量名")
        self.form_layout.addRow("变量名*:", self.name_edit)

        self.type_combo = QtWidgets.QComboBox(self)
        self.type_combo.addItems(self._type_items)
        self.form_layout.addRow(self.TYPE_FIELD_LABEL, self.type_combo)

        self.default_edit = QtWidgets.QLineEdit(self)
        self.default_edit.setPlaceholderText("默认值（留空表示无默认值）")
        self.form_layout.addRow("默认值:", self.default_edit)

        self.desc_edit = QtWidgets.QTextEdit(self)
        self.desc_edit.setPlaceholderText("描述变量的用途...")
        self.desc_edit.setMinimumHeight(80)
        self.desc_edit.setMaximumHeight(200)
        self.form_layout.addRow("描述:", self.desc_edit)

        layout.addLayout(self.form_layout)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            f"""
            QDialog {{
                background-color: {Colors.BG_CARD};
            }}
            {ThemeManager.button_style()}
            {ThemeManager.input_style()}
        """
        )

    def validate(self) -> bool:
        if not self.name_edit.text().strip():
            dialog_utils.show_warning_dialog(self, "警告", "请输入变量名")
            return False
        return True


class EntityVariableEditDialog(_BaseVariableDialog):
    """实体/模板变量编辑对话框。"""

    def __init__(self, parent=None, variable: Optional[VariableConfig] = None) -> None:
        super().__init__(title="编辑自定义变量" if variable else "新建自定义变量", type_items=get_all_variable_types(), parent=parent)
        self._variable = variable
        if variable:
            self._load_variable(variable)

    def _load_variable(self, variable: VariableConfig) -> None:
        self.name_edit.setText(variable.name)
        self.type_combo.setCurrentText(variable.variable_type)
        if variable.default_value is not None:
            self.default_edit.setText(str(variable.default_value))
        self.desc_edit.setPlainText(variable.description or "")

    def get_variable(self) -> VariableConfig:
        return VariableConfig(
            name=self.name_edit.text().strip(),
            variable_type=self.type_combo.currentText(),
            default_value=self.default_edit.text().strip(),
            description=self.desc_edit.toPlainText().strip(),
        )


class GraphVariableEditDialog(_BaseVariableDialog):
    """节点图变量编辑对话框（带暴露选项）。"""

    def __init__(self, var_config: Optional[GraphVariableConfig] = None, parent=None) -> None:
        super().__init__(
            title="编辑变量" if var_config else "新建变量",
            # 与实体/模板自定义变量共享同一类型列表，保持整个系统的变量类型语义一致
            type_items=get_all_variable_types(),
            parent=parent,
        )
        self.var_config = var_config
        self.exposed_checkbox = QtWidgets.QCheckBox("对外暴露（允许在挂载处覆盖值）", self)
        self.form_layout.insertRow(3, "", self.exposed_checkbox)
        if var_config:
            self._load_variable_data(var_config)

    def _load_variable_data(self, variable: GraphVariableConfig) -> None:
        self.name_edit.setText(variable.name)
        self.type_combo.setCurrentText(variable.variable_type)
        if variable.default_value is not None:
            self.default_edit.setText(str(variable.default_value))
        self.exposed_checkbox.setChecked(variable.is_exposed)
        self.desc_edit.setPlainText(variable.description or "")

    def get_variable_config(self) -> Optional[GraphVariableConfig]:
        var_name = self.name_edit.text().strip()
        if not var_name:
            return None
        var_type = self.type_combo.currentText()
        default_value_str = self.default_edit.text().strip()
        default_value = default_value_str if default_value_str else None
        description = self.desc_edit.toPlainText().strip()
        is_exposed = self.exposed_checkbox.isChecked()
        return GraphVariableConfig(
            name=var_name,
            variable_type=var_type,
            default_value=default_value,
            description=description,
            is_exposed=is_exposed,
        )

