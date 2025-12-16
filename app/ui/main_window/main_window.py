"""主窗口 - 使用 Mixin 架构。

约定：
- 主窗口尽量保持为“壳/装配层”，不在此文件中堆叠业务与缓存编排；
- 启动期装配结果集中在 `MainWindowAppState`；
- “资源库刷新”由 `ResourceRefreshService` 负责失效与重建，UI 只订阅结果并刷新页面。
"""
from __future__ import annotations

from pathlib import Path

from PyQt6 import QtCore, QtWidgets

from engine.utils.logging.logger import log_info
from app.ui.devtools.view_inspector import WidgetHoverInspector

# 导入所有Mixin
from .controller_setup_mixin import ControllerSetupMixin
from .ui_setup_mixin import UISetupMixin
from .mode_switch_mixin import ModeSwitchMixin
from .event_handler_mixin import EventHandlerMixin
from .app_state import MainWindowAppState, build_main_window_app_state
from .resource_refresh_service import ResourceRefreshService
from .view_state import MainWindowViewState
from .mode_presenters import ModeEnterRequest, ModePresenterCoordinator
from .mode_transition_service import ModeTransitionService


APP_TITLE = "小王千星工坊"


class MainWindowV2(
    ControllerSetupMixin,
    UISetupMixin,
    ModeSwitchMixin,
    EventHandlerMixin,
    QtWidgets.QMainWindow,
):
    """主窗口 V2 - 支持模式切换（Mixin架构）
    
    职责拆分：
    - ControllerSetupMixin: 控制器初始化和信号连接
    - UISetupMixin: UI组件创建和布局
    - ModeSwitchMixin: 视图模式切换和右侧面板管理
    - EventHandlerMixin: UI事件和信号响应
    - MainWindowV2: 核心初始化和属性定义
    """

    def __init__(self, workspace: Path):
        log_info("[BOOT][MainWindow] __init__ 开始，workspace={}", workspace)
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1800, 1000)
        log_info("[BOOT][MainWindow] QMainWindow 基类初始化完成，窗口大小={}x{}", self.width(), self.height())

        # 启动期装配结果（单一真源）：workspace / settings / 节点库 / 资源索引 / 图编辑器基础对象
        self.app_state: MainWindowAppState = build_main_window_app_state(workspace)
        # 向后兼容：Mixin 体系仍通过 self.* 访问这些属性
        self.workspace_path = self.app_state.workspace_path
        self.library = self.app_state.node_library
        self.resource_manager = self.app_state.resource_manager
        self.package_index_manager = self.app_state.package_index_manager
        self.model = self.app_state.graph_model
        self.scene = self.app_state.graph_scene
        self.view = self.app_state.graph_view

        # 资源刷新服务（只负责失效与重建）
        self.resource_refresh_service = ResourceRefreshService()

        # UI/View 单一真源（逐步替代散落的隐式状态）
        self.view_state = MainWindowViewState()

        # 模式 presenter 协调器（进入模式副作用）
        self.mode_presenter_coordinator = ModePresenterCoordinator(self)
        # 模式切换公共流程（服务化，降低 mixin 冲突面）
        self.mode_transition_service = ModeTransitionService()
        # 任务清单 → 节点图编辑器联动上下文
        self._graph_editor_todo_context = None
        self.graph_editor_todo_button = None
        # UI 开发者工具：悬停检查器（通过 F12 快捷键开关）
        self._widget_hover_inspector = WidgetHoverInspector(self)
        self._dev_tools_enabled = False
        log_info("[BOOT][MainWindow] 基础属性与开发者工具初始化完成")

        # 初始化控制器（必须在UI之前，因为UI中会引用控制器）
        log_info("[BOOT][MainWindow] 准备初始化控制器 _setup_controllers()")
        self._setup_controllers()
        log_info("[BOOT][MainWindow] 控制器初始化完成")

        # 设置UI
        log_info("[BOOT][MainWindow] 准备装配 UI 结构 _setup_ui()")
        self._setup_ui()
        log_info("[BOOT][MainWindow] UI 结构装配完成")

        log_info("[BOOT][MainWindow] 准备创建菜单栏 _setup_menubar()")
        self._setup_menubar()
        log_info("[BOOT][MainWindow] 菜单栏创建完成")

        log_info("[BOOT][MainWindow] 准备创建工具栏 _setup_toolbar()")
        self._setup_toolbar()
        log_info("[BOOT][MainWindow] 工具栏创建完成")

        # 应用全局主题样式
        log_info("[BOOT][MainWindow] 准备用于主窗口的全局主题样式 _apply_global_theme()")
        self._apply_global_theme()
        log_info("[BOOT][MainWindow] 主窗口全局主题样式应用完成")

        # 连接控制器信号
        log_info("[BOOT][MainWindow] 准备连接控制器信号 _connect_controller_signals()")
        self._connect_controller_signals()
        log_info("[BOOT][MainWindow] 控制器信号连接完成")

        # 加载最近的存档或创建默认存档
        log_info("[BOOT][MainWindow] 准备加载最近的存档或创建默认存档 load_initial_package()")
        self.package_controller.load_initial_package()
        log_info("[BOOT][MainWindow] 初始存档加载流程完成")

        # 在初始存档与视图装配完成后，尝试恢复上一次会话的 UI 状态
        if hasattr(self, "_restore_ui_session_state"):
            log_info("[BOOT][MainWindow] 检测到 UI 会话状态恢复入口，准备尝试恢复")
            # 延后到事件循环启动后执行，避免在主窗口构造期同步打开上次会话中的大图导致 UI 延迟显示。
            QtCore.QTimer.singleShot(0, self._restore_ui_session_state)
            log_info("[BOOT][MainWindow] UI 会话状态恢复已排队（将延后执行）")

        log_info("[BOOT][MainWindow] __init__ 完成")

    def _on_dev_tools_toggled(self, enabled: bool) -> None:
        """F12 开关：启用或关闭 UI 悬停检查器。"""
        self._dev_tools_enabled = enabled
        self._widget_hover_inspector.set_enabled(enabled)
    
    def refresh_resource_library(self) -> None:
        """刷新资源库：服务负责失效与重建，主窗口仅根据结果刷新 UI 上下文。"""
        refresh_outcome = self.resource_refresh_service.refresh(
            app_state=self.app_state,
            package_controller=self.package_controller,
            global_resource_view=getattr(self, "_global_resource_view", None),
        )

        # 1) 复用现有包加载完成逻辑：保持模板库/实体摆放/战斗预设/管理库/节点图库一致刷新。
        did_refresh_package_context = False
        if refresh_outcome.current_package_id:
            self._on_package_loaded(refresh_outcome.current_package_id)
            did_refresh_package_context = True

        # 2) 节点图库与存档库依赖 ResourceManager / PackageIndexManager 的聚合结果
        #    在资源索引变化后也需要刷新以反映最新落盘状态。
        #    注意：当 did_refresh_package_context=True 时，_on_package_loaded 已调用
        #    graph_library_widget.set_package(...) 并触发其内部刷新，无需再次重复 refresh。
        if (not did_refresh_package_context) and hasattr(self, "graph_library_widget"):
            self.graph_library_widget.refresh()
        if hasattr(self, "package_library_widget"):
            self.package_library_widget.refresh()

