"""
CombatPlayerEditorPanel 拆分模块：自定义变量（玩家/角色）与结构体查看。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.graph.models.entity_templates import get_all_variable_types
from engine.resources.definition_schema_view import get_default_definition_schema_view
from engine.resources.level_variable_schema_view import get_default_level_variable_schema_view
from engine.utils.name_utils import generate_unique_name
from app.ui.dialogs.struct_viewer_dialog import StructViewerDialog


class CombatPlayerPanelSectionsCustomVariablesMixin:
    current_template_data: Optional[Dict[str, Any]]
    player_editor: Any

    player_custom_variable_table: Any
    role_custom_variable_table: Any

    def _load_player_custom_variables(self) -> None:
        """根据 metadata 与 metadata.player_editor.player 加载玩家层级自定义变量视图。

        - 优先从关卡变量代码定义中按 `metadata["custom_variable_file"]` 引用的文件
          解析出一组代码级变量（只读视图，不写回 JSON）；
        - 其次加载 metadata.player_editor.player.custom_variables 中的非 chip_* 变量，
          作为模板级的额外自定义变量。
        """
        self.player_custom_variable_table.clear_fields()

        if not self.current_template_data:
            return

        schema_view = get_default_definition_schema_view()
        all_structs = schema_view.get_all_struct_definitions()
        struct_ids = sorted(all_structs.keys())
        self.player_custom_variable_table.set_struct_id_options(struct_ids)

        fields: List[Dict[str, Any]] = []

        # 1) 代码级关卡变量定义（只读视图，按 custom_variable_file 归属过滤）。
        external_payloads = self._get_external_player_level_variable_payloads()
        for payload in external_payloads:
            name_value = payload.get("variable_name") or payload.get("name")
            type_value = payload.get("variable_type")
            if not isinstance(name_value, str) or not isinstance(type_value, str):
                continue
            name_text = name_value.strip()
            type_text = type_value.strip()
            if not name_text or not type_text:
                continue
            value = payload.get("default_value")
            fields.append(
                {
                    "name": name_text,
                    "type_name": type_text,
                    "value": value,
                    "readonly": True,
                }
            )

        # 2) 玩家模板 JSON 中的额外自定义变量（非 chip_*，可编辑）。
        player_section = self.player_editor.player
        raw_variables = player_section.get("custom_variables")

        if isinstance(raw_variables, list):
            for entry in raw_variables:
                if not isinstance(entry, dict):
                    continue
                raw_name = entry.get("name")
                name = str(raw_name).strip() if isinstance(raw_name, str) else ""
                type_name = str(entry.get("variable_type", "")).strip()
                if not name or not type_name:
                    continue
                # chip_* 变量交由“自定义变量_局内存档变量”标签页管理
                if self._is_chip_variable_name(name):
                    continue
                value = entry.get("default_value")
                fields.append(
                    {
                        "name": name,
                        "type_name": type_name,
                        "value": value,
                    }
                )

        self.player_custom_variable_table.load_fields(fields)

    def _get_external_player_level_variable_payloads(self) -> List[Dict[str, Any]]:
        """按玩家模板 metadata.custom_variable_file 解析外部关卡变量定义列表。

        - 仅匹配“普通自定义变量”目录（`自定义变量/`），忽略 `自定义变量-局内存档变量/`；
        - 返回的列表元素为 LevelVariableSchemaView 聚合结果中的 payload 字典副本，
          仅用于 UI 层展示，不写回到玩家模板 JSON。
        """
        if not self.current_template_data:
            return []

        metadata_value = self.current_template_data.get("metadata") or {}
        if not isinstance(metadata_value, dict):
            return []

        raw_ref = metadata_value.get("custom_variable_file", "")
        if not isinstance(raw_ref, str):
            return []
        ref_text = raw_ref.strip()
        if not ref_text:
            return []

        normalized_ref = ref_text.replace("\\", "/")
        ref_stem = Path(normalized_ref).stem

        schema_view = get_default_level_variable_schema_view()
        all_variables = schema_view.get_all_variables()

        payloads: List[Dict[str, Any]] = []

        for payload in all_variables.values():
            if not isinstance(payload, dict):
                continue

            source_path_value = payload.get("source_path")
            source_stem_value = payload.get("source_stem")
            source_directory_value = payload.get("source_directory")

            # 仅关注普通自定义变量目录，过滤掉 `自定义变量-局内存档变量/` 等其他目录。
            if isinstance(source_directory_value, str):
                directory_text = source_directory_value.strip()
                if directory_text and directory_text != "自定义变量":
                    continue

            matched = False

            # 兼容旧写法：custom_variable_file 为完整相对路径
            if isinstance(source_path_value, str):
                candidate_path = source_path_value.replace("\\", "/").strip()
                if candidate_path and candidate_path == normalized_ref:
                    matched = True

            # 按 VARIABLE_FILE_ID 匹配（推荐写法）
            if not matched:
                variable_file_id = payload.get("variable_file_id")
                if isinstance(variable_file_id, str):
                    if variable_file_id.strip() == ref_text:
                        matched = True

            # 兼容写法：custom_variable_file 为文件名（不含扩展名），按 source_stem 匹配。
            if not matched and isinstance(source_stem_value, str):
                candidate_stem = source_stem_value.strip()
                if candidate_stem and candidate_stem == ref_stem:
                    matched = True

            if not matched:
                continue

            # 代码级 chip_* 存档镜像变量不在本标签页展示，交由“自定义变量_局内存档变量”管理。
            raw_var_name = payload.get("variable_name") or payload.get("name")
            if isinstance(raw_var_name, str):
                name_text = raw_var_name.strip()
                if name_text and self._is_chip_variable_name(name_text):
                    continue

            payloads.append(dict(payload))

        return payloads

    def _load_role_custom_variables(self) -> None:
        """根据 metadata.player_editor.role 加载角色层级自定义变量。"""
        self.role_custom_variable_table.clear_fields()

        if not self.current_template_data:
            return

        schema_view = get_default_definition_schema_view()
        all_structs = schema_view.get_all_struct_definitions()
        struct_ids = sorted(all_structs.keys())
        self.role_custom_variable_table.set_struct_id_options(struct_ids)

        role_section = self.player_editor.role
        raw_variables = role_section.get("custom_variables")
        fields: List[Dict[str, Any]] = []

        if isinstance(raw_variables, list):
            for entry in raw_variables:
                if not isinstance(entry, dict):
                    continue
                name = str(entry.get("name", "")).strip()
                type_name = str(entry.get("variable_type", "")).strip()
                if not name or not type_name:
                    continue
                value = entry.get("default_value")
                fields.append(
                    {
                        "name": name,
                        "type_name": type_name,
                        "value": value,
                    }
                )

        self.role_custom_variable_table.load_fields(fields)

    def _add_player_custom_variable(self) -> None:
        """玩家层级：添加一条新的自定义变量记录。"""
        if not self.current_template_data:
            return

        existing_fields = self.player_custom_variable_table.get_all_fields()
        existing_names: List[str] = []
        for field in existing_fields:
            name = str(field.get("name", "")).strip()
            if name:
                existing_names.append(name)
        variable_name = generate_unique_name("新变量", existing_names)

        supported_types = get_all_variable_types()
        default_type = supported_types[0] if supported_types else "字符串"

        self.player_custom_variable_table.add_field_row(
            name=variable_name,
            type_name=default_type,
            value="",
        )

        # 选中新添加的字段主行
        table = self.player_custom_variable_table.table
        last_main_row = table.rowCount() - 2
        if last_main_row >= 0:
            table.selectRow(last_main_row)
            table.setFocus()

    def _remove_player_custom_variable(self) -> None:
        """玩家层级：删除当前选中的自定义变量。"""
        if not self.current_template_data:
            return

        table = self.player_custom_variable_table.table
        current_row = table.currentRow()
        if current_row < 0:
            current_row = table.rowCount() - 2
        if current_row < 0:
            return

        self.player_custom_variable_table.remove_field_at_row(current_row)

    def _add_role_custom_variable(self) -> None:
        """角色层级：添加一条新的自定义变量记录。"""
        if not self.current_template_data:
            return

        existing_fields = self.role_custom_variable_table.get_all_fields()
        existing_names: List[str] = []
        for field in existing_fields:
            name = str(field.get("name", "")).strip()
            if name:
                existing_names.append(name)
        variable_name = generate_unique_name("新变量", existing_names)

        supported_types = get_all_variable_types()
        default_type = supported_types[0] if supported_types else "字符串"

        self.role_custom_variable_table.add_field_row(
            name=variable_name,
            type_name=default_type,
            value="",
        )

        table = self.role_custom_variable_table.table
        last_main_row = table.rowCount() - 2
        if last_main_row >= 0:
            table.selectRow(last_main_row)
            table.setFocus()

    def _remove_role_custom_variable(self) -> None:
        """角色层级：删除当前选中的自定义变量。"""
        if not self.current_template_data:
            return

        table = self.role_custom_variable_table.table
        current_row = table.currentRow()
        if current_row < 0:
            current_row = table.rowCount() - 2
        if current_row < 0:
            return

        self.role_custom_variable_table.remove_field_at_row(current_row)

    def _on_player_custom_variables_changed(self) -> None:
        """玩家层级自定义变量变更时写回 metadata.player_editor.player."""
        if not self.current_template_data:
            return

        player_section = self.player_editor.player

        # 外部关卡变量定义仅作为只读视图存在，不写回到玩家模板 JSON。
        external_names: List[str] = []
        for payload in self._get_external_player_level_variable_payloads():
            name_value = payload.get("variable_name") or payload.get("name")
            if isinstance(name_value, str):
                name_text = name_value.strip()
                if name_text:
                    external_names.append(name_text)
        external_name_set = set(external_names)

        # 普通自定义变量标签页仅负责非 chip_* 变量
        fields = self.player_custom_variable_table.get_all_fields()
        normal_variables: List[Dict[str, Any]] = []
        for field in fields:
            name = str(field.get("name", "")).strip()
            type_name = str(field.get("type_name", "")).strip()
            if not name or not type_name:
                continue
            # 外部关卡变量定义仅用于只读展示，不写入 custom_variables。
            if name in external_name_set:
                continue
            if self._is_chip_variable_name(name):
                # chip_* 变量交由局内存档标签页管理
                continue
            value = field.get("value")
            normal_variables.append(
                {
                    "name": name,
                    "variable_type": type_name,
                    "default_value": value,
                    "description": "",
                }
            )

        # 保留既有 chip_* 变量
        raw_existing = player_section.get("custom_variables")
        chip_variables: List[Dict[str, Any]] = []
        if isinstance(raw_existing, list):
            for entry in raw_existing:
                if not isinstance(entry, dict):
                    continue
                raw_name = entry.get("name")
                variable_name = str(raw_name).strip() if isinstance(raw_name, str) else ""
                if self._is_chip_variable_name(variable_name):
                    chip_variables.append(entry)

        player_section["custom_variables"] = normal_variables + chip_variables
        self._mark_template_modified()
        self.data_changed.emit()

    def _on_role_custom_variables_changed(self) -> None:
        """角色层级自定义变量变更时写回 metadata.player_editor.role."""
        if not self.current_template_data:
            return

        fields = self.role_custom_variable_table.get_all_fields()
        variables: List[Dict[str, Any]] = []
        for field in fields:
            name = str(field.get("name", "")).strip()
            type_name = str(field.get("type_name", "")).strip()
            if not name or not type_name:
                continue
            value = field.get("value")
            variables.append(
                {
                    "name": name,
                    "variable_type": type_name,
                    "default_value": value,
                    "description": "",
                }
            )

        self.player_editor.role["custom_variables"] = variables
        self.player_editor.role["last_modified"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._mark_template_modified()
        self.data_changed.emit()

    def _on_struct_view_requested(self, struct_id: str) -> None:
        """处理查看结构体请求，弹出只读结构体查看对话框。"""
        if not struct_id:
            return

        # 从定义视图获取结构体详情
        schema_view = get_default_definition_schema_view()
        all_structs = schema_view.get_all_struct_definitions()
        struct_payload = all_structs.get(struct_id)

        # 弹出只读结构体查看对话框
        dialog = StructViewerDialog(
            struct_id=struct_id,
            struct_payload=struct_payload,
            parent=self,  # type: ignore[arg-type]
        )
        dialog.exec()


