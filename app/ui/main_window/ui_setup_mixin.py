"""UI设置 Mixin - 负责UI组件的创建和布局"""
from __future__ import annotations

import sys

from dataclasses import dataclass
from typing import Callable, Iterable

from PyQt6 import QtCore, QtGui, QtWidgets

from app.models.view_modes import ViewMode
from app.ui.foundation.theme_manager import ThemeManager, Colors
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
from app.ui.todo.todo_list_widget import TodoListWidget
from app.ui.panels.validation_panel import ValidationPanel
from app.ui.panels.validation_detail_panel import ValidationDetailPanel
from app.ui.composite.composite_node_property_panel import CompositeNodePropertyPanel
from app.ui.composite.composite_node_pin_panel import CompositeNodePinPanel
from app.ui.graph.library_pages.graph_library_widget import GraphLibraryWidget
from app.ui.panels.graph_property_panel import GraphPropertyPanel
from app.ui.panels.ui_control_settings_panel import UIControlSettingsPanel
from app.ui.graph.library_pages.package_library_widget import PackageLibraryWidget
from app.ui.panels.combat_player_panel import CombatPlayerEditorPanel
from app.ui.panels.combat_class_panel import CombatPlayerClassPanel
from app.ui.panels.combat_skill_panel import CombatSkillPanel
from app.ui.panels.combat_item_panel import CombatItemPanel
from app.ui.management.section_registry import MANAGEMENT_SECTIONS, ManagementSectionSpec
from app.ui.main_window.right_panel_registry import RightPanelRegistry


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
        graph_library_widget = GraphLibraryWidget(self.resource_manager, self.package_index_manager)
        return graph_library_widget

    def _create_validation_page(self) -> ValidationPanel:
        """验证面板页面（ViewMode.VALIDATION）。"""
        validation_panel = ValidationPanel()
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
        self.graph_editor_todo_button.setToolTip("前往任务清单并定位/生成当前图对应的执行步骤")
        self.graph_editor_todo_button.setVisible(False)
        self.graph_editor_todo_button.clicked.connect(self._on_graph_editor_execute_from_todo)
        self.view.set_extra_top_right_button(self.graph_editor_todo_button)
        return self.view

    def _create_package_library_page(self) -> PackageLibraryWidget:
        """存档页面（ViewMode.PACKAGES）。"""
        package_library_widget = PackageLibraryWidget(self.resource_manager, self.package_index_manager)
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

        # 右侧标签注册表：集中管理 tab_id -> widget/标题/模式约束
        self.right_panel_registry = RightPanelRegistry(
            side_tab=self.side_tab,
            right_panel_container=self.right_panel_container,
        )

        # 安装主窗口 Feature（渐进迁移的单点扩展口）
        self._install_main_window_features()

        self.right_panel_container.setMinimumWidth(350)
        self.right_panel_container.setMaximumWidth(800)

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
        self.property_panel = TemplateInstancePanel(self.resource_manager, self.package_index_manager)
        self.property_panel.setMinimumWidth(300)

        # 玩家模板详情面板（战斗预设专用，具体挂载到 side_tab 由模式切换逻辑控制）
        self.player_editor_panel = CombatPlayerEditorPanel(
            self.resource_manager,
            self.package_index_manager,
            self.right_panel_container,
        )

        # 职业详情面板（战斗预设-职业）
        self.player_class_panel = CombatPlayerClassPanel(
            self.resource_manager,
            self.package_index_manager,
            self.right_panel_container,
        )

        # 技能详情面板（战斗预设-技能）
        self.skill_panel = CombatSkillPanel(
            self.resource_manager,
            self.package_index_manager,
            self.right_panel_container,
        )
        self.skill_panel.setMinimumWidth(360)

        # 道具详情面板（战斗预设-道具）
        self.item_panel = CombatItemPanel(
            self.resource_manager,
            self.package_index_manager,
            self.right_panel_container,
        )
        self.item_panel.setMinimumWidth(360)

        self.graph_property_panel = GraphPropertyPanel(self.resource_manager, self.package_index_manager)
        self.graph_property_panel.setMinimumWidth(300)

        self.composite_property_panel = CompositeNodePropertyPanel(self.package_index_manager)
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

        # 设置 / 更新 / 重启按钮组
        settings_action = QtGui.QAction("⚙️ 设置", self)
        settings_action.setToolTip("打开程序设置")
        settings_action.triggered.connect(self._open_settings_dialog)
        toolbar.addAction(settings_action)

        update_action = QtGui.QAction("更新", self)
        update_action.setToolTip("刷新资源库（当外部工具修改节点图、管理配置等资源时手动触发）")
        if hasattr(self, "_on_manual_refresh_resource_library"):
            update_action.triggered.connect(self._on_manual_refresh_resource_library)
        else:
            # 回退：直接调用主窗口统一的资源库刷新入口（若存在）
            update_action.triggered.connect(getattr(self, "refresh_resource_library", lambda: None))
        toolbar.addAction(update_action)

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

