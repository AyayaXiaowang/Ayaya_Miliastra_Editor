"""UI设置 Mixin - 负责UI组件的创建和布局"""
from __future__ import annotations

import sys

from dataclasses import dataclass
from typing import Callable, Iterable

from PyQt6 import QtCore, QtGui, QtWidgets

from app.models.view_modes import ViewMode
from app.ui.foundation.theme_manager import ThemeManager, Colors
from engine.configs.settings import settings
from app.ui.graph.graph_scene import GraphScene
from app.ui.graph.graph_view import GraphView
from app.ui.foundation.navigation_bar import NavigationBar
from app.ui.graph.library_pages.template_library_widget import TemplateLibraryWidget
from app.ui.graph.library_pages.entity_placement_widget import EntityPlacementWidget
from app.ui.graph.library_pages.combat_presets_widget import CombatPresetsWidget
from app.ui.graph.library_pages.management_library_widget import ManagementLibraryWidget
from app.ui.panels.template_instance_panel import TemplateInstancePanel
from app.ui.panels.management_property_panel import ManagementPropertyPanel
from app.ui.panels.signal_management_panel import SignalManagementPanel
from app.ui.panels.struct_definition_management_panel import StructDefinitionManagementPanel
from app.ui.panels.main_camera_panel import MainCameraManagementPanel
from app.ui.panels.peripheral_system_panel import PeripheralSystemManagementPanel
from app.ui.todo.list.todo_list_widget import TodoListWidget
from app.ui.panels.validation_panel import ValidationPanel
from app.ui.panels.validation_detail_panel import ValidationDetailPanel
from app.ui.composite.composite_node_property_panel import CompositeNodePropertyPanel
from app.ui.composite.composite_node_pin_panel import CompositeNodePinPanel
from app.ui.graph.library_pages.graph_library_widget import GraphLibraryWidget
from app.ui.panels.graph.graph_property_panel import GraphPropertyPanel
from app.ui.panels.ui.ui_control_settings_panel import UIControlSettingsPanel
from app.ui.graph.library_pages.package_library_widget import PackageLibraryWidget
from app.ui.panels.combat.combat_player_panel import CombatPlayerEditorPanel
from app.ui.panels.combat.combat_class_panel import CombatPlayerClassPanel
from app.ui.panels.combat.combat_skill_panel import CombatSkillPanel
from app.ui.panels.combat.combat_item_panel import CombatItemPanel
from app.ui.management.section_registry import MANAGEMENT_SECTIONS, ManagementSectionSpec
from app.ui.main_window.right_panel_registry import RightPanelRegistry
from app.ui.foundation.performance_monitor import get_shared_performance_monitor
from app.ui.foundation.performance_panel import AppPerformanceOverlay


@dataclass
class StackPageSpec:
    """描述中央堆叠中的页面构建与后置处理。"""

    attribute_name: str | None
    builder: Callable[[], QtWidgets.QWidget]
    after_create: Callable[[QtWidgets.QWidget], None] | None = None


