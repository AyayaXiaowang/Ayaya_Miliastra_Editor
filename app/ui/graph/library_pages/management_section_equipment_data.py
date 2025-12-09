from __future__ import annotations

from .management_sections_base import *


def _is_entry_payload(payload: Mapping[str, Any]) -> bool:
    """判断给定装备管理记录是否为“装备词条”类型。"""
    entry_name_value = payload.get("entry_name")
    entry_type_value = payload.get("entry_type")
    if isinstance(entry_name_value, str) and entry_name_value.strip():
        return True
    if isinstance(entry_type_value, str) and entry_type_value.strip():
        return True
    return False


def _is_tag_payload(payload: Mapping[str, Any]) -> bool:
    """判断给定装备管理记录是否为“装备标签”类型。"""
    tag_name_value = payload.get("tag_name")
    if isinstance(tag_name_value, str) and tag_name_value.strip():
        return True
    return False


def _is_type_payload(payload: Mapping[str, Any]) -> bool:
    """判断给定装备管理记录是否为“装备类型”类型。"""
    type_name_value = payload.get("type_name")
    allowed_slots_value = payload.get("allowed_slots")
    if isinstance(type_name_value, str) and type_name_value.strip():
        return True
    if isinstance(allowed_slots_value, list) and allowed_slots_value:
        return True
    return False


class EquipmentEntrySection(BaseManagementSection):
    """装备词条管理 Section（`ManagementData.equipment_data` 中的词条记录）。

    约定：
    - 仅枚举 payload 中具有 `entry_name`/`entry_type` 等字段的记录；
    - 其余记录（装备模板、标签、类型等）交由对应 Section 负责。
    """

    section_key = "equipment_entries"
    tree_label = "⚔️ 装备数据管理-词条"
    type_name = "装备词条"

    def iter_rows(self, package: ManagementPackage) -> Iterable[ManagementRowData]:
        equipment_map = package.management.equipment_data
        if not isinstance(equipment_map, dict):
            return

        for storage_id, payload_any in equipment_map.items():
            if not isinstance(payload_any, dict):
                continue
            if not _is_entry_payload(payload_any):
                continue

            payload = payload_any

            entry_name_raw = payload.get("entry_name")
            entry_name_text = str(entry_name_raw) if entry_name_raw is not None else ""

            config_id_raw = payload.get("config_id")
            config_id_text = str(config_id_raw).strip() if config_id_raw is not None else ""

            effect_timing_text = str(payload.get("effect_timing", "")).strip()
            entry_type_text = str(payload.get("entry_type", "")).strip()
            description_text = str(payload.get("custom_description", "")).strip()

            attr1_text = f"配置ID: {config_id_text or '（未设置）'}"
            attr2_text = f"生效时机: {effect_timing_text or '（未设置）'}"
            attr3_text = f"词条类型: {entry_type_text or '（未设置）'}"

            display_name = entry_name_text.strip() or config_id_text or str(storage_id)

            yield ManagementRowData(
                name=display_name,
                type_name=self.type_name,
                attr1=attr1_text,
                attr2=attr2_text,
                attr3=attr3_text,
                description=description_text,
                last_modified=self._get_last_modified_text(payload),
                user_data=(self.section_key, str(storage_id)),
            )

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

        existing_ids: set[str] = {str(storage_id) for storage_id in equipment_map.keys()}

        storage_id = generate_prefixed_id("equipment_entry")
        while storage_id in existing_ids:
            storage_id = generate_prefixed_id("equipment_entry")

        existing_entry_count = 0
        for payload_any in equipment_map.values():
            if isinstance(payload_any, dict) and _is_entry_payload(payload_any):
                existing_entry_count += 1
        default_index = existing_entry_count + 1
        default_name = f"词条{default_index}"

        payload: Dict[str, Any] = {
            "entry_name": default_name,
            "config_id": "0",
            "effect_timing": "获取时生效",
            "entry_type": "基础属性加成",
            "attribute_type": "",
            "bonus_type": "固定值",
            "random_range": [0.0, 0.0],
            "fixed_bonus": 0.0,
            "description_type": "固定描述",
            "custom_description": "",
            "related_node_graph": "",
            "related_unit_state": "",
            "metadata": {},
        }
        equipment_map[storage_id] = payload
        return True

    def edit_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
    ) -> bool:
        _ = (parent_widget, package, item_id)
        # 装备词条的编辑行为由右侧专用面板承担，此处不再弹出对话框。
        return False

    def delete_item(self, package: ManagementPackage, item_id: str) -> bool:
        equipment_map = package.management.equipment_data
        if not isinstance(equipment_map, dict):
            return False
        payload_any = equipment_map.get(item_id)
        if not isinstance(payload_any, dict):
            return False
        if not _is_entry_payload(payload_any):
            return False
        equipment_map.pop(item_id, None)
        return True


