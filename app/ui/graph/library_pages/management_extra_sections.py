"""额外的管理配置 Section 定义。

将技能资源 / 背景音乐 / 装备数据等资源型管理配置以列表视图的形式接入
`ManagementLibraryWidget`，保持与计时器/关卡变量/预设点等 Section 的统一接口。
"""

from __future__ import annotations

import types
from typing import Any, Dict, Iterable, Optional, Union

from PyQt6 import QtWidgets

from engine.configs.management.audio_music_configs import BackgroundMusicConfig
from engine.configs.management.resource_language_configs import SkillResourceConfig
from engine.configs.management.shop_economy_configs import EquipmentDataConfig
from engine.resources.global_resource_view import GlobalResourceView
from engine.resources.package_view import PackageView
from ui.foundation.id_generator import generate_prefixed_id
from ui.foundation.theme_manager import ThemeManager
from ui.graph.library_pages.management_sections import (
    BaseManagementSection,
    ManagementRowData,
)
from ui.forms.schema_dialog import FormDialogBuilder


ManagementPackage = Union[PackageView, GlobalResourceView]


class SkillResourceSection(BaseManagementSection):
    """技能资源管理 Section（对应 `ManagementData.skill_resources`）。"""

    section_key = "skill_resource"
    tree_label = "✨ 技能资源"
    type_name = "技能资源"

    def iter_rows(self, package: ManagementPackage) -> Iterable[ManagementRowData]:
        for resource_id, resource_data in package.management.skill_resources.items():
            if not isinstance(resource_data, dict):
                continue

            resource_name_value = str(resource_data.get("resource_name", ""))
            growth_type_value = str(resource_data.get("growth_type", "无条件增长"))
            max_obtainable_value = resource_data.get(
                "max_obtainable_value",
                resource_data.get("max_value", 100.0),
            )
            recovery_rate_value = resource_data.get("recovery_rate", 0.0)
            referenced_skills_value = resource_data.get("referenced_skills", [])
            referenced_count = (
                len(referenced_skills_value)
                if isinstance(referenced_skills_value, list)
                else 0
            )

            attr1_text = f"增长类型: {growth_type_value}" if growth_type_value else ""
            attr2_text = (
                f"可获取最大值: {max_obtainable_value}"
                if max_obtainable_value is not None
                else ""
            )

            attr3_parts: list[str] = []
            if recovery_rate_value:
                attr3_parts.append(f"恢复: {recovery_rate_value}/秒")
            if referenced_count:
                attr3_parts.append(f"引用技能: {referenced_count}")
            attr3_text = "，".join(attr3_parts) if attr3_parts else ""

            description_text = str(resource_data.get("description", ""))

            yield ManagementRowData(
                name=resource_name_value or resource_id,
                type_name=self.type_name,
                attr1=attr1_text,
                attr2=attr2_text,
                attr3=attr3_text,
                description=description_text,
                last_modified=self._get_last_modified_text(resource_data),
                user_data=(self.section_key, resource_id),
            )

    def _build_form(
        self,
        parent_widget: QtWidgets.QWidget,
        *,
        title: str,
        initial: Optional[Dict[str, Any]] = None,
        is_edit: bool,
        record_id: Optional[str],
        referenced_skills: Optional[list[str]],
    ) -> Optional[Dict[str, Any]]:
        initial_values: Dict[str, Any] = {
            "resource_name": "",
            "growth_type": "无条件增长",
            "max_obtainable_value": 100.0,
            "recovery_rate": 5.0,
        }
        if initial:
            initial_values.update(initial)

        builder = FormDialogBuilder(parent_widget, title, fixed_size=(450, 420))

        name_edit = builder.add_line_edit(
            "技能资源名*:",
            str(initial_values.get("resource_name", "")),
            "请输入资源名称",
        )
        growth_combo = builder.add_combo_box(
            "增长类型:",
            ["无条件增长", "跟随技能(保留值)", "跟随技能(不保留值)"],
            str(initial_values.get("growth_type", "无条件增长")),
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
            "恢复速率(每秒):",
            minimum=0.0,
            maximum=9999.0,
            value=float(initial_values.get("recovery_rate", 5.0)),
            decimals=2,
            single_step=0.5,
            suffix=" /秒",
        )

        growth_info_label = QtWidgets.QLabel(
            "• 无条件增长：超过最大值时也能增长\n"
            "• 跟随技能(保留值)：需要技能引用时才能改变，无引用时保留值\n"
            "• 跟随技能(不保留值)：需要技能引用时才能改变，无引用时清零"
        )
        growth_info_label.setStyleSheet(ThemeManager.hint_text_style())
        growth_info_label.setWordWrap(True)
        builder.add_custom_row("", growth_info_label)

        if is_edit and record_id:
            id_display = builder.add_line_edit(
                "配置ID:",
                record_id,
                read_only=True,
            )
            id_display.setStyleSheet(ThemeManager.readonly_input_style())

            referenced_list = referenced_skills or []
            referenced_display_text = (
                ", ".join(referenced_list) if referenced_list else "（暂无引用）"
            )
            referenced_text_widget = builder.add_plain_text_edit(
                "引用的技能:",
                referenced_display_text,
                min_height=60,
                max_height=120,
            )
            referenced_text_widget.setReadOnly(True)
            referenced_text_widget.setStyleSheet(ThemeManager.readonly_input_style())

        def _validate(dialog_self: QtWidgets.QDialog) -> bool:
            if not name_edit.text().strip():
                from ui.foundation import dialog_utils

                dialog_utils.show_warning_dialog(
                    dialog_self,
                    "提示",
                    "请输入技能资源名",
                )
                return False
            return True

        builder.dialog.validate = types.MethodType(_validate, builder.dialog)

        if not builder.exec():
            return None

        return {
            "resource_name": name_edit.text().strip(),
            "growth_type": str(growth_combo.currentText()),
            "max_obtainable_value": float(max_value_spin.value()),
            "recovery_rate": float(recovery_rate_spin.value()),
        }

    def create_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
    ) -> bool:
        dialog_data = self._build_form(
            parent_widget,
            title="新建技能资源",
            initial=None,
            is_edit=False,
            record_id=None,
            referenced_skills=None,
        )
        if dialog_data is None:
            return False

        resource_id = generate_prefixed_id(self.section_key)
        resource_config = SkillResourceConfig(
            resource_id=resource_id,
            resource_name=str(dialog_data["resource_name"]),
        )
        serialized = resource_config.serialize()
        serialized["growth_type"] = str(dialog_data["growth_type"])
        serialized["max_obtainable_value"] = float(dialog_data["max_obtainable_value"])
        serialized["recovery_rate"] = float(dialog_data["recovery_rate"])
        serialized["max_value"] = float(dialog_data["max_obtainable_value"])
        serialized["referenced_skills"] = []
        package.management.skill_resources[resource_id] = serialized
        return True

    def edit_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
    ) -> bool:
        resource_data = package.management.skill_resources.get(item_id)
        if resource_data is None:
            return False

        initial_values = {
            "resource_name": resource_data.get("resource_name", ""),
            "growth_type": resource_data.get("growth_type", "无条件增长"),
            "max_obtainable_value": resource_data.get(
                "max_obtainable_value",
                resource_data.get("max_value", 100.0),
            ),
            "recovery_rate": resource_data.get("recovery_rate", 5.0),
        }
        referenced_skills_list = list(resource_data.get("referenced_skills", []))
        dialog_data = self._build_form(
            parent_widget,
            title="编辑技能资源",
            initial=initial_values,
            is_edit=True,
            record_id=item_id,
            referenced_skills=referenced_skills_list,
        )
        if dialog_data is None:
            return False

        resource_data["resource_name"] = dialog_data["resource_name"]
        resource_data["growth_type"] = dialog_data["growth_type"]
        resource_data["max_obtainable_value"] = dialog_data["max_obtainable_value"]
        resource_data["recovery_rate"] = dialog_data["recovery_rate"]
        resource_data["max_value"] = dialog_data["max_obtainable_value"]
        return True

    def delete_item(self, package: ManagementPackage, item_id: str) -> bool:
        if item_id not in package.management.skill_resources:
            return False
        del package.management.skill_resources[item_id]
        return True


