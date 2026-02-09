from __future__ import annotations

from typing import Any, Callable

from app.models.view_modes import ViewMode
from app.ui.execution.monitor import ExecutionMonitorPanel
from app.ui.main_window.features.feature_protocol import MainWindowFeature
from app.ui.main_window.management_right_panel_registry import MANAGEMENT_RIGHT_PANEL_DYNAMIC_TABS
from app.ui.main_window.right_panel_controller import build_right_panel_controller
from app.ui.main_window.wiring.right_panel_binder import (
    bind_combat_panels,
    bind_composite_panels,
    bind_graph_property_panel,
    bind_management_panels,
    bind_template_instance_panel,
    bind_validation_detail_panel,
)


class RightPanelAssemblyFeature(MainWindowFeature):
    """右侧面板装配 Feature（大胆收敛：创建/连线/注册一处完成）。"""

    feature_id = "right_panel_assembly"

    def install(self, *, main_window: Any) -> None:
        side_tab = getattr(main_window, "side_tab", None)
        if side_tab is None:
            raise RuntimeError("RightPanelAssemblyFeature.install 需要 main_window.side_tab 先初始化")

        right_panel_registry = getattr(main_window, "right_panel_registry", None)
        if right_panel_registry is None:
            raise RuntimeError(
                "RightPanelAssemblyFeature.install 需要 main_window.right_panel_registry 先初始化"
            )

        # === 1) 创建执行监控面板（并注入上下文） ===
        execution_monitor_panel = ExecutionMonitorPanel(side_tab)
        execution_monitor_panel.hide()

        execution_monitor_panel.graph_view = main_window.app_state.graph_view
        execution_monitor_panel.current_workspace_path = main_window.app_state.workspace_path
        graph_controller = getattr(main_window, "graph_controller", None)
        getter = getattr(graph_controller, "get_current_model", None) if graph_controller is not None else None
        if callable(getter):
            execution_monitor_panel.get_current_graph_model = getter

        # === 2) 右侧面板信号 wiring（原本分散在 UISetupMixin） ===
        connect_optional_signal = getattr(main_window, "_connect_optional_signal", None)
        if not callable(connect_optional_signal):
            raise RuntimeError("RightPanelAssemblyFeature.install 需要 main_window._connect_optional_signal 可调用")

        self._bind_right_panel_signals(
            main_window=main_window,
            connect_optional_signal=connect_optional_signal,
        )

        # === 3) 右侧标签注册矩阵（原本在 wiring/right_panel_registry_config.py） ===
        self._register_right_panel_tabs(main_window=main_window, execution_monitor_panel=execution_monitor_panel)

        # === 4) 右侧对外唯一入口（Facade）：main_window.right_panel ===
        main_window.right_panel = build_right_panel_controller(
            main_window=main_window,
            registry=right_panel_registry,
        )
        # 注意：不再在 main_window 上额外暴露 right_panel_policy，避免多入口漂移。

    def _require_callable(self, main_window: Any, attribute_name: str) -> Callable[..., Any]:
        target = getattr(main_window, attribute_name, None)
        if not callable(target):
            raise RuntimeError(f"RightPanelAssemblyFeature 需要 main_window.{attribute_name} 可调用")
        return target

    def _bind_right_panel_signals(
        self,
        *,
        main_window: Any,
        connect_optional_signal: Callable[[object, str, Callable[..., None]], None],
    ) -> None:
        bind_template_instance_panel(
            property_panel=getattr(main_window, "property_panel", None),
            package_controller=getattr(main_window, "package_controller", None),
            on_data_updated=self._require_callable(main_window, "_on_data_updated"),
            on_graph_selected=self._require_callable(main_window, "_on_graph_selected"),
            on_template_package_membership_changed=self._require_callable(
                main_window, "_on_template_package_membership_changed"
            ),
            on_instance_package_membership_changed=self._require_callable(
                main_window, "_on_instance_package_membership_changed"
            ),
        )

        bind_combat_panels(
            connect_optional_signal=connect_optional_signal,
            player_editor_panel=getattr(main_window, "player_editor_panel", None),
            player_class_panel=getattr(main_window, "player_class_panel", None),
            skill_panel=getattr(main_window, "skill_panel", None),
            item_panel=getattr(main_window, "item_panel", None),
            on_immediate_persist_requested=self._require_callable(main_window, "_on_immediate_persist_requested"),
            on_player_editor_graph_selected=self._require_callable(main_window, "_on_player_editor_graph_selected"),
        )

        bind_graph_property_panel(
            graph_property_panel=getattr(main_window, "graph_property_panel", None),
            nav_coordinator=getattr(main_window, "nav_coordinator", None),
            graph_controller=getattr(main_window, "graph_controller", None),
            on_graph_updated_from_property=self._require_callable(main_window, "_on_graph_updated_from_property"),
            on_graph_package_membership_changed=self._require_callable(
                main_window, "_on_graph_package_membership_changed"
            ),
        )

        bind_composite_panels(
            composite_property_panel=getattr(main_window, "composite_property_panel", None),
            on_composite_package_membership_changed=self._require_callable(
                main_window, "_on_composite_package_membership_changed"
            ),
        )

        bind_management_panels(
            connect_optional_signal=connect_optional_signal,
            management_property_panel=getattr(main_window, "management_property_panel", None),
            on_management_property_panel_membership_changed=self._require_callable(
                main_window, "_on_management_property_panel_membership_changed"
            ),
            equipment_entry_panel=getattr(main_window, "equipment_entry_panel", None),
            on_equipment_entry_package_membership_changed=self._require_callable(
                main_window, "_on_equipment_entry_package_membership_changed"
            ),
            equipment_tag_panel=getattr(main_window, "equipment_tag_panel", None),
            on_equipment_tag_package_membership_changed=self._require_callable(
                main_window, "_on_equipment_tag_package_membership_changed"
            ),
            equipment_type_panel=getattr(main_window, "equipment_type_panel", None),
            on_equipment_type_package_membership_changed=self._require_callable(
                main_window, "_on_equipment_type_package_membership_changed"
            ),
            peripheral_system_panel=getattr(main_window, "peripheral_system_panel", None),
            on_peripheral_system_panel_package_membership_changed=self._require_callable(
                main_window, "_on_peripheral_system_panel_package_membership_changed"
            ),
            main_camera_panel=getattr(main_window, "main_camera_panel", None),
            on_main_camera_panel_package_membership_changed=self._require_callable(
                main_window, "_on_main_camera_panel_package_membership_changed"
            ),
            signal_management_panel=getattr(main_window, "signal_management_panel", None),
            on_signal_property_panel_changed=self._require_callable(main_window, "_on_signal_property_panel_changed"),
            on_signal_property_panel_package_membership_changed=self._require_callable(
                main_window, "_on_signal_property_panel_package_membership_changed"
            ),
            struct_definition_panel=getattr(main_window, "struct_definition_panel", None),
            on_struct_property_panel_struct_changed=self._require_callable(
                main_window, "_on_struct_property_panel_struct_changed"
            ),
            on_struct_property_panel_membership_changed=self._require_callable(
                main_window, "_on_struct_property_panel_membership_changed"
            ),
            on_management_edit_page_data_updated=self._require_callable(
                main_window, "_on_management_edit_page_data_updated"
            ),
        )

        bind_validation_detail_panel(
            validation_panel=getattr(main_window, "validation_panel", None),
            validation_detail_panel=getattr(main_window, "validation_detail_panel", None),
        )

    def _register_right_panel_tabs(
        self,
        *,
        main_window: Any,
        execution_monitor_panel: Any,
    ) -> None:
        registry = getattr(main_window, "right_panel_registry", None)
        if registry is None:
            raise RuntimeError("RightPanelAssemblyFeature._register_right_panel_tabs 缺少 right_panel_registry")

        # 静态标签（由 RIGHT_PANEL_TABS 控制）
        registry.register_static("graph_property", main_window.graph_property_panel, "图属性")
        registry.register_static(
            "graph_used_definitions",
            main_window.graph_used_definitions_panel,
            "信号/结构体/变量",
        )
        registry.register_static("composite_property", main_window.composite_property_panel, "复合节点属性")
        registry.register_static("composite_pins", main_window.composite_pin_panel, "虚拟引脚")
        registry.register_static("validation_detail", main_window.validation_detail_panel, "详细信息")

        # 动态标签（由选择态/上下文驱动，仅做越权回收 + 统一注册）
        registry.register_dynamic(
            "property",
            main_window.property_panel,
            "属性",
            allowed_modes=(ViewMode.TEMPLATE, ViewMode.PLACEMENT, ViewMode.PACKAGES, ViewMode.TODO),
        )
        registry.register_dynamic(
            "management_property",
            main_window.management_property_panel,
            "属性",
            allowed_modes=(ViewMode.MANAGEMENT, ViewMode.PACKAGES),
        )
        registry.register_dynamic(
            "execution_monitor",
            execution_monitor_panel,
            "执行监控",
            allowed_modes=(ViewMode.TODO,),
        )

        # 管理模式右侧 tab：统一走 registry 配置（避免 tab_id/title/属性名三处硬编码）
        for tab_spec in MANAGEMENT_RIGHT_PANEL_DYNAMIC_TABS:
            widget = getattr(main_window, tab_spec.main_window_attribute, None)
            if widget is None:
                raise RuntimeError(
                    f"RightPanelAssemblyFeature._register_right_panel_tabs 缺少 main_window.{tab_spec.main_window_attribute}"
                )
            registry.register_dynamic(
                tab_spec.tab_id,
                widget,
                tab_spec.title,
                allowed_modes=tab_spec.allowed_modes,
            )

        # 战斗预设详情页（战斗模式与存档库模式下允许临时拉起）
        registry.register_dynamic(
            "player_editor",
            main_window.player_editor_panel,
            "玩家模板",
            allowed_modes=(ViewMode.COMBAT, ViewMode.PACKAGES),
        )
        registry.register_dynamic(
            "player_class_editor",
            main_window.player_class_panel,
            "职业",
            allowed_modes=(ViewMode.COMBAT, ViewMode.PACKAGES),
        )
        registry.register_dynamic(
            "skill_editor",
            main_window.skill_panel,
            "技能",
            allowed_modes=(ViewMode.COMBAT, ViewMode.PACKAGES),
        )
        registry.register_dynamic(
            "item_editor",
            main_window.item_panel,
            "道具",
            allowed_modes=(ViewMode.COMBAT, ViewMode.PACKAGES),
        )