class EquipmentTagSection(BaseManagementSection):
    """装备标签管理 Section（`ManagementData.equipment_data` 中的标签记录）。"""

    section_key = "equipment_tags"
    tree_label = "⚔️ 装备数据管理-标签"
    type_name = "装备标签"

    def iter_rows(self, package: ManagementPackage) -> Iterable[ManagementRowData]:
        equipment_map = package.management.equipment_data
        if not isinstance(equipment_map, dict):
            return

        for storage_id, payload_any in equipment_map.items():
            if not isinstance(payload_any, dict):
                continue
            if not _is_tag_payload(payload_any):
                continue

            payload = payload_any

            tag_name_raw = payload.get("tag_name")
            tag_name_text = str(tag_name_raw) if tag_name_raw is not None else ""

            config_id_raw = payload.get("config_id")
            config_id_text = str(config_id_raw).strip() if config_id_raw is not None else ""

            description_text = str(payload.get("description", "")).strip()

            attr1_text = f"配置ID: {config_id_text or '（未设置）'}"
            attr2_text = ""
            attr3_text = ""

            display_name = tag_name_text.strip() or config_id_text or str(storage_id)

            yield ManagementRowData(
                name=display_name,
                type_name=self.type_name,
                attr1=attr1_text,
                attr2=attr2_text,
                attr3=attr3_text,
                description=description_text,
                last_modified=self._get_last_modified_text(payload),
                user_data=(self.section_key, str(storage_id)),
            )

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

        existing_ids: set[str] = {str(storage_id) for storage_id in equipment_map.keys()}

        storage_id = generate_prefixed_id("equipment_tag")
        while storage_id in existing_ids:
            storage_id = generate_prefixed_id("equipment_tag")

        existing_tag_count = 0
        for payload_any in equipment_map.values():
            if isinstance(payload_any, dict) and _is_tag_payload(payload_any):
                existing_tag_count += 1
        default_index = existing_tag_count + 1
        default_name = f"标签{default_index}"

        payload: Dict[str, Any] = {
            "tag_name": default_name,
            "config_id": "0",
            "description": "",
            "metadata": {},
        }
        equipment_map[storage_id] = payload
        return True

    def edit_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
    ) -> bool:
        _ = (parent_widget, package, item_id)
        # 装备标签的编辑由右侧专用面板完成。
        return False

    def delete_item(self, package: ManagementPackage, item_id: str) -> bool:
        equipment_map = package.management.equipment_data
        if not isinstance(equipment_map, dict):
            return False
        payload_any = equipment_map.get(item_id)
        if not isinstance(payload_any, dict):
            return False
        if not _is_tag_payload(payload_any):
            return False
        equipment_map.pop(item_id, None)
        return True


class EquipmentTypeSection(BaseManagementSection):
    """装备类型管理 Section（`ManagementData.equipment_data` 中的类型记录）。"""

    section_key = "equipment_types"
    tree_label = "⚔️ 装备数据管理-类型"
    type_name = "装备类型"

    def iter_rows(self, package: ManagementPackage) -> Iterable[ManagementRowData]:
        equipment_map = package.management.equipment_data
        if not isinstance(equipment_map, dict):
            return

        for storage_id, payload_any in equipment_map.items():
            if not isinstance(payload_any, dict):
                continue
            if not _is_type_payload(payload_any):
                continue

            payload = payload_any

            type_name_raw = payload.get("type_name")
            type_name_text = str(type_name_raw) if type_name_raw is not None else ""

            config_id_raw = payload.get("config_id")
            config_id_text = str(config_id_raw).strip() if config_id_raw is not None else ""

            description_text = str(payload.get("description", "")).strip()

            allowed_slots_any = payload.get("allowed_slots", [])
            allowed_slots_list: list[str] = []
            if isinstance(allowed_slots_any, list):
                for slot_value in allowed_slots_any:
                    if isinstance(slot_value, str) and slot_value.strip():
                        allowed_slots_list.append(slot_value.strip())
            allowed_slots_text = ", ".join(allowed_slots_list) if allowed_slots_list else "（未设置）"

            attr1_text = f"配置ID: {config_id_text or '（未设置）'}"
            attr2_text = f"可装备槽位: {allowed_slots_text}"
            attr3_text = ""

            display_name = type_name_text.strip() or config_id_text or str(storage_id)

            yield ManagementRowData(
                name=display_name,
                type_name=self.type_name,
                attr1=attr1_text,
                attr2=attr2_text,
                attr3=attr3_text,
                description=description_text,
                last_modified=self._get_last_modified_text(payload),
                user_data=(self.section_key, str(storage_id)),
            )

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

        existing_ids: set[str] = {str(storage_id) for storage_id in equipment_map.keys()}

        storage_id = generate_prefixed_id("equipment_type")
        while storage_id in existing_ids:
            storage_id = generate_prefixed_id("equipment_type")

        existing_type_count = 0
        for payload_any in equipment_map.values():
            if isinstance(payload_any, dict) and _is_type_payload(payload_any):
                existing_type_count += 1
        default_index = existing_type_count + 1
        default_name = f"类型{default_index}"

        payload: Dict[str, Any] = {
            "type_name": default_name,
            "config_id": "0",
            "description": "",
            "allowed_slots": [],
            "metadata": {},
        }
        equipment_map[storage_id] = payload
        return True

    def edit_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
    ) -> bool:
        _ = (parent_widget, package, item_id)
        # 装备类型的详细编辑由右侧专用面板完成。
        return False

    def delete_item(self, package: ManagementPackage, item_id: str) -> bool:
        equipment_map = package.management.equipment_data
        if not isinstance(equipment_map, dict):
            return False
        payload_any = equipment_map.get(item_id)
        if not isinstance(payload_any, dict):
            return False
        if not _is_type_payload(payload_any):
            return False
        equipment_map.pop(item_id, None)
        return True


__all__ = [
    "EquipmentEntrySection",
    "EquipmentTagSection",
    "EquipmentTypeSection",
]