class BackgroundMusicSection(BaseManagementSection):
    """背景音乐管理 Section（对应 `ManagementData.background_music`）。"""

    section_key = "background_music"
    tree_label = "🎵 背景音乐"
    type_name = "背景音乐"

    def iter_rows(self, package: ManagementPackage) -> Iterable[ManagementRowData]:
        for music_id, music_data in package.management.background_music.items():
            if not isinstance(music_data, dict):
                continue

            music_name_value = str(music_data.get("music_name", ""))
            audio_file_value = str(music_data.get("audio_file", ""))
            volume_value = float(music_data.get("volume", 1.0))
            loop_value = bool(music_data.get("loop", True))
            trigger_condition_value = str(music_data.get("trigger_condition", ""))

            display_name = music_name_value or music_id
            file_text = audio_file_value or "（未设置）"
            attr1_text = f"文件: {file_text}"
            attr2_text = f"音量: {volume_value:.2f}"
            loop_text = "是" if loop_value else "否"
            if trigger_condition_value:
                attr3_text = f"循环: {loop_text}；触发: {trigger_condition_value}"
            else:
                attr3_text = f"循环: {loop_text}"

            description_text = str(music_data.get("description", ""))

            yield ManagementRowData(
                name=display_name,
                type_name=self.type_name,
                attr1=attr1_text,
                attr2=attr2_text,
                attr3=attr3_text,
                description=description_text,
                last_modified=self._get_last_modified_text(music_data),
                user_data=(self.section_key, music_id),
            )

    def _build_form(
        self,
        parent_widget: QtWidgets.QWidget,
        *,
        title: str,
        initial: Optional[Dict[str, Any]],
        allow_edit_id: bool,
        existing_ids: Optional[set[str]],
    ) -> Optional[Dict[str, Any]]:
        initial_values: Dict[str, Any] = {
            "music_id": "",
            "music_name": "",
            "audio_file": "",
            "volume": 1.0,
            "loop": True,
            "fade_in_duration": 0.0,
            "fade_out_duration": 0.0,
            "trigger_condition": "",
            "description": "",
        }
        if initial:
            initial_values.update(initial)

        builder = FormDialogBuilder(parent_widget, title, fixed_size=(480, 520))

        music_id_value = str(initial_values.get("music_id", ""))
        id_edit = builder.add_line_edit(
            "音乐ID*:",
            music_id_value,
            "用于在数据中唯一标识该音乐",
            read_only=not allow_edit_id,
        )
        if not allow_edit_id:
            id_edit.setStyleSheet(ThemeManager.readonly_input_style())

        name_edit = builder.add_line_edit(
            "音乐名称*:",
            str(initial_values.get("music_name", "")),
            "请输入显示名称",
        )
        file_edit = builder.add_line_edit(
            "音频文件路径:",
            str(initial_values.get("audio_file", "")),
            "例如：audio/theme.wav",
        )
        volume_spin = builder.add_double_spin_box(
            "音量(0-1):",
            minimum=0.0,
            maximum=1.0,
            value=float(initial_values.get("volume", 1.0)),
            decimals=2,
            single_step=0.1,
        )
        loop_check = builder.add_check_box(
            "循环播放",
            bool(initial_values.get("loop", True)),
        )
        fade_in_spin = builder.add_double_spin_box(
            "淡入时长(秒):",
            minimum=0.0,
            maximum=10.0,
            value=float(initial_values.get("fade_in_duration", 0.0)),
            decimals=2,
            single_step=0.1,
        )
        fade_out_spin = builder.add_double_spin_box(
            "淡出时长(秒):",
            minimum=0.0,
            maximum=10.0,
            value=float(initial_values.get("fade_out_duration", 0.0)),
            decimals=2,
            single_step=0.1,
        )
        trigger_edit = builder.add_line_edit(
            "触发条件:",
            str(initial_values.get("trigger_condition", "")),
            "可选：填写触发条件",
        )
        desc_edit = builder.add_plain_text_edit(
            "描述:",
            str(initial_values.get("description", "")),
            min_height=100,
            max_height=220,
        )

        normalized_existing_ids: set[str] = set()
        if existing_ids is not None:
            for value in existing_ids:
                normalized_existing_ids.add(str(value))

        def _validate(dialog_self: QtWidgets.QDialog) -> bool:
            from ui.foundation import dialog_utils

            entered_id = id_edit.text().strip()
            music_name_text = name_edit.text().strip()
            if not entered_id:
                dialog_utils.show_warning_dialog(
                    dialog_self,
                    "提示",
                    "请输入音乐ID",
                )
                return False

            if allow_edit_id and normalized_existing_ids:
                original_id = str(initial_values.get("music_id", ""))
                if entered_id != original_id and entered_id in normalized_existing_ids:
                    dialog_utils.show_warning_dialog(
                        dialog_self,
                        "提示",
                        "该音乐ID已存在，请输入其他ID",
                    )
                    return False

            if not music_name_text:
                dialog_utils.show_warning_dialog(
                    dialog_self,
                    "提示",
                    "请输入音乐名称",
                )
                return False

            return True

        builder.dialog.validate = types.MethodType(_validate, builder.dialog)

        if not builder.exec():
            return None

        if allow_edit_id:
            final_id = id_edit.text().strip()
        else:
            final_id = music_id_value

        return {
            "music_id": final_id,
            "music_name": name_edit.text().strip(),
            "audio_file": file_edit.text().strip(),
            "volume": float(volume_spin.value()),
            "loop": bool(loop_check.isChecked()),
            "fade_in_duration": float(fade_in_spin.value()),
            "fade_out_duration": float(fade_out_spin.value()),
            "trigger_condition": trigger_edit.text().strip(),
            "description": desc_edit.toPlainText().strip(),
        }

    def create_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
    ) -> bool:
        music_map = package.management.background_music
        existing_ids: set[str] = set(music_map.keys())

        suggested_id = generate_prefixed_id(self.section_key)
        while suggested_id in existing_ids:
            suggested_id = generate_prefixed_id(self.section_key)

        initial_values = {"music_id": suggested_id}
        dialog_data = self._build_form(
            parent_widget,
            title="新建音乐",
            initial=initial_values,
            allow_edit_id=True,
            existing_ids=existing_ids,
        )
        if dialog_data is None:
            return False

        music_id = dialog_data["music_id"]
        music_config = BackgroundMusicConfig(
            music_id=music_id,
            music_name=dialog_data["music_name"] or f"音乐_{music_id}",
            audio_file=dialog_data["audio_file"],
            volume=dialog_data["volume"],
            loop=dialog_data["loop"],
            fade_in_duration=dialog_data["fade_in_duration"],
            fade_out_duration=dialog_data["fade_out_duration"],
            trigger_condition=dialog_data["trigger_condition"],
            description=dialog_data["description"],
        )
        music_map[music_id] = music_config.serialize()
        return True

    def edit_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
    ) -> bool:
        music_map = package.management.background_music
        original_data = music_map.get(item_id)
        if not isinstance(original_data, dict):
            from ui.foundation import dialog_utils

            dialog_utils.show_warning_dialog(
                parent_widget,
                "提示",
                "当前音乐配置不存在，无法编辑",
            )
            return False

        initial_data = dict(original_data)
        initial_data["music_id"] = item_id

        dialog_data = self._build_form(
            parent_widget,
            title="编辑背景音乐",
            initial=initial_data,
            allow_edit_id=False,
            existing_ids=None,
        )
        if dialog_data is None:
            return False

        target_entry = music_map[item_id]
        target_entry["music_name"] = dialog_data["music_name"]
        target_entry["audio_file"] = dialog_data["audio_file"]
        target_entry["volume"] = dialog_data["volume"]
        target_entry["loop"] = dialog_data["loop"]
        target_entry["fade_in_duration"] = dialog_data["fade_in_duration"]
        target_entry["fade_out_duration"] = dialog_data["fade_out_duration"]
        target_entry["trigger_condition"] = dialog_data["trigger_condition"]
        target_entry["description"] = dialog_data["description"]
        return True

    def delete_item(self, package: ManagementPackage, item_id: str) -> bool:
        music_map = package.management.background_music
        if item_id not in music_map:
            return False
        del music_map[item_id]
        return True


