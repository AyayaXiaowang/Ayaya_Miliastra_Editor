"""UI设置 Mixin - 负责UI组件的创建和布局"""
from __future__ import annotations

import sys

from dataclasses import dataclass
from typing import Callable, Iterable

from PyQt6 import QtCore, QtGui, QtWidgets

from app.models import UiNavigationRequest
from ui.foundation.theme_manager import ThemeManager, Colors
from ui.graph.graph_scene import GraphScene
from ui.graph.graph_view import GraphView
from ui.execution.monitor import ExecutionMonitorPanel
from ui.foundation.navigation_bar import NavigationBar
from ui.graph.library_pages.template_library_widget import TemplateLibraryWidget
from ui.graph.library_pages.entity_placement_widget import EntityPlacementWidget
from ui.graph.library_pages.combat_presets_widget import CombatPresetsWidget
from ui.graph.library_pages.management_library_widget import ManagementLibraryWidget
from ui.panels.template_instance_panel import TemplateInstancePanel
from ui.panels.management_property_panel import ManagementPropertyPanel
from ui.panels.signal_management_panel import SignalManagementPanel
from ui.panels.struct_definition_management_panel import StructDefinitionManagementPanel
from ui.panels.main_camera_panel import MainCameraManagementPanel
from ui.panels.peripheral_system_panel import PeripheralSystemManagementPanel
from ui.todo.todo_list_widget import TodoListWidget
from ui.panels.validation_panel import ValidationPanel
from ui.panels.validation_detail_panel import ValidationDetailPanel
from ui.composite.composite_node_property_panel import CompositeNodePropertyPanel
from ui.composite.composite_node_pin_panel import CompositeNodePinPanel
from ui.graph.library_pages.graph_library_widget import GraphLibraryWidget
from ui.panels.graph_property_panel import GraphPropertyPanel
from ui.panels.ui_control_settings_panel import UIControlSettingsPanel
from ui.graph.library_pages.package_library_widget import PackageLibraryWidget
from ui.panels.combat_player_panel import CombatPlayerEditorPanel
from ui.panels.combat_class_panel import CombatPlayerClassPanel
from ui.panels.combat_skill_panel import CombatSkillPanel
from ui.panels.combat_item_panel import CombatItemPanel
from ui.management.section_registry import MANAGEMENT_SECTIONS, ManagementSectionSpec


@dataclass
class StackPageSpec:
    """描述中央堆叠中的页面构建与后置处理。"""

    attribute_name: str
    builder: Callable[[], QtWidgets.QWidget]
    after_create: Callable[[QtWidgets.QWidget], None] | None = None


