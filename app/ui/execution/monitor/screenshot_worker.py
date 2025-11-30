# -*- coding: utf-8 -*-
"""
截图线程与抓取管理
职责：后台周期性截图抓取、线程生命周期管理
"""

from PyQt6 import QtCore
from PIL import Image
from app.automation import AutomationFacade


class ScreenshotWorker(QtCore.QThread):
    """后台截图线程：周期性抓取外部编辑器窗口截图"""
    screenshot_ready = QtCore.pyqtSignal(object)  # PIL.Image.Image

    def __init__(self, window_title: str, interval_ms: int, parent: QtCore.QObject | None = None):
        super().__init__(parent)
        self.window_title = window_title
        self.interval_ms = interval_ms
        self._running = True
        self._facade = AutomationFacade()

    def run(self) -> None:
        while self._running:
            screenshot = self._facade.capture_window(self.window_title)
            if screenshot is not None:
                self.screenshot_ready.emit(screenshot)
            QtCore.QThread.msleep(self.interval_ms)

    def stop(self) -> None:
        self._running = False


class ScreenshotCaptureManager:
    """截图抓取管理器：封装截图线程的启动、停止与信号连接"""
    
    def __init__(self, parent: QtCore.QObject, screenshot_interval_ms: int = 500):
        """
        Args:
            parent: 父对象（用于线程生命周期与信号接收）
            screenshot_interval_ms: 截图间隔（毫秒）
        """
        self._parent = parent
        self._screenshot_interval = screenshot_interval_ms
        self._screenshot_worker: ScreenshotWorker | None = None
        self._window_title: str = "千星沙箱"
        
    def start_capture(self, window_title: str, on_screenshot_ready) -> None:
        """启动后台截图线程
        
        Args:
            window_title: 目标窗口标题
            on_screenshot_ready: 截图就绪回调（接收 PIL.Image.Image）
        """
        if self._screenshot_worker is not None:
            self.stop_capture()
        self._window_title = window_title
        self._screenshot_worker = ScreenshotWorker(
            window_title, 
            self._screenshot_interval, 
            self._parent
        )
        self._screenshot_worker.screenshot_ready.connect(on_screenshot_ready)
        self._screenshot_worker.start()
    
    def stop_capture(self) -> None:
        """停止后台截图线程"""
        if self._screenshot_worker is not None:
            self._screenshot_worker.stop()
            self._screenshot_worker.wait()
            self._screenshot_worker = None
    
    def get_window_title(self) -> str:
        """获取当前窗口标题"""
        return self._window_title
    
    def set_window_title(self, title: str) -> None:
        """设置窗口标题（不重启线程）"""
        self._window_title = title

