"""管理模式（ViewMode.MANAGEMENT）右侧面板联动入口（薄壳）。

本文件仅保留对外稳定的 Mixin 方法名，具体编排与刷新逻辑已下沉到
`ManagementPanelsCoordinator`，以降低 Mixin 冲突面并便于渐进迁移。
"""

from __future__ import annotations

from typing import Any

from .management_panels_coordinator import ManagementPanelsCoordinator


class ManagementPanelsMixin:
    """根据管理库选中记录刷新右侧面板（委托给 coordinator）。"""

    def _get_management_panels_coordinator(self) -> ManagementPanelsCoordinator:
        coordinator = getattr(self, "_management_panels_coordinator", None)
        if isinstance(coordinator, ManagementPanelsCoordinator):
            return coordinator
        coordinator = ManagementPanelsCoordinator()
        setattr(self, "_management_panels_coordinator", coordinator)
        return coordinator

    # --- 向后兼容的委托方法 ---------------------------------------------------

    def _get_management_current_selection(self) -> tuple[str, str] | None:
        return self._get_management_panels_coordinator().get_current_selection(self)

    def _get_current_management_package(self) -> object | None:
        return self._get_management_panels_coordinator().get_current_management_package(self)

    def _update_signal_property_panel_for_selection(self, has_selection: bool) -> None:
        self._get_management_panels_coordinator().update_signal_property_panel_for_selection(
            self,
            has_selection,
        )

    def _update_struct_property_panel_for_selection(self, has_selection: bool) -> None:
        self._get_management_panels_coordinator().update_struct_property_panel_for_selection(
            self,
            has_selection,
        )

    def _update_timer_property_panel_for_selection(self, has_selection: bool) -> None:
        self._get_management_panels_coordinator().update_timer_property_panel_for_selection(
            self,
            has_selection,
        )

    def _update_save_points_property_panel_for_selection(self, has_selection: bool) -> None:
        self._get_management_panels_coordinator().update_save_points_property_panel_for_selection(
            self,
            has_selection,
        )

    def _update_main_camera_panel_for_selection(self, has_selection: bool) -> None:
        self._get_management_panels_coordinator().update_main_camera_panel_for_selection(
            self,
            has_selection,
        )

    def _update_peripheral_system_panel_for_selection(self, has_selection: bool) -> None:
        self._get_management_panels_coordinator().update_peripheral_system_panel_for_selection(
            self,
            has_selection,
        )

    def _update_equipment_entry_panel_for_selection(self, has_selection: bool) -> None:
        self._get_management_panels_coordinator().update_equipment_entry_panel_for_selection(
            self,
            has_selection,
        )

    def _update_equipment_tag_panel_for_selection(self, has_selection: bool) -> None:
        self._get_management_panels_coordinator().update_equipment_tag_panel_for_selection(
            self,
            has_selection,
        )

    def _update_equipment_type_panel_for_selection(self, has_selection: bool) -> None:
        self._get_management_panels_coordinator().update_equipment_type_panel_for_selection(
            self,
            has_selection,
        )

    def _resolve_management_resource_binding_for_section(self, section_key: str):
        return self._get_management_panels_coordinator().resolve_management_resource_binding_for_section(
            section_key
        )

    def _on_management_edit_page_data_updated(self) -> None:
        self._get_management_panels_coordinator().on_management_edit_page_data_updated(self)

    def _on_management_selection_changed(
        self,
        has_selection: bool,
        title: str,
        description: str,
        rows: list[tuple[str, str]],
    ) -> None:
        self._get_management_panels_coordinator().on_management_selection_changed(
            self,
            has_selection=has_selection,
            title=title,
            description=description,
            rows=rows,
        )


