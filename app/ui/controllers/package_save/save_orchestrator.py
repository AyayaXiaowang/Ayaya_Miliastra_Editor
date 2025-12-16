"""存档保存事务编排服务（从 PackageController 中抽离）。"""

from __future__ import annotations

from typing import Callable

from engine.resources.package_index import PackageIndex
from engine.resources.package_index_manager import PackageIndexManager
from engine.resources.package_view import PackageView
from engine.resources.resource_manager import ResourceManager
from app.ui.controllers.package_dirty_state import PackageDirtyState

from .fingerprint_baseline_service import FingerprintBaselineService
from .package_view_save_service import PackageViewSaveService
from .resource_container_save_service import ResourceContainerSaveService
from .special_view_save_service import SpecialViewSaveService


class PackageSaveOrchestrator:
    def __init__(
        self,
        *,
        resource_manager: ResourceManager,
        package_index_manager: PackageIndexManager,
        get_current_graph_container: Callable[[], object | None],
        get_property_panel_object_type: Callable[[], str | None],
    ):
        self._fingerprint_baseline_service = FingerprintBaselineService(resource_manager)
        self._resource_container_saver = ResourceContainerSaveService(resource_manager)
        self._special_view_save_service = SpecialViewSaveService(
            resource_manager=resource_manager,
            fingerprint_baseline_service=self._fingerprint_baseline_service,
            resource_container_saver=self._resource_container_saver,
            get_current_graph_container=get_current_graph_container,
            get_property_panel_object_type=get_property_panel_object_type,
        )
        self._package_view_save_service = PackageViewSaveService(
            resource_manager=resource_manager,
            package_index_manager=package_index_manager,
            fingerprint_baseline_service=self._fingerprint_baseline_service,
            resource_container_saver=self._resource_container_saver,
            get_current_graph_container=get_current_graph_container,
            get_property_panel_object_type=get_property_panel_object_type,
        )

    def save(
        self,
        *,
        current_package_id: str | None,
        current_package: object | None,
        current_package_index: PackageIndex | None,
        dirty_snapshot: PackageDirtyState,
        force_full: bool,
        flush_current_resource_panel: Callable[[], None] | None,
        request_save_current_graph: Callable[[], None],
    ) -> bool:
        """按需保存当前存档或视图，返回本次是否确实写盘。"""
        self._fingerprint_baseline_service.sync_before_save()

        is_special_view = current_package_id in ("global_view", "unclassified_view")

        if (not force_full) and dirty_snapshot.is_empty():
            return False

        if flush_current_resource_panel is not None:
            if force_full or dirty_snapshot.should_flush_property_panel():
                flush_current_resource_panel()

        print(
            "[PACKAGE-SAVE] 开始保存存档: "
            f"package_id={current_package_id!r}, force_full={force_full}"
        )

        if is_special_view:
            return self._special_view_save_service.save(
                current_package_id=current_package_id,
                current_package=current_package,
                dirty_snapshot=dirty_snapshot,
                force_full=force_full,
                request_save_current_graph=request_save_current_graph,
            )

        if current_package_index is None or not current_package_id:
            print("[PACKAGE-SAVE] 跳过保存：current_package_index 或 current_package_id 为空")
            return False

        if not isinstance(current_package, PackageView):
            return False

        return self._package_view_save_service.save(
            current_package_id=current_package_id,
            package=current_package,
            package_index=current_package_index,
            dirty_snapshot=dirty_snapshot,
            force_full=force_full,
            request_save_current_graph=request_save_current_graph,
        )


