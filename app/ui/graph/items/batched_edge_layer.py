from __future__ import annotations

"""批量连线渲染层（用于超大图 fast_preview_mode）。

目标：
- 将“每条边一个 QGraphicsItem”的开销降为“单一渲染层 + 轻量索引”；
- 保持只读预览的核心能力：点边/高亮边/灰显边；
- 与 fast_preview 的“节点级展开”兼容：被展开节点周围的边可被单独 materialize 为 QGraphicsItem，
  本层负责对这些 edge_id 做排除，避免重复绘制。
"""

import time

from dataclasses import dataclass
from typing import Iterable, Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from app.ui.graph.graph_palette import GraphPalette
from engine.configs.settings import settings


@dataclass(slots=True, frozen=True)
class _CubicCurve:
    p0: QtCore.QPointF
    p1: QtCore.QPointF
    p2: QtCore.QPointF
    p3: QtCore.QPointF


def _lerp(a: float, b: float, t: float) -> float:
    return float(a + (b - a) * t)


def _cubic_point(curve: _CubicCurve, t: float) -> QtCore.QPointF:
    """返回三次贝塞尔在 t∈[0,1] 的点（用于命中距离估算）。"""
    tt = float(max(0.0, min(1.0, t)))
    u = 1.0 - tt
    u2 = u * u
    tt2 = tt * tt
    # Bernstein basis
    b0 = u2 * u
    b1 = 3.0 * u2 * tt
    b2 = 3.0 * u * tt2
    b3 = tt2 * tt
    x = (
        float(curve.p0.x()) * b0
        + float(curve.p1.x()) * b1
        + float(curve.p2.x()) * b2
        + float(curve.p3.x()) * b3
    )
    y = (
        float(curve.p0.y()) * b0
        + float(curve.p1.y()) * b1
        + float(curve.p2.y()) * b2
        + float(curve.p3.y()) * b3
    )
    return QtCore.QPointF(float(x), float(y))


