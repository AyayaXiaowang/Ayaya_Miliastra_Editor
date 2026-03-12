"""实体摆放页面的实例列表构建与刷新逻辑。"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any, Optional

from PyQt6 import QtWidgets

from app.ui.foundation.shared_resource_badge_delegate import SHARED_RESOURCE_BADGE_ROLE
from app.ui.graph.library_mixins import rebuild_list_with_preserved_selection
from app.ui.graph.library_pages.entity_placement.constants import (
    CATEGORY_ALL,
    CATEGORY_LEVEL_ENTITY,
    ENTITY_TYPE_ROLE,
    INSTANCE_ID_ROLE,
    IS_SHARED_INSTANCE_ROLE,
    SEARCH_TEXT_ROLE,
    VECTOR_DISPLAY_DECIMALS,
    format_vector3,
)
from engine.configs.resource_types import ResourceType
from engine.graph.models.entity_templates import (
    get_entity_type_info,
    get_template_library_entity_types,
)
from engine.graph.models.package_model import InstanceConfig, TemplateConfig
from engine.resources.resource_manager import ResourceManager
from engine.utils.resource_library_layout import get_shared_root_dir


_SPECIAL_TEMPLATE_CATEGORIES = {"元件组", "掉落物"}


class EntityPlacementInstanceListMixin:
    """实体摆放页面实例列表 mixin。"""

    def _rebuild_instances(self) -> None:
        """根据当前分类重建右侧实体列表。"""
        previously_selected_id = self._current_instance_id()
        if not self.current_package:
            self.entity_list.clear()
            return

        effective_category = self.current_category or CATEGORY_ALL
        if effective_category == CATEGORY_LEVEL_ENTITY:
            self.entity_list.clear()
            self._rebuild_level_entity_view(previously_selected_id)
            return

        allowed_types = set(get_template_library_entity_types())
        shared_instance_ids = self._collect_shared_instance_ids()
        build_items = functools.partial(
            self._build_instance_items,
            effective_category=effective_category,
            allowed_types=allowed_types,
            shared_instance_ids=shared_instance_ids,
        )
        on_cleared = functools.partial(
            self._emit_empty_selection_after_rebuild,
            previously_selected_id=previously_selected_id,
        )

        rebuild_list_with_preserved_selection(
            self.entity_list,
            previous_key=previously_selected_id,
            had_selection_before_refresh=bool(previously_selected_id),
            build_items=build_items,
            key_getter=self._get_instance_item_key,
            on_restored_selection=self._emit_selection_for_instance_key,
            on_first_selection=self._emit_selection_for_instance_key,
            on_cleared_selection=on_cleared,
        )

    def _collect_shared_instance_ids(self) -> set[str]:
        """从资源路径推导属于 shared 根目录的实例 ID 集合。"""
        shared_instance_ids: set[str] = set()
        resource_manager_candidate = getattr(self.current_package, "resource_manager", None)
        if not isinstance(resource_manager_candidate, ResourceManager):
            return shared_instance_ids

        resource_library_dir = getattr(resource_manager_candidate, "resource_library_dir", None)
        if not isinstance(resource_library_dir, Path):
            return shared_instance_ids

        shared_root_dir = get_shared_root_dir(resource_library_dir)
        shared_root_abs = shared_root_dir if shared_root_dir.is_absolute() else shared_root_dir.absolute()
        shared_parts = tuple(part.casefold() for part in shared_root_abs.parts)

        instance_paths = resource_manager_candidate.list_resource_file_paths(ResourceType.INSTANCE)
        for resource_id, file_path in instance_paths.items():
            if not isinstance(resource_id, str) or not resource_id:
                continue
            if not isinstance(file_path, Path):
                continue

            file_abs = file_path if file_path.is_absolute() else file_path.absolute()
            if hasattr(file_abs, "is_relative_to"):
                if file_abs.is_relative_to(shared_root_abs):  # type: ignore[attr-defined]
                    shared_instance_ids.add(resource_id)
                continue

            file_parts = tuple(part.casefold() for part in file_abs.parts)
            if len(file_parts) >= len(shared_parts) and file_parts[: len(shared_parts)] == shared_parts:
                shared_instance_ids.add(resource_id)

        return shared_instance_ids

    def _build_instance_items(
        self,
        *,
        effective_category: str,
        allowed_types: set[str],
        shared_instance_ids: set[str],
    ) -> None:
        """向列表插入当前分类下的实例条目。"""
        displayed_instance_ids: set[str] = set()

        for instance_id, instance in self.current_package.instances.items():
            template = self.current_package.get_template(instance.template_id)
            resolved_entity_type, template_category, template_name = self._resolve_instance_entity_info(
                template=template,
                instance=instance,
            )
            if not self._should_include_instance(
                effective_category=effective_category,
                resolved_entity_type=resolved_entity_type,
                allowed_types=allowed_types,
            ):
                continue

            icon, display_type = self._resolve_instance_icon_and_type(
                resolved_entity_type=resolved_entity_type,
                template_category=template_category,
            )
            guid_text = self._resolve_instance_guid(instance)
            position_text = format_vector3(instance.position, decimals=VECTOR_DISPLAY_DECIMALS)
            rotation_text = format_vector3(instance.rotation, decimals=VECTOR_DISPLAY_DECIMALS)
            is_shared_instance = instance_id in shared_instance_ids

            list_item = self._create_instance_list_item(
                instance_id=instance_id,
                instance=instance,
                icon=icon,
                resolved_entity_type=resolved_entity_type,
                display_type=display_type,
                template_name=template_name,
                guid_text=guid_text,
                position_text=position_text,
                rotation_text=rotation_text,
                is_shared_instance=is_shared_instance,
            )
            self.entity_list.addItem(list_item)
            displayed_instance_ids.add(instance_id)

        if effective_category == CATEGORY_ALL:
            self._append_level_entity_in_all_category(displayed_instance_ids)

    def _resolve_instance_entity_info(
        self, *, template: TemplateConfig | None, instance: InstanceConfig
    ) -> tuple[str, str, str]:
        """从 template/instance 推导 entity_type、template_category 与 template_name。"""
        resolved_entity_type = ""
        template_category = ""
        template_name = ""

        if template is not None:
            template_name = str(getattr(template, "name", "") or "").strip()
            resolved_entity_type = str(getattr(template, "entity_type", "") or "").strip()
            template_metadata = getattr(template, "metadata", {}) or {}
            if isinstance(template_metadata, dict):
                category_value = template_metadata.get("template_category") or template_metadata.get("category")
                if isinstance(category_value, str):
                    template_category = category_value.strip()
        else:
            instance_metadata = getattr(instance, "metadata", {}) or {}
            if isinstance(instance_metadata, dict):
                entity_type_value = instance_metadata.get("entity_type")
                if isinstance(entity_type_value, str):
                    resolved_entity_type = entity_type_value.strip()
                category_value = instance_metadata.get("template_category") or instance_metadata.get("category")
                if isinstance(category_value, str):
                    template_category = category_value.strip()

        return resolved_entity_type, template_category, template_name

    def _should_include_instance(
        self,
        *,
        effective_category: str,
        resolved_entity_type: str,
        allowed_types: set[str],
    ) -> bool:
        """判断实例是否应出现在当前分类下。"""
        if resolved_entity_type and resolved_entity_type not in allowed_types:
            return False
        if effective_category not in (CATEGORY_ALL, "") and resolved_entity_type != effective_category:
            return False
        return True

    def _resolve_instance_icon_and_type(self, *, resolved_entity_type: str, template_category: str) -> tuple[str, str]:
        """解析实例条目的图标与展示类型。"""
        if template_category in _SPECIAL_TEMPLATE_CATEGORIES:
            icon = get_entity_type_info(template_category).get("icon", "📦")
            return icon, template_category

        icon = get_entity_type_info(resolved_entity_type).get("icon", "📦")
        return icon, (resolved_entity_type or "未知")

    def _resolve_instance_guid(self, instance: InstanceConfig) -> str:
        """从实例 metadata 中提取 guid 文本。"""
        instance_metadata = getattr(instance, "metadata", {}) or {}
        if not isinstance(instance_metadata, dict):
            return ""
        raw_guid = instance_metadata.get("guid")
        return str(raw_guid) if raw_guid is not None else ""

    def _create_instance_list_item(
        self,
        *,
        instance_id: str,
        instance: InstanceConfig,
        icon: str,
        resolved_entity_type: str,
        display_type: str,
        template_name: str,
        guid_text: str,
        position_text: str,
        rotation_text: str,
        is_shared_instance: bool,
    ) -> QtWidgets.QListWidgetItem:
        """创建实体列表项并填充 tooltip 与搜索字段。"""
        display_text = f"{icon} {instance.name}"
        list_item = QtWidgets.QListWidgetItem(display_text)
        list_item.setData(INSTANCE_ID_ROLE, instance_id)
        list_item.setData(ENTITY_TYPE_ROLE, resolved_entity_type)
        list_item.setData(IS_SHARED_INSTANCE_ROLE, bool(is_shared_instance))
        list_item.setData(SHARED_RESOURCE_BADGE_ROLE, bool(is_shared_instance))

        tooltip_lines = self._build_instance_tooltip_lines(
            instance=instance,
            display_type=display_type,
            template_name=template_name,
            guid_text=guid_text,
            position_text=position_text,
            rotation_text=rotation_text,
            is_shared_instance=is_shared_instance,
        )
        list_item.setToolTip("\n".join(tooltip_lines))

        search_value = self._build_instance_search_value(
            instance=instance,
            display_type=display_type,
            resolved_entity_type=resolved_entity_type,
            template_name=template_name,
            guid_text=guid_text,
            position_text=position_text,
            rotation_text=rotation_text,
        )
        list_item.setData(SEARCH_TEXT_ROLE, search_value.lower())
        return list_item

    def _build_instance_tooltip_lines(
        self,
        *,
        instance: InstanceConfig,
        display_type: str,
        template_name: str,
        guid_text: str,
        position_text: str,
        rotation_text: str,
        is_shared_instance: bool,
    ) -> list[str]:
        """构造实体列表项 tooltip 文案行。"""
        template_line = template_name if template_name else "(未绑定元件)"
        tooltip_lines: list[str] = [
            f"实体名称: {instance.name}",
            f"实体类型: {display_type}",
            f"元件: {template_line}",
            f"位置: {position_text}",
            f"旋转: {rotation_text}",
        ]
        if is_shared_instance:
            tooltip_lines.insert(0, "归属: 共享（所有存档可见）")

        template_id = str(instance.template_id or "").strip()
        if not template_name and template_id:
            tooltip_lines.append(f"元件ID: {template_id}")
        if guid_text:
            tooltip_lines.append(f"GUID: {guid_text}")
        return tooltip_lines

    def _build_instance_search_value(
        self,
        *,
        instance: InstanceConfig,
        display_type: str,
        resolved_entity_type: str,
        template_name: str,
        guid_text: str,
        position_text: str,
        rotation_text: str,
    ) -> str:
        """构造实体列表项的搜索拼接文本。"""
        search_tokens = [
            str(instance.name or "").strip(),
            template_name,
            display_type,
            resolved_entity_type,
            str(instance.template_id or "").strip(),
            guid_text,
            position_text,
            rotation_text,
        ]
        return " ".join(token for token in search_tokens if token)

    def _get_instance_item_key(self, list_item: QtWidgets.QListWidgetItem) -> Optional[str]:
        """从列表项提取 instance_id 作为业务 key。"""
        value = list_item.data(INSTANCE_ID_ROLE)
        return value if isinstance(value, str) else None

    def _emit_selection_for_instance_key(self, instance_id: Any) -> None:
        """在列表恢复/默认选中后发射选中联动信号。"""
        if not isinstance(instance_id, str) or not instance_id:
            return
        self._emit_current_selection_or_clear()

    def _emit_empty_selection_after_rebuild(self, *, previously_selected_id: Optional[str]) -> None:
        """在列表从有选中变为空时向上层发射空选中。"""
        if not previously_selected_id:
            return
        self.notify_selection_state(False, context={"source": "instance"})
        self.selection_changed.emit(None)

