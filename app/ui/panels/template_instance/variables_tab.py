"""Variables tab for template/instance panel - 关卡变量（代码定义）预览 + 实例覆写值编辑。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

from PyQt6 import QtCore, QtWidgets

from engine.graph.models.entity_templates import get_all_variable_types
from engine.graph.models.package_model import InstanceConfig, LevelVariableOverride, TemplateConfig
from engine.resources.level_variable_schema_view import get_default_level_variable_schema_view
from engine.utils.path_utils import normalize_slash
from engine.resources.custom_variable_file_refs import normalize_custom_variable_file_refs
from app.ui.foundation import input_dialogs
from app.ui.foundation.dialog_utils import show_warning_dialog
from app.ui.foundation.theme_manager import Colors, Sizes, ThemeManager
from app.ui.foundation.toast_notification import ToastNotification
from app.ui.foundation.toolbar_utils import apply_standard_toolbar
from app.ui.panels.template_instance.tab_base import TemplateInstanceTabBase
from app.ui.panels.template_instance.variables_external_loader import (
    load_external_level_variable_payloads,
)
from app.ui.panels.template_instance.variables_table_widget import (
    VariablesTwoRowFieldTableWidget,
)


def _safe_strip_text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _extract_level_variable_id_candidate(text_value: object) -> str:
    """从展示文本中提取 variable_id。

    兼容：
    - `name (variable_id)`
    - `name | variable_id | ...`
    - 直接为 `variable_id`
    """
    raw_text = _safe_strip_text(text_value)
    if not raw_text:
        return ""

    candidate = raw_text
    if candidate.endswith(")") and "(" in candidate:
        inside = candidate.rsplit("(", 1)[-1].rstrip(")").strip()
        if inside:
            candidate = inside

    if "|" in candidate:
        parts = [part.strip() for part in candidate.split("|")]
        if len(parts) >= 2 and parts[1]:
            candidate = parts[1]

    return candidate or raw_text


def _format_level_variable_display_name(variable_id: str, variable_name: str) -> str:
    name_text = _safe_strip_text(variable_name)
    var_id_text = _safe_strip_text(variable_id)
    if name_text and var_id_text:
        return f"{name_text} ({var_id_text})"
    return var_id_text or name_text


@dataclass(frozen=True)
class LevelVariableRow:
    variable_id: str
    variable_name: str
    variable_type: str
    value: Any
    source: str  # inherited / overridden / additional / definition
    readonly: bool
    foreground: Optional[str] = None
    background: Optional[str] = None


class VariablesTab(TemplateInstanceTabBase):
    """自定义变量标签页（已迁移到“关卡变量代码定义 + 实例覆写值”体系）。

    - 模板：仅预览 template.metadata.custom_variable_file 指向的变量文件（只读）。
    - 实例/关卡实体：编辑 override_variables（按 variable_id 覆写 value）。
    """

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self._is_read_only: bool = False
        self._add_button: Optional[QtWidgets.QPushButton] = None
        self._delete_button: Optional[QtWidgets.QPushButton] = None
        self._rows_cache: list[LevelVariableRow] = []
        self._build_ui()

    def _build_ui(self) -> None:
        layout = self._init_panel_layout(
            [
                ("+ 添加变量覆写", self._add_override),
                ("删除覆写", self._remove_override),
            ]
        )
        layout.setSpacing(Sizes.SPACING_SMALL)

        toolbar_item = layout.itemAt(0)
        toolbar_layout = toolbar_item.layout() if toolbar_item is not None else None
        if isinstance(toolbar_layout, QtWidgets.QHBoxLayout):
            apply_standard_toolbar(toolbar_layout)
            buttons: list[QtWidgets.QPushButton] = []
            for index in range(toolbar_layout.count()):
                widget = toolbar_layout.itemAt(index).widget()
                if isinstance(widget, QtWidgets.QPushButton):
                    buttons.append(widget)
            if len(buttons) >= 1:
                self._add_button = buttons[0]
            if len(buttons) >= 2:
                self._delete_button = buttons[1]

        hint = QtWidgets.QLabel(self)
        hint.setWordWrap(True)
        hint.setStyleSheet(ThemeManager.hint_text_style())
        hint.setText(
            "变量定义已统一迁移到【管理配置/关卡变量】的 Python 代码资源中。\n"
            "本页仅用于：预览模板引用的变量文件，以及为实例/关卡实体设置变量覆写值（按 variable_id）。"
        )
        layout.addWidget(hint)

        legend_label = QtWidgets.QLabel(self)
        legend_label.setText(
            (
                f'<span style="background-color:{Colors.BG_MAIN}; padding:2px 6px;'
                ' border-radius:4px;">继承默认值（只读）</span>'
                f'  <span style="background-color:{Colors.BG_SELECTED}; color:{Colors.PRIMARY}; padding:2px 6px;'
                ' border-radius:4px;">覆写值</span>'
                f'  <span style="background-color:{Colors.SUCCESS_BG}; padding:2px 6px;'
                ' border-radius:4px;">额外覆写</span>'
            )
        )
        legend_label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        legend_label.setWordWrap(True)
        legend_label.setStyleSheet(ThemeManager.hint_text_style())
        layout.addWidget(legend_label)

        self.fields_table_widget = VariablesTwoRowFieldTableWidget(
            get_all_variable_types(),
            parent=self,
        )
        layout.addWidget(self.fields_table_widget)

        self.fields_table_widget.field_changed.connect(self._on_rows_changed)
        self.fields_table_widget.field_deleted.connect(self._on_field_deleted_from_table)

    def _reset_ui(self) -> None:
        self._rows_cache = []
        self.fields_table_widget.clear_fields()

    def _refresh_ui(self) -> None:
        self._apply_struct_id_options()
        self._reload_rows()

    def set_resource_manager(self, resource_manager) -> None:
        super().set_resource_manager(resource_manager)
        if hasattr(self, "fields_table_widget"):
            self.fields_table_widget.set_resource_manager(resource_manager)

    def _apply_struct_id_options(self) -> None:
        from engine.configs.specialized.struct_definitions_data import list_struct_ids

        struct_ids = list_struct_ids(self.resource_manager)
        self.fields_table_widget.set_struct_id_options(struct_ids)

    # ------------------------------------------------------------------ 数据来源

    def _get_custom_variable_refs(self) -> list[str]:
        """返回当前上下文下的 custom_variable_file 引用列表（允许多文件）。"""
        obj = self.current_object
        if obj is None:
            return []

        # 模板：直接读模板 metadata
        if self.object_type == "template" and isinstance(obj, TemplateConfig):
            metadata = getattr(obj, "metadata", {}) or {}
            return normalize_custom_variable_file_refs(metadata.get("custom_variable_file"))

        # 实例：优先实例自身，其次模板侧（作为“继承变量”）
        if self.object_type == "instance" and isinstance(obj, InstanceConfig):
            instance_metadata = getattr(obj, "metadata", {}) or {}
            instance_refs = normalize_custom_variable_file_refs(instance_metadata.get("custom_variable_file"))
            if instance_refs:
                return instance_refs
            template_obj = self._template_for_instance(obj)
            template_metadata = getattr(template_obj, "metadata", {}) if template_obj else {}
            if isinstance(template_metadata, dict):
                return normalize_custom_variable_file_refs(template_metadata.get("custom_variable_file"))
            return []

        # 关卡实体：仅读自身 metadata（不假设存在模板）
        if self.object_type == "level_entity" and isinstance(obj, InstanceConfig):
            metadata = getattr(obj, "metadata", {}) or {}
            return normalize_custom_variable_file_refs(metadata.get("custom_variable_file"))

        return []

    def _get_available_level_variables(self) -> dict[str, dict[str, Any]]:
        """返回当前作用域下可见的关卡变量集合：{variable_id: payload}。"""
        package = self.current_package
        management = getattr(package, "management", None) if package is not None else None
        mapping = getattr(management, "level_variables", None) if management is not None else None
        if isinstance(mapping, dict) and mapping:
            return mapping
        all_variables = get_default_level_variable_schema_view().get_all_variables()
        return all_variables if isinstance(all_variables, dict) else {}

    def _load_definition_payloads(self) -> list[dict[str, Any]]:
        refs = self._get_custom_variable_refs()
        if not refs:
            return []
        return load_external_level_variable_payloads(refs)

    @staticmethod
    def _normalize_value_for_table(variable_type: str, value: Any) -> object:
        type_text = _safe_strip_text(variable_type)

        if type_text.endswith("列表") and type_text != "结构体列表":
            if isinstance(value, list):
                return [str(v) for v in value]
            return []

        if type_text == "字典":
            if isinstance(value, dict):
                return value
            return {}

        return value if value is not None else ""

    def _iter_rows(self) -> Iterable[LevelVariableRow]:
        obj = self.current_object
        if obj is None:
            return []

        available = self._get_available_level_variables()
        definition_payloads = self._load_definition_payloads()
        definition_by_id: dict[str, dict[str, Any]] = {}
        for payload in definition_payloads:
            if not isinstance(payload, dict):
                continue
            var_id = _safe_strip_text(payload.get("variable_id"))
            if var_id:
                definition_by_id[var_id] = payload

        if self.object_type == "template":
            rows: list[LevelVariableRow] = []
            for variable_id, payload in definition_by_id.items():
                variable_name = _safe_strip_text(payload.get("variable_name") or payload.get("name"))
                variable_type = _safe_strip_text(payload.get("variable_type"))
                default_value = payload.get("default_value")
                rows.append(
                    LevelVariableRow(
                        variable_id=variable_id,
                        variable_name=variable_name,
                        variable_type=variable_type,
                        value=self._normalize_value_for_table(variable_type, default_value),
                        source="definition",
                        readonly=True,
                    )
                )
            return rows

        if isinstance(obj, InstanceConfig) and self.object_type in {"instance", "level_entity"}:
            overrides: list[LevelVariableOverride] = list(getattr(obj, "override_variables", []) or [])
            override_map: dict[str, LevelVariableOverride] = {
                _safe_strip_text(item.variable_id): item for item in overrides if _safe_strip_text(item.variable_id)
            }

            rows: list[LevelVariableRow] = []

            # 1) 定义文件中的变量：继承/覆写
            for variable_id, payload in definition_by_id.items():
                variable_name = _safe_strip_text(payload.get("variable_name") or payload.get("name"))
                variable_type = _safe_strip_text(payload.get("variable_type"))
                default_value = payload.get("default_value")

                if variable_id in override_map:
                    override = override_map[variable_id]
                    value = override.value
                    rows.append(
                        LevelVariableRow(
                            variable_id=variable_id,
                            variable_name=variable_name,
                            variable_type=variable_type,
                            value=self._normalize_value_for_table(variable_type, value),
                            source="overridden",
                            readonly=self._is_read_only,
                            foreground=Colors.PRIMARY,
                            background=Colors.BG_SELECTED,
                        )
                    )
                else:
                    rows.append(
                        LevelVariableRow(
                            variable_id=variable_id,
                            variable_name=variable_name,
                            variable_type=variable_type,
                            value=self._normalize_value_for_table(variable_type, default_value),
                            source="inherited",
                            readonly=True,
                            foreground=Colors.TEXT_SECONDARY,
                            background=Colors.BG_MAIN,
                        )
                    )

            # 2) 仅存在于实例上的覆写：额外覆写（尽量从 available 同步 name/type）
            defined_ids = set(definition_by_id.keys())
            for variable_id, override in override_map.items():
                if variable_id in defined_ids:
                    continue

                payload = available.get(variable_id) if isinstance(available, dict) else None
                variable_name = _safe_strip_text(getattr(override, "variable_name", ""))
                variable_type = _safe_strip_text(getattr(override, "variable_type", ""))
                if isinstance(payload, dict):
                    variable_name = _safe_strip_text(payload.get("variable_name") or payload.get("name")) or variable_name
                    variable_type = _safe_strip_text(payload.get("variable_type")) or variable_type

                rows.append(
                    LevelVariableRow(
                        variable_id=variable_id,
                        variable_name=variable_name,
                        variable_type=variable_type,
                        value=self._normalize_value_for_table(variable_type, override.value),
                        source="additional",
                        readonly=self._is_read_only,
                        background=Colors.SUCCESS_BG,
                    )
                )

            return rows

        return []

    # ------------------------------------------------------------------ UI 刷新/写回

    def _reload_rows(self) -> None:
        rows = list(self._iter_rows())
        self._rows_cache = rows

        can_edit_overrides = (
            self.object_type in {"instance", "level_entity"} and isinstance(self.current_object, InstanceConfig)
        )
        if self._add_button is not None:
            self._add_button.setEnabled(can_edit_overrides and not self._is_read_only)
        if self._delete_button is not None:
            self._delete_button.setEnabled(can_edit_overrides and not self._is_read_only)

        fields: list[dict[str, Any]] = []
        for row in rows:
            fields.append(
                {
                    "name": _format_level_variable_display_name(row.variable_id, row.variable_name),
                    "type_name": row.variable_type,
                    "value": row.value,
                    "readonly": row.readonly,
                    "foreground": row.foreground,
                    "background": row.background,
                }
            )

        self.fields_table_widget.load_fields(fields)
        self._force_lock_name_and_type_cells()

    def _force_lock_name_and_type_cells(self) -> None:
        """强制锁定“名字/类型”列（只允许编辑 value），避免把 schema 层字段当作可编辑数据。"""
        table = self.fields_table_widget.table
        row_index = 0
        row_count = table.rowCount()
        while row_index < row_count:
            # name (col=1)
            name_widget = self.fields_table_widget._get_cell_line_edit(row_index, 1)  # type: ignore[attr-defined]
            if isinstance(name_widget, QtWidgets.QLineEdit):
                name_widget.setReadOnly(True)
                name_widget.setStyleSheet(ThemeManager.readonly_input_style())
            # type (col=2)
            type_widget = self.fields_table_widget._get_cell_combo_box(row_index, 2)  # type: ignore[attr-defined]
            if isinstance(type_widget, QtWidgets.QComboBox):
                type_widget.setEnabled(False)
            row_index += 2

    # ------------------------------------------------------------------ 覆写增删改

    def _add_override(self) -> None:
        obj = self.current_object
        if not isinstance(obj, InstanceConfig) or self.object_type not in {"instance", "level_entity"}:
            return
        if self._is_read_only:
            return

        available = self._get_available_level_variables()
        if not available:
            show_warning_dialog(self, "无法添加覆写", "当前作用域下未加载到任何关卡变量定义。")
            return

        existing_ids = {_safe_strip_text(item.variable_id) for item in (obj.override_variables or [])}
        candidates: list[str] = []
        for variable_id, payload in available.items():
            if not isinstance(payload, dict):
                continue
            variable_id_text = _safe_strip_text(variable_id)
            if not variable_id_text or variable_id_text in existing_ids:
                continue
            name_text = _safe_strip_text(payload.get("variable_name") or payload.get("name") or variable_id_text)
            type_text = _safe_strip_text(payload.get("variable_type"))
            source_stem = _safe_strip_text(payload.get("source_stem") or payload.get("source_file") or "")
            candidates.append(f"{name_text} | {variable_id_text} | {type_text} | {source_stem or '<unknown>'}")
        candidates.sort(key=lambda text: text.casefold())

        if not candidates:
            show_warning_dialog(self, "无法添加覆写", "没有可添加的变量（可能都已覆写）。")
            return

        selected = input_dialogs.prompt_item(
            self,
            "添加变量覆写",
            "变量:",
            candidates,
            current_index=0,
            editable=False,
        )
        if selected is None:
            return

        parts = [part.strip() for part in str(selected).split("|")]
        variable_id = parts[1] if len(parts) >= 2 else ""
        variable_id = _safe_strip_text(variable_id)
        if not variable_id:
            return

        payload = available.get(variable_id, {}) if isinstance(available, dict) else {}
        variable_name = _safe_strip_text(payload.get("variable_name") or payload.get("name") or "")
        variable_type = _safe_strip_text(payload.get("variable_type") or "")
        default_value = payload.get("default_value")

        obj.override_variables.append(
            LevelVariableOverride(
                variable_id=variable_id,
                variable_name=variable_name,
                variable_type=variable_type,
                value=default_value,
                metadata={},
            )
        )
        self._reload_rows()
        self.data_changed.emit()
        ToastNotification.show_message(self, f"已添加覆写：{variable_name or variable_id}", "success")

    def _remove_override(self) -> None:
        obj = self.current_object
        if not isinstance(obj, InstanceConfig) or self.object_type not in {"instance", "level_entity"}:
            return
        if self._is_read_only:
            return

        table = self.fields_table_widget.table
        current_row = table.currentRow()
        if current_row < 0:
            return

        row_index = current_row // 2
        if row_index >= len(self._rows_cache):
            return

        row = self._rows_cache[row_index]
        variable_id = row.variable_id

        # 继承默认值行：不允许删除（它不是覆写记录）
        if row.source == "inherited":
            show_warning_dialog(
                self,
                "无法删除",
                "这是继承的默认值（来自变量定义），不支持删除。\n如需修改，请先“添加变量覆写”。",
            )
            self._reload_rows()
            return

        before = len(obj.override_variables)
        obj.override_variables = [v for v in (obj.override_variables or []) if _safe_strip_text(v.variable_id) != variable_id]
        if len(obj.override_variables) == before:
            self._reload_rows()
            return

        self._reload_rows()
        self.data_changed.emit()
        ToastNotification.show_message(self, f"已删除覆写：{row.variable_name or variable_id}", "success")

    def _on_field_deleted_from_table(self) -> None:
        obj = self.current_object
        if not isinstance(obj, InstanceConfig) or self.object_type not in {"instance", "level_entity"}:
            # 模板只读：直接重建，恢复 UI
            self._reload_rows()
            return
        if self._is_read_only:
            self._reload_rows()
            return

        current_fields = self.fields_table_widget.get_all_fields()
        current_ids: set[str] = set()
        for field in current_fields:
            current_ids.add(_extract_level_variable_id_candidate(field.get("name")))

        removed_id = ""
        removed_row: LevelVariableRow | None = None
        for row in self._rows_cache:
            if row.variable_id not in current_ids:
                removed_id = row.variable_id
                removed_row = row
                break

        if not removed_id or removed_row is None:
            self._reload_rows()
            return

        if removed_row.source == "inherited":
            show_warning_dialog(
                self,
                "无法删除",
                "继承默认值行不可删除。\n如需修改，请先添加覆写；如需清理覆写，请删除覆写行。",
            )
            self._reload_rows()
            return

        obj.override_variables = [v for v in (obj.override_variables or []) if _safe_strip_text(v.variable_id) != removed_id]
        self._reload_rows()
        self.data_changed.emit()

    def _on_rows_changed(self) -> None:
        obj = self.current_object
        if not isinstance(obj, InstanceConfig) or self.object_type not in {"instance", "level_entity"}:
            return
        if self._is_read_only:
            return

        fields = self.fields_table_widget.get_all_fields()
        if len(fields) != len(self._rows_cache):
            # 行数变化由 field_deleted 分支处理；这里保持幂等并刷新 UI
            self._reload_rows()
            return

        available = self._get_available_level_variables()
        changed = False
        for index, row in enumerate(self._rows_cache):
            if row.source not in {"overridden", "additional"}:
                continue

            new_value = fields[index].get("value")
            variable_id = row.variable_id

            # 原地更新覆写记录（按 variable_id 匹配）
            for item in obj.override_variables:
                if _safe_strip_text(item.variable_id) == variable_id:
                    item.value = new_value
                    payload = available.get(variable_id) if isinstance(available, dict) else None
                    if isinstance(payload, dict):
                        name_text = _safe_strip_text(payload.get("variable_name") or payload.get("name"))
                        type_text = _safe_strip_text(payload.get("variable_type"))
                        if name_text:
                            item.variable_name = name_text
                        if type_text:
                            item.variable_type = type_text
                    changed = True
                    break

        if changed:
            self.data_changed.emit()

    # ------------------------------------------------------------------ 只读模式

    def set_read_only(self, read_only: bool) -> None:
        self._is_read_only = bool(read_only)
        self._reload_rows()


__all__ = ["VariablesTab"]
