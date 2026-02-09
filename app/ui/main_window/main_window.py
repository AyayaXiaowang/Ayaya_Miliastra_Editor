"""主窗口 - 使用 Mixin 架构。

约定：
- 主窗口尽量保持为“壳/装配层”，不在此文件中堆叠业务与缓存编排；
- 启动期装配结果集中在 `MainWindowAppState`；
- “资源库刷新”由 `ResourceRefreshService` 负责失效与重建，UI 只订阅结果并刷新页面。
"""
from __future__ import annotations

import time
from pathlib import Path

from PyQt6 import QtCore, QtWidgets

from engine.utils.logging.logger import log_debug, log_info, log_warn
from app.ui.devtools.view_inspector import WidgetHoverInspector
from app.models.view_modes import ViewMode

# 导入所有Mixin
from .controller_setup_mixin import ControllerSetupMixin
from .ui_setup_mixin import UISetupMixin
from .mode_switch_mixin import ModeSwitchMixin
from .event_handler_mixin import EventHandlerMixin
from .app_state import MainWindowAppState, build_main_window_app_state
from .resource_refresh_service import ResourceRefreshService
from .resource_refresh_coordinator import ResourceRefreshCoordinator, ResourceIndexSnapshot
from .view_state import MainWindowViewState
from .mode_presenters import ModeEnterRequest, ModePresenterCoordinator
from .mode_transition_service import ModeTransitionService
from .navigation_history import NavigationHistory


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
        boot_started = float(time.monotonic())
        log_debug("[BOOT] 启动中：workspace={}", workspace)
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1800, 1000)
        log_debug("[BOOT][MainWindow] QMainWindow 基类初始化完成，窗口大小={}x{}", self.width(), self.height())

        # 启动期装配结果（单一真源）：workspace / settings / 节点库 / 资源索引 / 图编辑器基础对象
        self.app_state: MainWindowAppState = build_main_window_app_state(workspace)

        # 资源刷新服务（只负责失效与重建）
        self.resource_refresh_service = ResourceRefreshService()
        self._resource_refresh_coordinator = ResourceRefreshCoordinator(
            workspace_path=self.app_state.workspace_path,
            resource_library_dir=self.app_state.resource_manager.resource_library_dir,
            parent=self,
        )
        self._resource_refresh_coordinator.refresh_started.connect(self._on_resource_refresh_started)
        self._resource_refresh_coordinator.snapshot_ready.connect(self._on_resource_refresh_snapshot_ready)

        # UI/View 单一真源（逐步替代散落的隐式状态）
        self.view_state = MainWindowViewState()

        # 全局导航历史（后退/前进）
        self.navigation_history = NavigationHistory(max_entries=200)
        self._navigation_history_ready = False
        self._navigation_history_is_replaying = False

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
        log_debug("[BOOT][MainWindow] 基础属性与开发者工具初始化完成")

        # 初始化控制器（必须在UI之前，因为UI中会引用控制器）
        log_debug("[BOOT][MainWindow] 准备初始化控制器 _setup_controllers()")
        self._setup_controllers()
        log_debug("[BOOT][MainWindow] 控制器初始化完成")

        # 设置UI
        log_debug("[BOOT][MainWindow] 准备装配 UI 结构 _setup_ui()")
        self._setup_ui()
        log_debug("[BOOT][MainWindow] UI 结构装配完成")

        log_debug("[BOOT][MainWindow] 准备创建菜单栏 _setup_menubar()")
        self._setup_menubar()
        log_debug("[BOOT][MainWindow] 菜单栏创建完成")

        log_debug("[BOOT][MainWindow] 准备创建工具栏 _setup_toolbar()")
        self._setup_toolbar()
        log_debug("[BOOT][MainWindow] 工具栏创建完成")

        # 应用全局主题样式
        log_debug("[BOOT][MainWindow] 准备用于主窗口的全局主题样式 _apply_global_theme()")
        self._apply_global_theme()
        log_debug("[BOOT][MainWindow] 主窗口全局主题样式应用完成")

        # 连接控制器信号
        log_debug("[BOOT][MainWindow] 准备连接控制器信号 _connect_controller_signals()")
        self._connect_controller_signals()
        log_debug("[BOOT][MainWindow] 控制器信号连接完成")

        # 加载最近的存档或创建默认存档
        log_debug("[BOOT][MainWindow] 准备加载最近的存档或创建默认存档 load_initial_package()")
        self.package_controller.load_initial_package()
        log_debug("[BOOT][MainWindow] 初始存档加载流程完成")

        # 在初始存档与视图装配完成后，尝试恢复上一次会话的 UI 状态
        log_debug("[BOOT][MainWindow] 准备尝试恢复 UI 会话状态（已排队，延后执行）")
        # 延后到事件循环启动后执行，避免在主窗口构造期同步打开上次会话中的大图导致 UI 延迟显示。
        QtCore.QTimer.singleShot(0, self._restore_ui_session_state)
        # 导航历史在“会话恢复”之后再初始化，避免把启动恢复过程当作用户操作入栈。
        QtCore.QTimer.singleShot(0, self._bootstrap_navigation_history_after_startup)

        log_warn("[BOOT] 主窗口创建完成：elapsed={:.2f}s", float(time.monotonic()) - boot_started)

    # === 显式接口：供服务层调用（避免依赖 mixin 私有方法名） ===

    def refresh_save_status_label_for_mode(self, view_mode: ViewMode) -> None:
        """稳定钩子：刷新右上角保存状态提示（由 WindowAndNavigationEventsMixin 实现）。"""
        self._refresh_save_status_label_for_mode(view_mode)

    def schedule_ui_session_state_save(self) -> None:
        """稳定钩子：请求一次轻量去抖的 UI 会话状态保存（由 WindowAndNavigationEventsMixin 实现）。"""
        self._schedule_ui_session_state_save()

    def on_mode_transition_completed(self, view_mode: ViewMode) -> None:
        """稳定钩子：模式切换完成后的通知（用于导航历史等收敛逻辑）。"""
        self._on_mode_transition_completed(view_mode)

    def save_current_composite_if_needed(self) -> None:
        """稳定钩子：离开复合节点模式前保存当前复合节点（由主窗口统一封装复合管理器协议）。"""
        composite_manager = getattr(self, "composite_widget", None)
        current_composite_identifier = getattr(composite_manager, "current_composite_id", None)
        if not current_composite_identifier:
            return
        log_debug("[MODE] saving composite before leaving: {}", current_composite_identifier)
        save_method = getattr(composite_manager, "_save_current_composite", None)
        if not callable(save_method):
            raise RuntimeError("composite_widget 缺少 _save_current_composite，无法保存当前复合节点")
        save_method()

    def _on_dev_tools_toggled(self, enabled: bool) -> None:
        """F12 开关：启用或关闭 UI 悬停检查器。"""
        self._dev_tools_enabled = enabled
        self._widget_hover_inspector.set_enabled(enabled)
    
    def refresh_resource_library(self) -> None:
        """刷新资源库（后台化）。

        UI 线程只发起请求：索引重建/指纹更新在后台执行；完成后主线程提交替换并刷新页面。
        """
        current_package_id_value = getattr(self.package_controller, "current_package_id", None)
        active_package_id: str | None = None
        current_package_id_text = str(current_package_id_value or "").strip()
        if current_package_id_text and current_package_id_text != "global_view":
            active_package_id = current_package_id_text
        self._resource_refresh_coordinator.request_refresh(active_package_id=active_package_id)

    def _on_resource_refresh_started(self) -> None:
        # 用户可见：让用户明确知道“正在同步”，避免误判为卡死。
        self._show_toast("正在同步资源库…", "info")
        file_watcher_manager = getattr(self, "file_watcher_manager", None)
        notify = getattr(file_watcher_manager, "notify_resource_refresh_started", None)
        if callable(notify):
            notify()

    def _on_resource_refresh_snapshot_ready(self, snapshot_obj: object) -> None:
        if not isinstance(snapshot_obj, ResourceIndexSnapshot):
            raise TypeError("resource refresh snapshot 类型不正确")
        snapshot: ResourceIndexSnapshot = snapshot_obj

        # 若后台快照的作用域已过期（用户切包），丢弃并按当前作用域补一次刷新。
        current_package_id_value = getattr(self.package_controller, "current_package_id", None)
        current_text = str(current_package_id_value or "").strip()
        current_active: str | None = None
        if current_text and current_text != "global_view":
            current_active = current_text
        if snapshot.active_package_id != current_active:
            log_debug(
                "[REFRESH] discard stale snapshot: snapshot_scope='{}' current_scope='{}'",
                str(snapshot.active_package_id or ""),
                str(current_active or ""),
            )
            file_watcher_manager = getattr(self, "file_watcher_manager", None)
            notify_done = getattr(file_watcher_manager, "notify_resource_refresh_completed", None)
            if callable(notify_done):
                notify_done()
            self._resource_refresh_coordinator.request_refresh(active_package_id=current_active)
            return

        refresh_started_monotonic = float(time.monotonic())
        log_warn(
            "[REFRESH] refresh_resource_library apply snapshot: current_package_id={}, view_mode={}",
            str(current_text or ""),
            str(getattr(self.view_state, "current_mode", None)),
        )

        service_started_monotonic = float(time.monotonic())
        file_watcher_manager = getattr(self, "file_watcher_manager", None)
        notify_done = getattr(file_watcher_manager, "notify_resource_refresh_completed", None)
        try:
            refresh_outcome = self.resource_refresh_service.refresh(
                app_state=self.app_state,
                package_controller=self.package_controller,
                graph_controller=self.graph_controller,
                global_resource_view=getattr(self, "_global_resource_view", None),
                prebuilt_index_data=snapshot.index_data,
                prebuilt_resource_library_fingerprint=snapshot.resource_library_fingerprint,
            )
            log_warn(
                "[REFRESH] ResourceRefreshService.refresh 完成：elapsed={:.2f}s, outcome={}",
                float(time.monotonic()) - service_started_monotonic,
                str(refresh_outcome),
            )

            # 1) 复用现有包加载完成逻辑：保持模板库/实体摆放/战斗预设/管理库/节点图库一致刷新。
            did_refresh_package_context = False
            if refresh_outcome.current_package_id:
                package_loaded_started_monotonic = float(time.monotonic())
                self._on_package_loaded(refresh_outcome.current_package_id)
                log_warn(
                    "[REFRESH] _on_package_loaded 完成：elapsed={:.2f}s, package_id={}",
                    float(time.monotonic()) - package_loaded_started_monotonic,
                    str(refresh_outcome.current_package_id),
                )
                did_refresh_package_context = True

            # 2) 节点图库与存档库依赖 ResourceManager / PackageIndexManager 的聚合结果
            if (not did_refresh_package_context) and hasattr(self, "graph_library_widget"):
                graph_library_reload_started = float(time.monotonic())
                self.graph_library_widget.reload()
                log_warn(
                    "[REFRESH] graph_library_widget.reload 完成：elapsed={:.2f}s",
                    float(time.monotonic()) - graph_library_reload_started,
                )
            if hasattr(self, "package_library_widget"):
                package_library_reload_started = float(time.monotonic())
                self.package_library_widget.reload()
                log_warn(
                    "[REFRESH] package_library_widget.reload 完成：elapsed={:.2f}s",
                    float(time.monotonic()) - package_library_reload_started,
                )

            # 3) 复合节点库变化：刷新 NodeRegistry（含复合节点）与复合节点管理器的内存索引。
            if getattr(refresh_outcome, "did_composite_library_change", False):
                composite_refresh_started = float(time.monotonic())
                self._refresh_node_library_and_sync_composites(reload_composite_widget_from_disk=True)
                log_warn(
                    "[REFRESH] _refresh_node_library_and_sync_composites 完成：elapsed={:.2f}s",
                    float(time.monotonic()) - composite_refresh_started,
                )

            log_warn(
                "[REFRESH] refresh_resource_library 完成：elapsed_total={:.2f}s",
                float(time.monotonic()) - refresh_started_monotonic,
            )
            self._show_toast("资源库已更新", "success")
        finally:
            if callable(notify_done):
                notify_done()