class UISetupMixin:
    """UI设置相关方法的Mixin"""

    def _apply_keymap_shortcuts(self) -> None:
        """将 KeymapStore 中的快捷键绑定应用到已创建的 QAction / 页面快捷键。"""
        keymap_store = getattr(self.app_state, "keymap_store", None)
        if keymap_store is None:
            return

        # ---- 主窗口级 QAction
        command_palette_action = getattr(self, "command_palette_action", None)
        if isinstance(command_palette_action, QtGui.QAction):
            shortcuts = keymap_store.get_shortcuts("global.command_palette")
            command_palette_action.setShortcuts([QtGui.QKeySequence(s) for s in shortcuts if s])

        validate_action = getattr(self, "validate_action", None)
        if isinstance(validate_action, QtGui.QAction):
            validate_action.setShortcut(keymap_store.get_primary_shortcut("global.validate"))

        dev_tools_action = getattr(self, "dev_tools_action", None)
        if isinstance(dev_tools_action, QtGui.QAction):
            dev_tools_action.setShortcut(keymap_store.get_primary_shortcut("global.dev_tools_toggle"))

        app_perf_overlay_action = getattr(self, "app_perf_overlay_action", None)
        if isinstance(app_perf_overlay_action, QtGui.QAction):
            app_perf_overlay_action.setShortcut(keymap_store.get_primary_shortcut("global.app_perf_overlay_toggle"))

        navigation_back_action = getattr(self, "navigation_back_action", None)
        if isinstance(navigation_back_action, QtGui.QAction):
            navigation_back_action.setShortcut(
                QtGui.QKeySequence(keymap_store.get_primary_shortcut("global.nav_back"))
            )
            navigation_back_action.setToolTip(
                f"后退（{keymap_store.get_primary_shortcut('global.nav_back') or '未绑定'}）"
            )

        navigation_forward_action = getattr(self, "navigation_forward_action", None)
        if isinstance(navigation_forward_action, QtGui.QAction):
            navigation_forward_action.setShortcut(
                QtGui.QKeySequence(keymap_store.get_primary_shortcut("global.nav_forward"))
            )
            navigation_forward_action.setToolTip(
                f"前进（{keymap_store.get_primary_shortcut('global.nav_forward') or '未绑定'}）"
            )

        # ---- 库页标准快捷键
        for attr_name in ("template_widget", "placement_widget", "combat_widget", "graph_library_widget"):
            widget = getattr(self, attr_name, None)
            apply_method = getattr(widget, "apply_keymap_shortcuts", None) if widget is not None else None
            if callable(apply_method):
                apply_method(keymap_store)

        # ---- 节点图画布快捷键
        graph_view = getattr(self.app_state, "graph_view", None)
        apply_graph_view = getattr(graph_view, "apply_keymap_shortcuts", None) if graph_view is not None else None
        if callable(apply_graph_view):
            apply_graph_view(keymap_store)

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

        # 全局性能悬浮面板（可选）：用于在任意页面定位 UI 卡顿来源。
        self._app_perf_monitor = get_shared_performance_monitor()
        self._app_perf_overlay = AppPerformanceOverlay(main_widget, monitor=self._app_perf_monitor)
        self._app_perf_overlay.requested_open_details.connect(self.open_performance_monitor_dialog)
        self.refresh_app_performance_monitor_visibility()

    def open_performance_monitor_dialog(self) -> None:
        """打开全局性能监控面板（非模态，可保持在所有页面）。"""
        dialog = getattr(self, "_app_perf_dialog", None)
        if isinstance(dialog, QtWidgets.QDialog):
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()
            return

        from app.ui.dialogs.performance_monitor_dialog import PerformanceMonitorDialog

        dlg = PerformanceMonitorDialog(monitor=self._app_perf_monitor, parent=self)
        setattr(self, "_app_perf_dialog", dlg)

        def _clear_dialog(*_args) -> None:
            setattr(self, "_app_perf_dialog", None)

        dlg.finished.connect(_clear_dialog)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def refresh_app_performance_monitor_visibility(self) -> None:
        """根据 settings 刷新全局性能监控（立即生效，无需重启）。"""
        monitor_enabled = bool(getattr(settings, "APP_PERF_MONITOR_ENABLED", False))
        overlay_enabled = bool(getattr(settings, "APP_PERF_OVERLAY_ENABLED", False))
        stall_threshold_ms = float(getattr(settings, "APP_PERF_STALL_THRESHOLD_MS", 250.0))
        capture_stacks = bool(getattr(settings, "APP_PERF_CAPTURE_STACKS_ENABLED", True))

        # 若悬浮面板已被关闭（可能来自设置页），则不再保留“由快捷键临时强制开启监控”的标记。
        forced = bool(getattr(self, "_app_perf_monitor_forced_by_hotkey", False))
        if forced and not overlay_enabled:
            setattr(self, "_app_perf_monitor_forced_by_hotkey", False)

        monitor = getattr(self, "_app_perf_monitor", None)
        if monitor is not None and hasattr(monitor, "configure"):
            monitor.configure(
                stall_threshold_ms=stall_threshold_ms,
                capture_stacks=capture_stacks,
            )

        if monitor is not None and hasattr(monitor, "start") and hasattr(monitor, "stop"):
            if monitor_enabled or overlay_enabled:
                monitor.start()
            else:
                monitor.stop()

        overlay = getattr(self, "_app_perf_overlay", None)
        if isinstance(overlay, AppPerformanceOverlay):
            if overlay_enabled and (monitor_enabled or overlay_enabled):
                overlay.start()
            else:
                overlay.stop()

        # 同步菜单动作的勾选态（避免设置页修改后动作状态不一致）
        action = getattr(self, "app_perf_overlay_action", None)
        if isinstance(action, QtGui.QAction):
            desired = bool(overlay_enabled)
            if action.isChecked() != desired:
                action.blockSignals(True)
                action.setChecked(desired)
                action.blockSignals(False)

    def _on_app_perf_overlay_toggled(self, enabled: bool) -> None:
        """F11 开关：显示/隐藏“全局性能悬浮面板”（卡顿定位）。"""
        will_enable = bool(enabled)
        if will_enable:
            settings.APP_PERF_OVERLAY_ENABLED = True
            was_monitor_enabled = bool(getattr(settings, "APP_PERF_MONITOR_ENABLED", False))
            if not was_monitor_enabled:
                settings.APP_PERF_MONITOR_ENABLED = True
                setattr(self, "_app_perf_monitor_forced_by_hotkey", True)
        else:
            settings.APP_PERF_OVERLAY_ENABLED = False
            forced = bool(getattr(self, "_app_perf_monitor_forced_by_hotkey", False))
            if forced:
                settings.APP_PERF_MONITOR_ENABLED = False
                setattr(self, "_app_perf_monitor_forced_by_hotkey", False)

        self.refresh_app_performance_monitor_visibility()

        toast = getattr(self, "_show_toast", None)
        if callable(toast):
            toast("性能悬浮面板：已显示" if will_enable else "性能悬浮面板：已隐藏", "info")

    def _setup_nav_bar(self, main_layout: QtWidgets.QHBoxLayout) -> None:
        """创建左侧导航栏并挂载到主布局。"""
        self.nav_bar = NavigationBar()
        self.nav_bar.mode_changed.connect(self._on_mode_changed)
        open_local_sim = getattr(self, "_open_local_graph_sim_dialog", None)
        if callable(open_local_sim):
            self.nav_bar.ensure_extension_button(
                key="local_graph_sim",
                icon_text="🧪",
                label="本地测试",
                on_click=open_local_sim,
                tooltip="节点图 + UI（HTML）本地测试：浏览器预览 + 点击注入 + 状态回显",
            )
        open_effect_preview = getattr(self, "_open_effect_preview", None)
        if callable(open_effect_preview):
            self.nav_bar.ensure_extension_button(
                key="effect_preview",
                icon_text="⚡",
                label="特效预览",
                on_click=open_effect_preview,
                tooltip="打开“千星沙箱全特效预览”（Web）",
            )
        main_layout.addWidget(self.nav_bar)

    def _create_central_stack(self) -> None:
        """创建中间堆叠窗口及各模式页面（数据驱动，便于扩展）。"""
        self.central_stack = QtWidgets.QStackedWidget()
        for page_spec in self._central_page_specs():
            page_widget = page_spec.builder()
            if page_spec.attribute_name:
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
            # 节点图编辑器视图由 AppState 持有，不在主窗口上再暴露兼容别名（避免多真源）。
            StackPageSpec("graph_editor_canvas_host", self._create_graph_editor_page),
            StackPageSpec("package_library_widget", self._create_package_library_page),
        )

    def _create_template_page(self) -> TemplateLibraryWidget:
        """元件库页面（ViewMode.TEMPLATE）。"""
        template_widget = TemplateLibraryWidget()
        return template_widget

    def _create_placement_page(self) -> EntityPlacementWidget:
        """实体摆放页面（ViewMode.PLACEMENT）。"""
        placement_widget = EntityPlacementWidget()
        return placement_widget

    def _create_combat_page(self) -> CombatPresetsWidget:
        """战斗预设页面（ViewMode.COMBAT）。"""
        combat_widget = CombatPresetsWidget()
        return combat_widget

    def _create_management_page(self) -> ManagementLibraryWidget:
        """管理面板页面（ViewMode.MANAGEMENT）。"""
        management_widget = ManagementLibraryWidget()
        return management_widget

    def _create_todo_page(self) -> TodoListWidget:
        """任务清单页面（ViewMode.TODO）。"""
        todo_widget = TodoListWidget()
        return todo_widget

    def _create_composite_placeholder_page(self) -> QtWidgets.QWidget:
        """复合节点管理器占位页面（ViewMode.COMPOSITE，懒加载）。"""
        self.composite_widget = None
        self._composite_placeholder = QtWidgets.QWidget()
        return self._composite_placeholder

    def _create_graph_library_page(self) -> GraphLibraryWidget:
        """节点图库页面（ViewMode.GRAPH_LIBRARY）。"""
        graph_library_widget = GraphLibraryWidget(
            self.app_state.resource_manager,
            self.app_state.package_index_manager,
        )
        return graph_library_widget

    def _create_validation_page(self) -> ValidationPanel:
        """验证面板页面（ViewMode.VALIDATION）。"""
        validation_panel = ValidationPanel()
        validation_panel.setMinimumWidth(600)
        return validation_panel

    def _create_graph_editor_page(self) -> QtWidgets.QWidget:
        """节点图编辑页面（ViewMode.GRAPH_EDITOR）。

        注意：中央堆叠页使用“Host 容器”承载全局唯一的 `app_state.graph_view`，
        以便同一张画布可以在 TODO 预览与编辑器之间移动复用。
        """
        from app.ui.graph.graph_canvas_host import GraphCanvasHost

        graph_view = self.app_state.graph_view
        graph_view.setMinimumWidth(400)

        host = GraphCanvasHost()
        host.setObjectName("graphEditorCanvasHost")
        host.attach_view(graph_view)

        self.graph_editor_todo_button = QtWidgets.QPushButton("前往执行", graph_view)
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
        self.graph_editor_todo_button.setToolTip("前往任务清单并定位/生成当前图对应的执行步骤")
        self.graph_editor_todo_button.setVisible(False)
        self.graph_editor_todo_button.clicked.connect(self._on_graph_editor_execute_from_todo)
        graph_view.set_extra_top_right_button(self.graph_editor_todo_button)
        return host

    def _create_package_library_page(self) -> PackageLibraryWidget:
        """存档页面（ViewMode.PACKAGES）。"""
        package_library_widget = PackageLibraryWidget(
            self.app_state.resource_manager,
            self.app_state.package_index_manager,
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
        # 右侧 tab 切换/增删时刷新右上角保存状态提示，确保只读页签不残留“已保存”文案
        if hasattr(self, "_on_right_panel_tab_changed"):
            self.side_tab.currentChanged.connect(self._on_right_panel_tab_changed)  # type: ignore[arg-type]
        right_panel_layout.addWidget(self.side_tab, 1)

        self.right_panel_container.setStyleSheet(ThemeManager.right_side_tab_style())

        self.ui_control_settings_panel = UIControlSettingsPanel()

        # 右侧标签注册表：集中管理 tab_id -> widget/标题/模式约束
        self.right_panel_registry = RightPanelRegistry(
            side_tab=self.side_tab,
            right_panel_container=self.right_panel_container,
        )

        # 安装主窗口 Feature（渐进迁移的单点扩展口）
        self._install_main_window_features()

        # 初始状态下可能没有任何可见 tab：统一由 RightPanelRegistry 决定容器可见性。
        self.right_panel_registry.update_visibility()

        self.right_panel_container.setMinimumWidth(350)
        # 右侧属性面板允许更宽：部分表格/多列编辑面板在窄宽度下可用性较差。
        self.right_panel_container.setMaximumWidth(1200)

    def _install_main_window_features(self) -> None:
        """安装默认主窗口 Feature 集合。

        约定：在 `side_tab` 与 `right_panel_registry` 初始化完成后调用，
        让 Feature 可以创建自己的控件并注册到右侧标签注册表中。
        """
        from app.ui.main_window.features import install_default_main_window_features

        self.main_window_features = install_default_main_window_features(main_window=self)

    def _create_property_panels(self) -> None:
        """创建右侧属性类面板（元件/图/复合节点/虚拟引脚/管理配置等）。"""
        from app.ui.panels.equipment_data_management_panel import (
            EquipmentEntryManagementPanel,
            EquipmentTagManagementPanel,
            EquipmentTypeManagementPanel,
        )
        from app.ui.panels.graph.graph_used_definitions_panel import GraphUsedDefinitionsPanel
        resource_manager = self.app_state.resource_manager
        package_index_manager = self.app_state.package_index_manager

        self.property_panel = TemplateInstancePanel(resource_manager, package_index_manager)
        self.property_panel.setMinimumWidth(300)

        # 玩家模板详情面板（战斗预设专用，具体挂载到 side_tab 由模式切换逻辑控制）
        self.player_editor_panel = CombatPlayerEditorPanel(
            resource_manager,
            package_index_manager,
            self.right_panel_container,
        )

        # 职业详情面板（战斗预设-职业）
        self.player_class_panel = CombatPlayerClassPanel(
            resource_manager,
            package_index_manager,
            self.right_panel_container,
        )

        # 技能详情面板（战斗预设-技能）
        self.skill_panel = CombatSkillPanel(
            resource_manager,
            package_index_manager,
            self.right_panel_container,
        )
        self.skill_panel.setMinimumWidth(360)

        # 道具详情面板（战斗预设-道具）
        self.item_panel = CombatItemPanel(
            resource_manager,
            package_index_manager,
            self.right_panel_container,
        )
        self.item_panel.setMinimumWidth(360)

        self.graph_property_panel = GraphPropertyPanel(resource_manager, package_index_manager)
        self.graph_property_panel.setMinimumWidth(300)

        # 节点图库：信号/结构体/自定义变量只读查看面板（由 GRAPH_LIBRARY 模式挂载到右侧 Tab）
        self.graph_used_definitions_panel = GraphUsedDefinitionsPanel(
            resource_manager,
            package_index_manager,
            self.right_panel_container,
        )
        self.graph_used_definitions_panel.setMinimumWidth(360)

        self.composite_property_panel = CompositeNodePropertyPanel(package_index_manager)
        self.composite_property_panel.setMinimumWidth(300)

        self.composite_pin_panel = CompositeNodePinPanel()
        self.composite_pin_panel.setMinimumWidth(300)

        # 管理配置通用属性面板（管理模式下复用主窗口右侧“属性”标签）
        self.management_property_panel = ManagementPropertyPanel(self.right_panel_container)
        self.management_property_panel.setMinimumWidth(300)

        # 装备数据管理专用编辑面板（词条 / 标签 / 类型）
        self.equipment_entry_panel = EquipmentEntryManagementPanel(self.right_panel_container)
        self.equipment_entry_panel.setMinimumWidth(380)

        self.equipment_tag_panel = EquipmentTagManagementPanel(self.right_panel_container)
        self.equipment_tag_panel.setMinimumWidth(360)

        self.equipment_type_panel = EquipmentTypeManagementPanel(self.right_panel_container)
        self.equipment_type_panel.setMinimumWidth(380)

        # 外围系统管理专用编辑面板（管理模式下“外围系统管理” Section 使用）
        self.peripheral_system_panel = PeripheralSystemManagementPanel(self.right_panel_container)
        self.peripheral_system_panel.setMinimumWidth(360)

        # 主镜头管理专用编辑面板（管理模式下“主镜头管理” Section 使用）
        self.main_camera_panel = MainCameraManagementPanel(self.right_panel_container)
        self.main_camera_panel.setMinimumWidth(360)

        # 信号管理专用编辑面板（管理模式下“信号管理” Section 使用）
        self.signal_management_panel = SignalManagementPanel(self.right_panel_container)
        self.signal_management_panel.setMinimumWidth(360)

        # 结构体定义专用编辑面板（管理模式下“结构体定义” Section 使用）
        self.struct_definition_panel = StructDefinitionManagementPanel(self.right_panel_container)
        self.struct_definition_panel.setMinimumWidth(360)

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

    def _setup_menubar(self) -> None:
        """设置菜单栏"""
        self.menuBar()

        # Ctrl+K / Ctrl+Shift+P：全局搜索/命令面板（避免与 Ctrl+P 全局暂停冲突）
        self.command_palette_action = QtGui.QAction("全局搜索 / 命令面板", self)
        open_palette = getattr(self, "_open_command_palette", None)
        if callable(open_palette):
            self.command_palette_action.triggered.connect(open_palette)
        self.addAction(self.command_palette_action)

        # F5 快捷键：切换到验证页面并触发验证
        self.validate_action = QtGui.QAction("验证项目存档", self)
        self.validate_action.triggered.connect(self._switch_to_validation_and_validate)
        self.addAction(self.validate_action)

        # F12 快捷键：开启/关闭 UI 开发者工具（悬停显示控件信息）
        self.dev_tools_action = QtGui.QAction("开发者工具（悬停显示控件）", self)
        self.dev_tools_action.setCheckable(True)
        self.dev_tools_action.toggled.connect(self._on_dev_tools_toggled)
        self.addAction(self.dev_tools_action)

        # F11 快捷键：显示/隐藏“全局性能悬浮面板”（卡顿定位）
        self.app_perf_overlay_action = QtGui.QAction("性能悬浮面板（卡顿定位）", self)
        self.app_perf_overlay_action.setCheckable(True)
        self.app_perf_overlay_action.toggled.connect(self._on_app_perf_overlay_toggled)
        desired = bool(getattr(settings, "APP_PERF_OVERLAY_ENABLED", False))
        self.app_perf_overlay_action.blockSignals(True)
        self.app_perf_overlay_action.setChecked(desired)
        self.app_perf_overlay_action.blockSignals(False)
        self.addAction(self.app_perf_overlay_action)

        # 统一应用 KeymapStore 中的快捷键配置
        self._apply_keymap_shortcuts()

    def _setup_toolbar(self) -> None:
        """设置工具栏"""
        toolbar = self.addToolBar("工具")

        # 后退 / 前进（全局导航历史）
        back_action = QtGui.QAction(
            self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_ArrowBack),
            "后退",
            self,
        )
        back_action.setToolTip("后退")
        back_action.setEnabled(False)
        back_action.triggered.connect(self._on_navigate_back)
        toolbar.addAction(back_action)
        self.navigation_back_action = back_action

        forward_action = QtGui.QAction(
            self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_ArrowForward),
            "前进",
            self,
        )
        forward_action.setToolTip("前进")
        forward_action.setEnabled(False)
        forward_action.triggered.connect(self._on_navigate_forward)
        toolbar.addAction(forward_action)
        self.navigation_forward_action = forward_action

        # 存档选择
        self.package_combo = QtWidgets.QComboBox()
        self.package_combo.setMinimumWidth(200)
        self.package_combo.currentIndexChanged.connect(self._on_package_combo_changed)
        toolbar.addWidget(QtWidgets.QLabel(" 项目存档: "))
        toolbar.addWidget(self.package_combo)

        toolbar.addSeparator()

        # 新建存档
        new_package_action = QtGui.QAction("新建项目存档", self)
        new_package_action.triggered.connect(lambda: self.package_controller.create_package(self))
        toolbar.addAction(new_package_action)

        # 保存
        save_action = QtGui.QAction("保存", self)
        # 统一保存语义：flush 去抖缓冲 + 按脏块增量保存（无改动则不写盘）。
        # 由主窗口统一入口负责更新“保存状态”标签与给出用户反馈。
        save_action.triggered.connect(self._on_save_requested_from_toolbar)
        toolbar.addAction(save_action)

        toolbar.addSeparator()

        # 设置 / 刷新 / 重启按钮组
        shortcuts_action = QtGui.QAction("⌨️ 快捷键", self)
        shortcuts_action.setToolTip("打开快捷键面板（查看当前程序快捷键）")
        open_shortcuts_panel = getattr(self, "_open_shortcut_help_panel", None)
        if callable(open_shortcuts_panel):
            shortcuts_action.triggered.connect(open_shortcuts_panel)
        toolbar.addAction(shortcuts_action)

        settings_action = QtGui.QAction("⚙️ 设置", self)
        settings_action.setToolTip("打开程序设置")
        settings_action.triggered.connect(self._open_settings_dialog)
        toolbar.addAction(settings_action)

        update_action = QtGui.QAction("刷新", self)
        update_action.setToolTip("刷新资源库（当外部工具修改节点图、管理配置等资源时手动触发）")
        update_action.triggered.connect(self._on_manual_refresh_resource_library)
        toolbar.addAction(update_action)

        check_updates_action = QtGui.QAction("检查更新", self)
        check_updates_action.setToolTip("检查当前版本是否为 GitHub 最新 Release")
        check_updates_action.triggered.connect(self._on_check_for_updates)
        toolbar.addAction(check_updates_action)

        check_environment_action = QtGui.QAction("检查环境", self)
        check_environment_action.setToolTip(
            "检查千星沙箱所在屏幕的分辨率/缩放、沙箱是否已打开，以及管理员权限与程序版本"
        )
        check_environment_action.triggered.connect(self._on_check_environment)
        toolbar.addAction(check_environment_action)

        import_action = QtGui.QAction("导入", self)
        import_action.setToolTip("读取 .gil 或导入 .gia 并写入项目存档")
        import_action.triggered.connect(self._on_import_requested_from_toolbar)
        toolbar.addAction(import_action)

        export_action = QtGui.QAction("导出", self)
        export_action.setToolTip("打开导出中心（.gil/.gia）")
        export_action.triggered.connect(self._on_export_requested_from_toolbar)
        toolbar.addAction(export_action)

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

        # Toolbar 创建完成后，统一应用 KeymapStore 中的快捷键配置（补齐后退/前进等）。
        self._apply_keymap_shortcuts()

    def _on_import_requested_from_toolbar(self) -> None:
        """工具栏“导入”：读取 `.gil` 或导入 `.gia` 并写入项目存档。

        约定：行为必须与“项目存档 → 导入/导出中心 → 导入”一致，避免出现两套导入链路。
        """
        from importlib.util import find_spec

        from app.ui.foundation import dialog_utils

        has_read_gil_full = find_spec("ugc_file_tools.ui_integration.read_gil") is not None
        has_read_gil_selected = find_spec("ugc_file_tools.ui_integration.read_gil_selected") is not None
        has_read_gia = find_spec("ugc_file_tools.ui_integration.read_gia") is not None

        if (not has_read_gil_full and not has_read_gil_selected) and (not has_read_gia):
            dialog_utils.show_warning_dialog(
                self,
                "未启用导入工具",
                "未检测到 ugc_file_tools 扩展，无法导入 `.gil/.gia`。\n"
                "请确保工作区存在 private_extensions/ugc_file_tools，并在启动日志中看到扩展已加载。",
            )
            return

        if has_read_gia and (not has_read_gil_full and not has_read_gil_selected):
            from ugc_file_tools.ui_integration.read_gia import on_read_clicked

            on_read_clicked(self)
            return

        if (has_read_gil_full or has_read_gil_selected) and (not has_read_gia):
            if has_read_gil_selected:
                from ugc_file_tools.ui_integration.read_gil_selected import on_read_clicked

                on_read_clicked(self)
                return
            from ugc_file_tools.ui_integration.read_gil import on_read_clicked

            on_read_clicked(self)
            return

        choices: list[tuple[str, str, str]] = []
        if has_read_gil_selected:
            choices.append(("gil_selected", "读取 .gil（选择）…", "action"))
        if has_read_gil_full:
            choices.append(("gil_full", "读取 .gil（整包）…", "action"))
        if has_read_gia:
            choices.append(("gia", "导入 .gia…", "action"))
        choices.append(("cancel", "取消", "reject"))

        choice = dialog_utils.ask_choice_dialog(
            self,
            "选择导入方式",
            "请选择要导入的内容：",
            icon="question",
            choices=choices,
            default_choice_key=("gil_selected" if has_read_gil_selected else ("gil_full" if has_read_gil_full else "gia")),
            escape_choice_key="cancel",
        )
        if choice == "gil_selected":
            from ugc_file_tools.ui_integration.read_gil_selected import on_read_clicked

            on_read_clicked(self)
            return
        if choice == "gil_full":
            from ugc_file_tools.ui_integration.read_gil import on_read_clicked

            on_read_clicked(self)
            return
        if choice == "gia":
            from ugc_file_tools.ui_integration.read_gia import on_read_clicked

            on_read_clicked(self)
            return

    def _on_export_requested_from_toolbar(self) -> None:
        """工具栏“导出”：打开导出中心（仅导出）。

        约定：行为必须与“项目存档 → 导入/导出中心 → 导出”一致，避免出现两套导出链路。
        """
        from importlib.util import find_spec

        from app.ui.foundation import dialog_utils

        if find_spec("ugc_file_tools.ui_integration.export_wizard") is None:
            dialog_utils.show_warning_dialog(
                self,
                "未启用导出工具",
                "未检测到 ugc_file_tools 扩展，无法打开导出中心。\n"
                "请确保工作区存在 private_extensions/ugc_file_tools，并在启动日志中看到扩展已加载。",
            )
            return

        from ugc_file_tools.ui_integration.export_wizard import on_open_export_center_clicked

        on_open_export_center_clicked(self)

    def _restart_application_from_toolbar(self) -> None:
        """从主窗口工具栏重启整个应用，行为与设置对话框中的重启一致。"""
        application = QtWidgets.QApplication.instance()
        if application is None:
            return
        QtCore.QProcess.startDetached(sys.executable, ["-m", "app.cli.run_app"])
        application.quit()

