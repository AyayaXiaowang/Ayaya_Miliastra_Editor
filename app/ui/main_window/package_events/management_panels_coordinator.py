"""管理模式右侧面板编排协调器。

目标：
- 将右侧面板的“选择 → 刷新 → 标签挂载/隐藏 → 即时持久化”编排从 Mixin 中抽离；
- 让 `ManagementPanelsMixin` 仅保留薄薄的事件入口与向后兼容的委托方法。
"""

from __future__ import annotations

from typing import Any, Callable, Protocol

from app.models.view_modes import ViewMode
from app.ui.graph.library_pages.library_scaffold import LibrarySelection
from app.ui.main_window.management_right_panel_registry import (
    get_management_section_right_panel_rule,
    iter_management_special_panel_updaters,
    update_equipment_entry_panel_for_selection,
    update_equipment_tag_panel_for_selection,
    update_equipment_type_panel_for_selection,
    update_main_camera_panel_for_selection,
    update_peripheral_system_panel_for_selection,
    update_signal_management_panel_for_selection,
    update_struct_definition_panel_for_selection,
)
from app.ui.graph.library_pages.management_sections import get_management_section_by_key
from app.ui.management.section_registry import (
    MANAGEMENT_SECTIONS,
    ManagementResourceBinding,
)
from engine.utils.logging.logger import log_info


class _CentralStackProtocol(Protocol):
    def currentIndex(self) -> int: ...


class _RightPanelProtocol(Protocol):
    def set_tab_visible(self, tab_id: str, *, visible: bool, switch_to: bool = False) -> None: ...

    def apply_management_selection(self, section_key: str | None, *, has_selection: bool) -> None: ...

    def update_visibility(self) -> None: ...


class _ManagementWidgetProtocol(Protocol):
    def get_selection(self) -> LibrarySelection | None: ...
    def reload(self) -> None: ...


class _PackageControllerProtocol(Protocol):
    current_package: object | None


class _ManagementPropertyPanelProtocol(Protocol):
    def set_header(self, title: str, description: str) -> None: ...

    def set_rows(self, rows: list[tuple[str, str]]) -> None: ...

    def build_edit_form(
        self,
        *,
        title: str,
        description: str,
        build_form: Callable[[Any], None],
    ) -> None: ...

    def set_membership_context(
        self,
        section_key: str,
        binding_key: str,
        item_id: str,
        packages: list[dict],
        membership: set[str],
    ) -> None: ...

    def _clear_membership_context(self) -> None: ...


class _ManagementViewStateProtocol(Protocol):
    section_key: str
    item_id: str


class _ViewStateProtocol(Protocol):
    management: _ManagementViewStateProtocol


class ManagementPanelsHost(Protocol):
    central_stack: _CentralStackProtocol
    right_panel: _RightPanelProtocol
    management_widget: _ManagementWidgetProtocol
    package_controller: _PackageControllerProtocol
    management_property_panel: _ManagementPropertyPanelProtocol
    view_state: _ViewStateProtocol

    def _on_immediate_persist_requested(self, *, management_keys: set[str] | None = None) -> None: ...

    def _on_library_selection_state_changed(self, has_selection: bool, context: dict) -> None: ...

    def _get_packages_and_membership_for_level_variable_group(
        self, group_id: str
    ) -> tuple[list[dict], set[str], list[str]]: ...

    def _get_management_packages_and_membership(
        self, binding_key: str, item_id: str
    ) -> tuple[list[dict], set[str]]: ...


