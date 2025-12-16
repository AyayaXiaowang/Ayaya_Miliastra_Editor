from __future__ import annotations

import atexit
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock
from typing import Callable, Dict, Optional

from PyQt6 import QtCore

from app.runtime.services.graph_data_service import GraphDataService, GraphLoadPayload

_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="graph-loader")
atexit.register(_EXECUTOR.shutdown, False)


class GraphAsyncLoader(QtCore.QObject):
    """共享的节点图异步加载调度器。"""

    _payload_ready = QtCore.pyqtSignal(object, str, object)
    _membership_ready = QtCore.pyqtSignal(object, str, object, object, object)

    def __init__(self, provider: GraphDataService, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self._provider = provider
        self._pending: Dict[str, Future] = {}
        self._callbacks: Dict[Future, list[Callable[[str, GraphLoadPayload], None]]] = {}
        self._lock = Lock()
        self._payload_ready.connect(self._dispatch_payload)
        self._membership_ready.connect(self._dispatch_membership)

    def request_payload(self, graph_id: str, callback: Callable[[str, GraphLoadPayload], None]) -> Future:
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
        def _load_membership() -> tuple[list[dict], set[str]]:
            packages = self._provider.get_packages()
            membership = self._provider.get_graph_membership(graph_id)
            return packages, membership

        future = _EXECUTOR.submit(_load_membership)

        def _deliver() -> None:
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


_SHARED_LOADERS: Dict[int, GraphAsyncLoader] = {}
_SHARED_LOCK = Lock()


def get_shared_graph_loader(provider: GraphDataService) -> GraphAsyncLoader:
    key = id(provider)
    with _SHARED_LOCK:
        loader = _SHARED_LOADERS.get(key)
        if loader is None:
            loader = GraphAsyncLoader(provider)
            _SHARED_LOADERS[key] = loader
        return loader

