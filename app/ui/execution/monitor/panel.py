# -*- coding: utf-8 -*-
"""
执行监控面板（右侧Tab）
与 ExecutionMonitorWindow API 保持一致：start_monitoring/stop_monitoring/log/update_status 等
本文件为重构后的主体面板，仅负责组装与委托
"""

from PyQt6 import QtCore, QtWidgets, QtGui
from PyQt6.QtCore import Qt, pyqtSignal
from PIL import Image

from app.automation.input.common import set_visual_sink as _set_visual_sink
from app.automation.input.common import clear_visual_sink as _clear_visual_sink
from app.automation.input.common import set_log_sink as _set_log_sink
from app.automation.input.common import clear_log_sink as _clear_log_sink

from .actions_recognition import RecognitionActions
from .focus_controller import FocusController
from .log_view import LogViewController
from .visual_renderer import VisualRenderer
from .screenshot_worker import ScreenshotCaptureManager
from .execution_control import ExecutionControl
from .execution_events import ExecutionEventModel
from . import panel_ui


class ExecutionMonitorPanel(QtWidgets.QWidget):
    """右侧标签中的执行监控面板"""

    # 信号：停止执行
    stop_requested = pyqtSignal()
    # 信号：点击了步骤标签（跳转左侧步骤）
    step_anchor_clicked = pyqtSignal(str)  # todo_id
    # 信号：定位镜头识别成功后，告知当前图中可见的节点ID列表（GraphModel.node_id）
    recognition_focus_succeeded = pyqtSignal(list)
    # 线程安全UI更新信号
    append_log_signal = pyqtSignal(str)
    set_status_signal = pyqtSignal(str)
    set_progress_signal = pyqtSignal(int, int)
    visual_update_signal = pyqtSignal(object, object)  # (PIL.Image, overlays dict or None)

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)

        # 截图刷新定时器（保留，但不再主动抓取）
        self.screenshot_timer = QtCore.QTimer()
        self.screenshot_timer.timeout.connect(self._update_screenshot)
        self.screenshot_interval = 500  # ms

        # 外部上下文（由调用方注入）
        self.current_graph_model = None  # 当前 GraphModel（可由执行入口或主窗口注入）
        self.current_workspace_path = None  # 工作区路径 Path
        self.graph_view = None  # 主编辑视图 GraphView
        # 可选：获取当前 GraphModel 的回调（作为回退）
        self.get_current_graph_model = None
        # 与执行线程共享的 EditorExecutor 实例（可复用视口状态与识别缓存）
        self._shared_executor = None

        # 运行统计
        self._current_run_total_steps: int = 0
        self._current_run_completed: int = 0
        self._current_run_failed: int = 0

        # 构建 UI（通过 panel_ui.build_monitor_ui）
        self._ui_refs = panel_ui.build_monitor_ui(self)
        self._extract_ui_refs()

        # 初始化委托：识别动作、定位控制器、日志控制器、渲染器、截图管理器、执行控制器
        self._init_delegates()

        # 线程安全信号
        self.append_log_signal.connect(self._append_log_via_controller)
        self.set_status_signal.connect(self._set_status)
        self.set_progress_signal.connect(self._set_progress)
        self.visual_update_signal.connect(self._render_visual_threadsafe)

        # 连接 UI 控件信号
        self._connect_ui_signals()

        # Ctrl+P 快捷键：随时暂停
        self._ctrlp_shortcut = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+P"), self)
        self._ctrlp_shortcut.activated.connect(self.request_pause)

    def _extract_ui_refs(self) -> None:
        """从 UI 引用字典中提取控件为实例变量（便于访问）"""
        self.status_label = self._ui_refs["status_label"]
        self.progress_label = self._ui_refs["progress_label"]
        self.step_context_label = self._ui_refs["step_context_label"]
        self.screenshot_label = self._ui_refs["screenshot_label"]
        self.pause_button = self._ui_refs["pause_button"]
        self.resume_button = self._ui_refs["resume_button"]
        self.next_step_button = self._ui_refs["next_step_button"]
        self.step_mode_checkbox = self._ui_refs["step_mode_checkbox"]
        self.stop_button = self._ui_refs["stop_button"]
        self.inspect_button = self._ui_refs["inspect_button"]
        self.match_focus_button = self._ui_refs["match_focus_button"]
        self.drag_origin_label = self._ui_refs["drag_origin_label"]
        self.drag_target_x_input = self._ui_refs["drag_target_x_input"]
        self.drag_target_y_input = self._ui_refs["drag_target_y_input"]
        self.drag_to_target_button = self._ui_refs["drag_to_target_button"]
        self.drag_left_button = self._ui_refs["drag_left_button"]
        self.drag_right_button = self._ui_refs["drag_right_button"]
        # 结构化执行事件表格与过滤控件
        self.events_table = self._ui_refs.get("events_table")
        self.event_errors_only_checkbox = self._ui_refs.get("event_errors_only_checkbox")
        self.log_text = self._ui_refs["log_text"]

    def _init_delegates(self) -> None:
        """初始化委托：识别动作、定位控制器、日志控制器、渲染器、截图管理器、执行控制器"""
        # 日志控制器（原始文本流）
        self._log_controller = LogViewController(
            log_text_browser=self._ui_refs["log_text"],
            search_input=self._ui_refs["log_search_input"],
            filter_combo=self._ui_refs["log_filter_combo"],
        )

        # 结构化执行事件模型（表格视图）
        self._event_model = ExecutionEventModel(self)
        if isinstance(self.events_table, QtWidgets.QTableView):
            table: QtWidgets.QTableView = self.events_table
            table.setModel(self._event_model)
            header = table.horizontalHeader()
            header.setStretchLastSection(True)
            header.setDefaultSectionSize(120)
            table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
            table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
            table.doubleClicked.connect(self._on_event_row_activated)
        
        # 渲染器
        self._renderer = VisualRenderer(
            screenshot_label=self.screenshot_label,
            parent_widget=self,
            get_current_display_title_callback=self._current_display_title,
            get_current_micro_action_callback=self._current_micro_action_title,
        )
        
        # 截图管理器
        self._screenshot_manager = ScreenshotCaptureManager(
            parent=self,
            screenshot_interval_ms=self.screenshot_interval,
        )
        
        # 执行控制器
        self._control = ExecutionControl(
            pause_button=self.pause_button,
            resume_button=self.resume_button,
            next_step_button=self.next_step_button,
            step_mode_checkbox=self.step_mode_checkbox,
            stop_button=self.stop_button,
            parent=self,
        )
        # 连接控制器信号
        self._control.stop_requested.connect(self._on_control_stop_requested)
        self._control.status_changed.connect(self._set_status)
        self._control.log_message.connect(self.log)
        
        # 识别动作
        self._actions = RecognitionActions(
            log_callback=self.log,
            update_visual_callback=self.update_visual,
            get_graph_model_callback=self._get_graph_model,
            get_workspace_path_callback=lambda: self.current_workspace_path,
            get_window_title_callback=lambda: self._screenshot_manager.get_window_title(),
        )
        
        # 定位控制器
        self._focus = FocusController(
            log_callback=self.log,
            update_visual_callback=self.update_visual,
            get_graph_model_callback=self._get_graph_model,
            get_workspace_path_callback=lambda: self.current_workspace_path,
            get_graph_view_callback=lambda: self.graph_view,
            on_focus_succeeded_callback=self._on_focus_succeeded,
            get_shared_executor_callback=self.get_shared_executor,
            set_shared_executor_callback=self.set_shared_executor,
        )

    def _connect_ui_signals(self) -> None:
        """连接 UI 控件信号到对应的槽函数"""
        # 检查与定位
        self.inspect_button.clicked.connect(lambda: self._actions.check_current_page())
        self.match_focus_button.clicked.connect(lambda: self._focus.match_and_focus())

        # 拖拽测试
        self.drag_to_target_button.clicked.connect(self._on_drag_to_target_clicked)
        self.drag_left_button.clicked.connect(lambda: self._on_directional_drag_clicked(is_left=True))
        self.drag_right_button.clicked.connect(lambda: self._on_directional_drag_clicked(is_left=False))

        # 测试按钮
        self._ui_refs["test_ocr_button"].clicked.connect(lambda: self._actions.test_ocr())
        self._ui_refs["test_settings_button"].clicked.connect(lambda: self._actions.test_settings())
        self._ui_refs["test_warning_button"].clicked.connect(lambda: self._actions.test_warning())
        self._ui_refs["test_ocr_zoom_button"].clicked.connect(lambda: self._actions.test_ocr_zoom())
        self._ui_refs["test_nodes_button"].clicked.connect(lambda: self._actions.test_nodes())
        self._ui_refs["test_ports_button"].clicked.connect(lambda: self._actions.test_ports())
        self._ui_refs["test_settings_tpl_button"].clicked.connect(lambda: self._actions.test_settings_tpl())
        self._ui_refs["test_add_button"].clicked.connect(lambda: self._actions.test_add_templates())
        self._ui_refs["test_search_button"].clicked.connect(lambda: self._actions.test_searchbar_templates())

        # 日志控制
        self._ui_refs["log_clear_button"].clicked.connect(self.clear_log)
        self.log_text.anchorClicked.connect(self._on_anchor_clicked)

        # 执行事件过滤
        if self.event_errors_only_checkbox is not None:
            self.event_errors_only_checkbox.toggled.connect(self._on_event_errors_only_toggled)

    def _get_graph_model(self):
        """统一的图模型获取：优先当前注入，再回退回调"""
        graph_model = self.current_graph_model
        if graph_model is None and self.get_current_graph_model and callable(self.get_current_graph_model):
            graph_model = self.get_current_graph_model()
        return graph_model

    def _on_focus_succeeded(self, visible_ids: list[str]) -> None:
        """定位镜头成功后发射信号并更新拖拽测试视口坐标显示"""
        self._update_drag_origin_from_focus()
        self.recognition_focus_succeeded.emit(visible_ids)

    def _on_control_stop_requested(self) -> None:
        """控制器发出停止请求"""
        self.screenshot_timer.stop()
        self.stop_requested.emit()

    # === 属性访问（委托到控制器）===
    @property
    def is_running(self) -> bool:
        return self._control.is_running

    @is_running.setter
    def is_running(self, value: bool) -> None:
        self._control.is_running = value

    @property
    def is_paused(self) -> bool:
        return self._control.is_paused

    @is_paused.setter
    def is_paused(self, value: bool) -> None:
        self._control.is_paused = value

    @property
    def step_mode_enabled(self) -> bool:
        return self._control.step_mode_enabled

    @step_mode_enabled.setter
    def step_mode_enabled(self, value: bool) -> None:
        self._control.step_mode_enabled = value

    def request_pause(self) -> None:
        """请求暂停（供快捷键调用）"""
        self._control.request_pause()

    # === 外部调用 API ===
    def start_monitoring(self) -> None:
        """开始监控"""
        self._control.start_execution()
        self.status_label.setText("执行中（展示上一步视觉产物）")
        self.log("开始监控：仅显示每一步产生的截图与叠加，不进行实时桌面轮询")
        # 不启动任何定时器或后台抓取，画面仅由 update_visual() 主动更新
        if self.screenshot_timer.isActive():
            self.screenshot_timer.stop()
        # 开启新会话：清空本次运行的截图记录
        self._renderer.clear_history()
        # 注册全局可视化/日志汇聚到本面板
        _set_visual_sink(self.update_visual)
        _set_log_sink(self.log)

    def stop_monitoring(self) -> None:
        """停止监控"""
        self._control.stop_execution()
        self.status_label.setText("已停止")
        self.screenshot_timer.stop()
        self.stop_screenshot_capture()
        # 清理全局汇聚器
        _clear_visual_sink()
        _clear_log_sink()

    def start_screenshot_capture(self, window_title: str) -> None:
        """启动后台截图线程，将截图通过信号回传到UI线程更新"""
        self._screenshot_manager.start_capture(window_title, self.update_screenshot)

    def stop_screenshot_capture(self) -> None:
        """停止后台截图线程"""
        self._screenshot_manager.stop_capture()

    def update_screenshot(self, screenshot: Image.Image) -> None:
        """收到后台截图，渲染到面板"""
        # 只要有截图就展示：不再受 is_running 限制
        self._renderer.render_visual_snapshot(screenshot, None)

    def update_visual(self, base_image: Image.Image, overlays: object | None = None) -> None:
        """线程安全：更新监控画面为一次真实的视觉产物（截图+可选叠加）。
        overlays 格式：
        {
          'rects': [ { 'bbox': (x,y,w,h), 'color': (r,g,b), 'label': str }, ... ],
          'circles': [ { 'center': (x,y), 'radius': int, 'color': (r,g,b), 'label': str }, ... ]
        }
        """
        if QtCore.QThread.currentThread() is self.thread():
            self._renderer.render_visual(base_image, overlays)
        else:
            self.visual_update_signal.emit(base_image, overlays)

    def _render_visual_threadsafe(self, base_image: Image.Image, overlays: object | None) -> None:
        """线程安全渲染（由信号触发）"""
        self._renderer.render_visual(base_image, overlays)

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        """事件过滤器（委托给渲染器）"""
        if self._renderer.eventFilter(obj, event):
            return True
        return super().eventFilter(obj, event)

    def _current_micro_action_title(self) -> str:
        """获取微动作标题（委托给日志控制器的最近一条日志）"""
        log_records = getattr(self._log_controller, "_log_records", [])
        if not isinstance(log_records, list) or len(log_records) == 0:
            return ""
        msg = str(log_records[-1].get('msg', '') or '').strip()
        if not msg:
            return ""
        # 去掉常见前缀符号
        if msg.startswith("· "):
            msg = msg[2:].strip()
        if msg.startswith("✓ ") or msg.startswith("✗ ") or msg.startswith("⚠ "):
            msg = msg[2:].strip()
        # 限长显示避免过长
        if len(msg) > 64:
            msg = msg[:64] + "…"
        return msg

    def _current_display_title(self) -> str:
        """获取当前显示标题（委托给日志控制器）"""
        return self._log_controller.get_current_display_title()

    # === 拖拽测试相关 ===

    def _update_drag_origin_from_focus(self) -> None:
        """根据 FocusController 中记录的视口矩形，刷新拖拽测试区的当前中心显示。"""
        if not hasattr(self, "_focus") or self._focus is None:
            self.drag_origin_label.setText("当前中心: 未定位")
            return
        center = self._focus.get_last_program_viewport_center()
        if center is None:
            self.drag_origin_label.setText("当前中心: 未定位")
            return
        center_x, center_y = center
        self.drag_origin_label.setText(f"当前中心: ({center_x:.1f}, {center_y:.1f})")
        # 若用户尚未填写目标坐标，优先填入当前中心，便于在此基础上偏移
        if not str(self.drag_target_x_input.text() or "").strip():
            self.drag_target_x_input.setText(f"{center_x:.1f}")
        if not str(self.drag_target_y_input.text() or "").strip():
            self.drag_target_y_input.setText(f"{center_y:.1f}")

    def _parse_program_coord(self, text: str):
        """解析程序坐标文本为 float；不使用 try/except，非法输入返回 None。"""
        raw = str(text or "").strip()
        if not raw:
            return None
        has_digit = False
        dot_count = 0
        for index, ch in enumerate(raw):
            if ch in "+-":
                if index != 0:
                    return None
            elif ch == ".":
                dot_count += 1
                if dot_count > 1:
                    return None
            elif ch.isdigit():
                has_digit = True
            else:
                return None
        if not has_digit:
            return None
        return float(raw)

    def _on_drag_to_target_clicked(self) -> None:
        """拖拽到用户指定的程序坐标（X/Y 输入框）。"""
        center = None
        if hasattr(self, "_focus") and self._focus is not None:
            center = self._focus.get_last_program_viewport_center()
        target_x = self._parse_program_coord(self.drag_target_x_input.text())
        target_y = self._parse_program_coord(self.drag_target_y_input.text())
        if target_x is None or target_y is None:
            if center is None:
                self.log("✗ 拖拽测试：请先点击一次“定位镜头”，并在 X/Y 输入框中填写合法的数值")
                return
            if target_x is None:
                target_x = center[0]
            if target_y is None:
                target_y = center[1]
        self.log(f"拖拽测试：目标程序坐标≈({float(target_x):.1f}, {float(target_y):.1f})")
        if hasattr(self, "_focus") and self._focus is not None:
            self._focus.ensure_point_visible(float(target_x), float(target_y))
            self._update_drag_origin_from_focus()

    def _on_directional_drag_clicked(self, is_left: bool) -> None:
        """以最近一次视口中心为基准，向左或向右拖拽一段距离。"""
        if not hasattr(self, "_focus") or self._focus is None:
            self.log("✗ 拖拽测试：尚未建立坐标映射，请先点击一次“定位镜头”按钮")
            return
        center = self._focus.get_last_program_viewport_center()
        if center is None:
            self.log("✗ 拖拽测试：当前无可用视口中心，请先执行一次“定位镜头”")
            return
        base_x, base_y = center
        # 若用户在 X 输入框中填写了数值，则作为偏移量使用；否则采用默认步长
        offset_value = self._parse_program_coord(self.drag_target_x_input.text())
        if offset_value is None:
            offset_value = 400.0
        step = float(offset_value)
        if step < 0:
            step = -step
        if is_left:
            target_x = base_x - step
            direction_text = "向左"
        else:
            target_x = base_x + step
            direction_text = "向右"
        target_y = base_y
        self.drag_target_x_input.setText(f"{target_x:.1f}")
        self.drag_target_y_input.setText(f"{target_y:.1f}")
        self.log(
            f"拖拽测试：{direction_text}拖拽一段距离，目标程序坐标≈({target_x:.1f}, {target_y:.1f})"
        )
        self._focus.ensure_point_visible(float(target_x), float(target_y))
        self._update_drag_origin_from_focus()

    def update_status(self, status: str) -> None:
        if QtCore.QThread.currentThread() is self.thread():
            self._set_status(status)
        else:
            self.set_status_signal.emit(status)

    def update_progress(self, current: int, total: int) -> None:
        if QtCore.QThread.currentThread() is self.thread():
            self._set_progress(current, total)
        else:
            self.set_progress_signal.emit(current, total)

    def log(self, message: str) -> None:
        if QtCore.QThread.currentThread() is self.thread():
            self._log_controller.append(message)
        else:
            self.append_log_signal.emit(message)

    # === 结构化执行事件 API（供执行桥接层调用）===

    def begin_run(self, total_steps: int) -> str:
        """
        标记一次新的执行运行开始，并在事件表格中记录 RUN_STARTED。

        返回:
            run_id 字符串（当前仅用于内部标识）
        """
        if not hasattr(self, "_event_model") or self._event_model is None:
            return ""
        self._current_run_total_steps = int(total_steps or 0)
        self._current_run_completed = 0
        self._current_run_failed = 0
        run_id = self._event_model.start_new_run(self._current_run_total_steps)
        if self._current_run_total_steps > 0:
            self.progress_label.setText(f"步骤: 0/{self._current_run_total_steps}")
        return run_id

    def end_run(self, success: bool, reason: str | None = None) -> None:
        """结束当前运行，在事件表格中记录结果并更新状态标签。"""
        if hasattr(self, "_event_model") and self._event_model is not None:
            self._event_model.finish_run(bool(success), reason=reason)
        if success:
            self.status_label.setText("执行完成")
        else:
            self.status_label.setText("执行结束（含失败）")

    def notify_step_started(
        self,
        todo_id: str,
        title: str,
        index: int | None,
        total_steps: int | None,
    ) -> None:
        """记录某个步骤即将开始（由执行桥接层调用）。"""
        if not hasattr(self, "_event_model") or self._event_model is None:
            return
        total = total_steps if total_steps is not None else self._current_run_total_steps
        self._event_model.add_step_started(todo_id, title, index, total or None)

    def notify_step_completed(
        self,
        todo_id: str,
        title: str,
        index: int | None,
        total_steps: int | None,
        success: bool,
        reason: str | None = None,
    ) -> None:
        """记录某个步骤完成，并更新运行统计。"""
        if not hasattr(self, "_event_model") or self._event_model is None:
            return
        total = total_steps if total_steps is not None else self._current_run_total_steps
        self._event_model.add_step_completed(todo_id, title, index, total or None, success, reason)
        # 更新统计
        self._current_run_completed += 1
        if not success:
            self._current_run_failed += 1
        if total and total > 0:
            if self._current_run_failed > 0:
                self.progress_label.setText(
                    f"步骤: {self._current_run_completed}/{total}（失败 {self._current_run_failed}）"
                )
            else:
                self.progress_label.setText(f"步骤: {self._current_run_completed}/{total}")

    def notify_step_skipped(
        self,
        todo_id: str,
        title: str,
        index: int | None,
        total_steps: int | None,
        reason: str,
    ) -> None:
        """记录某个步骤被跳过（仅在确实被视为“跳过”时调用）。"""
        if not hasattr(self, "_event_model") or self._event_model is None:
            return
        total = total_steps if total_steps is not None else self._current_run_total_steps
        self._event_model.add_step_skipped(todo_id, title, index, total or None, reason)

    def set_current_step_context(self, step_title: str, parent_title: str) -> None:
        """设置当前步骤上下文（委托给日志控制器 + 更新 UI 标签）"""
        self._log_controller.set_current_step_context(step_title, parent_title)
        # 更新 UI 标签
        self.step_context_label.setText(f"步骤: {step_title}" if step_title else "")
        # 回填最近的空标题项，避免早期截图（如启动校验）无标题
        self._renderer.backfill_recent_empty_titles()

    def set_current_step_tokens(self, step_id: str, tokens: list) -> None:
        """设置用于每行行首展示的分段富文本（委托给日志控制器）"""
        self._log_controller.set_current_step_tokens(step_id, tokens)
        # 回填最近的空标题项
        self._renderer.backfill_recent_empty_titles()

    def clear_log(self) -> None:
        """清空日志（委托给日志控制器）"""
        self._log_controller.clear()

    def wait_if_paused(self) -> None:
        """等待（阻塞），直到不再暂停（委托给控制器）"""
        self._control.wait_if_paused()

    def is_execution_allowed(self) -> bool:
        """检查是否允许执行（委托给控制器）"""
        return self._control.is_execution_allowed()

    def is_step_mode_enabled(self) -> bool:
        """检查是否启用单步模式（委托给控制器）"""
        return self._control.is_step_mode_enabled()

    # === 私有槽 ===
    def _append_log_via_controller(self, message: str) -> None:
        """通过日志控制器追加日志（用于线程安全信号）"""
        self._log_controller.append(message)

    def _set_status(self, status: str) -> None:
        self.status_label.setText(status)

    def _set_progress(self, current: int, total: int) -> None:
        if total > 0:
            self.progress_label.setText(f"进度: {current}/{total} ({current*100//total}%)")
        else:
            self.progress_label.setText(f"进度: {current}")

    def _on_anchor_clicked(self, url: QtCore.QUrl) -> None:
        """处理日志锚点点击（委托给日志控制器解析，然后发射信号）"""
        todo_id = self._log_controller.on_anchor_clicked(url)
        if todo_id:
            self.step_anchor_clicked.emit(todo_id)

    def _on_event_row_activated(self, index: QtCore.QModelIndex) -> None:
        """双击执行事件表格行：根据 todo_id 在左侧任务/图中定位。"""
        if not index.isValid():
            return
        model = getattr(self, "_event_model", None)
        if model is None:
            return
        event = model.get_event_at(index.row())
        if event is None or not event.todo_id:
            return
        self.step_anchor_clicked.emit(str(event.todo_id))

    def _on_event_errors_only_toggled(self, checked: bool) -> None:
        """切换“仅错误/警告”过滤。"""
        model = getattr(self, "_event_model", None)
        if model is None:
            return
        model.set_only_errors(bool(checked))

    def _update_screenshot(self) -> None:
        # 外部拉取截图后调用 update_screenshot，这里不主动抓取
        pass

    # === 外部注入上下文 ===
    def set_context(self, workspace_path, graph_model, graph_view=None) -> None:
        """设置执行上下文"""
        self.current_workspace_path = workspace_path
        self.current_graph_model = graph_model
        if graph_view is not None:
            self.graph_view = graph_view

    # === 与执行子系统共享 EditorExecutor 实例（用于复用视口状态） ===
    def get_shared_executor(self):
        return self._shared_executor

    def set_shared_executor(self, executor) -> None:
        self._shared_executor = executor

