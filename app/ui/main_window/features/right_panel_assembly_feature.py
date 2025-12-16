from __future__ import annotations

from typing import Any, Callable

from app.models.view_modes import ViewMode
from app.ui.execution.monitor import ExecutionMonitorPanel
from app.ui.main_window.features.feature_protocol import MainWindowFeature
from app.ui.main_window.right_panel_policy import RightPanelPolicy
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

        if hasattr(execution_monitor_panel, "graph_view"):
            execution_monitor_panel.graph_view = getattr(main_window, "view", None)
        if hasattr(execution_monitor_panel, "current_workspace_path"):
            execution_monitor_panel.current_workspace_path = getattr(main_window, "workspace_path", None)
        if hasattr(execution_monitor_panel, "get_current_graph_model"):
            graph_controller = getattr(main_window, "graph_controller", None)
            getter = getattr(graph_controller, "get_current_model", None) if graph_controller is not None else None
            if callable(getter):
                execution_monitor_panel.get_current_graph_model = getter

        # 兼容旧访问路径：Todo/快捷键路由会 getattr(main_window, "execution_monitor_panel", None)
        main_window.execution_monitor_panel = execution_monitor_panel

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

        # === 4) 右侧联动策略（集中管理 section/mode → tabs 显隐） ===
        main_window.right_panel_policy = RightPanelPolicy(main_window)

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
            "ui_settings",
            main_window.ui_control_settings_panel,
            "界面控件设置",
            allowed_modes=(ViewMode.MANAGEMENT,),
        )
        registry.register_dynamic(
            "execution_monitor",
            execution_monitor_panel,
            "执行监控",
            allowed_modes=(ViewMode.TODO,),
        )

        # 管理模式专用编辑页
        registry.register_dynamic(
            "signal_editor",
            main_window.signal_management_panel,
            "信号",
            allowed_modes=(ViewMode.MANAGEMENT,),
        )
        registry.register_dynamic(
            "struct_editor",
            main_window.struct_definition_panel,
            "结构体",
            allowed_modes=(ViewMode.MANAGEMENT,),
        )
        registry.register_dynamic(
            "main_camera_editor",
            main_window.main_camera_panel,
            "主镜头",
            allowed_modes=(ViewMode.MANAGEMENT,),
        )
        registry.register_dynamic(
            "peripheral_system_editor",
            main_window.peripheral_system_panel,
            "外围系统",
            allowed_modes=(ViewMode.MANAGEMENT,),
        )
        registry.register_dynamic(
            "equipment_entry_editor",
            main_window.equipment_entry_panel,
            "装备词条",
            allowed_modes=(ViewMode.MANAGEMENT,),
        )
        registry.register_dynamic(
            "equipment_tag_editor",
            main_window.equipment_tag_panel,
            "装备标签",
            allowed_modes=(ViewMode.MANAGEMENT,),
        )
        registry.register_dynamic(
            "equipment_type_editor",
            main_window.equipment_type_panel,
            "装备类型",
            allowed_modes=(ViewMode.MANAGEMENT,),
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


