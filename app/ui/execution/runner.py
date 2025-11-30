# -*- coding: utf-8 -*-
"""
执行驱动器（轻耦合）：在后台线程顺序执行节点图步骤，并通过信号暴露编排事件。

使用方式：
    runner = ExecutionRunner()
    runner.step_will_start.connect(...)
    runner.step_completed.connect(...)
    runner.finished.connect(...)
    runner.start(executor, graph_model, step_list, monitor)

约定：
    monitor 需实现以下方法属性：
      - start_monitoring()
      - stop_monitoring()
      - update_status(str)
      - log(str)
      - wait_if_paused()
      - is_execution_allowed() -> bool
      - update_visual(Image, overlays)
"""

from PyQt6 import QtCore
from PyQt6.QtCore import pyqtSignal
from .thread import ExecutionThread


class ExecutionRunner(QtCore.QObject):
    """执行驱动器：负责按顺序驱动 EditorExecutor 执行步骤。"""

    finished = pyqtSignal()
    step_will_start = pyqtSignal(str)  # todo_id
    step_completed = pyqtSignal(str, bool)  # todo_id, success
    step_skipped = pyqtSignal(str, str)  # todo_id, reason

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QtCore.QThread | None = None

    def start(self, executor, graph_model, steps, monitor, *, fast_chain_mode: bool = False) -> None:
        """启动执行线程。

        Args:
            executor: EditorExecutor 实例（符合 EditorExecutorProtocol 协议）
            graph_model: GraphModel 实例
            steps: List[TodoItem]
            monitor: 执行监控对象（见模块头约定）
            fast_chain_mode: 是否启用快速链模式（跳过步骤缓冲等待）
        """
        if self._thread is not None:
            return

        # 创建独立的执行线程实例
        self._thread = ExecutionThread(executor, graph_model, steps, monitor, fast_chain_mode=fast_chain_mode)
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.step_will_start.connect(self.step_will_start)
        self._thread.step_completed.connect(self.step_completed)
        self._thread.step_skipped.connect(self.step_skipped)
        # 在启动后台线程之前：
        # 1) 预先绑定第一步的步骤上下文，确保启动阶段（缩放检查/快速匹配/校准）产生的截图也带有步骤名
        if isinstance(steps, (list, tuple)) and len(steps) > 0 and hasattr(monitor, 'set_current_step_context'):
            first_title = str(getattr(steps[0], 'title', '') or '')
            if first_title:
                monitor.set_current_step_context(first_title, "")
        # 2) 提前启动监控，使全局可视化/日志接收器就绪，避免早期识别画面漏接
        if hasattr(monitor, 'start_monitoring'):
            monitor.start_monitoring()
        # 启动执行线程
        self._thread.start()

    def _on_thread_finished(self) -> None:
        self._thread = None
        self.finished.emit()


