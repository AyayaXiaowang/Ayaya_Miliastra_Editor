"""场景叠加渲染 Mixin

提供网格背景、基本块、Y调试Tooltip、链路高亮等叠加渲染能力。
假设宿主场景提供: model, node_items, edge_items 等属性。
"""

from __future__ import annotations

import time

from PyQt6 import QtCore, QtGui, QtWidgets
from typing import Optional, Dict, List
from app.ui.overlays.text_layout import GridOccupancyIndex
from app.ui.graph.graph_palette import GraphPalette
from app.ui.foundation import fonts as ui_fonts


class SceneOverlayMixin:
    """场景叠加渲染 Mixin
    
    要求宿主类提供以下属性:
    - model: GraphModel
    - node_items: dict[str, NodeGraphicsItem]
    - edge_items: dict[str, EdgeGraphicsItem]
    - grid_size: int
    """
    
    def drawBackground(self, painter: QtGui.QPainter, rect: QtCore.QRectF) -> None:
        """绘制网格背景和基本块矩形"""
        from app.ui.foundation.theme_manager import ThemeManager
        from engine.configs.settings import settings

        monitor = getattr(self, "_perf_monitor", None)
        t_total0 = time.perf_counter() if monitor is not None else 0.0

        blocks_only = bool(getattr(self, "blocks_only_overview_mode", False))
        view_panning = bool(getattr(self, "_view_panning", False))
        
        # 绘制网格背景
        # 低倍率下仍然保留画布背景（底色+网格），但会自动放大网格间距，
        # 避免因为“网格线过密”造成噪音与绘制开销（鸟瞰模式下阈值更激进）。
        grid_enabled = bool(getattr(settings, "GRAPH_GRID_ENABLED", True))
        # 极致性能：平移期间不绘制网格线（只保留纯底色）。
        # 说明：平移时视图禁用 CacheBackground，会导致背景每帧重绘；网格线又是高频 drawLine 调用，
        # 因此 panning 期间跳过网格线可显著降低卡顿。
        if (not grid_enabled) or view_panning:
            t0 = time.perf_counter() if monitor is not None else 0.0
            painter.fillRect(rect, QtGui.QColor(GraphPalette.CANVAS_BG))
            if monitor is not None:
                monitor.record_ms("scene.drawBackground.grid", (time.perf_counter() - float(t0)) * 1000.0)
        else:
            grid_size = int(getattr(self, "grid_size", 50) or 50)
            if grid_size <= 0:
                grid_size = 50
            effective_grid_size = grid_size
            import math

            scale_hint = float(painter.worldTransform().m11())
            min_grid_px = float(
                getattr(
                    settings,
                    "GRAPH_BLOCK_OVERVIEW_GRID_MIN_PX" if blocks_only else "GRAPH_GRID_MIN_PX",
                    24.0 if blocks_only else 12.0,
                )
            )
            if scale_hint > 0.0 and min_grid_px > 0.0:
                spacing_px = float(grid_size) * float(scale_hint)
                if spacing_px < float(min_grid_px):
                    factor = int(math.ceil(float(min_grid_px) / float(max(1e-6, spacing_px))))
                    if factor > 1:
                        effective_grid_size = int(grid_size * factor)

            if monitor is not None:
                t0 = time.perf_counter()
                ThemeManager.draw_grid_background(painter, rect, int(effective_grid_size))
                monitor.record_ms("scene.drawBackground.grid", (time.perf_counter() - float(t0)) * 1000.0)
            else:
                ThemeManager.draw_grid_background(painter, rect, int(effective_grid_size))
        
        # 绘制基本块矩形(如果启用)
        # 鸟瞰模式下即使 SHOW_BASIC_BLOCKS 关闭，也应绘制 basic blocks（否则画布会空白）。
        show_blocks = bool(settings.SHOW_BASIC_BLOCKS) or bool(blocks_only)
        if show_blocks and self.model and self.model.basic_blocks:
            t_blocks0 = time.perf_counter() if monitor is not None else 0.0
            painter.save()

            # 遍历所有基本块
            for block_index, block in enumerate(self.model.basic_blocks):
                if not block.nodes:
                    continue

                # 计算基本块的边界矩形
                block_rect = self._calculate_block_rect(block, block_index=int(block_index))

                if block_rect and block_rect.intersects(rect):
                    # 设置颜色和透明度
                    color = QtGui.QColor(block.color)
                    color.setAlphaF(settings.BASIC_BLOCK_ALPHA)

                    # 绘制半透明矩形
                    painter.setBrush(QtGui.QBrush(color))
                    painter.setPen(QtCore.Qt.PenStyle.NoPen)  # 无边框
                    painter.drawRoundedRect(block_rect, 8, 8)  # 圆角8px

                    # 注意:标签在drawForeground中绘制,确保不被节点遮挡

            painter.restore()
            if monitor is not None:
                monitor.record_ms(
                    "scene.drawBackground.basic_blocks",
                    (time.perf_counter() - float(t_blocks0)) * 1000.0,
                )

        if monitor is not None:
            monitor.record_ms(
                "scene.drawBackground.total",
                (time.perf_counter() - float(t_total0)) * 1000.0,
            )
    
    def drawForeground(self, painter: QtGui.QPainter, rect: QtCore.QRectF) -> None:
        """绘制前景层(基本块标签)"""
        from engine.configs.settings import settings

        monitor = getattr(self, "_perf_monitor", None)
        t_total0 = time.perf_counter() if monitor is not None else 0.0

        lod_enabled = bool(getattr(settings, "GRAPH_LOD_ENABLED", True))
        details_min_scale = float(getattr(settings, "GRAPH_LOD_NODE_DETAILS_MIN_SCALE", 0.55))
        scale_hint = float(painter.worldTransform().m11())
        low_detail = bool(lod_enabled and (scale_hint < details_min_scale))
        blocks_only = bool(getattr(self, "blocks_only_overview_mode", False))
        view_panning = bool(getattr(self, "_view_panning", False))
        if view_panning and bool(getattr(settings, "GRAPH_PAN_HIDE_ICONS_ENABLED", True)):
            # 平移期间：视为低细节模式，隐藏 YDebug 图标/链路徽标等调试叠层以提升流畅度。
            low_detail = True
        if blocks_only:
            # 鸟瞰只看块颜色：视为低细节模式（隐藏Y调试图标/链路徽标等噪音）
            low_detail = True
        
        # 绘制基本块编号标签(在前景层,确保不被节点遮挡)
        # 鸟瞰只看块颜色：不绘制块编号标签，避免在低倍率视角产生文本噪音。
        if (not blocks_only) and settings.SHOW_BASIC_BLOCKS and self.model and self.model.basic_blocks:
            t0 = time.perf_counter() if monitor is not None else 0.0
            painter.save()
            
            # 遍历所有基本块
            for block_index, block in enumerate(self.model.basic_blocks):
                if not block.nodes:
                    continue
                
                # 计算基本块的边界矩形
                block_rect = self._calculate_block_rect(block, block_index=int(block_index))
                
                if block_rect and block_rect.intersects(rect):
                    # 获取块颜色
                    color = QtGui.QColor(block.color)
                    
                    # 绘制基本块编号标签
                    self._draw_block_label(painter, block_rect, block_index + 1, color)
            
            painter.restore()
            if monitor is not None:
                monitor.record_ms(
                    "scene.drawForeground.block_labels",
                    (time.perf_counter() - float(t0)) * 1000.0,
                )

        # 轻量:布局Y调试图标(节点右上角"!"),点击弹出可复制Tooltip
        #
        # LOD：低倍率缩放时仅保留节点标题栏，不绘制调试图标与徽标，避免在超大图鸟瞰时造成噪音与额外开销。
        if (not low_detail) and getattr(settings, "SHOW_LAYOUT_Y_DEBUG", False) and self.model:
            debug_map = getattr(self.model, "_layout_y_debug_info", {}) or {}
            if not hasattr(self, "_ydebug_icon_rects"):
                self._ydebug_icon_rects = {}
            # 每帧重算：避免 debug_map/可见范围变化后命中矩形残留导致误判
            self._ydebug_icon_rects.clear()
            if debug_map and self.node_items:
                t0 = time.perf_counter() if monitor is not None else 0.0
                painter.save()
                visible_rect = rect.adjusted(-60.0, -60.0, 60.0, 60.0)
                icon_size = 28.0
                icon_margin = 6.0

                # 先收集可见图标，再分两趟绘制（减少 setPen/setBrush/setFont 的状态切换开销）
                icon_rects: List[QtCore.QRectF] = []
                icon_map = self._ydebug_icon_rects
                node_items = self.node_items
                for node_id in debug_map.keys():
                    node_item = node_items.get(node_id)
                    if node_item is None:
                        continue
                    node_rect = node_item.sceneBoundingRect()
                    if not node_rect.intersects(visible_rect):
                        continue
                    icon_rect = QtCore.QRectF(
                        float(node_rect.right()) - icon_margin - icon_size,
                        float(node_rect.top()) + icon_margin,
                        icon_size,
                        icon_size,
                    )
                    icon_rects.append(icon_rect)
                    icon_map[str(node_id)] = icon_rect

                if icon_rects:
                    # 背景圆：一次性设置笔刷/画笔后批量绘制
                    painter.setPen(QtCore.Qt.PenStyle.NoPen)
                    painter.setBrush(QtGui.QBrush(QtGui.QColor(GraphPalette.BADGE_ACCENT)))
                    for r in icon_rects:
                        painter.drawEllipse(r)

                    # "!"：一次性设置字体/画笔后批量绘制（避免每个图标都 setFont）
                    painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                    painter.setPen(QtGui.QPen(QtGui.QColor(GraphPalette.TEXT_BRIGHT)))
                    font = painter.font()
                    font.setBold(True)
                    font.setPointSizeF(14.0)
                    painter.setFont(font)
                    for r in icon_rects:
                        painter.drawText(r, QtCore.Qt.AlignmentFlag.AlignCenter, "!")
                painter.restore()
                if monitor is not None:
                    monitor.record_ms(
                        "scene.drawForeground.ydebug_icons",
                        (time.perf_counter() - float(t0)) * 1000.0,
                    )
        else:
            # 未绘制 YDebug 图标时确保命中映射清空，避免点击误判
            if hasattr(self, "_ydebug_icon_rects"):
                self._ydebug_icon_rects.clear()
        # 链路序号徽标(当前高亮链路时显示在节点上方,醒目且有描边)
        if (not low_detail) and getattr(settings, "SHOW_LAYOUT_Y_DEBUG", False):
            if hasattr(self, "_active_chain_node_positions") and self._active_chain_node_positions:
                t0 = time.perf_counter() if monitor is not None else 0.0
                painter.save()
                for node_id, order_index in self._active_chain_node_positions.items():
                    node_item = self.node_items.get(node_id)
                    if not node_item:
                        continue
                    node_rect = node_item.sceneBoundingRect()
                    # 徽标参数
                    badge_size = 24.0
                    badge_margin = 6.0
                    badge_rect = QtCore.QRectF(
                        float(node_rect.left()) + badge_margin,
                        float(node_rect.top()) + badge_margin,
                        badge_size,
                        badge_size
                    )
                    # 背景(圆形) + 边框描边
                    painter.setPen(QtGui.QPen(QtGui.QColor(GraphPalette.BADGE_OUTLINE), 3))
                    painter.setBrush(QtGui.QBrush(QtGui.QColor(GraphPalette.BADGE_FILL)))
                    painter.drawEllipse(badge_rect)
                    # 文字(黑色加粗,居中)
                    font = painter.font()
                    font.setBold(True)
                    font.setPointSizeF(12.0)
                    painter.setFont(font)
                    painter.setPen(QtGui.QPen(QtGui.QColor(GraphPalette.BADGE_OUTLINE)))
                    painter.drawText(badge_rect, QtCore.Qt.AlignmentFlag.AlignCenter, str(int(order_index)))
                painter.restore()
                if monitor is not None:
                    monitor.record_ms(
                        "scene.drawForeground.chain_badges",
                        (time.perf_counter() - float(t0)) * 1000.0,
                    )
            # 全链路高亮:为相关节点绘制彩色描边
            if hasattr(self, "_all_chain_node_color_map") and self._all_chain_node_color_map:
                t0 = time.perf_counter() if monitor is not None else 0.0
                painter.save()
                for node_id, color in self._all_chain_node_color_map.items():
                    node_item = self.node_items.get(node_id)
                    if not node_item:
                        continue
                    node_rect = node_item.sceneBoundingRect()
                    pen = QtGui.QPen(color)
                    pen.setWidth(4)
                    painter.setPen(pen)
                    painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                    painter.drawRoundedRect(node_rect.adjusted(-2, -2, 2, 2), 12, 12)
                painter.restore()
                if monitor is not None:
                    monitor.record_ms(
                        "scene.drawForeground.chain_outlines",
                        (time.perf_counter() - float(t0)) * 1000.0,
                    )
                # 在“高亮全部”模式下，为每个节点绘制链编号徽标（链ID），与描边颜色一致
                if hasattr(self, "_all_chain_node_chain_ids") and self._all_chain_node_chain_ids:
                    t0 = time.perf_counter() if monitor is not None else 0.0
                    painter.save()
                    for node_id, chain_id in self._all_chain_node_chain_ids.items():
                        node_item = self.node_items.get(node_id)
                        if not node_item:
                            continue
                        node_rect = node_item.sceneBoundingRect()
                        badge_size = 22.0
                        badge_margin = 6.0
                        badge_rect = QtCore.QRectF(
                            float(node_rect.left()) + badge_margin,
                            float(node_rect.top()) + badge_margin,
                            badge_size,
                            badge_size
                        )
                        badge_color = self._all_chain_node_color_map.get(node_id, QtGui.QColor(GraphPalette.BADGE_FILL))
                        painter.setPen(QtGui.QPen(QtGui.QColor(GraphPalette.BADGE_OUTLINE), 3))
                        painter.setBrush(QtGui.QBrush(badge_color))
                        painter.drawEllipse(badge_rect)
                        font = painter.font()
                        font.setBold(True)
                        font.setPointSizeF(11.0)
                        painter.setFont(font)
                        painter.setPen(QtGui.QPen(QtGui.QColor(GraphPalette.BADGE_OUTLINE)))
                        painter.drawText(badge_rect, QtCore.Qt.AlignmentFlag.AlignCenter, str(int(chain_id)))
                    painter.restore()
                    if monitor is not None:
                        monitor.record_ms(
                            "scene.drawForeground.chain_id_badges",
                            (time.perf_counter() - float(t0)) * 1000.0,
                        )

        if monitor is not None:
            monitor.record_ms(
                "scene.drawForeground.total",
                (time.perf_counter() - float(t_total0)) * 1000.0,
            )

    def _get_ydebug_icon_rect_for_item(self, node_item: 'NodeGraphicsItem', icon_size: float = 28.0, icon_margin: float = 6.0) -> QtCore.QRectF:
        """计算给定节点的Y调试图标的矩形(右上角)"""
        node_rect = node_item.sceneBoundingRect()
        return QtCore.QRectF(
            float(node_rect.right()) - float(icon_margin) - float(icon_size),
            float(node_rect.top()) + float(icon_margin),
            float(icon_size),
            float(icon_size)
        )

    def _draw_block_label(self, painter: QtGui.QPainter, block_rect: QtCore.QRectF, 
                          block_number: int, block_color: QtGui.QColor) -> None:
        """在基本块矩形上绘制编号标签
        
        Args:
            painter: QPainter对象
            block_rect: 基本块的边界矩形
            block_number: 基本块编号(从1开始)
            block_color: 基本块颜色
        """
        # 标签尺寸
        label_size = 40
        padding = 8
        margin = 10
        
        # 标签位置(左上角)
        label_x = block_rect.left() + margin
        label_y = block_rect.top() + margin
        label_rect = QtCore.QRectF(label_x, label_y, label_size, label_size)
        
        # 使用块颜色的不透明版本作为标签背景
        bg_color = QtGui.QColor(block_color)
        bg_color.setAlphaF(0.9)  # 90%不透明
        
        # 绘制标签背景(圆角矩形)
        painter.setBrush(QtGui.QBrush(bg_color))
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.drawRoundedRect(label_rect, 6, 6)
        
        # 计算文字颜色(根据背景亮度选择黑或白)
        # 使用亮度公式: 0.299*R + 0.587*G + 0.114*B
        brightness = (0.299 * bg_color.red() + 
                     0.587 * bg_color.green() + 
                     0.114 * bg_color.blue())
        text_color = QtGui.QColor(QtCore.Qt.GlobalColor.white) if brightness < 128 else QtGui.QColor(QtCore.Qt.GlobalColor.black)
        
        # 绘制编号文字
        painter.setPen(QtGui.QPen(text_color))
        font = painter.font()
        font.setPointSize(14)
        font.setBold(True)
        painter.setFont(font)
        
        painter.drawText(label_rect, QtCore.Qt.AlignmentFlag.AlignCenter, str(block_number))
    
    def _ensure_basic_block_rect_cache(self) -> dict[int, QtCore.QRectF]:
        cache = getattr(self, "_basic_block_rect_cache", None)
        if not isinstance(cache, dict):
            cache = {}
            self._basic_block_rect_cache = cache
        return cache
    
    def _ensure_basic_block_rect_dirty_indices(self) -> set[int]:
        dirty = getattr(self, "_basic_block_rect_dirty_indices", None)
        if not isinstance(dirty, set):
            dirty = set()
            self._basic_block_rect_dirty_indices = dirty
        return dirty

    def _ensure_basic_block_node_to_indices(self) -> dict[str, list[int]]:
        mapping = getattr(self, "_basic_block_node_to_indices", None)
        token = getattr(self, "_basic_block_node_to_indices_token", None)
        model = getattr(self, "model", None)
        blocks = getattr(model, "basic_blocks", None) if model is not None else None
        current_token = (id(model), id(blocks))
        if isinstance(mapping, dict) and token == current_token:
            return mapping

        new_mapping: dict[str, list[int]] = {}
        if isinstance(blocks, list):
            for idx, block in enumerate(blocks):
                node_ids = getattr(block, "nodes", None) or []
                for node_id in node_ids:
                    node_id_text = str(node_id or "").strip()
                    if not node_id_text:
                        continue
                    new_mapping.setdefault(node_id_text, []).append(int(idx))

        # basic_blocks 变更：映射与 rect cache 都需要重建
        self._basic_block_node_to_indices = new_mapping
        self._basic_block_node_to_indices_token = current_token
        self.invalidate_basic_block_rect_cache()
        return new_mapping

    def invalidate_basic_block_rect_cache(self) -> None:
        cache = getattr(self, "_basic_block_rect_cache", None)
        if isinstance(cache, dict):
            cache.clear()
        dirty = getattr(self, "_basic_block_rect_dirty_indices", None)
        if isinstance(dirty, set):
            dirty.clear()

    def mark_basic_block_rect_dirty_for_node(self, node_id: str) -> None:
        """标记与指定节点相关的 basic block 矩形为 dirty，下一次绘制时会重算（可收缩）。"""
        node_id_text = str(node_id or "").strip()
        if not node_id_text:
            return

        node_to_indices = self._ensure_basic_block_node_to_indices()
        indices = node_to_indices.get(node_id_text) or []
        if not indices:
            return

        dirty = self._ensure_basic_block_rect_dirty_indices()
        for idx in indices:
            dirty.add(int(idx))

    def note_basic_block_node_moved(self, node_id: str, node_pos: tuple[float, float]) -> None:
        """节点移动时增量更新 basic block 的缓存矩形（仅扩张，不收缩）。

        用途：
        - 拖拽节点过程中保持 basic block 背景跟随（避免“看起来不更新”）；
        - 精确边界（包含可变高度节点）在拖拽结束后通过 dirty 重算收敛。
        """
        node_id_text = str(node_id or "").strip()
        if not node_id_text:
            return
        
        cache = self._ensure_basic_block_rect_cache()

        node_to_indices = self._ensure_basic_block_node_to_indices()
        indices = node_to_indices.get(node_id_text) or []
        if not indices:
            return

        margin = 25.0
        node_outer: QtCore.QRectF | None = None

        node_items = getattr(self, "node_items", None)
        node_item = node_items.get(node_id_text) if isinstance(node_items, dict) else None
        if node_item is not None:
            rect = node_item.sceneBoundingRect()
            children_rect = node_item.childrenBoundingRect()
            if not children_rect.isEmpty():
                rect = rect.united(node_item.mapRectToScene(children_rect))
            node_outer = rect.adjusted(-margin, -margin, margin, margin)
        else:
            # fallback：仅用 model pos 的近似尺寸
            if not isinstance(node_pos, (tuple, list)) or len(node_pos) < 2:
                return
            from engine.configs.settings import settings

            approx_w = float(getattr(settings, "GRAPH_MINIMAP_APPROX_NODE_WIDTH", 280.0))
            approx_h = float(getattr(settings, "GRAPH_MINIMAP_APPROX_NODE_HEIGHT", 140.0))
            x = float(node_pos[0])
            y = float(node_pos[1])
            node_outer = QtCore.QRectF(
                x - margin,
                y - margin,
                approx_w + margin * 2.0,
                approx_h + margin * 2.0,
            )

        if node_outer is None or node_outer.isEmpty():
            return
        for idx in indices:
            idx_int = int(idx)
            existing = cache.get(idx_int)
            if isinstance(existing, QtCore.QRectF):
                cache[idx_int] = existing.united(node_outer)
            else:
                cache[idx_int] = QtCore.QRectF(node_outer)

    def _calculate_block_rect(self, block, *, block_index: int | None = None) -> Optional[QtCore.QRectF]:
        """计算基本块的边界矩形
        
        Args:
            block: BasicBlock对象
            
        Returns:
            包含所有节点的矩形,留出边距(20-30px)
        """
        if not block.nodes:
            return None

        cache = self._ensure_basic_block_rect_cache()
        dirty = self._ensure_basic_block_rect_dirty_indices()
        if block_index is not None:
            cached = cache.get(int(block_index))
            if isinstance(cached, QtCore.QRectF) and int(block_index) not in dirty:
                return cached

        node_items = getattr(self, "node_items", None)
        node_items_dict = node_items if isinstance(node_items, dict) else {}

        from engine.configs.settings import settings

        model = getattr(self, "model", None)
        model_nodes = getattr(model, "nodes", None) if model is not None else None
        approx_w = float(getattr(settings, "GRAPH_MINIMAP_APPROX_NODE_WIDTH", 280.0))
        approx_h = float(getattr(settings, "GRAPH_MINIMAP_APPROX_NODE_HEIGHT", 140.0))
        margin = 25.0

        union_rect: QtCore.QRectF | None = None
        for node_id in block.nodes:
            node_id_text = str(node_id or "").strip()
            if not node_id_text:
                continue

            node_item = node_items_dict.get(node_id_text)
            if node_item is not None:
                rect = node_item.sceneBoundingRect()
                children_rect = node_item.childrenBoundingRect()
                if not children_rect.isEmpty():
                    rect = rect.united(node_item.mapRectToScene(children_rect))
            else:
                # fallback：节点图元缺失时用 model pos 做近似
                if not isinstance(model_nodes, dict):
                    continue
                node_model = model_nodes.get(node_id_text)
                pos = getattr(node_model, "pos", None) if node_model is not None else None
                if not isinstance(pos, (list, tuple)) or len(pos) < 2:
                    continue
                rect = QtCore.QRectF(float(pos[0]), float(pos[1]), float(approx_w), float(approx_h))

            if union_rect is None:
                union_rect = QtCore.QRectF(rect)
            else:
                union_rect = union_rect.united(rect)

        if union_rect is None or union_rect.isEmpty():
            return None

        rect = union_rect.adjusted(-margin, -margin, margin, margin)
        if block_index is not None:
            cache[int(block_index)] = rect
            dirty.discard(int(block_index))
        return rect

    def _draw_text_with_stroke(
        self,
        painter: QtGui.QPainter,
        x: float,
        y_center: float,
        text: str,
        font: QtGui.QFont | None = None,
        fill_color: QtGui.QColor | None = None,
        stroke_color: QtGui.QColor | None = None,
        stroke_width: int = 3
    ) -> None:
        """在场景中绘制描边文本(用于调试叠加)。
        
        文本基线按字体上升线进行微调,使其在y_center附近视觉居中。
        """
        if not text:
            return
        use_font = font if font is not None else ui_fonts.ui_font(10, bold=True)
        use_fill = fill_color if fill_color is not None else QtGui.QColor(QtCore.Qt.GlobalColor.white)
        use_stroke = stroke_color if stroke_color is not None else QtGui.QColor(0, 0, 0, 220)

        # 懒加载文本路径缓存(降低 addText 频率)
        if not hasattr(self, "_text_path_cache"):
            self._text_path_cache = {}
            self._font_ascent_cache = {}
        font_key = (use_font.family(), use_font.pointSize(), use_font.weight(), use_font.italic())
        cache_key = (font_key, text)
        base_path = self._text_path_cache.get(cache_key)
        if base_path is None:
            base_path = QtGui.QPainterPath()
            # 以原点为基准构建路径(后续平移)
            base_path.addText(QtCore.QPointF(0.0, 0.0), use_font, text)
            self._text_path_cache[cache_key] = base_path
        ascent = self._font_ascent_cache.get(font_key)
        if ascent is None:
            fm = QtGui.QFontMetricsF(use_font)
            ascent = float(fm.ascent())
            self._font_ascent_cache[font_key] = ascent
        baseline_y = y_center + ascent * 0.45

        painter.save()
        path = QtGui.QPainterPath(base_path)
        path.translate(float(x), float(baseline_y))
        pen = QtGui.QPen(use_stroke)
        pen.setWidth(int(stroke_width))
        pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.fillPath(path, QtGui.QBrush(use_fill))

    def _measure_text_rect(self, x: float, y_center: float, text: str, font: QtGui.QFont | None = None) -> QtCore.QRectF:
        """估算文本占位矩形(用于避免重叠排布)"""
        use_font = font if font is not None else ui_fonts.ui_font(10, bold=True)
        fm = QtGui.QFontMetricsF(use_font)
        width = float(fm.horizontalAdvance(text))
        height = float(fm.height())
        # 以 y_center 为视觉中心,构造占位矩形(略加2px缓冲)
        rect = QtCore.QRectF(float(x), float(y_center - height * 0.5), width, height)
        return rect.adjusted(-1.0, -1.0, 1.0, 1.0)

    def _draw_non_overlapping_label(
        self,
        painter: QtGui.QPainter,
        x: float,
        y_center: float,
        text: str,
        occupied: list[QtCore.QRectF],
        font: QtGui.QFont | None = None
    ) -> None:
        """绘制不与已放置文本重叠的标签(仅沿Y方向避让)"""
        if not text:
            return
        use_font = font if font is not None else ui_fonts.ui_font(10, bold=True)
        fm = QtGui.QFontMetricsF(use_font)
        step = float(fm.height() + 2.0)
        max_shift = step * 20  # 上限防止极端情况下无限下移
        attempt_y = float(y_center)
        candidate = self._measure_text_rect(x, attempt_y, text, use_font)
        # 向下避让,直到与所有已占用矩形不相交
        while any(candidate.intersects(r) for r in occupied) and (attempt_y - y_center) <= max_shift:
            attempt_y += step
            candidate = self._measure_text_rect(x, attempt_y, text, use_font)
        # 绘制并记录占位
        self._draw_text_with_stroke(painter, float(x), float(attempt_y), text, font=use_font)
        occupied.append(candidate)
        painter.restore()
    
    def _draw_non_overlapping_label_grid(
        self,
        painter: QtGui.QPainter,
        x: float,
        y_center: float,
        text: str,
        grid_occupied: GridOccupancyIndex,
        font: QtGui.QFont,
        font_metrics: QtGui.QFontMetricsF,
        max_attempts: int = 8
    ) -> None:
        """使用网格索引绘制不重叠标签(优化版,复杂度从O(N²)降至O(N×桶内数量))"""
        if not text:
            return
        step = float(font_metrics.height() + 2.0)
        attempt_y = float(y_center)
        candidate = self._measure_text_rect(x, attempt_y, text, font)
        # 向下避让,使用网格索引检查相交(限制最大尝试次数)
        attempts = 0
        while grid_occupied.check_intersects(candidate) and attempts < max_attempts:
            attempt_y += step
            candidate = self._measure_text_rect(x, attempt_y, text, font)
            attempts += 1
        # 绘制并记录占位
        self._draw_text_with_stroke(painter, float(x), float(attempt_y), text, font=font)
        grid_occupied.add(candidate)
        painter.restore()

