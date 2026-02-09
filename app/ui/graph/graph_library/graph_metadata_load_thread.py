from __future__ import annotations

from PyQt6 import QtCore

from engine.resources.resource_manager import ResourceManager


class GraphMetadataLoadThread(QtCore.QThread):
    """后台加载节点图轻量元数据（ResourceManager.load_graph_metadata）。

    设计目标：
    - 列表页切目录时不阻塞 UI 线程（大图/多图时 AST 解析会明显卡顿）
    - 支持 requestInterruption() 取消
    """

    metadata_loaded = QtCore.pyqtSignal(str, object)  # (graph_id, metadata_dict | None)

    def __init__(
        self,
        *,
        resource_manager: ResourceManager,
        graph_ids: list[str],
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("GraphMetadataLoadThread")
        self._resource_manager = resource_manager
        self._graph_ids = [str(graph_id or "").strip() for graph_id in list(graph_ids or [])]

    def run(self) -> None:
        for graph_id in self._graph_ids:
            if self.isInterruptionRequested():
                return
            graph_id_text = str(graph_id or "").strip()
            if not graph_id_text:
                continue
            metadata = self._resource_manager.load_graph_metadata(graph_id_text)
            self.metadata_loaded.emit(graph_id_text, metadata)

