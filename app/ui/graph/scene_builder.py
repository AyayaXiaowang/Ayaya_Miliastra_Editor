from __future__ import annotations

"""GraphScene 装配辅助函数。"""

import time
from typing import Optional

from PyQt6 import QtCore

from engine.graph.models.graph_model import GraphModel
from app.ui.graph.graph_scene import GraphScene


def populate_scene_from_model(
    scene: GraphScene,
    *,
    enable_batch_mode: bool = True,
) -> None:
    """将 GraphModel 的节点与连线一次性添加到场景。

    Args:
        scene: 目标 GraphScene，需已绑定 `model`。
        enable_batch_mode: 是否在批量模式下插入，默认开启以避免重复计算场景边界。
    """
    if not isinstance(scene.model, GraphModel):
        raise ValueError("GraphScene 缺少有效的 GraphModel，无法装配内容")

    previous_bulk_flag = bool(getattr(scene, "is_bulk_adding_items", False))
    if enable_batch_mode:
        scene.is_bulk_adding_items = True

    try:
        for node in scene.model.nodes.values():
            scene.add_node_item(node)

        for edge in scene.model.edges.values():
            scene.add_edge_item(edge)

        if enable_batch_mode:
            # 批量装配时：连线创建会延迟“目标节点端口重排”，这里统一 flush 一次，
            # 避免每条边都触发 _layout_ports() 造成 O(E) 的重排开销。
            if hasattr(scene, "flush_deferred_port_layouts"):
                scene.flush_deferred_port_layouts()

        # 统一刷新场景矩形与小地图缓存，确保视图加载后立即可用
        scene.rebuild_scene_rect_and_minimap()
    finally:
        if enable_batch_mode:
            scene.is_bulk_adding_items = previous_bulk_flag


class IncrementalScenePopulateJob(QtCore.QObject):
    """分帧增量装配 GraphScene（避免一次性构建阻塞 UI 事件循环）。

    说明：
    - 该 job 运行在主线程，通过 QTimer(0) 分帧推进；
    - 仅负责“把 model.nodes/model.edges 变成图元”，不做任何后台线程操作；
    - 若 enable_batch_mode=True，会在开始时临时开启 scene.is_bulk_adding_items，
      结束后 flush 延迟端口重排并一次性刷新 sceneRect/小地图缓存。
    """

    progress = QtCore.pyqtSignal(int, int, int, int)  # nodes_done, nodes_total, edges_done, edges_total
    finished = QtCore.pyqtSignal()
    cancelled = QtCore.pyqtSignal()

    def __init__(
        self,
        scene: GraphScene,
        *,
        enable_batch_mode: bool = True,
        time_budget_ms: int = 10,
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        if not isinstance(scene, GraphScene):
            raise TypeError(f"scene 必须是 GraphScene（got: {type(scene).__name__}）")
        if not isinstance(scene.model, GraphModel):
            raise ValueError("GraphScene 缺少有效的 GraphModel，无法装配内容")

        self._scene = scene
        self._enable_batch_mode = bool(enable_batch_mode)
        self._time_budget_s = max(0.0, float(time_budget_ms) / 1000.0)

        self._previous_bulk_flag = bool(getattr(scene, "is_bulk_adding_items", False))
        self._nodes = list(scene.model.nodes.values())
        self._edges = list(scene.model.edges.values())
        self._nodes_total = int(len(self._nodes))
        self._edges_total = int(len(self._edges))
        self._node_index = 0
        self._edge_index = 0

        # 批量装配收尾阶段：延迟端口重排（flush_deferred_port_layouts）也需要分帧推进，
        # 否则会在“节点/连线已装配完毕”的最后一帧产生一次性长耗时阻塞（大图尤为明显）。
        self._flush_initialized: bool = False
        self._flush_total: int = 0
        self._flush_done: int = 0
        self._phase: str = "nodes"

        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(False)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._on_tick)

        self._last_progress_emit_ts = 0.0
        self._progress_throttle_s = 0.12

    @property
    def nodes_total(self) -> int:
        return int(self._nodes_total)

    @property
    def edges_total(self) -> int:
        return int(self._edges_total)

    @property
    def flush_total(self) -> int:
        return int(self._flush_total)

    @property
    def flush_done(self) -> int:
        return int(self._flush_done)

    @property
    def phase(self) -> str:
        return str(self._phase or "")

    def start(self) -> None:
        if self._enable_batch_mode:
            self._scene.is_bulk_adding_items = True
        self._phase = "nodes"
        self._emit_progress(force=True)
        self._timer.start()

    def cancel(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
        if self._enable_batch_mode:
            self._scene.is_bulk_adding_items = self._previous_bulk_flag
        self._phase = "cancelled"
        self.cancelled.emit()

    def _emit_progress(self, *, force: bool = False) -> None:
        now = time.perf_counter()
        if (not force) and (now - float(self._last_progress_emit_ts)) < float(self._progress_throttle_s):
            return
        self._last_progress_emit_ts = now
        self.progress.emit(
            int(self._node_index),
            int(self._nodes_total),
            int(self._edge_index),
            int(self._edges_total),
        )

    def _on_tick(self) -> None:
        scene = self._scene
        budget_s = float(self._time_budget_s)
        t0 = time.perf_counter()

        # 先装配节点，再装配边（确保 add_edge_item 能命中 node_items）
        self._phase = "nodes"
        while self._node_index < self._nodes_total:
            scene.add_node_item(self._nodes[self._node_index])
            self._node_index += 1
            if budget_s > 0.0 and (time.perf_counter() - float(t0)) >= budget_s:
                self._emit_progress()
                return

        self._phase = "edges"
        while self._edge_index < self._edges_total:
            scene.add_edge_item(self._edges[self._edge_index])
            self._edge_index += 1
            if budget_s > 0.0 and (time.perf_counter() - float(t0)) >= budget_s:
                self._emit_progress()
                return

        # 节点/连线装配完成：批量模式下还需要 flush 延迟端口重排（分帧推进，避免最后一帧长阻塞）
        if self._enable_batch_mode:
            self._phase = "flush_ports"
            deferred_ids = getattr(scene, "_deferred_port_layout_node_ids", None)
            if not self._flush_initialized:
                self._flush_total = int(len(deferred_ids)) if isinstance(deferred_ids, set) else 0
                self._flush_done = 0
                self._flush_initialized = True

            if isinstance(deferred_ids, set) and deferred_ids:
                while deferred_ids:
                    node_id = str(deferred_ids.pop() or "")
                    if node_id:
                        node_item = scene.node_items.get(node_id)
                        if node_item is not None:
                            node_item._layout_ports()
                    self._flush_done += 1
                    if budget_s > 0.0 and (time.perf_counter() - float(t0)) >= budget_s:
                        self._emit_progress()
                        return

            # flush 完成：统一刷新场景矩形与小地图缓存，恢复批量标志
            self._phase = "finalize"
            scene.rebuild_scene_rect_and_minimap()
            scene.is_bulk_adding_items = self._previous_bulk_flag

        # 完成：停止计时器并发出 finished
        if self._timer.isActive():
            self._timer.stop()
        self._phase = "finished"
        self._emit_progress(force=True)
        self.finished.emit()

