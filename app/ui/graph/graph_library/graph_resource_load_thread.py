from __future__ import annotations

import time
from dataclasses import dataclass

from PyQt6 import QtCore

from engine.resources.resource_manager import ResourceManager, ResourceType
from app.ui.foundation.performance_monitor import get_shared_performance_monitor


@dataclass(frozen=True, slots=True)
class GraphResourceLoadResult:
    """节点图资源加载结果（GraphConfig.serialize dict）。"""

    graph_id: str
    graph_data: dict | None


class GraphResourceLoadThread(QtCore.QThread):
    """后台加载节点图资源（ResourceManager.load_resource）。"""

    def __init__(
        self,
        *,
        resource_manager: ResourceManager,
        graph_id: str,
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("GraphResourceLoadThread")
        self._resource_manager = resource_manager
        self._graph_id = str(graph_id or "").strip()
        self.result: GraphResourceLoadResult | None = None

    def run(self) -> None:
        graph_id = str(self._graph_id or "").strip()
        if not graph_id:
            self.result = GraphResourceLoadResult(graph_id="", graph_data=None)
            return

        monitor = get_shared_performance_monitor()
        started = time.perf_counter()
        graph_data = self._resource_manager.load_resource(ResourceType.GRAPH, graph_id)
        monitor.record_span(
            name=f"graph.load_resource:{graph_id}",
            dt_ms=float((time.perf_counter() - float(started)) * 1000.0),
            start_ts_s=float(started),
        )
        self.result = GraphResourceLoadResult(
            graph_id=graph_id,
            graph_data=graph_data if isinstance(graph_data, dict) else None,
        )

