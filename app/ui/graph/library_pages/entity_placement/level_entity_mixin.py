"""实体摆放页面的关卡实体逻辑。"""

from __future__ import annotations

from typing import Optional

from PyQt6 import QtWidgets

from app.ui.foundation.id_generator import generate_prefixed_id
from app.ui.graph.library_pages.entity_placement.constants import (
    DEFAULT_VECTOR3,
    ENTITY_TYPE_ROLE,
    INSTANCE_ID_ROLE,
    LEVEL_ENTITY_ICON,
    SEARCH_TEXT_ROLE,
    VECTOR_DISPLAY_DECIMALS,
    format_vector3,
)
from engine.graph.models.package_model import InstanceConfig
from engine.resources.global_resource_view import GlobalResourceView
from engine.resources.package_view import PackageView


class EntityPlacementLevelEntityMixin:
    """实体摆放页面关卡实体 mixin。"""

    def _is_level_entity_instance_id(self, instance_id: str) -> bool:
        """判断给定 instance_id 是否为当前视图的关卡实体。"""
        if not self.current_package:
            return False
        level_entity = getattr(self.current_package, "level_entity", None)
        if not level_entity:
            return False
        level_instance_id = getattr(level_entity, "instance_id", "")
        return isinstance(level_instance_id, str) and level_instance_id == instance_id

    def _rebuild_level_entity_view(self, previously_selected_id: Optional[str]) -> None:
        """在关卡实体分类下重建右侧列表。"""
        _ = previously_selected_id
        level_entity = getattr(self.current_package, "level_entity", None) if self.current_package else None
        if not level_entity:
            return

        level_entity_item = self._create_level_entity_item(level_entity)
        self.entity_list.addItem(level_entity_item)
        self.entity_list.setCurrentRow(0)
        self._emit_current_selection_or_clear()

    def _append_level_entity_in_all_category(self, displayed_instance_ids: set[str]) -> None:
        """在全部实体分类下追加关卡实体条目。"""
        if not self.current_package:
            return

        level_entity = getattr(self.current_package, "level_entity", None)
        if not level_entity:
            return

        if not isinstance(level_entity.instance_id, str):
            return
        if level_entity.instance_id in displayed_instance_ids:
            return

        level_entity_item = self._create_level_entity_item(level_entity)
        self.entity_list.addItem(level_entity_item)
        displayed_instance_ids.add(level_entity.instance_id)

    def _create_level_entity_item(self, level_entity: InstanceConfig) -> QtWidgets.QListWidgetItem:
        """构造关卡实体在列表中的展示项。"""
        metadata = getattr(level_entity, "metadata", {}) or {}
        guid_text = ""
        if isinstance(metadata, dict):
            raw_guid = metadata.get("guid")
            if raw_guid is not None:
                guid_text = str(raw_guid)

        position_text = format_vector3(level_entity.position, decimals=VECTOR_DISPLAY_DECIMALS)
        rotation_text = format_vector3(level_entity.rotation, decimals=VECTOR_DISPLAY_DECIMALS)

        item = QtWidgets.QListWidgetItem(f"{LEVEL_ENTITY_ICON} {level_entity.name}")
        item.setData(INSTANCE_ID_ROLE, level_entity.instance_id)
        item.setData(ENTITY_TYPE_ROLE, "关卡")

        tooltip_lines: list[str] = [
            f"实体名称: {level_entity.name}",
            "实体类型: 关卡实体",
            f"位置: {position_text}",
            f"旋转: {rotation_text}",
        ]
        if guid_text:
            tooltip_lines.append(f"GUID: {guid_text}")
        item.setToolTip("\n".join(tooltip_lines))

        search_tokens = [
            level_entity.name,
            "关卡实体",
            "关卡",
            guid_text,
            position_text,
            rotation_text,
        ]
        search_value = " ".join(token for token in search_tokens if token)
        item.setData(SEARCH_TEXT_ROLE, search_value.lower())
        return item

    def _ensure_level_entity_exists(self) -> None:
        """确保当前视图存在关卡实体实例。"""
        if not self.current_package:
            return

        level_entity = getattr(self.current_package, "level_entity", None)
        if level_entity:
            return

        if isinstance(self.current_package, PackageView):
            existing: Optional[InstanceConfig] = None
            for instance in self.current_package.instances.values():
                metadata = getattr(instance, "metadata", {}) or {}
                if isinstance(metadata, dict) and metadata.get("is_level_entity"):
                    existing = instance
                    break

            index = self.current_package.package_index
            if existing:
                index.level_entity_id = existing.instance_id
                if existing.instance_id not in index.resources.instances:
                    index.add_instance(existing.instance_id)
                self.current_package.update_level_entity(existing)
                return

            package_id = getattr(self.current_package, "package_id", "")
            instance_id = f"level_{package_id}" if package_id else generate_prefixed_id("level")
            new_level = InstanceConfig(
                instance_id=instance_id,
                name="关卡实体",
                template_id=instance_id,
                position=list(DEFAULT_VECTOR3),
                rotation=list(DEFAULT_VECTOR3),
                metadata={"is_level_entity": True, "entity_type": "关卡"},
            )

            index.level_entity_id = instance_id
            index.add_instance(instance_id)
            self.current_package.update_level_entity(new_level)
            return

        if isinstance(self.current_package, GlobalResourceView):
            instance_id = generate_prefixed_id("level")
            new_level = InstanceConfig(
                instance_id=instance_id,
                name="关卡实体",
                template_id=instance_id,
                position=list(DEFAULT_VECTOR3),
                rotation=list(DEFAULT_VECTOR3),
                metadata={"is_level_entity": True, "entity_type": "关卡"},
            )
            self.current_package.add_instance(new_level)