class UISetupMixin:
    """UI设置相关方法的Mixin"""

    def _connect_optional_signal(
        self, sender: object, signal_name: str, handler: Callable[..., None]
    ) -> None:
        """安全连接可选信号，避免到处散落的 hasattr 判断。"""
        optional_signal = getattr(sender, signal_name, None)
        if optional_signal is None:
            return
        optional_signal.connect(handler)

    def _apply_global_theme(self) -> None:
        """应用全局主题样式"""
        # 设置主窗口背景色
        self.setStyleSheet(
            f"""
            QMainWindow {{
                background-color: {Colors.BG_MAIN};
            }}
            {ThemeManager.scrollbar_style()}
        """
        )

    def _setup_ui(self) -> None:
        """设置UI"""
        main_widget = QtWidgets.QWidget()
        self.setCentralWidget(main_widget)

        main_layout = QtWidgets.QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._setup_nav_bar(main_layout)

        self.main_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self._create_central_stack()
        self._create_right_panel_container()

        self.main_splitter.addWidget(self.central_stack)
        self.main_splitter.addWidget(self.right_panel_container)
        self.main_splitter.setStretchFactor(0, 3)
        self.main_splitter.setStretchFactor(1, 1)
        # 初始分栏宽度：右侧面板默认更宽，以便属性表格类页面有足够空间展示。
        # Qt 会按当前窗口总宽度按比例缩放这两个值。
        self.main_splitter.setSizes([1200, 800])

        main_layout.addWidget(self.main_splitter)

        self._create_execution_monitor_panel()

    def _setup_nav_bar(self, main_layout: QtWidgets.QHBoxLayout) -> None:
        """创建左侧导航栏并挂载到主布局。"""
        self.nav_bar = NavigationBar()
        self.nav_bar.mode_changed.connect(self._on_mode_changed)
        main_layout.addWidget(self.nav_bar)

    def _create_central_stack(self) -> None:
        """创建中间堆叠窗口及各模式页面（数据驱动，便于扩展）。"""
        self.central_stack = QtWidgets.QStackedWidget()
        for page_spec in self._central_page_specs():
            page_widget = page_spec.builder()
            setattr(self, page_spec.attribute_name, page_widget)
            self.central_stack.addWidget(page_widget)
            if page_spec.after_create is not None:
                page_spec.after_create(page_widget)

    def _central_page_specs(self) -> Iterable[StackPageSpec]:
        """集中描述中央堆叠页，新增模式时只需扩展此列表。"""
        return (
            StackPageSpec("template_widget", self._create_template_page),
            StackPageSpec("placement_widget", self._create_placement_page),
            StackPageSpec("combat_widget", self._create_combat_page),
            StackPageSpec("management_widget", self._create_management_page),
            StackPageSpec("todo_widget", self._create_todo_page),
            StackPageSpec("_composite_placeholder", self._create_composite_placeholder_page),
            StackPageSpec("graph_library_widget", self._create_graph_library_page),
            StackPageSpec("validation_panel", self._create_validation_page),
            StackPageSpec("view", self._create_graph_editor_page),
            StackPageSpec("package_library_widget", self._create_package_library_page),
        )

    def _create_template_page(self) -> TemplateLibraryWidget:
        """元件库页面（ViewMode.TEMPLATE）。"""
        template_widget = TemplateLibraryWidget()
        template_widget.template_selected.connect(self._on_template_selected)
        self._connect_optional_signal(template_widget, "data_changed", self._on_library_page_data_changed)
        return template_widget

    def _create_placement_page(self) -> EntityPlacementWidget:
        """实体摆放页面（ViewMode.PLACEMENT）。"""
        placement_widget = EntityPlacementWidget()
        placement_widget.instance_selected.connect(self._on_instance_selected)
        placement_widget.level_entity_selected.connect(self._on_level_entity_selected)
        self._connect_optional_signal(placement_widget, "data_changed", self._on_library_page_data_changed)
        return placement_widget

    def _create_combat_page(self) -> CombatPresetsWidget:
        """战斗预设页面（ViewMode.COMBAT）。"""
        combat_widget = CombatPresetsWidget()
        self._connect_optional_signal(combat_widget, "player_template_selected", self._on_player_template_selected)
        self._connect_optional_signal(combat_widget, "player_class_selected", self._on_player_class_selected)
        self._connect_optional_signal(combat_widget, "skill_selected", self._on_skill_selected)
        self._connect_optional_signal(combat_widget, "item_selected", self._on_item_selected)
        self._connect_optional_signal(combat_widget, "data_changed", self._on_library_page_data_changed)
        return combat_widget

    def _create_management_page(self) -> ManagementLibraryWidget:
        """管理面板页面（ViewMode.MANAGEMENT）。"""
        management_widget = ManagementLibraryWidget()
        self._connect_optional_signal(management_widget, "data_changed", self._on_library_page_data_changed)
        self._connect_optional_signal(management_widget, "active_section_changed", self._on_management_section_changed)
        if hasattr(management_widget, "ui_control_group_manager"):

            def _on_open_player_editor_requested() -> None:
                request = UiNavigationRequest(
                    resource_kind="combat",
                    resource_id=None,
                    desired_focus="player_editor",
                    origin="ui_control_groups",
                )
                self.nav_coordinator.handle_request(request)

            management_widget.ui_control_group_manager.open_player_editor_requested.connect(
                _on_open_player_editor_requested
            )
        return management_widget

    def _create_todo_page(self) -> TodoListWidget:
        """任务清单页面（ViewMode.TODO）。"""
        todo_widget = TodoListWidget()
        todo_widget.main_window = self
        if hasattr(self, "resource_manager"):
            todo_widget.resource_manager = self.resource_manager
        todo_widget.todo_checked.connect(self._on_todo_checked)

        def _on_todo_jump_to_task(detail_info: dict) -> None:
            graph_id = str(detail_info.get("graph_id") or "")
            request = UiNavigationRequest(
                resource_kind="graph_task",
                resource_id=graph_id,
                graph_id=graph_id or None,
                desired_focus="graph_task",
                origin="todo",
                payload=dict(detail_info),
            )
            self.nav_coordinator.handle_request(request)

        def _on_todo_preview_jump(jump_info: dict) -> None:
            jump_type = jump_info.get("type", "")
            if jump_type == "node":
                node_id = jump_info.get("node_id")
                request = UiNavigationRequest(
                    resource_kind="graph_preview",
                    resource_id=None,
                    desired_focus="graph_node",
                    origin="todo_preview",
                    node_id=str(node_id) if node_id else None,
                    payload=dict(jump_info),
                )
                self.nav_coordinator.handle_request(request)
            elif jump_type == "edge":
                edge_id = jump_info.get("edge_id")
                source_node_id = jump_info.get("src_node")
                target_node_id = jump_info.get("dst_node")
                request = UiNavigationRequest(
                    resource_kind="graph_preview",
                    resource_id=None,
                    desired_focus="graph_edge",
                    origin="todo_preview",
                    edge_id=str(edge_id) if edge_id else None,
                    source_node_id=str(source_node_id) if source_node_id else None,
                    target_node_id=str(target_node_id) if target_node_id else None,
                    payload=dict(jump_info),
                )
                self.nav_coordinator.handle_request(request)

        todo_widget.jump_to_task.connect(_on_todo_jump_to_task)
        todo_widget.preview_view.jump_to_graph_element.connect(_on_todo_preview_jump)
        return todo_widget

    def _create_composite_placeholder_page(self) -> QtWidgets.QWidget:
        """复合节点管理器占位页面（ViewMode.COMPOSITE，懒加载）。"""
        self.composite_widget = None
        self._composite_placeholder = QtWidgets.QWidget()
        return self._composite_placeholder

    def _create_graph_library_page(self) -> GraphLibraryWidget:
        """节点图库页面（ViewMode.GRAPH_LIBRARY）。"""
        graph_library_widget = GraphLibraryWidget(self.resource_manager, self.package_index_manager)
        graph_library_widget.graph_selected.connect(self._on_graph_library_selected)
        graph_library_widget.graph_double_clicked.connect(self._on_graph_library_double_clicked)

        def _on_graph_library_jump(entity_type: str, entity_id: str, package_id: str) -> None:
            request = UiNavigationRequest(
                resource_kind=entity_type,
                resource_id=entity_id,
                package_id=package_id,
                desired_focus="property_panel",
                origin="graph_library",
            )
            self.nav_coordinator.handle_request(request)

        graph_library_widget.jump_to_entity_requested.connect(_on_graph_library_jump)
        return graph_library_widget

    def _create_validation_page(self) -> ValidationPanel:
        """验证面板页面（ViewMode.VALIDATION）。"""
        validation_panel = ValidationPanel()

        def _on_validation_jump_to_issue(detail: dict) -> None:
            request = UiNavigationRequest.for_validation_issue(detail)
            self.nav_coordinator.handle_request(request)

        validation_panel.jump_to_issue.connect(_on_validation_jump_to_issue)
        validation_panel.setMinimumWidth(600)
        return validation_panel

    def _create_graph_editor_page(self) -> GraphView:
        """节点图编辑页面（ViewMode.GRAPH_EDITOR）。"""
        self.view.setMinimumWidth(400)

        self.graph_editor_todo_button = QtWidgets.QPushButton("前往执行", self.view)
        self.graph_editor_todo_button.setObjectName("graphEditorTodoButton")
        self.graph_editor_todo_button.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        self.graph_editor_todo_button.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {Colors.ACCENT};
                color: {Colors.TEXT_ON_PRIMARY};
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Colors.ACCENT_LIGHT};
            }}
            QPushButton:pressed {{
                background-color: {Colors.ACCENT};
            }}
            QPushButton:disabled {{
                background-color: {Colors.BG_DISABLED};
                color: {Colors.TEXT_DISABLED};
            }}
            """
        )
        self.graph_editor_todo_button.setToolTip("返回任务清单并定位到当前图对应的步骤")
        self.graph_editor_todo_button.setVisible(False)
        self.graph_editor_todo_button.clicked.connect(self._on_graph_editor_execute_from_todo)
        self.view.set_extra_top_right_button(self.graph_editor_todo_button)
        return self.view

    def _create_package_library_page(self) -> PackageLibraryWidget:
        """存档页面（ViewMode.PACKAGES）。"""
        package_library_widget = PackageLibraryWidget(self.resource_manager, self.package_index_manager)
        package_library_widget.packages_changed.connect(self._refresh_package_list)
        self._connect_optional_signal(
            package_library_widget, "resource_activated", self._on_package_resource_activated
        )
        self._connect_optional_signal(
            package_library_widget,
            "management_resource_activated",
            self._on_package_management_resource_activated,
        )
        if hasattr(self, "nav_coordinator"):

            def _on_package_library_jump(entity_type: str, entity_id: str, package_id: str) -> None:
                request = UiNavigationRequest(
                    resource_kind=entity_type,
                    resource_id=entity_id,
                    package_id=package_id,
                    desired_focus="property_panel",
                    origin="package_library",
                )
                self.nav_coordinator.handle_request(request)

            package_library_widget.jump_to_entity_requested.connect(_on_package_library_jump)
        self._connect_optional_signal(
            package_library_widget, "management_item_requested", self._on_package_management_item_requested
        )
        self._connect_optional_signal(
            package_library_widget, "graph_double_clicked", self._on_graph_library_double_clicked
        )
        return package_library_widget

    def _create_right_panel_container(self) -> None:
        """创建右侧标签面板及属性相关组件。"""
        self.right_panel_container = QtWidgets.QWidget()
        right_panel_layout = QtWidgets.QVBoxLayout(self.right_panel_container)
        right_panel_layout.setContentsMargins(0, 0, 0, 0)
        right_panel_layout.setSpacing(0)

        self._create_property_panels()

        self.side_tab = QtWidgets.QTabWidget(self.right_panel_container)
        self.side_tab.setObjectName("sideTab")
        self.side_tab.addTab(self.property_panel, "属性")
        right_panel_layout.addWidget(self.side_tab, 1)

        self.right_panel_container.setStyleSheet(ThemeManager.right_side_tab_style())

        self.ui_control_settings_panel = UIControlSettingsPanel()

        self.right_panel_container.setMinimumWidth(350)
        self.right_panel_container.setMaximumWidth(800)

    def _create_property_panels(self) -> None:
        """创建右侧属性类面板（元件/图/复合节点/虚拟引脚/管理配置等）。"""
        from ui.panels.equipment_data_management_panel import (
            EquipmentEntryManagementPanel,
            EquipmentTagManagementPanel,
            EquipmentTypeManagementPanel,
        )
        self.property_panel = TemplateInstancePanel(self.resource_manager, self.package_index_manager)
        self.property_panel.data_updated.connect(self._on_data_updated)
        self.property_panel.graph_selected.connect(self._on_graph_selected)
        self.property_panel.template_package_membership_changed.connect(
            self._on_template_package_membership_changed
        )
        self.property_panel.instance_package_membership_changed.connect(
            self._on_instance_package_membership_changed
        )
        self.property_panel.setMinimumWidth(300)
        # 在保存存档前，通过 PackageController 回调刷新基础信息页中尚未通过去抖写回的编辑内容。
        if hasattr(self, "package_controller"):
            self.package_controller.flush_current_resource_panel = self.property_panel.flush_pending_changes

        # 玩家模板详情面板（战斗预设专用，具体挂载到 side_tab 由模式切换逻辑控制）
        self.player_editor_panel = CombatPlayerEditorPanel(
            self.resource_manager,
            self.package_index_manager,
            self.right_panel_container,
        )
        # 玩家模板详情只负责更新地图与索引，与模板/实例属性面板的刷新逻辑解耦
        self.player_editor_panel.data_changed.connect(
            lambda: self._on_immediate_persist_requested(
                combat_dirty=True,
                index_dirty=True,
            )
        )
        self._connect_optional_signal(
            self.player_editor_panel, "graph_selected", self._on_player_editor_graph_selected
        )

        # 职业详情面板（战斗预设-职业）
        self.player_class_panel = CombatPlayerClassPanel(
            self.resource_manager,
            self.package_index_manager,
            self.right_panel_container,
        )
        self.player_class_panel.data_changed.connect(
            lambda: self._on_immediate_persist_requested(
                combat_dirty=True,
                index_dirty=True,
            )
        )
        self._connect_optional_signal(
            self.player_class_panel, "graph_selected", self._on_player_editor_graph_selected
        )

        # 技能详情面板（战斗预设-技能）
        self.skill_panel = CombatSkillPanel(
            self.resource_manager,
            self.package_index_manager,
            self.right_panel_container,
        )
        self.skill_panel.setMinimumWidth(360)
        self.skill_panel.data_changed.connect(
            lambda: self._on_immediate_persist_requested(
                combat_dirty=True,
                index_dirty=True,
            )
        )
        self._connect_optional_signal(self.skill_panel, "graph_selected", self._on_player_editor_graph_selected)

        # 道具详情面板（战斗预设-道具）
        self.item_panel = CombatItemPanel(
            self.resource_manager,
            self.package_index_manager,
            self.right_panel_container,
        )
        self.item_panel.setMinimumWidth(360)
        self.item_panel.data_changed.connect(
            lambda: self._on_immediate_persist_requested(
                combat_dirty=True,
                index_dirty=True,
            )
        )

        self.graph_property_panel = GraphPropertyPanel(self.resource_manager, self.package_index_manager)

        def _on_graph_property_jump(entity_type: str, entity_id: str, package_id: str) -> None:
            request = UiNavigationRequest(
                resource_kind=entity_type,
                resource_id=entity_id,
                package_id=package_id,
                desired_focus="property_panel",
                origin="graph_property",
            )
            self.nav_coordinator.handle_request(request)

        self.graph_property_panel.jump_to_reference.connect(_on_graph_property_jump)
        self.graph_property_panel.graph_updated.connect(self._on_graph_updated_from_property)
        self.graph_property_panel.package_membership_changed.connect(
            self._on_graph_package_membership_changed
        )
        self.graph_property_panel.setMinimumWidth(300)
        self.graph_property_panel.graph_editor_controller = self.graph_controller

        self.composite_property_panel = CompositeNodePropertyPanel(self.package_index_manager)
        self.composite_property_panel.setMinimumWidth(300)
        self.composite_property_panel.package_membership_changed.connect(
            self._on_composite_package_membership_changed
        )

        self.composite_pin_panel = CompositeNodePinPanel()
        self.composite_pin_panel.setMinimumWidth(300)

        # 管理配置通用属性面板（管理模式下复用主窗口右侧“属性”标签）
        self.management_property_panel = ManagementPropertyPanel(self.right_panel_container)
        self.management_property_panel.setMinimumWidth(300)
        self._connect_optional_signal(
            self.management_property_panel,
            "management_package_membership_changed",
            self._on_management_property_panel_membership_changed,
        )

        # 装备数据管理专用编辑面板（词条 / 标签 / 类型）
        self.equipment_entry_panel = EquipmentEntryManagementPanel(self.right_panel_container)
        self.equipment_entry_panel.setMinimumWidth(380)
        self.equipment_entry_panel.data_updated.connect(self._on_management_edit_page_data_updated)
        self._connect_optional_signal(
            self.equipment_entry_panel,
            "package_membership_changed",
            self._on_equipment_entry_package_membership_changed,
        )

        self.equipment_tag_panel = EquipmentTagManagementPanel(self.right_panel_container)
        self.equipment_tag_panel.setMinimumWidth(360)
        self.equipment_tag_panel.data_updated.connect(self._on_management_edit_page_data_updated)
        self._connect_optional_signal(
            self.equipment_tag_panel,
            "package_membership_changed",
            self._on_equipment_tag_package_membership_changed,
        )

        self.equipment_type_panel = EquipmentTypeManagementPanel(self.right_panel_container)
        self.equipment_type_panel.setMinimumWidth(380)
        self.equipment_type_panel.data_updated.connect(self._on_management_edit_page_data_updated)
        self._connect_optional_signal(
            self.equipment_type_panel,
            "package_membership_changed",
            self._on_equipment_type_package_membership_changed,
        )

        # 外围系统管理专用编辑面板（管理模式下“外围系统管理” Section 使用）
        self.peripheral_system_panel = PeripheralSystemManagementPanel(self.right_panel_container)
        self.peripheral_system_panel.setMinimumWidth(360)
        self.peripheral_system_panel.data_updated.connect(self._on_management_edit_page_data_updated)
        self._connect_optional_signal(
            self.peripheral_system_panel,
            "system_package_membership_changed",
            self._on_peripheral_system_panel_package_membership_changed,
        )

        # 主镜头管理专用编辑面板（管理模式下“主镜头管理” Section 使用）
        self.main_camera_panel = MainCameraManagementPanel(self.right_panel_container)
        self.main_camera_panel.setMinimumWidth(360)
        self.main_camera_panel.data_updated.connect(self._on_management_edit_page_data_updated)
        self._connect_optional_signal(
            self.main_camera_panel,
            "camera_package_membership_changed",
            self._on_main_camera_panel_package_membership_changed,
        )

        # 信号管理专用编辑面板（管理模式下“信号管理” Section 使用）
        self.signal_management_panel = SignalManagementPanel(self.right_panel_container)
        self.signal_management_panel.setMinimumWidth(360)
        if hasattr(self.signal_management_panel, "editor"):
            self.signal_management_panel.editor.signal_changed.connect(
                self._on_signal_property_panel_changed  # type: ignore[attr-defined]
            )
        self._connect_optional_signal(
            self.signal_management_panel,
            "signal_package_membership_changed",
            self._on_signal_property_panel_package_membership_changed,
        )

        # 结构体定义专用编辑面板（管理模式下“结构体定义” Section 使用）
        self.struct_definition_panel = StructDefinitionManagementPanel(self.right_panel_container)
        self.struct_definition_panel.setMinimumWidth(360)
        self.struct_definition_panel.editor.struct_changed.connect(  # type: ignore[attr-defined]
            self._on_struct_property_panel_struct_changed  # type: ignore[attr-defined]
        )
        self.struct_definition_panel.struct_package_membership_changed.connect(  # type: ignore[attr-defined]
            self._on_struct_property_panel_membership_changed  # type: ignore[attr-defined]
        )

        # 管理编辑页逻辑统一使用：
        # - `ManagementPropertyPanel` 构建只读或可编辑表单；
        # - 专用编辑面板（信号 / 结构体 / 主镜头等）承载复杂配置。
        self.management_edit_pages: dict[str, QtWidgets.QWidget] = {
            "equipment_entries": self.equipment_entry_panel,
            "equipment_tags": self.equipment_tag_panel,
            "equipment_types": self.equipment_type_panel,
            "peripheral_systems": self.peripheral_system_panel,
            "main_cameras": self.main_camera_panel,
            "signals": self.signal_management_panel,
            "struct_definitions": self.struct_definition_panel,
        }

        # 验证问题详情面板（验证模式下右侧“详细信息”标签使用）
        self.validation_detail_panel = ValidationDetailPanel(self.right_panel_container)
        if hasattr(self, "validation_panel"):
            self.validation_panel.issue_selected.connect(self.validation_detail_panel.set_issue)

    def _create_execution_monitor_panel(self) -> None:
        """创建执行监控面板并注入上下文。"""
        self.execution_monitor_panel = ExecutionMonitorPanel(self.side_tab)
        self.execution_monitor_panel.hide()
        if hasattr(self.execution_monitor_panel, "graph_view"):
            self.execution_monitor_panel.graph_view = self.view
        if hasattr(self.execution_monitor_panel, "current_workspace_path"):
            self.execution_monitor_panel.current_workspace_path = self.workspace_path
        if hasattr(self.execution_monitor_panel, "get_current_graph_model"):
            self.execution_monitor_panel.get_current_graph_model = self.graph_controller.get_current_model

    def _setup_menubar(self) -> None:
        """设置菜单栏"""
        self.menuBar()

        # F5 快捷键：切换到验证页面并触发验证
        self.validate_action = QtGui.QAction("验证存档", self)
        self.validate_action.setShortcut("F5")
        self.validate_action.triggered.connect(self._switch_to_validation_and_validate)
        self.addAction(self.validate_action)

        # F12 快捷键：开启/关闭 UI 开发者工具（悬停显示控件信息）
        self.dev_tools_action = QtGui.QAction("开发者工具（悬停显示控件）", self)
        self.dev_tools_action.setShortcut("F12")
        self.dev_tools_action.setCheckable(True)
        if hasattr(self, "_on_dev_tools_toggled"):
            self.dev_tools_action.toggled.connect(self._on_dev_tools_toggled)
        self.addAction(self.dev_tools_action)

    def _setup_toolbar(self) -> None:
        """设置工具栏"""
        toolbar = self.addToolBar("工具")

        # 存档选择
        self.package_combo = QtWidgets.QComboBox()
        self.package_combo.setMinimumWidth(200)
        self.package_combo.currentIndexChanged.connect(self._on_package_combo_changed)
        toolbar.addWidget(QtWidgets.QLabel(" 存档: "))
        toolbar.addWidget(self.package_combo)

        toolbar.addSeparator()

        # 新建存档
        new_package_action = QtGui.QAction("新建存档", self)
        new_package_action.triggered.connect(lambda: self.package_controller.create_package(self))
        toolbar.addAction(new_package_action)

        # 保存
        save_action = QtGui.QAction("保存", self)
        save_action.triggered.connect(self.package_controller.save_package)
        toolbar.addAction(save_action)

        toolbar.addSeparator()

        # 设置与重启按钮组
        settings_action = QtGui.QAction("⚙️ 设置", self)
        settings_action.setToolTip("打开程序设置")
        settings_action.triggered.connect(self._open_settings_dialog)
        toolbar.addAction(settings_action)

        restart_action = QtGui.QAction("重启", self)
        restart_action.setToolTip("重启程序以应用需要启动阶段生效的设置")
        restart_action.triggered.connect(self._restart_application_from_toolbar)
        toolbar.addAction(restart_action)

        toolbar.addSeparator()

        # 添加弹簧，将保存状态推到右侧
        spacer = QtWidgets.QWidget()
        spacer.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred
        )
        toolbar.addWidget(spacer)

        # 保存状态指示器
        self.save_status_label = QtWidgets.QLabel("已保存")
        self.save_status_label.setProperty("status", "saved")
        self.save_status_label.setStyleSheet(
            f"""
            QLabel {{
                padding: 4px 12px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 11px;
            }}
            QLabel[status="saved"] {{
                background-color: {Colors.SUCCESS};
                color: {Colors.TEXT_ON_PRIMARY};
            }}
            QLabel[status="unsaved"] {{
                background-color: {Colors.WARNING};
                color: {Colors.TEXT_ON_PRIMARY};
            }}
            QLabel[status="saving"] {{
                background-color: {Colors.INFO};
                color: {Colors.TEXT_ON_PRIMARY};
            }}
            QLabel[status="readonly"] {{
                background-color: {Colors.BG_DISABLED};
                color: {Colors.TEXT_SECONDARY};
            }}
        """
        )
        toolbar.addWidget(self.save_status_label)

        # （已移除）真实执行入口按钮

    def _restart_application_from_toolbar(self) -> None:
        """从主窗口工具栏重启整个应用，行为与设置对话框中的重启一致。"""
        application = QtWidgets.QApplication.instance()
        if application is None:
            return
        QtCore.QProcess.startDetached(sys.executable, ["-m", "app.cli.run_app"])
        application.quit()