class EquipmentDataSection(BaseManagementSection):
    """装备数据管理 Section（对应 `ManagementData.equipment_data`）。"""

    section_key = "equipment_data"
    tree_label = "⚔️ 装备数据"
    type_name = "装备数据"

    def iter_rows(self, package: ManagementPackage) -> Iterable[ManagementRowData]:
        slot_label_map = {
            "weapon": "武器",
            "head": "头部",
            "body": "身体",
            "legs": "腿部",
            "feet": "鞋子",
            "shield": "盾牌",
            "accessory": "饰品",
        }

        for equipment_id, equipment_data in package.management.equipment_data.items():
            if not isinstance(equipment_data, dict):
                continue

            equipment_name_value = str(equipment_data.get("equipment_name", ""))
            slot_value = str(equipment_data.get("equipment_slot", ""))
            slot_label = slot_label_map.get(slot_value, slot_value or "未设置")
            rarity_value = str(equipment_data.get("rarity", "common"))
            level_requirement_value = equipment_data.get("level_requirement", 1)

            description_text = str(equipment_data.get("description", ""))

            yield ManagementRowData(
                name=equipment_name_value or equipment_id,
                type_name=self.type_name,
                attr1=f"槽位: {slot_label}",
                attr2=f"稀有度: {rarity_value}",
                attr3=f"等级需求: {level_requirement_value}",
                description=description_text,
                last_modified=self._get_last_modified_text(equipment_data),
                user_data=(self.section_key, equipment_id),
            )

    def _build_form(
        self,
        parent_widget: QtWidgets.QWidget,
        *,
        title: str,
        initial: Optional[Dict[str, Any]],
        allow_edit_id: bool,
        existing_ids: Optional[set[str]],
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

        builder = FormDialogBuilder(parent_widget, title, fixed_size=(480, 460))

        equipment_id_value = str(initial_values.get("equipment_id", ""))
        id_edit = builder.add_line_edit(
            "装备ID*:",
            equipment_id_value,
            "用于在数据中唯一标识该装备",
            read_only=not allow_edit_id,
        )
        if not allow_edit_id:
            id_edit.setStyleSheet(ThemeManager.readonly_input_style())

        name_edit = builder.add_line_edit(
            "装备名称*:",
            str(initial_values.get("equipment_name", "")),
        )

        slot_combo = builder.add_combo_box(
            "装备槽位:",
            ["weapon", "head", "body", "legs", "feet", "shield", "accessory"],
            str(initial_values.get("equipment_slot", "weapon")),
        )

        rarity_combo = builder.add_combo_box(
            "稀有度:",
            ["common", "uncommon", "rare", "epic", "legendary"],
            str(initial_values.get("rarity", "common")),
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

        desc_edit = builder.add_plain_text_edit(
            "描述:",
            str(initial_values.get("description", "")),
            min_height=80,
            max_height=200,
        )

        normalized_existing_ids: set[str] = set()
        if existing_ids is not None:
            for value in existing_ids:
                normalized_existing_ids.add(str(value))

        def _validate(dialog_self: QtWidgets.QDialog) -> bool:
            from ui.foundation import dialog_utils

            entered_id = id_edit.text().strip()
            equipment_name_text = name_edit.text().strip()

            if not entered_id:
                dialog_utils.show_warning_dialog(
                    dialog_self,
                    "提示",
                    "请输入装备ID",
                )
                return False

            if allow_edit_id and normalized_existing_ids:
                original_id = str(initial_values.get("equipment_id", ""))
                if entered_id != original_id and entered_id in normalized_existing_ids:
                    dialog_utils.show_warning_dialog(
                        dialog_self,
                        "提示",
                        "该装备ID已存在，请使用其他标识",
                    )
                    return False

            if not equipment_name_text:
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

        if allow_edit_id:
            final_id = id_edit.text().strip()
        else:
            final_id = equipment_id_value

        return {
            "equipment_id": final_id,
            "equipment_name": name_edit.text().strip(),
            "equipment_slot": str(slot_combo.currentText()),
            "rarity": str(rarity_combo.currentText()),
            "level_requirement": int(level_spin.value()),
            "icon": icon_edit.text().strip(),
            "model": model_edit.text().strip(),
            "description": desc_edit.toPlainText().strip(),
        }

    def create_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
    ) -> bool:
        equipment_map = package.management.equipment_data
        existing_ids: set[str] = set(equipment_map.keys())

        suggested_id = generate_prefixed_id(self.section_key)
        while suggested_id in existing_ids:
            suggested_id = generate_prefixed_id(self.section_key)

        initial_values = {"equipment_id": suggested_id}
        dialog_data = self._build_form(
            parent_widget,
            title="添加装备",
            initial=initial_values,
            allow_edit_id=True,
            existing_ids=existing_ids,
        )
        if dialog_data is None:
            return False

        equipment_id_value = dialog_data["equipment_id"]
        equipment_config = EquipmentDataConfig(
            equipment_id=equipment_id_value,
            equipment_name=dialog_data["equipment_name"] or f"装备_{equipment_id_value}",
            equipment_slot=dialog_data["equipment_slot"],
            rarity=dialog_data["rarity"],
            level_requirement=dialog_data["level_requirement"],
            icon=dialog_data["icon"],
            model=dialog_data["model"],
            description=dialog_data["description"],
        )
        equipment_map[equipment_id_value] = equipment_config.serialize()
        return True

    def edit_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
    ) -> bool:
        equipment_map = package.management.equipment_data
        equipment_data = equipment_map.get(item_id)
        if equipment_data is None:
            from ui.foundation import dialog_utils

            dialog_utils.show_warning_dialog(
                parent_widget,
                "提示",
                "未找到对应装备",
            )
            return False

        initial_values = {
            "equipment_id": item_id,
            "equipment_name": equipment_data.get("equipment_name", ""),
            "equipment_slot": equipment_data.get("equipment_slot", "weapon"),
            "rarity": equipment_data.get("rarity", "common"),
            "level_requirement": equipment_data.get("level_requirement", 1),
            "icon": equipment_data.get("icon", ""),
            "model": equipment_data.get("model", ""),
            "description": equipment_data.get("description", ""),
        }
        dialog_data = self._build_form(
            parent_widget,
            title="编辑装备",
            initial=initial_values,
            allow_edit_id=False,
            existing_ids=None,
        )
        if dialog_data is None:
            return False

        equipment_data["equipment_name"] = dialog_data["equipment_name"]
        equipment_data["equipment_slot"] = dialog_data["equipment_slot"]
        equipment_data["rarity"] = dialog_data["rarity"]
        equipment_data["level_requirement"] = dialog_data["level_requirement"]
        equipment_data["icon"] = dialog_data["icon"]
        equipment_data["model"] = dialog_data["model"]
        equipment_data["description"] = dialog_data["description"]
        return True

    def delete_item(self, package: ManagementPackage, item_id: str) -> bool:
        equipment_map = package.management.equipment_data
        if item_id not in equipment_map:
            return False
        equipment_map.pop(item_id, None)
        return True


__all__ = [
    "SkillResourceSection",
    "BackgroundMusicSection",
    "EquipmentDataSection",
]












