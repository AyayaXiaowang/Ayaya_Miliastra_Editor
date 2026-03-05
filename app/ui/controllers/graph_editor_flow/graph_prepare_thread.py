from __future__ import annotations

import time
from dataclasses import dataclass

from PyQt6 import QtCore

from engine.graph.models.graph_model import GraphModel
from engine.graph.semantic import GraphSemanticPass
from app.ui.foundation.performance_monitor import get_shared_performance_monitor


@dataclass(frozen=True, slots=True)
class GraphPrepareResult:
    graph_id: str
    model: GraphModel
    baseline_content_hash: str


class GraphPrepareThread(QtCore.QThread):
    """后台线程：节点图加载的“纯模型准备阶段”。

    目标：
    - 将 `GraphModel.deserialize + GraphSemanticPass.apply` 等纯 Python 重活挪出 UI 线程；
    - 不触碰任何 Qt 图元（GraphScene/QGraphicsItem），避免线程亲和性问题；
    - 不做 try/except：若 run 内部抛错，交由控制器在 finished 回调中抛出“线程失败”异常并终止流程。
    """

    def __init__(
        self,
        *,
        graph_id: str,
        graph_data: dict,
        node_library: dict,
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("GraphPrepareThread")
        self._graph_id = str(graph_id or "")
        self._graph_data = graph_data
        self._node_library = node_library
        self.result: GraphPrepareResult | None = None

    def run(self) -> None:
        monitor = get_shared_performance_monitor()
        t_total0 = time.perf_counter()

        graph_id = str(self._graph_id or "")
        graph_data = self._graph_data

        if not isinstance(graph_data, dict) or not graph_data:
            raise ValueError("节点图数据为空或类型错误")

        t0 = time.perf_counter()
        model = GraphModel.deserialize(graph_data)
        monitor.record_span(
            "graph.prepare.deserialize",
            float((time.perf_counter() - float(t0)) * 1000.0),
            start_ts_s=float(t0),
        )

        node_library = self._node_library
        if isinstance(node_library, dict) and node_library:
            t_sync = time.perf_counter()
            updated_count = model.sync_composite_nodes_from_library(node_library)
            monitor.record_span(
                "graph.prepare.sync_composites",
                float((time.perf_counter() - float(t_sync)) * 1000.0),
                start_ts_s=float(t_sync),
            )
            if updated_count > 0:
                print(f"[加载] 同步了 {updated_count} 个复合节点的端口定义")

        # 语义元数据（signal_bindings/struct_bindings）统一对齐
        t_sem = time.perf_counter()
        GraphSemanticPass.apply(model=model)
        monitor.record_span(
            "graph.prepare.semantic_pass",
            float((time.perf_counter() - float(t_sem)) * 1000.0),
            start_ts_s=float(t_sem),
        )

        t_hash = time.perf_counter()
        baseline_hash = model.get_content_hash()
        monitor.record_span(
            "graph.prepare.content_hash",
            float((time.perf_counter() - float(t_hash)) * 1000.0),
            start_ts_s=float(t_hash),
        )

        monitor.record_span(
            name=f"graph.prepare.total:{graph_id}",
            dt_ms=float((time.perf_counter() - float(t_total0)) * 1000.0),
            start_ts_s=float(t_total0),
        )
        self.result = GraphPrepareResult(
            graph_id=graph_id,
            model=model,
            baseline_content_hash=str(baseline_hash),
        )

