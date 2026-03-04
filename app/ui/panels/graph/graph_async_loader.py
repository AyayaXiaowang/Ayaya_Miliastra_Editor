from __future__ import annotations

import atexit
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock
from typing import Callable, Dict, Optional, Iterable

from PyQt6 import QtCore

from app.runtime.services.graph_data_service import GraphDataService, GraphLoadPayload

_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="graph-loader")
atexit.register(_EXECUTOR.shutdown, False)
_EXECUTOR_SHUTDOWN = False
_EXECUTOR_LOCK = Lock()

_GLOBAL_SHUTTING_DOWN: bool = False


class GraphAsyncLoader(QtCore.QObject):
    """共享的节点图异步加载调度器。"""

    _payload_ready = QtCore.pyqtSignal(object, str, object)
    _membership_ready = QtCore.pyqtSignal(object, str, object, object, object)
    _references_ready = QtCore.pyqtSignal(object, str, object, object)

    def __init__(self, provider: GraphDataService, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self._provider = provider
        self._pending: Dict[str, Future] = {}
        self._callbacks: Dict[Future, list[Callable[[str, GraphLoadPayload], None]]] = {}
        self._lock = Lock()
        self._is_shutdown: bool = False
        self._payload_ready.connect(self._dispatch_payload)
        self._membership_ready.connect(self._dispatch_membership)
        self._references_ready.connect(self._dispatch_references)

    def shutdown(self) -> None:
        """关闭当前 loader：取消 pending futures，清空回调，避免退出阶段跨线程 emit Qt 信号。"""
        self._is_shutdown = True
        futures_to_cancel: list[Future] = []
        with self._lock:
            for future in self._pending.values():
                futures_to_cancel.append(future)
            self._pending.clear()
            self._callbacks.clear()
        for future in futures_to_cancel:
            future.cancel()

    def request_payload(self, graph_id: str, callback: Callable[[str, GraphLoadPayload], None]) -> Future:
        if self._is_shutdown or _GLOBAL_SHUTTING_DOWN:
            cancelled = Future()
            cancelled.cancel()
            return cancelled
        with self._lock:
            existing = self._pending.get(graph_id)
            if existing and not existing.done():
                self._callbacks.setdefault(existing, []).append(callback)
                return existing
        future = _EXECUTOR.submit(self._provider.load_graph_payload, graph_id)
        with self._lock:
            self._pending[graph_id] = future
            self._callbacks[future] = [callback]

        def _deliver() -> None:
            if self._is_shutdown or _GLOBAL_SHUTTING_DOWN:
                with self._lock:
                    self._pending.pop(graph_id, None)
                    self._callbacks.pop(future, None)
                return
            if QtCore.QCoreApplication.instance() is None or QtCore.QCoreApplication.closingDown():
                with self._lock:
                    self._pending.pop(graph_id, None)
                    self._callbacks.pop(future, None)
                return
            payload = GraphLoadPayload(error="节点图加载任务已取消。")
            if future.cancelled():
                payload = GraphLoadPayload(error="节点图加载已取消。")
            else:
                error = future.exception()
                if error:
                    payload = GraphLoadPayload(error=str(error))
                else:
                    payload = future.result()
            with self._lock:
                self._pending.pop(graph_id, None)
                callbacks = self._callbacks.pop(future, [])
            if not callbacks:
                return
            for cb in callbacks:
                self._payload_ready.emit(cb, graph_id, payload)

        future.add_done_callback(lambda _: _deliver())
        return future

    def request_membership(
        self,
        graph_id: str,
        callback: Callable[[str, list[dict], set[str], Optional[str]], None],
    ) -> Future:
        if self._is_shutdown or _GLOBAL_SHUTTING_DOWN:
            cancelled = Future()
            cancelled.cancel()
            return cancelled
        def _load_membership() -> tuple[list[dict], set[str]]:
            packages = self._provider.get_packages()
            membership = self._provider.get_graph_membership(graph_id)
            return packages, membership

        future = _EXECUTOR.submit(_load_membership)

        def _deliver() -> None:
            if self._is_shutdown or _GLOBAL_SHUTTING_DOWN:
                return
            if QtCore.QCoreApplication.instance() is None or QtCore.QCoreApplication.closingDown():
                return
            packages: list[dict] = []
            membership: set[str] = set()
            error_text: Optional[str] = None
            if not future.cancelled():
                error = future.exception()
                if error:
                    error_text = str(error)
                else:
                    packages, membership = future.result()
            self._membership_ready.emit(callback, graph_id, packages, membership, error_text)

        future.add_done_callback(lambda _: _deliver())
        return future

    def request_references(
        self,
        graph_id: str,
        callback: Callable[[str, list, Optional[str]], None],
    ) -> Future:
        """异步加载节点图引用列表（不依赖节点图解析）。

        典型场景：
        - 节点图库轻量预览：单击只展示引用次数，切到“引用列表”页签时再按需加载详情；
        - 避免在 UI 线程同步构建大列表导致单击卡顿。
        """
        if self._is_shutdown or _GLOBAL_SHUTTING_DOWN:
            cancelled = Future()
            cancelled.cancel()
            return cancelled

        def _load_references() -> list:
            return list(self._provider.get_references(graph_id))

        future = _EXECUTOR.submit(_load_references)

        def _deliver() -> None:
            if self._is_shutdown or _GLOBAL_SHUTTING_DOWN:
                return
            if QtCore.QCoreApplication.instance() is None or QtCore.QCoreApplication.closingDown():
                return

            references: list = []
            error_text: Optional[str] = None
            if not future.cancelled():
                error = future.exception()
                if error:
                    error_text = str(error)
                else:
                    references = future.result()
            self._references_ready.emit(callback, graph_id, references, error_text)

        future.add_done_callback(lambda _: _deliver())
        return future

    def cancel(self, graph_id: str) -> None:
        with self._lock:
            future = self._pending.pop(graph_id, None)
            if future:
                self._callbacks.pop(future, None)
        if future:
            future.cancel()

    @QtCore.pyqtSlot(object, str, object)
    def _dispatch_payload(self, callback: Optional[Callable[[str, GraphLoadPayload], None]], graph_id: str, payload: GraphLoadPayload) -> None:
        if callable(callback):
            callback(graph_id, payload)

    @QtCore.pyqtSlot(object, str, object, object, object)
    def _dispatch_membership(
        self,
        callback: Optional[Callable[[str, list[dict], set[str], Optional[str]], None]],
        graph_id: str,
        packages: object,
        membership: object,
        error_text: object,
    ) -> None:
        if callable(callback):
            callback(graph_id, packages, membership, error_text)

    @QtCore.pyqtSlot(object, str, object, object)
    def _dispatch_references(
        self,
        callback: Optional[Callable[[str, list, Optional[str]], None]],
        graph_id: str,
        references: object,
        error_text: object,
    ) -> None:
        if callable(callback):
            callback(graph_id, references, error_text)


_SHARED_LOADERS: Dict[int, GraphAsyncLoader] = {}
_SHARED_LOCK = Lock()


def get_shared_graph_loader(provider: GraphDataService) -> GraphAsyncLoader:
    key = id(provider)
    with _SHARED_LOCK:
        loader = _SHARED_LOADERS.get(key)
        if loader is None:
            # 绑定到 QApplication（如存在），确保退出阶段 QObject 析构顺序稳定
            parent = QtCore.QCoreApplication.instance()
            loader = GraphAsyncLoader(provider, parent=parent)
            _SHARED_LOADERS[key] = loader
        return loader


def shutdown_graph_async_loader_system() -> None:
    """退出阶段显式关闭：停止所有共享 loader 并关闭线程池。

    设计目标：避免窗口关闭阶段仍有线程池回调跨线程 emit Qt 信号，触发 native access violation。
    """
    global _GLOBAL_SHUTTING_DOWN, _EXECUTOR_SHUTDOWN
    _GLOBAL_SHUTTING_DOWN = True

    loaders: list[GraphAsyncLoader] = []
    with _SHARED_LOCK:
        for loader in _SHARED_LOADERS.values():
            loaders.append(loader)
        _SHARED_LOADERS.clear()

    for loader in loaders:
        loader.shutdown()

    with _EXECUTOR_LOCK:
        if _EXECUTOR_SHUTDOWN:
            return
        _EXECUTOR_SHUTDOWN = True
    _EXECUTOR.shutdown(wait=False, cancel_futures=True)

