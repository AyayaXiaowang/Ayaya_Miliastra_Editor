"""管理模式右侧面板编排协调器。

目标：
- 将右侧面板的“选择 → 刷新 → 标签挂载/隐藏 → 即时持久化”编排从 Mixin 中抽离；
- 让 `ManagementPanelsMixin` 仅保留薄薄的事件入口与向后兼容的委托方法。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.models.view_modes import ViewMode
from app.ui.graph.library_pages.management_sections import get_management_section_by_key
from app.ui.management.section_registry import (
    MANAGEMENT_SECTIONS,
    ManagementResourceBinding,
)


class ManagementPanelsCoordinator:
    """封装管理模式下右侧面板的选择联动与刷新编排。"""

    # === selection / context ==================================================

    def get_current_selection(self, main_window: Any) -> tuple[str, str] | None:
        """从管理库页面获取当前选中的 (section_key, item_id)。"""
        management_widget = getattr(main_window, "management_widget", None)
        if management_widget is None:
            return None
        get_selection = getattr(management_widget, "get_current_selection", None)
        if callable(get_selection):
            return get_selection()
        current_key_getter = getattr(management_widget, "get_current_section_key", None)
        if callable(current_key_getter):
            section_key = current_key_getter()
            if section_key:
                return section_key, ""
        return None

    def get_current_management_package(self, main_window: Any) -> object | None:
        """获取当前管理视图的包上下文（优先 PackageController，回退管理库自身）。"""
        package = getattr(getattr(main_window, "package_controller", None), "current_package", None)
        if package is not None:
            return package
        management_widget = getattr(main_window, "management_widget", None)
        if management_widget is not None:
            return getattr(management_widget, "current_package", None)
        return None

    # === special panels: signals / structs ===================================

    def update_signal_property_panel_for_selection(self, main_window: Any, has_selection: bool) -> None:
        """根据当前管理库选中记录刷新信号编辑面板。"""
        if not hasattr(main_window, "signal_management_panel"):
            return
        from app.ui.graph.library_pages.management_section_signals import SignalSection

        selection = self.get_current_selection(main_window)
        if not has_selection or selection is None:
            main_window.signal_management_panel.reset()
            policy = getattr(main_window, "right_panel_policy", None)
            set_method = getattr(policy, "set_tab_visible", None)
            if callable(set_method):
                set_method("signal_editor", visible=False)
            return

        section_key, signal_id = selection
        if section_key != "signals" or not signal_id:
            main_window.signal_management_panel.reset()
            policy = getattr(main_window, "right_panel_policy", None)
            set_method = getattr(policy, "set_tab_visible", None)
            if callable(set_method):
                set_method("signal_editor", visible=False)
            return

        package = getattr(getattr(main_window, "package_controller", None), "current_package", None)
        if package is None:
            main_window.signal_management_panel.reset()
            policy = getattr(main_window, "right_panel_policy", None)
            set_method = getattr(policy, "set_tab_visible", None)
            if callable(set_method):
                set_method("signal_editor", visible=False)
            return

        signals_dict = SignalSection._get_signal_dict_from_package(package)
        if signal_id not in signals_dict:
            main_window.signal_management_panel.reset()
            policy = getattr(main_window, "right_panel_policy", None)
            set_method = getattr(policy, "set_tab_visible", None)
            if callable(set_method):
                set_method("signal_editor", visible=False)
            return

        config = signals_dict[signal_id]
        main_window.signal_management_panel.editor.load_from_config(config)

        display_name = config.signal_name or signal_id
        main_window.signal_management_panel.set_title(f"编辑信号：{display_name}")
        main_window.signal_management_panel.set_description(
            "信号定义当前为代码级只读视图：右侧内容仅供查看与校验，实际修改请在 Python 模块中完成。"
        )

        usage_stats = SignalSection._build_signal_usage_stats(package)
        usage_entry = usage_stats.get(signal_id)
        if usage_entry:
            graph_count = int(usage_entry.get("graph_count", 0))
            node_count = int(usage_entry.get("node_count", 0))
            if graph_count > 0 or node_count > 0:
                usage_text = f"已在 {graph_count} 个图 / {node_count} 个节点中使用"
            else:
                usage_text = "未在任何服务器节点图中使用"
        else:
            usage_text = "未在任何服务器节点图中使用"
        main_window.signal_management_panel.set_usage_text(usage_text)

        packages = main_window.package_index_manager.list_packages()
        membership_index = main_window._build_signal_membership_index()
        membership = membership_index.get(signal_id, set())
        main_window.signal_management_panel.set_current_signal_id(signal_id)
        main_window.signal_management_panel.set_signal_membership(packages, membership)

        policy = getattr(main_window, "right_panel_policy", None)
        set_method = getattr(policy, "set_tab_visible", None)
        if callable(set_method):
            set_method("signal_editor", visible=True)

    def update_struct_property_panel_for_selection(self, main_window: Any, has_selection: bool) -> None:
        """根据当前管理库选中记录刷新结构体编辑面板。"""
        if not hasattr(main_window, "struct_definition_panel"):
            return
        from engine.configs.specialized.node_graph_configs import (
            STRUCT_TYPE_BASIC,
            STRUCT_TYPE_INGAME_SAVE,
        )
        from engine.resources.resource_manager import ResourceManager
        from app.ui.graph.library_pages.management_section_struct_definitions import (
            StructDefinitionSection,
        )

        selection = self.get_current_selection(main_window)
        if not has_selection or selection is None:
            main_window.struct_definition_panel.reset()
            policy = getattr(main_window, "right_panel_policy", None)
            set_method = getattr(policy, "set_tab_visible", None)
            if callable(set_method):
                set_method("struct_editor", visible=False)
            return

        section_key, struct_id = selection
        if section_key not in ("struct_definitions", "ingame_struct_definitions") or not struct_id:
            main_window.struct_definition_panel.reset()
            policy = getattr(main_window, "right_panel_policy", None)
            set_method = getattr(policy, "set_tab_visible", None)
            if callable(set_method):
                set_method("struct_editor", visible=False)
            return

        package = getattr(getattr(main_window, "package_controller", None), "current_package", None)
        if package is None:
            main_window.struct_definition_panel.reset()
            policy = getattr(main_window, "right_panel_policy", None)
            set_method = getattr(policy, "set_tab_visible", None)
            if callable(set_method):
                set_method("struct_editor", visible=False)
            return

        resource_manager_candidate = getattr(package, "resource_manager", None)
        if not isinstance(resource_manager_candidate, ResourceManager):
            main_window.struct_definition_panel.reset()
            policy = getattr(main_window, "right_panel_policy", None)
            set_method = getattr(policy, "set_tab_visible", None)
            if callable(set_method):
                set_method("struct_editor", visible=False)
            return

        from engine.configs.specialized.struct_definitions_data import get_struct_payload

        payload = get_struct_payload(struct_id)
        if not isinstance(payload, dict):
            main_window.struct_definition_panel.reset()
            policy = getattr(main_window, "right_panel_policy", None)
            set_method = getattr(policy, "set_tab_visible", None)
            if callable(set_method):
                set_method("struct_editor", visible=False)
            return

        struct_type_value = (
            STRUCT_TYPE_INGAME_SAVE if section_key == "ingame_struct_definitions" else STRUCT_TYPE_BASIC
        )

        _, initial_fields = StructDefinitionSection._extract_initial_fields_from_struct_data(payload)
        display_name = StructDefinitionSection._get_struct_display_name(struct_id, payload)

        editor_widget = getattr(main_window.struct_definition_panel, "editor", None)
        if editor_widget is None:
            main_window.struct_definition_panel.reset()
            policy = getattr(main_window, "right_panel_policy", None)
            set_method = getattr(policy, "set_tab_visible", None)
            if callable(set_method):
                set_method("struct_editor", visible=False)
            return

        setattr(editor_widget, "_struct_type", struct_type_value)
        editor_widget.load_struct(
            struct_name=display_name,
            fields=initial_fields,
            allow_edit_name=False,
        )
        if hasattr(editor_widget, "set_read_only"):
            editor_widget.set_read_only(True)  # type: ignore[attr-defined]

        main_window._struct_editor_snapshot = editor_widget.build_struct_data()
        main_window._struct_editor_snapshot_id = struct_id

        field_count = StructDefinitionSection._calculate_field_count(payload)
        main_window.struct_definition_panel.set_field_count(field_count)
        main_window.struct_definition_panel.set_title(f"编辑结构体：{display_name}")
        main_window.struct_definition_panel.set_description(
            "结构体定义当前为代码级只读视图：右侧内容仅供查看与校验，实际修改请在 Python 模块中完成。"
        )

        packages = main_window.package_index_manager.list_packages()
        membership_index = main_window._build_struct_membership_index()
        membership = membership_index.get(struct_id, set())
        main_window.struct_definition_panel.set_current_struct_id(struct_id)
        main_window.struct_definition_panel.set_packages_and_membership(packages, membership)

        policy = getattr(main_window, "right_panel_policy", None)
        set_method = getattr(policy, "set_tab_visible", None)
        if callable(set_method):
            set_method("struct_editor", visible=True)

    # === common management property panel: timer / save points =================

    def update_timer_property_panel_for_selection(self, main_window: Any, has_selection: bool) -> None:
        """根据当前管理库选中记录刷新计时器编辑面板（复用通用管理属性面板）。"""
        if not hasattr(main_window, "management_property_panel"):
            return

        management_panel = main_window.management_property_panel

        selection = self.get_current_selection(main_window)
        if not has_selection or selection is None:
            management_panel.clear()
            if hasattr(main_window, "_ensure_management_property_tab_visible"):
                main_window._ensure_management_property_tab_visible(False)
            return

        section_key, timer_id = selection
        if section_key != "timer" or not timer_id:
            management_panel.clear()
            if hasattr(main_window, "_ensure_management_property_tab_visible"):
                main_window._ensure_management_property_tab_visible(False)
            return

        current_package = getattr(getattr(main_window, "package_controller", None), "current_package", None)
        if current_package is None:
            management_panel.clear()
            if hasattr(main_window, "_ensure_management_property_tab_visible"):
                main_window._ensure_management_property_tab_visible(False)
            return

        management_view = getattr(current_package, "management", None)
        timers_mapping = getattr(management_view, "timers", None)
        if not isinstance(timers_mapping, dict):
            management_panel.clear()
            if hasattr(main_window, "_ensure_management_property_tab_visible"):
                main_window._ensure_management_property_tab_visible(False)
            return

        timer_payload_any = timers_mapping.get(timer_id)
        if not isinstance(timer_payload_any, dict):
            management_panel.clear()
            if hasattr(main_window, "_ensure_management_property_tab_visible"):
                main_window._ensure_management_property_tab_visible(False)
            return

        timer_payload = timer_payload_any

        from PyQt6 import QtWidgets

        def build_form(form_layout: QtWidgets.QFormLayout) -> None:
            timer_name_value = timer_payload.get("timer_name", "")
            initial_time_raw = timer_payload.get("initial_time", 60.0)
            initial_time_value = float(initial_time_raw) if isinstance(initial_time_raw, (int, float)) else 60.0
            is_loop_enabled = bool(timer_payload.get("is_loop", False))
            is_auto_start_enabled = bool(timer_payload.get("auto_start", False))

            name_edit = QtWidgets.QLineEdit(str(timer_name_value))
            initial_time_spin = QtWidgets.QDoubleSpinBox()
            initial_time_spin.setRange(0.0, 86400.0)
            initial_time_spin.setDecimals(2)
            initial_time_spin.setSingleStep(1.0)
            initial_time_spin.setValue(initial_time_value)

            loop_checkbox = QtWidgets.QCheckBox()
            loop_checkbox.setChecked(is_loop_enabled)

            auto_start_checkbox = QtWidgets.QCheckBox()
            auto_start_checkbox.setChecked(is_auto_start_enabled)

            def apply_changes() -> None:
                normalized_name = name_edit.text().strip()
                if normalized_name:
                    timer_payload["timer_name"] = normalized_name
                timer_payload["initial_time"] = float(initial_time_spin.value())
                timer_payload["is_loop"] = bool(loop_checkbox.isChecked())
                timer_payload["auto_start"] = bool(auto_start_checkbox.isChecked())

                if hasattr(main_window, "management_widget"):
                    main_window.management_widget._refresh_items()  # type: ignore[attr-defined]
                main_window._on_immediate_persist_requested(management_keys={"timers"})

            name_edit.editingFinished.connect(apply_changes)
            initial_time_spin.editingFinished.connect(apply_changes)
            loop_checkbox.stateChanged.connect(lambda _state: apply_changes())
            auto_start_checkbox.stateChanged.connect(lambda _state: apply_changes())

            form_layout.addRow("计时器名", name_edit)
            form_layout.addRow("初始时间(秒)", initial_time_spin)
            form_layout.addRow("循环", loop_checkbox)
            form_layout.addRow("自动开始", auto_start_checkbox)

        management_panel.build_edit_form(
            title="计时器详情",
            description="直接在右侧修改计时器名称与运行属性，修改会立即保存到当前视图。",
            build_form=build_form,
        )

        if hasattr(main_window, "_ensure_management_property_tab_visible"):
            main_window._ensure_management_property_tab_visible(True)
        if hasattr(main_window, "_hide_all_management_edit_pages"):
            main_window._hide_all_management_edit_pages(None)  # type: ignore[attr-defined]

    def update_save_points_property_panel_for_selection(self, main_window: Any, has_selection: bool) -> None:
        """根据当前管理库选中记录刷新局内存档模板编辑表单。"""
        if not hasattr(main_window, "management_property_panel"):
            return

        management_panel = main_window.management_property_panel
        from app.ui.graph.library_pages.management_section_save_points import SavePointsSection
        from PyQt6 import QtWidgets

        selection = self.get_current_selection(main_window)
        if not has_selection or selection is None:
            management_panel.clear()
            if hasattr(main_window, "_ensure_management_property_tab_visible"):
                main_window._ensure_management_property_tab_visible(False)
            return

        section_key, template_id = selection
        if section_key != "save_points" or not template_id:
            management_panel.clear()
            if hasattr(main_window, "_ensure_management_property_tab_visible"):
                main_window._ensure_management_property_tab_visible(False)
            return

        current_package = getattr(getattr(main_window, "package_controller", None), "current_package", None)
        if current_package is None:
            management_panel.clear()
            if hasattr(main_window, "_ensure_management_property_tab_visible"):
                main_window._ensure_management_property_tab_visible(False)
            return

        config_data = SavePointsSection._ensure_config(current_package)  # type: ignore[arg-type]
        template_payload = SavePointsSection._find_template_by_id(config_data, template_id)
        if template_payload is None:
            management_panel.clear()
            if hasattr(main_window, "_ensure_management_property_tab_visible"):
                main_window._ensure_management_property_tab_visible(False)
            return

        def build_form(form_layout: QtWidgets.QFormLayout) -> None:
            template_name_value = str(template_payload.get("template_name", ""))
            description_value = str(template_payload.get("description", ""))

            entries_value = template_payload.get("entries", [])
            entry_count = 0
            if isinstance(entries_value, list):
                for entry in entries_value:
                    if isinstance(entry, dict):
                        entry_count += 1

            name_edit = QtWidgets.QLineEdit(template_name_value)
            description_edit = QtWidgets.QTextEdit()
            description_edit.setPlainText(description_value)
            description_edit.setMinimumHeight(60)
            description_edit.setMaximumHeight(120)

            active_checkbox = QtWidgets.QCheckBox("将该模板设为当前启用模板")
            enabled_flag_local = bool(config_data.get("enabled", False))
            active_template_id = str(config_data.get("active_template_id", "")).strip()
            is_active_template_local = enabled_flag_local and active_template_id == template_id
            active_checkbox.setChecked(is_active_template_local)

            template_id_label = QtWidgets.QLabel(template_id)

            def build_summary_text() -> str:
                status_text = "已启用" if bool(config_data.get("enabled", False)) else "未启用"
                return f"条目数：{entry_count}    当前状态：{status_text}"

            summary_label = QtWidgets.QLabel(build_summary_text())
            summary_label.setWordWrap(True)

            def apply_changes() -> None:
                normalized_name = name_edit.text().strip()
                template_payload["template_name"] = normalized_name or template_id
                template_payload["description"] = description_edit.toPlainText().strip()

                is_currently_active = bool(config_data.get("enabled", False)) and str(
                    config_data.get("active_template_id", "")
                ).strip() == template_id

                if active_checkbox.isChecked():
                    config_data["enabled"] = True
                    config_data["active_template_id"] = template_id
                else:
                    if is_currently_active:
                        config_data["enabled"] = False
                        config_data["active_template_id"] = ""

                summary_label.setText(build_summary_text())

                if hasattr(main_window, "management_widget"):
                    main_window.management_widget._refresh_items()  # type: ignore[attr-defined]
                main_window._on_immediate_persist_requested(management_keys={"save_points"})

            name_edit.editingFinished.connect(apply_changes)
            description_edit.textChanged.connect(lambda: apply_changes())
            active_checkbox.stateChanged.connect(lambda _state: apply_changes())

            form_layout.addRow("模板名称", name_edit)
            form_layout.addRow("模板 ID", template_id_label)
            form_layout.addRow("概要", summary_label)
            form_layout.addRow("", active_checkbox)
            form_layout.addRow("描述", description_edit)

        management_panel.build_edit_form(
            title="局内存档模板详情",
            description="在右侧直接编辑局内存档模板名称、描述与启用状态，修改会立即保存到当前视图。",
            build_form=build_form,
        )

        if hasattr(main_window, "_ensure_management_property_tab_visible"):
            main_window._ensure_management_property_tab_visible(True)
        if hasattr(main_window, "_hide_all_management_edit_pages"):
            main_window._hide_all_management_edit_pages(None)  # type: ignore[attr-defined]

    # === specialized edit pages: main camera / peripheral system ===============

    def update_main_camera_panel_for_selection(self, main_window: Any, has_selection: bool) -> None:
        if not hasattr(main_window, "main_camera_panel"):
            return

        selection = self.get_current_selection(main_window)
        if not has_selection or selection is None:
            main_window.main_camera_panel.clear()
            policy = getattr(main_window, "right_panel_policy", None)
            set_method = getattr(policy, "set_tab_visible", None)
            if callable(set_method):
                set_method("main_camera_editor", visible=False)
            return

        section_key, camera_id = selection
        if section_key != "main_cameras" or not camera_id:
            main_window.main_camera_panel.clear()
            policy = getattr(main_window, "right_panel_policy", None)
            set_method = getattr(policy, "set_tab_visible", None)
            if callable(set_method):
                set_method("main_camera_editor", visible=False)
            return

        package = getattr(getattr(main_window, "package_controller", None), "current_package", None)
        if package is None:
            main_window.main_camera_panel.clear()
            policy = getattr(main_window, "right_panel_policy", None)
            set_method = getattr(policy, "set_tab_visible", None)
            if callable(set_method):
                set_method("main_camera_editor", visible=False)
            return

        main_window.main_camera_panel.set_context(package, camera_id)
        policy = getattr(main_window, "right_panel_policy", None)
        set_method = getattr(policy, "set_tab_visible", None)
        if callable(set_method):
            set_method("main_camera_editor", visible=True)

    def update_peripheral_system_panel_for_selection(self, main_window: Any, has_selection: bool) -> None:
        if not hasattr(main_window, "peripheral_system_panel"):
            return

        selection = self.get_current_selection(main_window)
        if not has_selection or selection is None:
            main_window.peripheral_system_panel.clear()
            policy = getattr(main_window, "right_panel_policy", None)
            set_method = getattr(policy, "set_tab_visible", None)
            if callable(set_method):
                set_method("peripheral_system_editor", visible=False)
            return

        section_key, system_id = selection
        if section_key != "peripheral_systems" or not system_id:
            main_window.peripheral_system_panel.clear()
            policy = getattr(main_window, "right_panel_policy", None)
            set_method = getattr(policy, "set_tab_visible", None)
            if callable(set_method):
                set_method("peripheral_system_editor", visible=False)
            return

        package = getattr(getattr(main_window, "package_controller", None), "current_package", None)
        if package is None:
            main_window.peripheral_system_panel.clear()
            policy = getattr(main_window, "right_panel_policy", None)
            set_method = getattr(policy, "set_tab_visible", None)
            if callable(set_method):
                set_method("peripheral_system_editor", visible=False)
            return

        main_window.peripheral_system_panel.set_context(package, system_id)

        packages, membership = main_window._get_management_packages_and_membership("peripheral_systems", system_id)
        if hasattr(main_window.peripheral_system_panel, "set_current_system_id"):
            main_window.peripheral_system_panel.set_current_system_id(system_id)  # type: ignore[attr-defined]
        if hasattr(main_window.peripheral_system_panel, "set_packages_and_membership"):
            main_window.peripheral_system_panel.set_packages_and_membership(  # type: ignore[attr-defined]
                packages,
                membership,
            )
        policy = getattr(main_window, "right_panel_policy", None)
        set_method = getattr(policy, "set_tab_visible", None)
        if callable(set_method):
            set_method("peripheral_system_editor", visible=True)

    # --- equipment panels ------------------------------------------------------

    @staticmethod
    def _is_equipment_entry_payload(payload: object) -> bool:
        return isinstance(payload, dict) and (("entry_name" in payload) or ("entry_type" in payload))

    @staticmethod
    def _is_equipment_tag_payload(payload: object) -> bool:
        return isinstance(payload, dict) and ("tag_name" in payload)

    @staticmethod
    def _is_equipment_type_payload(payload: object) -> bool:
        return isinstance(payload, dict) and (("type_name" in payload) or ("allowed_slots" in payload))

    def _get_equipment_payload(self, package: object, storage_id: str) -> Optional[Dict[str, Any]]:
        management_view = getattr(package, "management", None)
        equipment_map = getattr(management_view, "equipment_data", None)
        if not isinstance(equipment_map, dict):
            return None
        payload_any = equipment_map.get(storage_id)
        return payload_any if isinstance(payload_any, dict) else None

    def update_equipment_entry_panel_for_selection(self, main_window: Any, has_selection: bool) -> None:
        if not hasattr(main_window, "equipment_entry_panel"):
            return

        panel = main_window.equipment_entry_panel
        selection = self.get_current_selection(main_window)
        if not has_selection or selection is None:
            panel.clear()
            policy = getattr(main_window, "right_panel_policy", None)
            set_method = getattr(policy, "set_tab_visible", None)
            if callable(set_method):
                set_method("equipment_entry_editor", visible=False)
            return

        section_key, storage_id = selection
        if section_key != "equipment_entries" or not storage_id:
            panel.clear()
            policy = getattr(main_window, "right_panel_policy", None)
            set_method = getattr(policy, "set_tab_visible", None)
            if callable(set_method):
                set_method("equipment_entry_editor", visible=False)
            return

        package = self.get_current_management_package(main_window)
        if package is None:
            panel.clear()
            policy = getattr(main_window, "right_panel_policy", None)
            set_method = getattr(policy, "set_tab_visible", None)
            if callable(set_method):
                set_method("equipment_entry_editor", visible=False)
            return

        payload = self._get_equipment_payload(package, storage_id)
        if not self._is_equipment_entry_payload(payload):
            panel.clear()
            policy = getattr(main_window, "right_panel_policy", None)
            set_method = getattr(policy, "set_tab_visible", None)
            if callable(set_method):
                set_method("equipment_entry_editor", visible=False)
            return

        panel._set_context_internal(package, storage_id, payload)  # type: ignore[attr-defined]
        packages, membership = main_window._get_management_packages_and_membership("equipment_data", storage_id)
        panel.set_packages_and_membership(packages, membership)

        policy = getattr(main_window, "right_panel_policy", None)
        set_method = getattr(policy, "set_tab_visible", None)
        if callable(set_method):
            set_method("equipment_entry_editor", visible=True)
        if hasattr(main_window, "_hide_all_management_edit_pages"):
            main_window._hide_all_management_edit_pages("equipment_entries")  # type: ignore[attr-defined]

    def update_equipment_tag_panel_for_selection(self, main_window: Any, has_selection: bool) -> None:
        if not hasattr(main_window, "equipment_tag_panel"):
            return

        panel = main_window.equipment_tag_panel
        selection = self.get_current_selection(main_window)
        if not has_selection or selection is None:
            panel.clear()
            policy = getattr(main_window, "right_panel_policy", None)
            set_method = getattr(policy, "set_tab_visible", None)
            if callable(set_method):
                set_method("equipment_tag_editor", visible=False)
            return

        section_key, storage_id = selection
        if section_key != "equipment_tags" or not storage_id:
            panel.clear()
            policy = getattr(main_window, "right_panel_policy", None)
            set_method = getattr(policy, "set_tab_visible", None)
            if callable(set_method):
                set_method("equipment_tag_editor", visible=False)
            return

        package = self.get_current_management_package(main_window)
        if package is None:
            panel.clear()
            policy = getattr(main_window, "right_panel_policy", None)
            set_method = getattr(policy, "set_tab_visible", None)
            if callable(set_method):
                set_method("equipment_tag_editor", visible=False)
            return

        payload = self._get_equipment_payload(package, storage_id)
        if not self._is_equipment_tag_payload(payload):
            panel.clear()
            policy = getattr(main_window, "right_panel_policy", None)
            set_method = getattr(policy, "set_tab_visible", None)
            if callable(set_method):
                set_method("equipment_tag_editor", visible=False)
            return

        panel._set_context_internal(package, storage_id, payload)  # type: ignore[attr-defined]
        packages, membership = main_window._get_management_packages_and_membership("equipment_data", storage_id)
        panel.set_packages_and_membership(packages, membership)

        policy = getattr(main_window, "right_panel_policy", None)
        set_method = getattr(policy, "set_tab_visible", None)
        if callable(set_method):
            set_method("equipment_tag_editor", visible=True)
        if hasattr(main_window, "_hide_all_management_edit_pages"):
            main_window._hide_all_management_edit_pages("equipment_tags")  # type: ignore[attr-defined]

    def update_equipment_type_panel_for_selection(self, main_window: Any, has_selection: bool) -> None:
        if not hasattr(main_window, "equipment_type_panel"):
            return

        panel = main_window.equipment_type_panel
        selection = self.get_current_selection(main_window)
        if not has_selection or selection is None:
            panel.clear()
            policy = getattr(main_window, "right_panel_policy", None)
            set_method = getattr(policy, "set_tab_visible", None)
            if callable(set_method):
                set_method("equipment_type_editor", visible=False)
            return

        section_key, storage_id = selection
        if section_key != "equipment_types" or not storage_id:
            panel.clear()
            policy = getattr(main_window, "right_panel_policy", None)
            set_method = getattr(policy, "set_tab_visible", None)
            if callable(set_method):
                set_method("equipment_type_editor", visible=False)
            return

        package = self.get_current_management_package(main_window)
        if package is None:
            panel.clear()
            policy = getattr(main_window, "right_panel_policy", None)
            set_method = getattr(policy, "set_tab_visible", None)
            if callable(set_method):
                set_method("equipment_type_editor", visible=False)
            return

        payload = self._get_equipment_payload(package, storage_id)
        if not self._is_equipment_type_payload(payload):
            panel.clear()
            policy = getattr(main_window, "right_panel_policy", None)
            set_method = getattr(policy, "set_tab_visible", None)
            if callable(set_method):
                set_method("equipment_type_editor", visible=False)
            return

        panel._set_context_internal(package, storage_id, payload)  # type: ignore[attr-defined]
        packages, membership = main_window._get_management_packages_and_membership("equipment_data", storage_id)
        panel.set_packages_and_membership(packages, membership)

        policy = getattr(main_window, "right_panel_policy", None)
        set_method = getattr(policy, "set_tab_visible", None)
        if callable(set_method):
            set_method("equipment_type_editor", visible=True)
        if hasattr(main_window, "_hide_all_management_edit_pages"):
            main_window._hide_all_management_edit_pages("equipment_types")  # type: ignore[attr-defined]

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

    def on_management_edit_page_data_updated(self, main_window: Any) -> None:
        """右侧管理编辑页数据更新后，刷新管理库列表并立即持久化。"""
        if hasattr(main_window, "management_widget"):
            main_window.management_widget._refresh_items()  # type: ignore[attr-defined]
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
        main_window: Any,
        *,
        has_selection: bool,
        title: str,
        description: str,
        rows: list[tuple[str, str]],
    ) -> None:
        """管理页面选中记录变化时，同步到主窗口右侧属性与编辑面板。"""
        current_view_mode = ViewMode.from_index(main_window.central_stack.currentIndex())
        if not hasattr(main_window, "management_property_panel"):
            return

        selection = self.get_current_selection(main_window)
        section_key = selection[0] if selection is not None else None
        item_id = selection[1] if selection is not None else ""
        view_state = getattr(main_window, "view_state", None)
        management_state = getattr(view_state, "management", None)
        if management_state is not None:
            setattr(management_state, "section_key", str(section_key or ""))
            setattr(management_state, "item_id", str(item_id or ""))
        print(
            "[MANAGEMENT-LIB] _on_management_selection_changed:",
            f"has_selection={has_selection!r}, section_key={section_key!r}, "
            f"item_id={item_id!r}, current_view_mode={current_view_mode}",
        )

        if current_view_mode != ViewMode.MANAGEMENT:
            return

        if not has_selection:
            main_window._on_library_selection_state_changed(False, {"section_key": section_key})
            return

        if section_key == "signals":
            self.update_signal_property_panel_for_selection(main_window, True)
            if hasattr(main_window, "_ensure_management_property_tab_visible"):
                main_window._ensure_management_property_tab_visible(False)
            return

        if section_key in ("struct_definitions", "ingame_struct_definitions"):
            self.update_struct_property_panel_for_selection(main_window, True)
            if hasattr(main_window, "_ensure_management_property_tab_visible"):
                main_window._ensure_management_property_tab_visible(False)
            return

        if section_key == "main_cameras":
            self.update_main_camera_panel_for_selection(main_window, True)
            if hasattr(main_window, "_ensure_management_property_tab_visible"):
                main_window._ensure_management_property_tab_visible(False)
            if hasattr(main_window, "_hide_all_management_edit_pages"):
                main_window._hide_all_management_edit_pages(None)  # type: ignore[attr-defined]
            return

        if section_key == "peripheral_systems":
            self.update_peripheral_system_panel_for_selection(main_window, True)
            if hasattr(main_window, "_ensure_management_property_tab_visible"):
                main_window._ensure_management_property_tab_visible(False)
            if hasattr(main_window, "_hide_all_management_edit_pages"):
                main_window._hide_all_management_edit_pages(None)  # type: ignore[attr-defined]
            return

        if section_key == "equipment_entries":
            self.update_equipment_entry_panel_for_selection(main_window, True)
            if hasattr(main_window, "_ensure_management_property_tab_visible"):
                main_window._ensure_management_property_tab_visible(False)
            if hasattr(main_window, "_hide_all_management_edit_pages"):
                main_window._hide_all_management_edit_pages("equipment_entries")  # type: ignore[attr-defined]
            return

        if section_key == "equipment_tags":
            self.update_equipment_tag_panel_for_selection(main_window, True)
            if hasattr(main_window, "_ensure_management_property_tab_visible"):
                main_window._ensure_management_property_tab_visible(False)
            if hasattr(main_window, "_hide_all_management_edit_pages"):
                main_window._hide_all_management_edit_pages("equipment_tags")  # type: ignore[attr-defined]
            return

        if section_key == "equipment_types":
            self.update_equipment_type_panel_for_selection(main_window, True)
            if hasattr(main_window, "_ensure_management_property_tab_visible"):
                main_window._ensure_management_property_tab_visible(False)
            if hasattr(main_window, "_hide_all_management_edit_pages"):
                main_window._hide_all_management_edit_pages("equipment_types")  # type: ignore[attr-defined]
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
                membership_supported = getattr(binding, "aggregation_mode", "id_list") == "id_list"

        if (
            hasattr(main_window, "management_property_panel")
            and membership_supported
            and item_id
            and binding is not None
        ):
            if section_key == "variable":
                packages, membership, variable_ids = main_window._get_packages_and_membership_for_level_variable_group(
                    item_id
                )
                _ = variable_ids
                if section_obj is not None and hasattr(section_obj, "set_usage_text"):
                    usage_names = [
                        pkg.get("name", pkg.get("package_id", ""))
                        for pkg in packages
                        if pkg.get("package_id") in membership
                    ]
                    section_obj.set_usage_text("，".join(usage_names) if usage_names else "未被任何存档引用")
                main_window.management_property_panel.set_membership_context(  # type: ignore[attr-defined]
                    section_key,
                    binding.key,
                    item_id,
                    packages,
                    membership,
                )
            else:
                packages, membership = main_window._get_management_packages_and_membership(binding.key, item_id)
                main_window.management_property_panel.set_membership_context(  # type: ignore[attr-defined]
                    section_key,
                    binding.key,
                    item_id,
                    packages,
                    membership,
                )
        elif hasattr(main_window, "management_property_panel"):
            main_window.management_property_panel._clear_membership_context()  # type: ignore[attr-defined]

        if hasattr(main_window, "_update_right_panel_visibility"):
            main_window._update_right_panel_visibility()

        if section_key and item_id:
            current_package = getattr(getattr(main_window, "package_controller", None), "current_package", None)
            management_panel = main_window.management_property_panel
            if current_package is not None and section_obj is not None:

                def _on_inline_changed() -> None:
                    if hasattr(main_window, "management_widget"):
                        main_window.management_widget._refresh_items()  # type: ignore[attr-defined]
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
                    if hasattr(main_window, "_ensure_management_property_tab_visible"):
                        main_window._ensure_management_property_tab_visible(True)
                    if hasattr(main_window, "_hide_all_management_edit_pages"):
                        main_window._hide_all_management_edit_pages(None)  # type: ignore[attr-defined]
                    inline_handled = True

        if not inline_handled:
            if hasattr(main_window, "management_property_panel"):
                main_window.management_property_panel.set_header(title, description)
                main_window.management_property_panel.set_rows(rows)
            if hasattr(main_window, "_ensure_management_property_tab_visible"):
                main_window._ensure_management_property_tab_visible(True)


