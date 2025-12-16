"""全局视图/未分类视图保存服务。"""

from __future__ import annotations

from typing import Callable

from engine.resources.global_resource_view import GlobalResourceView
from engine.resources.ingame_save_template_schema_view import (
    get_default_ingame_save_template_schema_view,
    update_default_template_id,
)
from engine.resources.resource_manager import ResourceManager, ResourceType
from engine.resources.unclassified_resource_view import UnclassifiedResourceView
from app.ui.controllers.package_dirty_state import PackageDirtyState

from .fingerprint_baseline_service import FingerprintBaselineService
from .resource_container_save_service import ResourceContainerSaveService
from app.ui.management.section_registry import MANAGEMENT_RESOURCE_BINDINGS


class SpecialViewSaveService:
    def __init__(
        self,
        *,
        resource_manager: ResourceManager,
        fingerprint_baseline_service: FingerprintBaselineService,
        resource_container_saver: ResourceContainerSaveService,
        get_current_graph_container: Callable[[], object | None],
        get_property_panel_object_type: Callable[[], str | None],
    ):
        self._resource_manager = resource_manager
        self._fingerprint_baseline_service = fingerprint_baseline_service
        self._resource_container_saver = resource_container_saver
        self._get_current_graph_container = get_current_graph_container
        self._get_property_panel_object_type = get_property_panel_object_type

    def save(
        self,
        *,
        current_package_id: str | None,
        current_package: object | None,
        dirty_snapshot: PackageDirtyState,
        force_full: bool,
        request_save_current_graph: Callable[[], None],
    ) -> bool:
        """在全局/未分类视图下按需保存。"""
        did_write = False

        if force_full or dirty_snapshot.graph_dirty:
            request_save_current_graph()
            did_write = True

        if current_package is None:
            return did_write

        if (
            force_full
            or dirty_snapshot.template_ids
            or dirty_snapshot.instance_ids
            or dirty_snapshot.level_entity_dirty
        ):
            resource_saved = self._save_global_view_resources(
                current_package,
                allowed_template_ids=None if force_full else dirty_snapshot.template_ids,
                allowed_instance_ids=None if force_full else dirty_snapshot.instance_ids,
            )
            did_write = did_write or resource_saved

        if force_full or dirty_snapshot.combat_dirty:
            self._save_combat_presets_for_special_view(current_package_id, current_package)
            did_write = True

        if force_full or dirty_snapshot.full_management_sync or dirty_snapshot.management_keys:
            allowed_keys = (
                None
                if force_full or dirty_snapshot.full_management_sync
                else set(dirty_snapshot.management_keys)
            )
            self._save_management_for_special_view(current_package, allowed_keys=allowed_keys)
            did_write = True

        if did_write:
            self._fingerprint_baseline_service.refresh_after_write()
            print(
                "[PACKAGE-SAVE] 已保存全局/未分类视图下的资源，"
                f"mode={current_package_id!r}"
            )

        return did_write

    def _save_global_view_resources(
        self,
        package: object,
        *,
        allowed_template_ids: set[str] | None,
        allowed_instance_ids: set[str] | None,
    ) -> bool:
        """保存全局视图模式下修改的资源。"""
        # 优先按传入的 ID 集合保存；若未提供，则回退到当前属性上下文
        if allowed_template_ids or allowed_instance_ids:
            return self._resource_container_saver.save_resources_for_ids(
                package,
                allowed_template_ids or set(),
                allowed_instance_ids or set(),
                save_level_entity=False,
                verbose=True,
            )

        return self._resource_container_saver.save_current_property_context(
            self._get_current_graph_container,
            self._get_property_panel_object_type,
            verbose=True,
        )

    def _save_combat_presets_for_special_view(self, current_package_id: str | None, package: object) -> None:
        """在全局视图/未分类视图下，将战斗预设视图模型写回资源库。"""
        if not isinstance(package, (GlobalResourceView, UnclassifiedResourceView)):
            return

        combat_presets_view = getattr(package, "combat_presets", None)
        if combat_presets_view is None:
            return

        bucket_definitions = [
            ("player_templates", ResourceType.PLAYER_TEMPLATE, "template_id"),
            ("player_classes", ResourceType.PLAYER_CLASS, "class_id"),
            ("unit_statuses", ResourceType.UNIT_STATUS, "status_id"),
            ("skills", ResourceType.SKILL, "skill_id"),
            ("projectiles", ResourceType.PROJECTILE, "projectile_id"),
            ("items", ResourceType.ITEM, "item_id"),
        ]

        for bucket_key, resource_type, id_field in bucket_definitions:
            bucket_mapping_any = getattr(combat_presets_view, bucket_key, None)
            if not isinstance(bucket_mapping_any, dict):
                continue

            bucket_mapping = bucket_mapping_any
            print(
                "[COMBAT-PRESETS] special-view bucket 写回：",
                f"mode={current_package_id!r}, bucket_key={bucket_key!r}, "
                f"preset_count={len(bucket_mapping)}",
            )

            for preset_id, payload_any in bucket_mapping.items():
                if not isinstance(preset_id, str) or not preset_id:
                    continue
                if not isinstance(payload_any, dict):
                    continue

                payload = payload_any
                if "id" not in payload:
                    payload["id"] = preset_id
                specific_id_value = payload.get(id_field)
                if not isinstance(specific_id_value, str) or not specific_id_value:
                    payload[id_field] = preset_id

                self._resource_manager.save_resource(resource_type, preset_id, payload)

    def _save_management_for_special_view(self, package: object, *, allowed_keys: set[str] | None) -> None:
        """在全局视图/未分类视图下，将管理页面编辑的配置直接写回管理配置资源。"""
        management = getattr(package, "management", None)
        if management is None:
            return

        single_config_fields = {
            "currency_backpack",
            "peripheral_systems",
            "level_settings",
        }

        for resource_key, resource_type in MANAGEMENT_RESOURCE_BINDINGS.items():
            if allowed_keys is not None and resource_key not in allowed_keys:
                continue
            if resource_key in {"signals", "struct_definitions"}:
                continue
            if resource_key == "level_variables":
                continue

            value = getattr(management, resource_key, None)

            if resource_key == "save_points":
                self._save_single_config_save_points(value)
                continue

            if resource_key in single_config_fields:
                if not isinstance(value, dict) or not value:
                    continue
                resource_id = f"global_view_{resource_key}"
                self._resource_manager.save_resource(resource_type, resource_id, dict(value))
                continue

            if not isinstance(value, dict):
                continue

            for resource_id, payload in value.items():
                if not isinstance(resource_id, str) or not resource_id:
                    continue
                if not isinstance(payload, dict):
                    continue
                self._resource_manager.save_resource(resource_type, resource_id, payload)

    def _save_single_config_save_points(self, raw_value: object) -> None:
        """在全局/未分类视图下，将 management.save_points 的“当前模板状态”写回模板。"""
        if not isinstance(raw_value, dict):
            return

        enabled_flag = bool(raw_value.get("enabled", False))
        active_template_id = str(raw_value.get("active_template_id", "")).strip()

        schema_view = get_default_ingame_save_template_schema_view()
        all_templates = schema_view.get_all_templates()

        if enabled_flag and active_template_id:
            if active_template_id not in all_templates:
                enabled_flag = False
                active_template_id = ""
                raw_value["enabled"] = False
                raw_value["active_template_id"] = ""

        if enabled_flag and active_template_id:
            update_default_template_id(active_template_id)
        else:
            update_default_template_id(None)


