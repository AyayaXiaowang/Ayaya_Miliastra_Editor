"""
CombatPlayerEditorPanel 拆分模块：局内存档模板绑定与 chip_* 变量。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.resources.definition_schema_view import get_default_definition_schema_view
from engine.resources.global_resource_view import GlobalResourceView
from app.ui.foundation.theme_manager import Sizes


class CombatPlayerPanelSectionsIngameSaveMixin:
    resource_manager: Optional[Any]
    current_template_data: Optional[Dict[str, Any]]
    player_editor: Any

    player_ingame_save_template_combo: Any
    player_ingame_save_summary_label: Any
    player_ingame_save_table: Any

    def _get_ingame_save_selection_store_path(self) -> Optional[Path]:
        """返回记忆局内存档模板选择的本地状态文件路径。"""
        if self.resource_manager is None:
            return None
        workspace_path = getattr(self.resource_manager, "workspace_path", None)
        if not isinstance(workspace_path, Path):
            return None
        cache_directory = workspace_path / "app" / "runtime" / "cache"
        return cache_directory / "player_ingame_save_selection.json"

    def _load_last_selected_ingame_save_template(self) -> str:
        """读取当前玩家模板对应的上次选择的局内存档模板 ID。"""
        store_path = self._get_ingame_save_selection_store_path()
        if store_path is None or not store_path.exists():
            return ""

        serialized_text = store_path.read_text(encoding="utf-8")
        if not serialized_text.strip():
            return ""

        payload = json.loads(serialized_text)
        if not isinstance(payload, dict):
            return ""

        mapping_value = payload.get("player_template_last_selection")
        if not isinstance(mapping_value, dict):
            return ""

        current_template_id = getattr(self, "current_template_id", None)
        if not isinstance(current_template_id, str) or not current_template_id:
            return ""

        stored_value = mapping_value.get(current_template_id)
        if isinstance(stored_value, str):
            return stored_value.strip()
        return ""

    def _persist_ingame_save_selection(self, selected_template_id: str) -> None:
        """将当前玩家模板的局内存档模板选择写入本地状态文件。"""
        store_path = self._get_ingame_save_selection_store_path()
        current_template_id = getattr(self, "current_template_id", None)
        if store_path is None:
            return
        if not isinstance(current_template_id, str) or not current_template_id:
            return

        existing_payload: Dict[str, Any] = {}
        if store_path.exists():
            existing_text = store_path.read_text(encoding="utf-8")
            if existing_text.strip():
                loaded_payload = json.loads(existing_text)
                if isinstance(loaded_payload, dict):
                    existing_payload = loaded_payload

        selection_mapping = existing_payload.get("player_template_last_selection")
        if not isinstance(selection_mapping, dict):
            selection_mapping = {}

        if selected_template_id:
            selection_mapping[current_template_id] = selected_template_id
        else:
            if current_template_id in selection_mapping:
                selection_mapping.pop(current_template_id)

        existing_payload["player_template_last_selection"] = selection_mapping
        existing_payload["schema_version"] = 1

        store_path.parent.mkdir(parents=True, exist_ok=True)
        serialized_payload = json.dumps(
            existing_payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        store_path.write_text(serialized_payload, encoding="utf-8")

    def _load_player_ingame_save_binding(self, forced_template_id: Optional[str] = None) -> None:
        """加载局内存档模板绑定与 chip_* 变量视图。

        Args:
            forced_template_id: 当由下拉框选择触发时，显式指定要绑定的模板 ID；
                为 None 时按 metadata.player_editor.player.ingame_save.template_id
                或全局启用模板 active_template_id 推导。
        """
        if not hasattr(self, "player_ingame_save_template_combo") or not hasattr(
            self, "player_ingame_save_table"
        ):
            return

        self.player_ingame_save_table.clear_fields()
        self.player_ingame_save_table.setEnabled(False)

        if not self.current_template_data or self.resource_manager is None:
            self.player_ingame_save_template_combo.blockSignals(True)
            self.player_ingame_save_template_combo.clear()
            self.player_ingame_save_template_combo.blockSignals(False)
            self.player_ingame_save_summary_label.setText("当前工程未提供局内存档管理模板。")
            return

        save_points_config = self._get_save_points_config()
        templates_value = save_points_config.get("templates", [])
        if not isinstance(templates_value, list) or not templates_value:
            self.player_ingame_save_template_combo.blockSignals(True)
            self.player_ingame_save_template_combo.clear()
            self.player_ingame_save_template_combo.blockSignals(False)
            self.player_ingame_save_summary_label.setText("当前工程未配置任何局内存档管理模板。")
            return

        player_section = self.player_editor.player
        ingame_save_meta = player_section.get("ingame_save")
        if not isinstance(ingame_save_meta, dict):
            ingame_save_meta = {}
            player_section["ingame_save"] = ingame_save_meta

        enabled_flag = bool(save_points_config.get("enabled", False))
        active_template_id = str(save_points_config.get("active_template_id", "")).strip()
        previous_template_id = str(ingame_save_meta.get("template_id", "")).strip()
        last_selected_template_id = self._load_last_selected_ingame_save_template()

        if forced_template_id is not None:
            selected_template_id = forced_template_id.strip()
        else:
            selected_template_id = (
                previous_template_id
                or last_selected_template_id
                or (active_template_id if enabled_flag else "")
            )

        # 重建模板下拉列表
        self.player_ingame_save_template_combo.blockSignals(True)
        self.player_ingame_save_template_combo.clear()
        self.player_ingame_save_template_combo.addItem("（未选择）", "")

        template_map: Dict[str, Dict[str, Any]] = {}
        for template_payload in templates_value:
            if not isinstance(template_payload, dict):
                continue
            raw_template_id = template_payload.get("template_id", "")
            template_id = str(raw_template_id).strip()
            if not template_id:
                continue
            raw_name = template_payload.get("template_name")
            template_name = str(raw_name).strip() if isinstance(raw_name, str) else ""
            display_name = template_name or template_id
            if template_name and template_name != template_id:
                label_text = f"{template_name} ({template_id})"
            else:
                label_text = display_name
            self.player_ingame_save_template_combo.addItem(label_text, template_id)
            template_map[template_id] = template_payload

        # 应用当前选择（如无显式绑定则回退到全局启用模板）
        if selected_template_id not in template_map:
            selected_template_id = ""

        if selected_template_id:
            index = self.player_ingame_save_template_combo.findData(selected_template_id)
            if index < 0:
                index = 0
        else:
            index = 0

        self.player_ingame_save_template_combo.setCurrentIndex(index)
        self.player_ingame_save_template_combo.setEnabled(True)
        self.player_ingame_save_template_combo.blockSignals(False)

        if not selected_template_id or selected_template_id not in template_map:
            self.player_ingame_save_summary_label.setText("未选择局内存档管理模板。")
            return

        selected_template = template_map[selected_template_id]
        self._persist_ingame_save_selection(selected_template_id)

        # 确保 metadata.player_editor.player.ingame_save.template_id 与当前选择一致
        if selected_template_id != previous_template_id:
            ingame_save_meta["template_id"] = selected_template_id
            player_section["ingame_save"] = ingame_save_meta
            # 仅在显式选择模板时（forced_template_id 非空字符串）视为用户触发的修改，
            # 避免在首次加载或仅切换页面时就触发保存。
            if forced_template_id is not None and forced_template_id.strip():
                self._mark_template_modified()
                self.data_changed.emit()

        # 根据局内存档模板 entries 构建 chip_* 变量表格字段（仅作为只读视图，不写回玩家模板 JSON）。
        chip_fields: List[Dict[str, Any]] = []
        entries_value = selected_template.get("entries", [])

        # 预先构造 struct_id -> 结构体名称 的映射，便于在表格中展示更友好的名称。
        struct_name_map: Dict[str, str] = {}
        schema_view = get_default_definition_schema_view()
        all_structs = schema_view.get_all_struct_definitions()
        for struct_id, payload in all_structs.items():
            if not isinstance(payload, dict):
                continue
            struct_type_value = payload.get("struct_ype")
            if not isinstance(struct_type_value, str):
                continue
            if struct_type_value.strip() != "ingame_save":
                continue
            raw_name = payload.get("name") or payload.get("struct_name") or struct_id
            display_name = str(raw_name)
            struct_name_map[str(struct_id)] = display_name

        if isinstance(entries_value, list):
            for index_in_list, entry_payload in enumerate(entries_value, start=1):
                if not isinstance(entry_payload, dict):
                    continue

                raw_index = entry_payload.get("index")
                if isinstance(raw_index, str) and raw_index.strip().isdigit():
                    struct_index = int(raw_index.strip())
                else:
                    struct_index = index_in_list

                struct_id_value = entry_payload.get("struct_id")
                struct_id_text = (
                    str(struct_id_value).strip() if isinstance(struct_id_value, str) else ""
                )

                max_length_value = entry_payload.get("max_length")
                max_length: int | None = None
                if isinstance(max_length_value, (int, float)):
                    max_length = int(max_length_value)
                elif isinstance(max_length_value, str) and max_length_value.strip().isdigit():
                    max_length = int(max_length_value.strip())

                variable_name = f"1_chip_{struct_index}"
                type_name_text = "结构体"
                effective_name = variable_name

                struct_display_name = struct_name_map.get(
                    struct_id_text, struct_id_text or "（未指定结构体）"
                )

                # 表格值列展示“结构体名称 + 最大条目数”元信息，但内部仍保留 struct_id 作为真实值，
                # 以便后续从表格读取字段时能写回 chip_* 自定义变量的默认值。
                if isinstance(max_length, int) and max_length > 0:
                    display_text = f"{struct_display_name}（最大 {max_length} 条）"
                else:
                    display_text = f"{struct_display_name}（最大条目数不限）"

                value_object: Dict[str, Any] = {
                    "raw": struct_id_text,
                    "display": display_text,
                }

                chip_fields.append(
                    {
                        "name": effective_name,
                        "type_name": type_name_text,
                        "value": value_object,
                        "readonly": True,
                    }
                )

        if self.resource_manager is not None:
            struct_ids = self._load_ingame_save_struct_ids()
            self.player_ingame_save_table.set_struct_id_options(struct_ids)

        self.player_ingame_save_table.load_fields(chip_fields)
        self.player_ingame_save_table.setEnabled(True)
        self._update_player_ingame_save_table_height()

        template_name_text = (
            str(selected_template.get("template_name", "")).strip() or selected_template_id
        )

        summary_lines: List[str] = []
        summary_lines.append(
            f"当前模板：{template_name_text}（共 {len(chip_fields)} 条 chip 映射，变量名约定为 1_chip_序号）。"
        )
        # 详细的“变量名 → 结构体: 最大条目数”信息改由下方表格的“最大条目数”列展示，
        # 概要区域仅保留模板层面的整体说明，避免重复信息。
        self.player_ingame_save_summary_label.setText("\n".join(summary_lines))

    def _get_save_points_config(self) -> Dict[str, Any]:
        """从 GlobalResourceView 读取聚合后的局内存档管理配置。"""
        global_view = GlobalResourceView(self.resource_manager)
        management_data = global_view.management
        save_points_value = getattr(management_data, "save_points", {})
        if isinstance(save_points_value, dict):
            return save_points_value
        return {}

    def _load_ingame_save_struct_ids(self) -> List[str]:
        """加载 struct_ype == "ingame_save" 的结构体 ID 列表。"""
        struct_ids: List[str] = []
        schema_view = get_default_definition_schema_view()
        all_structs = schema_view.get_all_struct_definitions()

        for struct_id, payload in all_structs.items():
            if not isinstance(payload, dict):
                continue
            struct_type_value = payload.get("struct_ype")
            if not isinstance(struct_type_value, str):
                continue
            if struct_type_value.strip() != "ingame_save":
                continue
            struct_ids.append(str(struct_id))
        return struct_ids

    @staticmethod
    def _is_chip_variable_name(variable_name: str) -> bool:
        """判断变量名是否符合 N_chip_M 约定格式。"""
        text = variable_name.strip()
        if "_chip_" not in text:
            return False
        prefix, suffix = text.split("_chip_", 1)
        if not prefix or not suffix:
            return False
        if not prefix.isdigit() or not suffix.isdigit():
            return False
        return True

    def _update_player_ingame_save_table_height(self) -> None:
        """根据当前行数与行高调整局内存档变量表格高度，使其随内容自然增减。"""
        if not hasattr(self, "player_ingame_save_table"):
            return
        table = self.player_ingame_save_table.table
        if table is None:
            return

        row_count = table.rowCount()
        vertical_header = table.verticalHeader()
        if vertical_header is not None and row_count > 0:
            row_height = vertical_header.sectionSize(0)
        else:
            row_height = Sizes.INPUT_HEIGHT + Sizes.PADDING_SMALL

        horizontal_header = table.horizontalHeader()
        header_height = horizontal_header.height() if horizontal_header is not None else 0

        frame_height = table.frameWidth() * 2
        effective_rows = max(1, row_count)
        content_height = row_height * effective_rows
        extra_padding = Sizes.PADDING_SMALL

        total_height = header_height + frame_height + content_height + extra_padding
        table.setMinimumHeight(total_height)
        table.setMaximumHeight(total_height)

    def _on_player_ingame_save_template_changed(self, index: int) -> None:
        """局内存档模板下拉变化时，刷新绑定与 chip_* 变量视图。"""
        if not self.current_template_data:
            return
        if not hasattr(self, "player_ingame_save_template_combo"):
            return

        combo = self.player_ingame_save_template_combo
        if index < 0 or index >= combo.count():
            return

        data = combo.itemData(index)
        if isinstance(data, str):
            selected_template_id = data.strip()
        else:
            selected_template_id = combo.itemText(index).strip()

        self._persist_ingame_save_selection(selected_template_id)
        # 直接复用加载逻辑，根据当前下拉选择重新构建绑定与表格
        self._load_player_ingame_save_binding(selected_template_id or None)

    def _on_player_ingame_save_variables_changed(self) -> None:
        """局内存档 chip_* 变量表格变更时写回 metadata.player_editor.player.custom_variables。"""
        if not self.current_template_data:
            return
        player_section = self.player_editor.player

        fields = self.player_ingame_save_table.get_all_fields()
        chip_variables_by_name: Dict[str, Dict[str, Any]] = {}
        for field in fields:
            name = str(field.get("name", "")).strip()
            type_name = str(field.get("type_name", "")).strip()
            if not name or not type_name:
                continue
            if not self._is_chip_variable_name(name):
                continue
            value = field.get("value")
            chip_variables_by_name[name] = {
                "name": name,
                "variable_type": type_name,
                "default_value": value,
                "description": "",
            }

        # 先保留所有非 chip_* 变量，再追加最新的 chip_* 变量
        raw_existing = player_section.get("custom_variables")
        normal_variables: List[Dict[str, Any]] = []
        if isinstance(raw_existing, list):
            for entry in raw_existing:
                if not isinstance(entry, dict):
                    continue
                raw_name = entry.get("name")
                variable_name = str(raw_name).strip() if isinstance(raw_name, str) else ""
                if self._is_chip_variable_name(variable_name):
                    continue
                normal_variables.append(entry)

        merged_variables: List[Dict[str, Any]] = normal_variables + list(
            chip_variables_by_name.values()
        )
        player_section["custom_variables"] = merged_variables

        self._mark_template_modified()
        self.data_changed.emit()
        self._update_player_ingame_save_table_height()


