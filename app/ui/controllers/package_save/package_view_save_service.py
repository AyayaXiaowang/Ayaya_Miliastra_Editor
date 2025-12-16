"""具体存档视图（PackageView）保存服务。"""

from __future__ import annotations

from typing import Callable

from engine.resources.package_index import PackageIndex
from engine.resources.package_index_manager import PackageIndexManager
from engine.resources.package_view import PackageView
from engine.resources.resource_manager import ResourceManager
from app.ui.controllers.package_dirty_state import PackageDirtyState

from .combat_presets_save_service import CombatPresetsSaveService
from .fingerprint_baseline_service import FingerprintBaselineService
from .management_save_service import ManagementSaveService
from .package_index_persist_service import PackageIndexPersistService
from .resource_container_save_service import ResourceContainerSaveService
from .signals_save_service import SignalsSaveService


class PackageViewSaveService:
    def __init__(
        self,
        *,
        resource_manager: ResourceManager,
        package_index_manager: PackageIndexManager,
        fingerprint_baseline_service: FingerprintBaselineService,
        resource_container_saver: ResourceContainerSaveService,
        get_current_graph_container: Callable[[], object | None],
        get_property_panel_object_type: Callable[[], str | None],
    ):
        self._resource_manager = resource_manager
        self._package_index_manager = package_index_manager
        self._fingerprint_baseline_service = fingerprint_baseline_service
        self._resource_container_saver = resource_container_saver
        self._get_current_graph_container = get_current_graph_container
        self._get_property_panel_object_type = get_property_panel_object_type

        self._combat_presets_save_service = CombatPresetsSaveService(resource_manager)
        self._signals_save_service = SignalsSaveService(resource_manager)
        self._management_save_service = ManagementSaveService(resource_manager)
        self._index_persist_service = PackageIndexPersistService(
            package_index_manager,
            fingerprint_baseline_service,
        )

    def save(
        self,
        *,
        current_package_id: str | None,
        package: PackageView,
        package_index: PackageIndex,
        dirty_snapshot: PackageDirtyState,
        force_full: bool,
        request_save_current_graph: Callable[[], None],
    ) -> bool:
        """在具体存档视图下保存按需落盘的脏块。"""
        did_write = False
        need_save_index = False

        if force_full or dirty_snapshot.graph_dirty:
            request_save_current_graph()
            did_write = True

        if force_full:
            saved_resources = self._save_package_resources()
        else:
            saved_resources = self._resource_container_saver.save_resources_for_ids(
                package,
                dirty_snapshot.template_ids,
                dirty_snapshot.instance_ids,
                dirty_snapshot.level_entity_dirty,
                verbose=False,
            )
        did_write = did_write or saved_resources

        if force_full or dirty_snapshot.combat_dirty:
            self._combat_presets_save_service.sync_to_index(
                package=package,
                package_index=package_index,
            )
            need_save_index = True
            did_write = True

        if force_full or dirty_snapshot.signals_dirty:
            self._signals_save_service.sync_to_index(
                package=package,
                package_index=package_index,
            )
            need_save_index = True

        if force_full or dirty_snapshot.full_management_sync or dirty_snapshot.management_keys:
            allowed_keys = (
                None
                if force_full or dirty_snapshot.full_management_sync
                else set(dirty_snapshot.management_keys)
            )
            self._management_save_service.sync_to_index(
                package=package,
                package_index=package_index,
                allowed_keys=allowed_keys,
            )
            need_save_index = True
            did_write = True

        if dirty_snapshot.index_dirty:
            need_save_index = True

        if need_save_index:
            self._index_persist_service.persist(
                package_index=package_index,
                current_package_id=current_package_id,
            )
            did_write = True
        elif did_write:
            self._index_persist_service.refresh_after_write()

        return did_write

    def _save_package_resources(self) -> bool:
        """保存当前属性上下文对应的资源到 ResourceManager。"""
        return self._resource_container_saver.save_current_property_context(
            self._get_current_graph_container,
            self._get_property_panel_object_type,
            verbose=False,
        )
