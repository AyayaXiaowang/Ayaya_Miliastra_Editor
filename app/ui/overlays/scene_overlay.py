"""场景叠加渲染 Mixin

提供网格背景、基本块、Y调试Tooltip、链路高亮等叠加渲染能力。
假设宿主场景提供: model, node_items, edge_items 等属性。
"""

from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets
from typing import Optional, Dict, List
from ui.overlays.text_layout import GridOccupancyIndex
from ui.graph.graph_palette import GraphPalette


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
        from ui.foundation.theme_manager import ThemeManager
        from engine.configs.settings import settings
        
        # 绘制网格背景
        ThemeManager.draw_grid_background(painter, rect, self.grid_size)
        
        # 绘制基本块矩形(如果启用)
        if settings.SHOW_BASIC_BLOCKS and self.model and self.model.basic_blocks:
            painter.save()
            
            # 遍历所有基本块
            for block_index, block in enumerate(self.model.basic_blocks):
                if not block.nodes:
                    continue
                
                # 计算基本块的边界矩形
                block_rect = self._calculate_block_rect(block)
                
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
    
    def drawForeground(self, painter: QtGui.QPainter, rect: QtCore.QRectF) -> None:
        """绘制前景层(基本块标签)"""
        from engine.configs.settings import settings
        
        # 绘制基本块编号标签(在前景层,确保不被节点遮挡)
        if settings.SHOW_BASIC_BLOCKS and self.model and self.model.basic_blocks:
            painter.save()
            
            # 遍历所有基本块
            for block_index, block in enumerate(self.model.basic_blocks):
                if not block.nodes:
                    continue
                
                # 计算基本块的边界矩形
                block_rect = self._calculate_block_rect(block)
                
                if block_rect and block_rect.intersects(rect):
                    # 获取块颜色
                    color = QtGui.QColor(block.color)
                    
                    # 绘制基本块编号标签
                    self._draw_block_label(painter, block_rect, block_index + 1, color)
            
            painter.restore()

        # 轻量:布局Y调试图标(节点右上角"!"),点击弹出可复制Tooltip
        if getattr(settings, "SHOW_LAYOUT_Y_DEBUG", False) and self.model:
            self._ensure_layout_y_debug_info()
            debug_map = getattr(self.model, "_layout_y_debug_info", {}) or {}
            if debug_map and self.node_items:
                if not hasattr(self, "_ydebug_icon_rects"):
                    self._ydebug_icon_rects = {}
                self._ydebug_icon_rects.clear()
                painter.save()
                visible_rect = rect.adjusted(-60.0, -60.0, 60.0, 60.0)
                for node_id, node_item in self.node_items.items():
                    # 仅对存在调试信息的节点绘制图标,避免点击无反馈
                    if node_id not in debug_map:
                        continue
                    node_rect = node_item.sceneBoundingRect()
                    if not node_rect.intersects(visible_rect):
                        continue
                    icon_size = 28.0
                    icon_margin = 6.0
                    # 改为右上角:以节点右侧为参考点放置图标
                    icon_rect = QtCore.QRectF(
                        float(node_rect.right()) - icon_margin - icon_size,
                        float(node_rect.top()) + icon_margin,
                        icon_size,
                        icon_size
                    )
                    painter.setPen(QtCore.Qt.PenStyle.NoPen)
                    painter.setBrush(QtGui.QBrush(QtGui.QColor(GraphPalette.BADGE_ACCENT)))
                    painter.drawEllipse(icon_rect)
                    pen = QtGui.QPen(QtGui.QColor(GraphPalette.TEXT_BRIGHT))
                    painter.setPen(pen)
                    font = painter.font()
                    font.setBold(True)
                    font.setPointSizeF(14.0)
                    painter.setFont(font)
                    painter.drawText(icon_rect, QtCore.Qt.AlignmentFlag.AlignCenter, "!")
                    self._ydebug_icon_rects[node_id] = icon_rect
                painter.restore()
        # 链路序号徽标(当前高亮链路时显示在节点上方,醒目且有描边)
        if getattr(settings, "SHOW_LAYOUT_Y_DEBUG", False):
            if hasattr(self, "_active_chain_node_positions") and self._active_chain_node_positions:
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
            # 全链路高亮:为相关节点绘制彩色描边
            if hasattr(self, "_all_chain_node_color_map") and self._all_chain_node_color_map:
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
                # 在“高亮全部”模式下，为每个节点绘制链编号徽标（链ID），与描边颜色一致
                if hasattr(self, "_all_chain_node_chain_ids") and self._all_chain_node_chain_ids:
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

    def _get_ydebug_icon_rect_for_item(self, node_item: 'NodeGraphicsItem', icon_size: float = 28.0, icon_margin: float = 6.0) -> QtCore.QRectF:
        """计算给定节点的Y调试图标的矩形(右上角)"""
        node_rect = node_item.sceneBoundingRect()
        return QtCore.QRectF(
            float(node_rect.right()) - float(icon_margin) - float(icon_size),
            float(node_rect.top()) + float(icon_margin),
            float(icon_size),
            float(icon_size)
        )

    def _ensure_layout_y_debug_info(self) -> None:
        """当叠加开启但当前模型没有调试信息时，临时运行布局以生成调试数据。"""
        if not getattr(self, "model", None):
            return
        debug_map = getattr(self.model, "_layout_y_debug_info", None)
        if isinstance(debug_map, dict) and debug_map:
            return
        if getattr(self, "_layout_y_debug_lazy_synced", False):
            return
        try:
            from engine.layout import LayoutService
            from engine.layout.core.layout_context import LayoutContext
            from engine.layout.flow.event_flow_analyzer import find_event_roots
            from engine.layout.utils.graph_query_utils import has_flow_edges
            result = LayoutService.compute_layout(self.model, include_augmented_model=True)
            augmented = getattr(result, "augmented_model", None)
            debug_map_aug = getattr(augmented, "_layout_y_debug_info", None) if augmented is not None else None

            final_debug_map = None
            if isinstance(debug_map_aug, dict) and debug_map_aug:
                final_debug_map = dict(debug_map_aug)
            elif getattr(result, "y_debug_info", None):
                final_debug_map = dict(result.y_debug_info)

            if final_debug_map:
                setattr(self.model, "_layout_y_debug_info", final_debug_map)
            else:
                target_model = augmented if augmented is not None else self.model
                graph_name = getattr(target_model, "graph_name", "") or "<unnamed>"
                node_count = len(getattr(target_model, "nodes", {}) or {})
                edge_count = len(getattr(target_model, "edges", {}) or {})

                cached_ctx = getattr(target_model, "_layout_context_cache", None)
                layout_ctx = cached_ctx if isinstance(cached_ctx, LayoutContext) else LayoutContext(target_model)

                has_flow = has_flow_edges(target_model)
                flow_node_count = len(getattr(layout_ctx, "flowCapableNodeIds", []) or [])
                event_roots = find_event_roots(
                    target_model,
                    include_virtual_pin_roots=True,
                    layout_context=layout_ctx,
                )

                if edge_count == 0 and flow_node_count > 0:
                    category_desc = (
                        "仅包含流程控制/执行节点但没有任何流程连线"
                        "（例如只有一个带“流程入/流程出”的节点尚未接线）"
                    )
                elif not has_flow:
                    category_desc = "纯数据图（图结构中不存在任何流程边）"
                elif has_flow and not event_roots:
                    category_desc = "仅包含流程连线但未识别到事件起点（例如只有流程入口/流程控制节点）"
                else:
                    category_desc = "存在事件起点但布局调试信息为空（需要检查块识别与调试写入逻辑）"

                print(
                    "[YDebug] 布局完成但未生成Y轴调试信息："
                    f"图='{graph_name}'，节点数={node_count}，边数={edge_count}，"
                    f"flow_nodes={flow_node_count}，has_flow_edges={has_flow}，事件起点数量={len(event_roots)}，"
                    f"分类={category_desc}；不再重复尝试。"
                )
                # 为了进一步排查，将前若干个事件起点打印出来（若存在）
                max_roots_preview = 5
                for root in event_roots[:max_roots_preview]:
                    title = getattr(root, "title", "") or "<no-title>"
                    category = getattr(root, "category", "") or "<no-category>"
                    print(
                        f"[YDebug]  事件起点: id={root.id}, 标题='{title}', category='{category}'"
                    )
            self._layout_y_debug_lazy_synced = True
        except Exception as exc:
            print(f"[YDebug] 无法自动生成布局Y调试信息: {exc}")
            # 若布局始终失败，记住状态以避免不断重试导致控制台刷屏
            self._layout_y_debug_lazy_synced = True
    
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
    
    def _calculate_block_rect(self, block) -> Optional[QtCore.QRectF]:
        """计算基本块的边界矩形
        
        Args:
            block: BasicBlock对象
            
        Returns:
            包含所有节点的矩形,留出边距(20-30px)
        """
        if not block.nodes:
            return None
        
        # 收集所有节点的边界矩形
        node_rects = []
        for node_id in block.nodes:
            node_item = self.node_items.get(node_id)
            if node_item:
                # 获取节点在场景中的边界矩形
                node_rects.append(node_item.sceneBoundingRect())
        
        if not node_rects:
            return None
        
        # 计算包含所有节点的最小矩形
        min_x = min(r.left() for r in node_rects)
        min_y = min(r.top() for r in node_rects)
        max_x = max(r.right() for r in node_rects)
        max_y = max(r.bottom() for r in node_rects)
        
        # 留出边距(20-30px)
        margin = 25
        
        return QtCore.QRectF(
            min_x - margin,
            min_y - margin,
            max_x - min_x + 2 * margin,
            max_y - min_y + 2 * margin
        )

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
        use_font = font if font is not None else QtGui.QFont('Microsoft YaHei UI', 10, QtGui.QFont.Weight.Bold)
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
        use_font = font if font is not None else QtGui.QFont('Microsoft YaHei UI', 10, QtGui.QFont.Weight.Bold)
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
        use_font = font if font is not None else QtGui.QFont('Microsoft YaHei UI', 10, QtGui.QFont.Weight.Bold)
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