class BatchedFastPreviewEdgeLayer(QtWidgets.QGraphicsItem):
    """fast_preview_mode 的批量连线渲染层。

    约束：
    - 本层不参与 Qt 的 itemAt/选择等命中机制（shape() 返回空）；
    - 点击命中由 GraphScene 显式调用 pick_edge_id_at(...) 完成。
    """

    def __init__(self) -> None:
        super().__init__()
        self.setZValue(4)
        self.setAcceptedMouseButtons(QtCore.Qt.MouseButton.NoButton)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

        # edge_id -> (src_node_id, dst_node_id)
        self._endpoints: dict[str, tuple[str, str]] = {}
        # node_id -> set(edge_id)
        self._edge_ids_by_node_id: dict[str, set[str]] = {}

        # edge_id -> cached geometry
        self._curves: dict[str, _CubicCurve] = {}
        self._paths: dict[str, QtGui.QPainterPath] = {}
        self._edge_bounds: dict[str, QtCore.QRectF] = {}

        # grid index for pick
        self._cell_size: float = float(getattr(settings, "GRAPH_FAST_PREVIEW_BATCHED_EDGE_PICK_CELL_SIZE", 600.0))
        self._grid: dict[tuple[int, int], set[str]] = {}
        self._edge_cells: dict[str, set[tuple[int, int]]] = {}

        # render states
        self._selected_edge_ids: set[str] = set()
        self._dim_active: bool = False
        self._dim_focused_edge_ids: set[str] = set()
        self._excluded_edge_ids: set[str] = set()

        # bounding rect cache (scene coords, since item stays at (0,0))
        self._bounds: QtCore.QRectF = QtCore.QRectF()

    # --------------------------------------------------------------------- Qt overrides
    def boundingRect(self) -> QtCore.QRectF:  # noqa: N802 - Qt naming
        return QtCore.QRectF(self._bounds)

    def shape(self) -> QtGui.QPainterPath:  # noqa: N802 - Qt naming
        # 不参与 Qt 的 hit-test；避免 QGraphicsScene.itemAt() 命中本层导致逻辑误判
        return QtGui.QPainterPath()

    def paint(self, painter: QtGui.QPainter, option, widget=None) -> None:  # noqa: ANN001
        _ = widget

        scene_ref = self.scene()
        if scene_ref is None:
            return

        monitor = getattr(scene_ref, "_perf_monitor", None)
        inc = getattr(monitor, "inc", None) if monitor is not None else None
        accum = getattr(monitor, "accum_ns", None) if monitor is not None else None
        track = getattr(monitor, "track_slowest", None) if monitor is not None else None
        t_total0 = time.perf_counter_ns() if monitor is not None else 0
        if callable(inc):
            inc("items.paint.batched_edges.calls", 1)

        # 鸟瞰 blocks-only：边不绘制（可见性也会由 GraphScene 切换，但这里再做一道门禁更稳）
        if bool(getattr(scene_ref, "blocks_only_overview_mode", False)):
            if monitor is not None and callable(accum):
                dt_ns = int(time.perf_counter_ns() - int(t_total0))
                accum("items.paint.batched_edges.total", dt_ns)
            return

        lod_enabled = bool(getattr(settings, "GRAPH_LOD_ENABLED", True))
        scale_hint = float(painter.worldTransform().m11())
        edge_min_scale = float(getattr(settings, "GRAPH_LOD_EDGE_MIN_SCALE", 0.22))

        culled_mode = bool(getattr(scene_ref, "lod_edges_culled_mode", False))

        selected = set(getattr(self, "_selected_edge_ids", set()) or set())
        excluded = set(getattr(self, "_excluded_edge_ids", set()) or set())

        # exposedRect（局部坐标；本 item 固定在(0,0)，等同场景坐标）：
        # 用于大幅减少“每帧迭代所有边”的 Python 开销。
        exposed_rect = None
        if option is not None:
            exposed_rect = getattr(option, "exposedRect", None)
        if isinstance(exposed_rect, QtCore.QRectF):
            exposed = QtCore.QRectF(exposed_rect)
        else:
            exposed = QtCore.QRectF(self.boundingRect())
        if exposed.isEmpty():
            exposed = QtCore.QRectF(self.boundingRect())

        # 低倍率/裁剪模式：仅画选中（与原 fast preview edge 的“非选中直接 return”语义对齐）
        t_select0 = time.perf_counter_ns() if monitor is not None and callable(accum) else 0
        if culled_mode or (lod_enabled and (scale_hint < edge_min_scale)):
            edge_ids_to_draw: list[str] = []
            for eid in selected:
                if not eid:
                    continue
                if eid in excluded:
                    continue
                if eid not in self._paths:
                    continue
                edge_ids_to_draw.append(eid)
        else:
            # 视口裁剪：只枚举 exposedRect 覆盖的网格单元内的边，再按 bounds 二次过滤
            candidate_edge_ids: set[str] = set()
            for cell in self._cell_coords_for_rect(exposed):
                bucket = self._grid.get(cell)
                if isinstance(bucket, set) and bucket:
                    candidate_edge_ids.update(bucket)
            if not candidate_edge_ids:
                # 极端情况下 exposedRect 可能为空/异常，回退全量
                candidate_edge_ids = set(self._paths.keys())

            edge_ids_to_draw = []
            for eid in candidate_edge_ids:
                if not eid:
                    continue
                if eid in excluded:
                    continue
                path = self._paths.get(eid)
                if path is None:
                    continue
                bounds = self._edge_bounds.get(eid)
                if bounds is not None and (not bounds.isEmpty()) and (not bounds.intersects(exposed)):
                    continue
                edge_ids_to_draw.append(eid)

        if not edge_ids_to_draw:
            if monitor is not None and callable(accum):
                if t_select0:
                    accum("items.paint.batched_edges.select", int(time.perf_counter_ns() - int(t_select0)))
                dt_ns = int(time.perf_counter_ns() - int(t_total0))
                accum("items.paint.batched_edges.total", dt_ns)
            return
        if monitor is not None and callable(accum):
            if t_select0:
                accum("items.paint.batched_edges.select", int(time.perf_counter_ns() - int(t_select0)))
            if callable(inc):
                inc("items.paint.batched_edges.edges_drawn", int(len(edge_ids_to_draw)))

        painter.save()
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)

        base_color = QtGui.QColor(GraphPalette.EDGE_DATA)
        selected_color = QtGui.QColor(GraphPalette.EDGE_DATA_SELECTED)

        normal_pen = QtGui.QPen(base_color, 1)
        selected_pen = QtGui.QPen(selected_color, 3)

        dim_color = QtGui.QColor(base_color)
        dim_color.setAlphaF(0.3)
        dim_pen = QtGui.QPen(dim_color, 1)

        dim_selected_color = QtGui.QColor(selected_color)
        dim_selected_color.setAlphaF(0.3)
        dim_selected_pen = QtGui.QPen(dim_selected_color, 3)

        dim_active = bool(getattr(self, "_dim_active", False))
        focused_edges = set(getattr(self, "_dim_focused_edge_ids", set()) or set())

        # 批量绘制：按边切换 pen（低频），避免每条边都 new QPen
        t_draw0 = time.perf_counter_ns() if monitor is not None and callable(accum) else 0
        for edge_id in edge_ids_to_draw:
            path = self._paths.get(edge_id)
            if path is None:
                continue
            is_selected = edge_id in selected
            is_dimmed = bool(dim_active and (edge_id not in focused_edges))
            if is_selected and is_dimmed:
                painter.setPen(dim_selected_pen)
            elif is_selected:
                painter.setPen(selected_pen)
            elif is_dimmed:
                painter.setPen(dim_pen)
            else:
                painter.setPen(normal_pen)
            painter.drawPath(path)

        painter.restore()
        if monitor is not None and callable(accum):
            if t_draw0:
                accum("items.paint.batched_edges.draw", int(time.perf_counter_ns() - int(t_draw0)))
            dt_ns = int(time.perf_counter_ns() - int(t_total0))
            accum("items.paint.batched_edges.total", dt_ns)
            if callable(track):
                track(f"batched_edges:{len(edge_ids_to_draw)}", dt_ns)

    # --------------------------------------------------------------------- Public API (GraphScene calls)
    def has_edge(self, edge_id: str) -> bool:
        return str(edge_id or "") in self._endpoints

    def get_edge_ids_for_node(self, node_id: str) -> set[str]:
        nid = str(node_id or "")
        if not nid:
            return set()
        return set(self._edge_ids_by_node_id.get(nid, set()) or set())

    def add_edge(self, *, edge_id: str, src_node_id: str, dst_node_id: str) -> None:
        eid = str(edge_id or "")
        if not eid:
            return
        src = str(src_node_id or "")
        dst = str(dst_node_id or "")
        if not src or not dst:
            return
        if eid in self._endpoints:
            return
        self._endpoints[eid] = (src, dst)
        self._edge_ids_by_node_id.setdefault(src, set()).add(eid)
        self._edge_ids_by_node_id.setdefault(dst, set()).add(eid)
        self._recompute_edge_geometry(eid)
        self._ensure_bounds_contains(self._edge_bounds.get(eid))

    def remove_edge(self, edge_id: str) -> None:
        eid = str(edge_id or "")
        if not eid:
            return

        old_bounds = self._edge_bounds.get(eid)
        if old_bounds is not None and (not old_bounds.isEmpty()):
            # 删除前先失效旧区域，避免残影
            self.update(old_bounds)

        endpoints = self._endpoints.pop(eid, None)
        if endpoints is not None:
            src, dst = endpoints
            src_set = self._edge_ids_by_node_id.get(src)
            if isinstance(src_set, set):
                src_set.discard(eid)
                if not src_set:
                    del self._edge_ids_by_node_id[src]
            dst_set = self._edge_ids_by_node_id.get(dst)
            if isinstance(dst_set, set):
                dst_set.discard(eid)
                if not dst_set:
                    del self._edge_ids_by_node_id[dst]

        self._curves.pop(eid, None)
        self._paths.pop(eid, None)
        self._edge_bounds.pop(eid, None)
        self._selected_edge_ids.discard(eid)
        self._dim_focused_edge_ids.discard(eid)
        self._excluded_edge_ids.discard(eid)

        # grid index cleanup
        old_cells = self._edge_cells.pop(eid, None)
        if isinstance(old_cells, set):
            for cell in old_cells:
                bucket = self._grid.get(cell)
                if isinstance(bucket, set):
                    bucket.discard(eid)
                    if not bucket:
                        del self._grid[cell]

    def set_edge_excluded(self, edge_id: str, excluded: bool) -> None:
        eid = str(edge_id or "")
        if not eid:
            return
        if excluded:
            if eid in self._excluded_edge_ids:
                return
            self._excluded_edge_ids.add(eid)
        else:
            if eid not in self._excluded_edge_ids:
                return
            self._excluded_edge_ids.discard(eid)
        bounds = self._edge_bounds.get(eid)
        if bounds is not None and (not bounds.isEmpty()):
            self.update(bounds)

    def clear_selected_edges(self) -> None:
        if not self._selected_edge_ids:
            return
        rect = self._union_bounds_for_edges(self._selected_edge_ids)
        self._selected_edge_ids.clear()
        if rect is not None:
            self.update(rect)

    def set_selected_edge_ids(self, edge_ids: Iterable[str]) -> None:
        new_set = {str(eid) for eid in (edge_ids or []) if str(eid or "").strip()}
        old_set = set(self._selected_edge_ids)
        if new_set == old_set:
            return
        changed = (new_set - old_set) | (old_set - new_set)
        rect = self._union_bounds_for_edges(changed)
        self._selected_edge_ids = new_set
        if rect is not None:
            self.update(rect)

    def set_dim_state(self, *, active: bool, focused_edge_ids: Iterable[str]) -> None:
        new_active = bool(active)
        new_focused = {str(eid) for eid in (focused_edge_ids or []) if str(eid or "").strip()}
        old_active = bool(self._dim_active)
        old_focused = set(self._dim_focused_edge_ids)
        if new_active == old_active and new_focused == old_focused:
            return
        self._dim_active = new_active
        self._dim_focused_edge_ids = new_focused

        # dim 开关变化会影响“全部边”的 alpha，因此必须全量重绘（但仅重绘 bounds 范围即可）。
        if new_active != old_active:
            self.update()
            return

        # dim 集合变化：仅对差集做局部重绘即可
        changed = (new_focused - old_focused) | (old_focused - new_focused)
        rect = self._union_bounds_for_edges(changed)
        if rect is None:
            return
        self.update(rect)

    def clear_dim_state(self) -> None:
        if not bool(self._dim_active):
            return
        self._dim_active = False
        self._dim_focused_edge_ids.clear()
        self.update()

    def update_edges_for_node_ids(self, node_ids: Iterable[str]) -> None:
        """节点移动/重布局后，增量更新相关边的缓存几何并局部重绘。"""
        unique = {str(nid) for nid in (node_ids or []) if str(nid or "").strip()}
        if not unique:
            return

        edge_ids: set[str] = set()
        for nid in unique:
            edge_ids.update(self._edge_ids_by_node_id.get(nid, set()) or set())
        if not edge_ids:
            return

        # 先收集旧 bounds，用于失效旧路径区域（避免残影）
        old_bounds = [self._edge_bounds.get(eid) for eid in edge_ids]

        # 更新几何缓存
        for eid in edge_ids:
            self._recompute_edge_geometry(eid)

        # union old+new bounds
        rect = QtCore.QRectF()
        have_rect = False
        for r in old_bounds:
            if r is None or r.isEmpty():
                continue
            rect = r if not have_rect else rect.united(r)
            have_rect = True
        for eid in edge_ids:
            r = self._edge_bounds.get(eid)
            if r is None or r.isEmpty():
                continue
            rect = r if not have_rect else rect.united(r)
            have_rect = True

        if have_rect:
            self._ensure_bounds_contains(rect)
            self.update(rect)

    def pick_edge_id_at(
        self,
        scene_pos: QtCore.QPointF,
        *,
        scale_hint: float,
    ) -> Optional[str]:
        """在 scene_pos 附近命中一条边，返回 edge_id（只读预览点击用）。"""
        if not self._paths:
            return None

        lod_enabled = bool(getattr(settings, "GRAPH_LOD_ENABLED", True))
        hit_min_scale = float(getattr(settings, "GRAPH_LOD_EDGE_HITTEST_MIN_SCALE", 0.28))
        if lod_enabled and float(scale_hint) < hit_min_scale:
            # 与 EdgeGraphicsItem/FastPreviewEdgeGraphicsItem 对齐：低倍率下边不可点
            return None

        # 仅允许命中当前“可见”的边：
        # - 裁剪/低倍率：只命中 selected（避免从不可见边里“捞”）
        scene_ref = self.scene()
        culled_mode = bool(getattr(scene_ref, "lod_edges_culled_mode", False)) if scene_ref is not None else False
        edge_min_scale = float(getattr(settings, "GRAPH_LOD_EDGE_MIN_SCALE", 0.22))
        low_detail_edges_only = bool(culled_mode or (lod_enabled and float(scale_hint) < edge_min_scale))

        allowed_edges = set(self._paths.keys())
        allowed_edges -= set(getattr(self, "_excluded_edge_ids", set()) or set())
        if low_detail_edges_only:
            allowed_edges &= set(getattr(self, "_selected_edge_ids", set()) or set())
        if not allowed_edges:
            return None

        cell_size = float(self._cell_size) if float(self._cell_size) > 1.0 else 600.0
        cx = int(float(scene_pos.x()) // cell_size)
        cy = int(float(scene_pos.y()) // cell_size)

        candidates: set[str] = set()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                bucket = self._grid.get((cx + dx, cy + dy))
                if bucket:
                    candidates.update(bucket)

        candidates &= allowed_edges
        if not candidates:
            return None

        hit_width = float(getattr(settings, "GRAPH_FAST_PREVIEW_BATCHED_EDGE_PICK_STROKE_WIDTH", 6.0))
        hit_width = max(2.0, min(24.0, hit_width))

        # 先用 bounds 粗筛
        margin = hit_width * 1.2
        best_edge_id: str | None = None
        best_dist2: float | None = None

        for eid in candidates:
            bounds = self._edge_bounds.get(eid)
            if bounds is None or bounds.isEmpty():
                continue
            if not bounds.adjusted(-margin, -margin, margin, margin).contains(scene_pos):
                continue

            path = self._paths.get(eid)
            curve = self._curves.get(eid)
            if path is None or curve is None:
                continue

            stroker = QtGui.QPainterPathStroker()
            stroker.setWidth(hit_width)
            stroker.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
            stroker.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
            hit_shape = stroker.createStroke(path)
            if not hit_shape.contains(scene_pos):
                continue

            # 距离估算：采样 12 段，取最小点距
            px = float(scene_pos.x())
            py = float(scene_pos.y())
            min_d2 = 1e30
            steps = 12
            for i in range(steps + 1):
                t = float(i) / float(steps)
                pt = _cubic_point(curve, t)
                dx = float(pt.x()) - px
                dy = float(pt.y()) - py
                d2 = dx * dx + dy * dy
                if d2 < min_d2:
                    min_d2 = d2
            if best_dist2 is None or min_d2 < best_dist2:
                best_dist2 = min_d2
                best_edge_id = eid

        return best_edge_id

    # --------------------------------------------------------------------- Internal helpers
    def _union_bounds_for_edges(self, edge_ids: Iterable[str]) -> Optional[QtCore.QRectF]:
        rect = QtCore.QRectF()
        have = False
        for eid in edge_ids or []:
            r = self._edge_bounds.get(str(eid))
            if r is None or r.isEmpty():
                continue
            rect = r if not have else rect.united(r)
            have = True
        return rect if have else None

    def _ensure_bounds_contains(self, rect: QtCore.QRectF | None) -> None:
        if rect is None or rect.isEmpty():
            return
        if self._bounds.isNull() or self._bounds.isEmpty():
            self.prepareGeometryChange()
            self._bounds = QtCore.QRectF(rect)
            return
        if self._bounds.contains(rect):
            return
        self.prepareGeometryChange()
        self._bounds = self._bounds.united(rect)

    def _cell_coords_for_rect(self, rect: QtCore.QRectF) -> set[tuple[int, int]]:
        if rect.isEmpty():
            return set()
        cell_size = float(self._cell_size) if float(self._cell_size) > 1.0 else 600.0
        min_x = int(float(rect.left()) // cell_size)
        max_x = int(float(rect.right()) // cell_size)
        min_y = int(float(rect.top()) // cell_size)
        max_y = int(float(rect.bottom()) // cell_size)
        coords: set[tuple[int, int]] = set()
        for cx in range(min_x, max_x + 1):
            for cy in range(min_y, max_y + 1):
                coords.add((int(cx), int(cy)))
        return coords

    def _update_grid_for_edge(self, edge_id: str, new_bounds: QtCore.QRectF) -> None:
        eid = str(edge_id or "")
        if not eid:
            return
        old_cells = self._edge_cells.get(eid, set()) or set()
        new_cells = self._cell_coords_for_rect(new_bounds)
        if old_cells == new_cells:
            return

        # remove old
        for cell in old_cells - new_cells:
            bucket = self._grid.get(cell)
            if isinstance(bucket, set):
                bucket.discard(eid)
                if not bucket:
                    del self._grid[cell]

        # add new
        for cell in new_cells - old_cells:
            self._grid.setdefault(cell, set()).add(eid)

        self._edge_cells[eid] = set(new_cells)

    def _compute_curve_for_edge(self, edge_id: str) -> Optional[_CubicCurve]:
        endpoints = self._endpoints.get(str(edge_id or ""))
        if endpoints is None:
            return None
        src_node_id, dst_node_id = endpoints
        scene_ref = self.scene()
        if scene_ref is None:
            return None
        node_items = getattr(scene_ref, "node_items", {}) or {}
        src_item = node_items.get(src_node_id)
        dst_item = node_items.get(dst_node_id)
        if src_item is None or dst_item is None:
            return None

        src_rect = src_item.sceneBoundingRect()
        dst_rect = dst_item.sceneBoundingRect()
        start = QtCore.QPointF(float(src_rect.right()), float(src_rect.center().y()))
        end = QtCore.QPointF(float(dst_rect.left()), float(dst_rect.center().y()))
        dx = abs(float(end.x() - start.x())) * 0.5
        c1 = QtCore.QPointF(float(start.x() + dx), float(start.y()))
        c2 = QtCore.QPointF(float(end.x() - dx), float(end.y()))
        return _CubicCurve(p0=start, p1=c1, p2=c2, p3=end)

    def _recompute_edge_geometry(self, edge_id: str) -> None:
        eid = str(edge_id or "")
        if not eid:
            return
        curve = self._compute_curve_for_edge(eid)
        if curve is None:
            self._curves.pop(eid, None)
            self._paths.pop(eid, None)
            self._edge_bounds.pop(eid, None)
            self._update_grid_for_edge(eid, QtCore.QRectF())
            return

        path = QtGui.QPainterPath(curve.p0)
        path.cubicTo(curve.p1, curve.p2, curve.p3)
        bounds = path.boundingRect()

        # 给 stroke 留足 margin，避免 update/bounds 过窄导致残影
        margin = float(getattr(settings, "GRAPH_FAST_PREVIEW_BATCHED_EDGE_BOUNDS_MARGIN", 8.0))
        margin = max(2.0, min(32.0, margin))
        bounds = bounds.adjusted(-margin, -margin, margin, margin)

        self._curves[eid] = curve
        self._paths[eid] = path
        self._edge_bounds[eid] = bounds
        self._update_grid_for_edge(eid, bounds)

