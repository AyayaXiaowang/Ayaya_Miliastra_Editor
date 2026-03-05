from __future__ import annotations

from dataclasses import dataclass

from PyQt6 import QtCore

from engine.resources.resource_manager import ResourceManager
from .auto_layout_prepare_service import GraphEditorAutoLayoutPrepareService


@dataclass(frozen=True, slots=True)
class GraphAutoLayoutReparseResult:
    """自动排版前重解析结果。"""

    graph_id: str
    graph_data: dict | None


class GraphAutoLayoutReparseThread(QtCore.QThread):
    """后台线程：自动排版前按需执行“清缓存 + 从 .py 重解析”。

    目标：
    - 避免 `ResourceManager.invalidate_graph_for_reparse + load_resource` 阻塞 UI；
    - 不触碰 Qt 图元对象，仅返回 graph_data 给主线程继续加载管线。
    """

    def __init__(
        self,
        *,
        prepare_service: GraphEditorAutoLayoutPrepareService,
        resource_manager: ResourceManager,
        graph_id: str,
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("GraphAutoLayoutReparseThread")
        self._prepare_service = prepare_service
        self._resource_manager = resource_manager
        self._graph_id = str(graph_id or "").strip()
        self.result: GraphAutoLayoutReparseResult | None = None

    def run(self) -> None:
        graph_id = str(self._graph_id or "").strip()
        if not graph_id:
            self.result = GraphAutoLayoutReparseResult(graph_id="", graph_data=None)
            return
        if self.isInterruptionRequested():
            return

        reparse_result = self._prepare_service.reparse_graph_from_py(
            resource_manager=self._resource_manager,
            graph_id=graph_id,
        )
        if self.isInterruptionRequested():
            return

        graph_data = reparse_result.graph_data if isinstance(reparse_result.graph_data, dict) else None
        self.result = GraphAutoLayoutReparseResult(
            graph_id=graph_id,
            graph_data=graph_data,
        )