class ManagementPanelsCoordinator:
    """封装管理模式下右侧面板的选择联动与刷新编排。"""

    def reset_special_panels(self, main_window: ManagementPanelsHost) -> None:
        """清空所有管理模式下的专用右侧面板内容（不负责 tab 显隐）。"""
        for updater in iter_management_special_panel_updaters():
            updater(main_window, None)

    # === selection / context ==================================================

    def _set_right_tab_visible(
        self,
        main_window: ManagementPanelsHost,
        tab_id: str,
        *,
        visible: bool,
        switch_to: bool = False,
    ) -> None:
        """统一通过 policy/registry 控制右侧标签显隐，避免散落 mixin 私有方法依赖。"""
        main_window.right_panel.set_tab_visible(tab_id, visible=visible, switch_to=switch_to)

    def _apply_management_tab_policy(
        self, main_window: ManagementPanelsHost, section_key: str | None, *, has_selection: bool
    ) -> None:
        """管理模式下统一执行 section/selection → tabs 收敛策略。"""
        main_window.right_panel.apply_management_selection(section_key, has_selection=has_selection)

    def _update_right_panel_visibility(self, main_window: ManagementPanelsHost) -> None:
        """统一刷新右侧面板可见性（避免依赖 ModeSwitchMixin._update_right_panel_visibility）。"""
        main_window.right_panel.update_visibility()

    def get_current_selection(self, main_window: ManagementPanelsHost) -> tuple[str, str] | None:
        """从管理库页面获取当前选中的 (section_key, item_id)。"""
        selection = main_window.management_widget.get_selection()
        if selection is None:
            return None
        if selection.kind != "management":
            return None
        context = selection.context or {}
        section_key_any = context.get("section_key")
        if not isinstance(section_key_any, str) or not section_key_any:
            return None
        if not isinstance(selection.id, str) or not selection.id:
            return None
        return section_key_any, selection.id

    def get_current_management_package(self, main_window: ManagementPanelsHost) -> object | None:
        """获取当前管理视图的包上下文（以 PackageController 为准，不再回退到其它上下文）。"""
        return main_window.package_controller.current_package

    # === special panels (delegated to registry) ===============================

    def update_signal_property_panel_for_selection(
        self, main_window: ManagementPanelsHost, selection: tuple[str, str] | None
    ) -> None:
        update_signal_management_panel_for_selection(main_window, selection)

    def update_struct_property_panel_for_selection(
        self, main_window: ManagementPanelsHost, selection: tuple[str, str] | None
    ) -> None:
        update_struct_definition_panel_for_selection(main_window, selection)

    def update_main_camera_panel_for_selection(
        self, main_window: ManagementPanelsHost, selection: tuple[str, str] | None
    ) -> None:
        update_main_camera_panel_for_selection(main_window, selection)

    def update_peripheral_system_panel_for_selection(
        self, main_window: ManagementPanelsHost, selection: tuple[str, str] | None
    ) -> None:
        update_peripheral_system_panel_for_selection(main_window, selection)

    def update_equipment_entry_panel_for_selection(
        self, main_window: ManagementPanelsHost, selection: tuple[str, str] | None
    ) -> None:
        update_equipment_entry_panel_for_selection(main_window, selection)

    def update_equipment_tag_panel_for_selection(
        self, main_window: ManagementPanelsHost, selection: tuple[str, str] | None
    ) -> None:
        update_equipment_tag_panel_for_selection(main_window, selection)

    def update_equipment_type_panel_for_selection(
        self, main_window: ManagementPanelsHost, selection: tuple[str, str] | None
    ) -> None:
        update_equipment_type_panel_for_selection(main_window, selection)

    # === generic management property panel ===================================

    def resolve_management_resource_binding_for_section(
        self, section_key: str
    ) -> ManagementResourceBinding | None:
        """根据 section_key 查找唯一的管理资源绑定信息。"""
        for spec in MANAGEMENT_SECTIONS:
            if spec.key != section_key:
                continue
            if len(spec.resources) != 1:
                return None
            return spec.resources[0]
        return None

    # === edit page change =====================================================

    def on_management_edit_page_data_updated(self, main_window: ManagementPanelsHost) -> None:
        """右侧管理编辑页数据更新后，刷新管理库列表并立即持久化。"""
        main_window.management_widget.reload()
        selection = self.get_current_selection(main_window)
        management_keys: set[str] = set()
        if selection is not None:
            section_key = selection[0]
            if isinstance(section_key, str) and section_key:
                management_keys.add(section_key)
        main_window._on_immediate_persist_requested(management_keys=management_keys if management_keys else None)

    # === selection changed (main entry) ======================================

    def on_management_selection_changed(
        self,
        main_window: ManagementPanelsHost,
        *,
        has_selection: bool,
        title: str,
        description: str,
        rows: list[tuple[str, str]],
    ) -> None:
        """管理页面选中记录变化时，同步到主窗口右侧属性与编辑面板。"""
        current_view_mode = ViewMode.from_index(main_window.central_stack.currentIndex())

        selection = self.get_current_selection(main_window)
        section_key = selection[0] if selection is not None else None
        item_id = selection[1] if selection is not None else ""
        main_window.view_state.management.section_key = str(section_key or "")
        main_window.view_state.management.item_id = str(item_id or "")
        log_info(
            "[MANAGEMENT-LIB] selection_changed: has_selection={} section_key={} item_id={} current_view_mode={}",
            has_selection,
            section_key,
            item_id,
            current_view_mode,
        )

        if current_view_mode != ViewMode.MANAGEMENT:
            return

        if not has_selection:
            main_window._on_library_selection_state_changed(False, {"section_key": section_key})
            return

        # 专用编辑面板：由注册表驱动，避免 if/elif 指数膨胀。
        if isinstance(section_key, str) and section_key:
            rule = get_management_section_right_panel_rule(section_key)
            selection_updater = rule.selection_updater if rule is not None else None
            if selection_updater is not None:
                selection_updater(main_window, selection)
                self._apply_management_tab_policy(main_window, section_key, has_selection=True)
                self._set_right_tab_visible(main_window, "management_property", visible=False)
                return

        # 其余类型仍由主窗口原有分支处理（通用属性/内联表单/专用编辑页）。
        # 这里保持逻辑与旧实现一致，避免行为漂移。
        inline_handled = False
        binding: ManagementResourceBinding | None = None
        section_obj = None
        if section_key:
            binding = self.resolve_management_resource_binding_for_section(section_key)
            section_obj = get_management_section_by_key(section_key)

        membership_supported = False
        if section_key == "variable":
            membership_supported = True
        elif binding is not None:
            if binding.key in {"save_points", "currency_backpack", "level_settings"}:
                membership_supported = True
            else:
                membership_supported = binding.aggregation_mode == "id_list"

        if membership_supported and item_id and binding is not None:
            if section_key == "variable":
                packages, membership, reference_ids = main_window._get_packages_and_membership_for_level_variable_group(
                    item_id
                )
                _ = reference_ids
                if section_obj is not None:
                    usage_names = [
                        pkg.get("name", pkg.get("package_id", ""))
                        for pkg in packages
                        if pkg.get("package_id") in membership
                    ]
                    section_obj.set_usage_text("，".join(usage_names) if usage_names else "未被任何存档引用")
                main_window.management_property_panel.set_membership_context(
                    section_key,
                    binding.key,
                    item_id,
                    packages,
                    membership,
                )
            else:
                packages, membership = main_window._get_management_packages_and_membership(binding.key, item_id)
                main_window.management_property_panel.set_membership_context(
                    section_key,
                    binding.key,
                    item_id,
                    packages,
                    membership,
                )
        else:
            main_window.management_property_panel._clear_membership_context()

        self._update_right_panel_visibility(main_window)

        if section_key and item_id:
            current_package = main_window.package_controller.current_package
            management_panel = main_window.management_property_panel
            if current_package is not None and section_obj is not None:

                def _on_inline_changed() -> None:
                    main_window.management_widget.reload()
                    key_set = {section_key} if isinstance(section_key, str) and section_key else None
                    main_window._on_immediate_persist_requested(management_keys=key_set)

                inline_result = section_obj.build_inline_edit_form(
                    parent=management_panel,
                    package=current_package,
                    item_id=item_id,
                    on_changed=_on_inline_changed,
                )
                if inline_result is not None:
                    inline_title, inline_description, build_form = inline_result
                    management_panel.build_edit_form(
                        title=inline_title,
                        description=inline_description,
                        build_form=build_form,
                    )
                    self._apply_management_tab_policy(main_window, section_key, has_selection=False)
                    self._set_right_tab_visible(main_window, "management_property", visible=True)
                    inline_handled = True

        if not inline_handled:
            main_window.management_property_panel.set_header(title, description)
            main_window.management_property_panel.set_rows(rows)
            self._apply_management_tab_policy(main_window, section_key, has_selection=False)
            self._set_right_tab_visible(main_window, "management_property", visible=True)


