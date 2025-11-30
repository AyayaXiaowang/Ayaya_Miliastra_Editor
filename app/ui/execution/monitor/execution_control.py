# -*- coding: utf-8 -*-
"""
执行控制与单步模式
职责：暂停/继续/终止控制、单步模式逻辑、执行状态管理
"""

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import Qt, pyqtSignal


class ExecutionControl(QtCore.QObject):
    """执行控制器：管理暂停/继续/单步/终止"""
    
    # 信号：停止执行请求
    stop_requested = pyqtSignal()
    # 信号：状态更新（用于通知面板更新状态标签）
    status_changed = pyqtSignal(str)
    # 信号：日志消息
    log_message = pyqtSignal(str)
    
    def __init__(
        self,
        pause_button: QtWidgets.QPushButton,
        resume_button: QtWidgets.QPushButton,
        next_step_button: QtWidgets.QPushButton,
        step_mode_checkbox: QtWidgets.QCheckBox,
        stop_button: QtWidgets.QPushButton,
        parent: QtCore.QObject | None = None
    ):
        """
        Args:
            pause_button: 暂停按钮
            resume_button: 继续按钮
            next_step_button: 下一步按钮
            step_mode_checkbox: 单步模式复选框
            stop_button: 终止按钮
            parent: 父对象
        """
        super().__init__(parent)
        
        # UI 控件
        self._pause_button = pause_button
        self._resume_button = resume_button
        self._next_step_button = next_step_button
        self._step_mode_checkbox = step_mode_checkbox
        self._stop_button = stop_button
        
        # 状态
        self.is_running = False
        self.is_paused = False
        self.step_mode_enabled = False
        
        # 连接信号
        self._connect_signals()
    
    def _connect_signals(self) -> None:
        """连接内部信号"""
        self._pause_button.clicked.connect(self._on_pause_clicked)
        self._resume_button.clicked.connect(self._on_resume_clicked)
        self._next_step_button.clicked.connect(self._on_next_step_clicked)
        self._step_mode_checkbox.stateChanged.connect(self._on_step_mode_toggled)
        self._stop_button.clicked.connect(self._on_stop_clicked)
    
    def start_execution(self) -> None:
        """开始执行"""
        self.is_running = True
        self.is_paused = False
        self._pause_button.setEnabled(True)
        self._resume_button.setEnabled(False)
        self._next_step_button.setEnabled(self.step_mode_enabled)
        self._stop_button.setEnabled(True)
    
    def stop_execution(self) -> None:
        """停止执行"""
        self.is_running = False
        self.is_paused = False
        self._pause_button.setEnabled(False)
        self._resume_button.setEnabled(False)
        self._next_step_button.setEnabled(False)
        self._stop_button.setEnabled(False)
    
    def request_pause(self) -> None:
        """请求暂停（可从快捷键调用）"""
        if self.is_running and not self.is_paused:
            self.is_paused = True
            self._pause_button.setEnabled(False)
            self._resume_button.setEnabled(True)
            self.log_message.emit("已暂停（Ctrl+P）")
            self.status_changed.emit("已暂停")
    
    def wait_if_paused(self) -> None:
        """等待（阻塞），直到不再暂停"""
        while self.is_paused and self.is_running:
            QtCore.QThread.msleep(100)
    
    def is_execution_allowed(self) -> bool:
        """检查是否允许执行"""
        return self.is_running and not self.is_paused
    
    def is_step_mode_enabled(self) -> bool:
        """检查是否启用单步模式"""
        return self.step_mode_enabled
    
    def _on_pause_clicked(self) -> None:
        """暂停按钮点击"""
        if not self.is_running:
            return
        if not self.is_paused:
            self.is_paused = True
            self._pause_button.setEnabled(False)
            self._resume_button.setEnabled(True)
            self.log_message.emit("已暂停")
            self.status_changed.emit("已暂停")
    
    def _on_resume_clicked(self) -> None:
        """继续按钮点击"""
        if not self.is_running:
            return
        if self.is_paused:
            self.is_paused = False
            self._pause_button.setEnabled(True)
            self._resume_button.setEnabled(False)
            self.log_message.emit("继续执行")
            self.status_changed.emit("执行中...")
            # 用户选择"继续"，退出单步模式
            if self.step_mode_enabled:
                self.step_mode_enabled = False
                if self._step_mode_checkbox.isChecked():
                    self._step_mode_checkbox.blockSignals(True)
                    self._step_mode_checkbox.setChecked(False)
                    self._step_mode_checkbox.blockSignals(False)
                self._next_step_button.setEnabled(False)
    
    def _on_stop_clicked(self) -> None:
        """终止按钮点击"""
        self.is_running = False
        self.is_paused = False
        self.stop_requested.emit()
        self.log_message.emit("终止执行")
    
    def _on_step_mode_toggled(self, state: int) -> None:
        """单步模式切换"""
        enabled = state == Qt.CheckState.Checked.value
        self.step_mode_enabled = enabled
        if self.is_running:
            self._next_step_button.setEnabled(enabled)
        else:
            self._next_step_button.setEnabled(False)
    
    def _on_next_step_clicked(self) -> None:
        """下一步按钮点击"""
        if not self.is_running:
            return
        if not self.step_mode_enabled:
            return
        # 允许继续一步；下一步开始时由外部在 step_will_start 中重新触发暂停
        if self.is_paused:
            self._on_resume_clicked()
        # 若当前未处于暂停但用户点击了"下一步"，忽略（执行线程会在下一步开始前再暂停）

