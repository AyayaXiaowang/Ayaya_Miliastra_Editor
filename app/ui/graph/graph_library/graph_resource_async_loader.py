from __future__ import annotations

from PyQt6 import QtCore

from engine.resources.resource_manager import ResourceManager

from .graph_resource_load_thread import GraphResourceLoadThread


class GraphResourceAsyncLoader(QtCore.QObject):
    """可复用的“后台加载节点图资源”封装（generation 防串包 + 取消语义）。

    设计目标：
    - 统一 GraphResourceLoadThread 的启动/回收与 generation 防串包逻辑；
    - 页面侧只需订阅信号：成功拿到 graph_data 后再决定如何打开/跳转；
    - 取消语义：新请求会 requestInterruption() 旧线程，并通过 generation 忽略旧结果。
    """

    graph_loaded = QtCore.pyqtSignal(str, dict)
    graph_load_failed = QtCore.pyqtSignal(str)

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("GraphResourceAsyncLoader")
        self._generation: int = 0
        self._thread: GraphResourceLoadThread | None = None

    def cancel(self) -> None:
        """取消当前请求（若仍在运行）。"""
        self._generation += 1
        thread = self._thread
        if thread is not None and thread.isRunning():
            thread.requestInterruption()
        self._thread = None

    def request_load(
        self,
        *,
        resource_manager: ResourceManager,
        graph_id: str,
    ) -> None:
        graph_id_text = str(graph_id or "").strip()
        if not graph_id_text:
            return

        self._generation += 1
        generation = int(self._generation)

        prev_thread = self._thread
        if prev_thread is not None and prev_thread.isRunning():
            prev_thread.requestInterruption()
        self._thread = None

        thread = GraphResourceLoadThread(
            resource_manager=resource_manager,
            graph_id=graph_id_text,
            parent=self,
        )
        self._thread = thread

        def _on_finished() -> None:
            if int(self._generation) != int(generation):
                return
            self._thread = None

            result = getattr(thread, "result", None)
            if result is None or not isinstance(result.graph_data, dict):
                self.graph_load_failed.emit(graph_id_text)
                return
            self.graph_loaded.emit(str(result.graph_id or graph_id_text), result.graph_data)

        thread.finished.connect(_on_finished)
        thread.finished.connect(thread.deleteLater)
        thread.start()

