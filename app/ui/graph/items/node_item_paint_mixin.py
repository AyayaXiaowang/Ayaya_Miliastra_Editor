"""NodeGraphicsItem：绘制逻辑（paint/boundingRect + 标题栏渐变/LOD/验证标记等）。"""

from __future__ import annotations

import time
from typing import Any, cast

from PyQt6 import QtCore, QtGui

from app.ui.foundation import fonts as ui_fonts
from app.ui.foundation.theme_manager import Colors
from app.ui.graph.graph_palette import GraphPalette
from app.ui.graph.items.port_settings_button import PortSettingsButton
from engine.configs.settings import settings

from app.ui.graph.items.node_item_constants import (
    NODE_PADDING,
    OUTPUT_SETTINGS_BUTTON_CENTER_X_FROM_RIGHT_PX,
    PORT_SETTINGS_BUTTON_MARGIN_PX,
    ROW_HEIGHT,
)


class NodePaintMixin:
    def boundingRect(self) -> QtCore.QRectF:
        return getattr(self, "_rect", QtCore.QRectF(0, 0, 280, 140))

    def paint(self, painter: QtGui.QPainter | None, option, widget=None) -> None:
        if painter is None:
            return

        scene_ref_for_perf = self.scene()
        monitor = getattr(scene_ref_for_perf, "_perf_monitor", None) if scene_ref_for_perf is not None else None
        inc = getattr(monitor, "inc", None) if monitor is not None else None
        accum = getattr(monitor, "accum_ns", None) if monitor is not None else None
        track = getattr(monitor, "track_slowest", None) if monitor is not None else None
        t_total0 = time.perf_counter_ns() if monitor is not None else 0
        if callable(inc):
            inc("items.paint.node.calls", 1)

        r = self.boundingRect()
        header_h = ROW_HEIGHT + 10
        corner_radius = 12

        # === 缩放分级渲染（LOD）：低倍率下跳过高成本细节绘制 ===
        lod_enabled = bool(getattr(settings, "GRAPH_LOD_ENABLED", True))
        details_min_scale = float(getattr(settings, "GRAPH_LOD_NODE_DETAILS_MIN_SCALE", 0.55))
        lod_scale = 1.0
        if lod_enabled:
            if option is not None and hasattr(option, "levelOfDetailFromTransform"):
                lod_scale = float(option.levelOfDetailFromTransform(painter.worldTransform()))
            else:
                lod_scale = float(painter.worldTransform().m11())
        low_detail = bool(lod_enabled and (lod_scale < details_min_scale))
        title_min_scale = float(getattr(settings, "GRAPH_LOD_NODE_TITLE_MIN_SCALE", 0.28))
        show_title_text = True
        if lod_enabled and (lod_scale < title_min_scale):
            # 低倍率下标题文字通常不可读且绘制成本很高；仅对“选中/搜索命中”的节点保留文字。
            show_title_text = bool(self.isSelected() or getattr(self, "_search_highlighted", False))

        # 搜索命中描边：在选中高亮之前绘制，且选中态下不重复叠加
        if monitor is not None and callable(accum):
            t0 = time.perf_counter_ns()
            self._paint_search_highlight_outline(painter, r, corner_radius=float(corner_radius))
            accum("items.paint.node.search_outline", int(time.perf_counter_ns() - int(t0)))
        else:
            self._paint_search_highlight_outline(painter, r, corner_radius=float(corner_radius))

        # 选中状态的高亮效果（使用主题主色系描边，与全局渐变高亮保持一致）
        if self.isSelected():
            if monitor is not None and callable(accum):
                t0 = time.perf_counter_ns()
                glow_pen = QtGui.QPen(QtGui.QColor(Colors.PRIMARY))
                glow_pen.setWidth(4)
                painter.setPen(glow_pen)
                painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(r.adjusted(-2, -2, 2, 2), 14, 14)
                accum("items.paint.node.selection_glow", int(time.perf_counter_ns() - int(t0)))
            else:
                glow_pen = QtGui.QPen(QtGui.QColor(Colors.PRIMARY))
                glow_pen.setWidth(4)
                painter.setPen(glow_pen)
                painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(r.adjusted(-2, -2, 2, 2), 14, 14)

        # 绘制标题栏背景（带圆角的顶部）
        # 创建标题栏路径 - 只在顶部有圆角
        if monitor is not None and callable(accum):
            t0 = time.perf_counter_ns()
            title_path = QtGui.QPainterPath()
            # 从左下角开始
            title_path.moveTo(r.left(), r.top() + header_h)
            # 左边直线到圆角开始处
            title_path.lineTo(r.left(), r.top() + corner_radius)
            # 左上圆角 - 使用quadTo简化，避免arcTo在小尺寸下的问题
            title_path.quadTo(r.left(), r.top(), r.left() + corner_radius, r.top())
            # 顶边直线到右圆角
            title_path.lineTo(r.right() - corner_radius, r.top())
            # 右上圆角
            title_path.quadTo(r.right(), r.top(), r.right(), r.top() + corner_radius)
            # 右边直线到标题栏底部
            title_path.lineTo(r.right(), r.top() + header_h)
            # 封闭路径
            title_path.closeSubpath()
            accum("items.paint.node.title_path", int(time.perf_counter_ns() - int(t0)))
        else:
            title_path = QtGui.QPainterPath()

            # 从左下角开始
            title_path.moveTo(r.left(), r.top() + header_h)
            # 左边直线到圆角开始处
            title_path.lineTo(r.left(), r.top() + corner_radius)
            # 左上圆角 - 使用quadTo简化，避免arcTo在小尺寸下的问题
            title_path.quadTo(r.left(), r.top(), r.left() + corner_radius, r.top())
            # 顶边直线到右圆角
            title_path.lineTo(r.right() - corner_radius, r.top())
            # 右上圆角
            title_path.quadTo(r.right(), r.top(), r.right(), r.top() + corner_radius)
            # 右边直线到标题栏底部
            title_path.lineTo(r.right(), r.top() + header_h)
            # 封闭路径
            title_path.closeSubpath()

        # 使用渐变填充标题栏
        if monitor is not None and callable(accum):
            t0 = time.perf_counter_ns()
            grad = QtGui.QLinearGradient(r.topLeft(), r.topRight())
            grad.setColorAt(0.0, self._category_color_start())
            grad.setColorAt(1.0, self._category_color_end())
            painter.fillPath(title_path, QtGui.QBrush(grad))
            accum("items.paint.node.title_gradient", int(time.perf_counter_ns() - int(t0)))
        else:
            grad = QtGui.QLinearGradient(r.topLeft(), r.topRight())
            grad.setColorAt(0.0, self._category_color_start())
            grad.setColorAt(1.0, self._category_color_end())
            painter.fillPath(title_path, QtGui.QBrush(grad))

        # 节点内容区背景不透明度（由设置面板控制；默认 70% 与当前观感一致）
        node_content_alpha = float(getattr(settings, "GRAPH_NODE_CONTENT_ALPHA", 0.7))

        # 兼容既有观感：标题栏当前有一层“暗底覆罩”让渐变更柔和；
        # 为避免用户将不透明度调到 100% 时把标题渐变完全盖掉，这里将标题覆罩上限固定为 70%。
        header_overlay_alpha = min(float(node_content_alpha), 0.7)
        header_overlay_color = QtGui.QColor(GraphPalette.NODE_CONTENT_BG)
        header_overlay_color.setAlpha(int(255 * header_overlay_alpha))
        if monitor is not None and callable(accum):
            t0 = time.perf_counter_ns()
            painter.fillPath(title_path, QtGui.QBrush(header_overlay_color))
            accum("items.paint.node.title_overlay", int(time.perf_counter_ns() - int(t0)))
        else:
            painter.fillPath(title_path, QtGui.QBrush(header_overlay_color))

        # 内容区填充：只对 header 以下区域生效，避免覆盖标题栏的类别渐变
        content_rect = QtCore.QRectF(
            r.left(),
            r.top() + header_h,
            r.width(),
            r.height() - header_h,
        )
        content_color = QtGui.QColor(GraphPalette.NODE_CONTENT_BG)
        content_color.setAlpha(int(255 * node_content_alpha))

        if monitor is not None and callable(accum):
            t0 = time.perf_counter_ns()
            node_path = QtGui.QPainterPath()
            node_path.addRoundedRect(r, corner_radius, corner_radius)
            painter.save()
            painter.setClipRect(content_rect)
            painter.fillPath(node_path, QtGui.QBrush(content_color))
            painter.restore()
            accum("items.paint.node.content_fill", int(time.perf_counter_ns() - int(t0)))
        else:
            node_path = QtGui.QPainterPath()
            node_path.addRoundedRect(r, corner_radius, corner_radius)
            painter.save()
            painter.setClipRect(content_rect)
            painter.fillPath(node_path, QtGui.QBrush(content_color))
            painter.restore()

        # 绘制整体轮廓（圆角矩形描边）
        pen_color = (
            QtGui.QColor(Colors.PRIMARY)
            if self.isSelected()
            else QtGui.QColor(GraphPalette.NODE_CONTENT_BORDER)
        )
        if monitor is not None and callable(accum):
            t0 = time.perf_counter_ns()
            pen = QtGui.QPen(pen_color)
            pen.setWidth(2 if self.isSelected() else 1)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawPath(node_path)
            accum("items.paint.node.outline", int(time.perf_counter_ns() - int(t0)))
        else:
            pen = QtGui.QPen(pen_color)
            pen.setWidth(2 if self.isSelected() else 1)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawPath(node_path)

        # title text
        if show_title_text:
            if monitor is not None and callable(accum):
                t0 = time.perf_counter_ns()
            painter.setFont(self.title_font)
            painter.setPen(QtGui.QColor(GraphPalette.TEXT_BRIGHT))

            # 如果是虚拟引脚节点，在标题前添加序号标记
            if self.node.is_virtual_pin:
                direction_symbol = "⬅️ " if self.node.is_virtual_pin_input else "➡️ "
                title_text = f"[{self.node.virtual_pin_index}] {direction_symbol}{self.node.title}"
            else:
                title_text = self.node.title

            # 定义标题区域用于绘制文本
            title_rect = QtCore.QRectF(r.left(), r.top(), r.width(), header_h)
            painter.drawText(
                title_rect.adjusted(12, 0, -12, 0),
                QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignLeft,
                title_text,
            )
            if monitor is not None and callable(accum):
                accum("items.paint.node.title_text", int(time.perf_counter_ns() - int(t0)))

        # LOD：低倍率下仅保留“标题栏颜色 + 标题文本 + 节点框”，其它细节（端口/常量/验证图标等）全部跳过
        if low_detail:
            if monitor is not None and callable(accum):
                dt_total_ns = int(time.perf_counter_ns() - int(t_total0))
                accum("items.paint.node.total", dt_total_ns)
                if callable(track):
                    track(f"node:{getattr(self.node, 'id', '')}", dt_total_ns)
            return

        # port labels (including flow ports) - 所有标签都使用亮色
        t_ports0 = time.perf_counter_ns() if monitor is not None and callable(accum) else 0
        painter.setFont(ui_fonts.ui_font(9))
        painter.setPen(QtGui.QColor(GraphPalette.TEXT_LABEL))  # 统一使用亮色
        header_h = ROW_HEIGHT + 10

        # draw input port labels（使用真实行索引映射）
        input_start_y = header_h + NODE_PADDING
        fm_label = painter.fontMetrics()
        btn_half = PortSettingsButton.DEFAULT_SIZE_PX / 2
        for p in self.node.inputs:
            # 如果此端口未渲染（如变参占位），跳过
            if p.name not in self._input_row_index_map:
                continue
            row_index = self._input_row_index_map.get(p.name, 0)
            label_y = input_start_y + row_index * ROW_HEIGHT

            # 输入标签：端口右侧开始，左对齐
            painter.setPen(QtGui.QColor(GraphPalette.TEXT_LABEL))  # 确保标签是亮色

            # 检查端口是否有控件，并获取控件信息
            has_control = p.name in self._control_positions

            # 标签在独立一行渲染，固定起点与宽度
            label_x = 30
            label_width = r.width() - 60

            # 预留“⚙”按钮区域，避免标签文本覆盖按钮（与布局阶段的按钮定位保持同一规则）
            text_width = float(fm_label.horizontalAdvance(str(p.name)))
            btn_x = float(label_x) + text_width + float(PORT_SETTINGS_BUTTON_MARGIN_PX) + float(btn_half)
            max_btn_x = float(r.width()) * 0.5 - float(btn_half) - float(PORT_SETTINGS_BUTTON_MARGIN_PX)
            btn_x = min(btn_x, max_btn_x)
            label_right_edge = min(float(label_x + label_width), float(btn_x - btn_half - 2.0))
            label_width = max(0.0, label_right_edge - float(label_x))

            # 绘制标签（使用clip确保不超出区域，避免遮挡控件）
            label_rect = QtCore.QRectF(label_x, label_y, label_width, ROW_HEIGHT)
            painter.save()
            painter.setClipRect(label_rect)  # 裁剪区域，防止文本溢出到控件
            painter.drawText(label_rect, QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignLeft, p.name)
            painter.restore()

            # 为文本类型的常量编辑框绘制背景（只为text类型绘制，bool和vector自带样式）
            if has_control:
                control_x, control_y, control_width, control_type = self._control_positions[p.name]
                control_type_text = str(control_type or "")
                placeholder_rect = self._inline_constant_rect_for_port(p.name)
                if placeholder_rect is None:
                    continue

                is_materialized = p.name in self._constant_edits
                display_text = str(self._inline_constant_display_text.get(p.name, "") or "")

                if control_type_text == "text":
                    # 文本输入框背景：无论是否 materialize，都由节点自绘（ConstantTextEdit 本身无底色）
                    painter.fillRect(placeholder_rect, QtGui.QColor(GraphPalette.INPUT_BG))
                    painter.setPen(QtGui.QColor(GraphPalette.BORDER_SUBTLE))
                    painter.drawRoundedRect(placeholder_rect, 2, 2)

                    # 占位文本：仅在未创建真实控件时绘制（避免与 ConstantTextEdit 重叠）
                    if (not is_materialized) and display_text:
                        painter.save()
                        painter.setPen(QtGui.QColor(GraphPalette.TEXT_LABEL))
                        painter.setFont(ui_fonts.monospace_font(8))
                        inner = placeholder_rect.adjusted(4.0, 0.0, -4.0, 0.0)
                        painter.setClipRect(inner)
                        fm = QtGui.QFontMetrics(painter.font())
                        elided = fm.elidedText(
                            display_text,
                            QtCore.Qt.TextElideMode.ElideRight,
                            max(0, int(inner.width())),
                        )
                        painter.drawText(
                            inner,
                            QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignLeft,
                            elided,
                        )
                        painter.restore()
                else:
                    # bool/vector：占位绘制（真实控件不存在时）
                    if is_materialized:
                        continue
                    painter.save()
                    painter.fillRect(placeholder_rect, QtGui.QColor(GraphPalette.INPUT_BG))
                    painter.setPen(QtGui.QColor(GraphPalette.BORDER_SUBTLE))
                    painter.drawRoundedRect(placeholder_rect, 2, 2)
                    painter.setPen(QtGui.QColor(GraphPalette.TEXT_LABEL))
                    painter.setFont(ui_fonts.monospace_font(8))
                    inner = placeholder_rect.adjusted(4.0, 0.0, -4.0, 0.0)
                    painter.setClipRect(inner)
                    fm = QtGui.QFontMetrics(painter.font())
                    elided = fm.elidedText(
                        display_text,
                        QtCore.Qt.TextElideMode.ElideRight,
                        max(0, int(inner.width())),
                    )
                    align = (
                        QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignCenter
                        if control_type_text == "bool"
                        else QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignLeft
                    )
                    painter.drawText(inner, align, elided)
                    painter.restore()

        # draw output port labels
        painter.setPen(QtGui.QColor(GraphPalette.TEXT_LABEL))  # 确保标签是亮色
        output_start_y = header_h + NODE_PADDING
        for out_index, p in enumerate(self.node.outputs):
            label_y = output_start_y + out_index * ROW_HEIGHT
            # 输出标签：端口左侧结束，右对齐（多分支分支口也绘制常规标签）
            btn_half = PortSettingsButton.DEFAULT_SIZE_PX / 2
            btn_left = float(r.width()) - float(OUTPUT_SETTINGS_BUTTON_CENTER_X_FROM_RIGHT_PX) - float(btn_half)
            label_right_edge = float(btn_left) - 6.0
            label_left = float(r.width()) * 0.5
            label_width = max(0.0, label_right_edge - label_left)
            painter.drawText(
                QtCore.QRectF(label_left, label_y, label_width, ROW_HEIGHT),
                QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignRight,
                p.name,
            )
        if monitor is not None and callable(accum):
            accum("items.paint.node.port_labels", int(time.perf_counter_ns() - int(t_ports0)))

        # 绘制验证警告（基于验证系统的结果）
        t_val0 = time.perf_counter_ns() if monitor is not None and callable(accum) else 0
        scene_ref_for_validation = self.scene()
        scene_any = cast(Any, scene_ref_for_validation)
        validation_issues = getattr(scene_any, "validation_issues", None)
        if validation_issues is not None:
            issues = validation_issues.get(self.node.id, [])
            for issue in issues:
                # 获取端口名称
                port_name = issue.detail.get("port_name") if hasattr(issue, "detail") else None
                if port_name:
                    # 找到对应的输入端口索引
                    for p in self.node.inputs:
                        if p.name not in self._input_row_index_map:
                            continue
                        if p.name == port_name:
                            row_index = self._input_row_index_map.get(p.name, 0)
                            label_y = input_start_y + row_index * ROW_HEIGHT

                            # 根据issue级别选择颜色
                            if hasattr(issue, "level"):
                                if issue.level == "error":
                                    warning_color = QtGui.QColor(GraphPalette.WARN_GOLD)  # 金黄色
                                elif issue.level == "warning":
                                    warning_color = QtGui.QColor(GraphPalette.WARN_ORANGE)  # 橙色
                                else:
                                    warning_color = QtGui.QColor(GraphPalette.INFO_SKY)  # 浅蓝色
                            else:
                                warning_color = QtGui.QColor(GraphPalette.WARN_GOLD)

                            # 绘制警告感叹号（在输入框位置）
                            painter.setPen(warning_color)
                            painter.setFont(ui_fonts.ui_font(11, bold=True))
                            warning_rect = QtCore.QRectF(r.width() * 0.35, label_y, 20, ROW_HEIGHT)
                            painter.drawText(warning_rect, QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignCenter, "!")
                            painter.setFont(ui_fonts.ui_font(9))  # 恢复字体
                            break
        if monitor is not None and callable(accum):
            accum("items.paint.node.validation", int(time.perf_counter_ns() - int(t_val0)))

        if monitor is not None and callable(accum):
            dt_total_ns = int(time.perf_counter_ns() - int(t_total0))
            accum("items.paint.node.total", dt_total_ns)
            if callable(track):
                track(f"node:{getattr(self.node, 'id', '')}", dt_total_ns)

    def _category_color_start(self) -> QtGui.QColor:
        cat = self.node.category

        # 虚拟引脚节点使用特殊颜色
        if self.node.is_virtual_pin:
            return QtGui.QColor(GraphPalette.CATEGORY_VIRTUAL_IN) if self.node.is_virtual_pin_input else QtGui.QColor(GraphPalette.CATEGORY_VIRTUAL_OUT)

        # 复合节点使用集中管理的银白渐变色（优先于category判断）
        if hasattr(self.node, "composite_id") and self.node.composite_id:
            return QtGui.QColor(Colors.NODE_HEADER_COMPOSITE_START)

        # 支持简化版（"事件"）和完整版（"事件节点"）
        color_map = {
            "查询": QtGui.QColor(GraphPalette.CATEGORY_QUERY),
            "查询节点": QtGui.QColor(GraphPalette.CATEGORY_QUERY),
            "事件": QtGui.QColor(GraphPalette.CATEGORY_EVENT),
            "事件节点": QtGui.QColor(GraphPalette.CATEGORY_EVENT),
            "运算": QtGui.QColor(GraphPalette.CATEGORY_COMPUTE),
            "运算节点": QtGui.QColor(GraphPalette.CATEGORY_COMPUTE),
            "执行": QtGui.QColor(GraphPalette.CATEGORY_EXECUTION),
            "执行节点": QtGui.QColor(GraphPalette.CATEGORY_EXECUTION),
            "流程控制": QtGui.QColor(GraphPalette.CATEGORY_FLOW),
            "流程控制节点": QtGui.QColor(GraphPalette.CATEGORY_FLOW),
            "复合": QtGui.QColor(Colors.NODE_HEADER_COMPOSITE_START),
            "复合节点": QtGui.QColor(Colors.NODE_HEADER_COMPOSITE_START),
        }
        return color_map.get(cat, QtGui.QColor(GraphPalette.CATEGORY_DEFAULT))

    def _category_color_end(self) -> QtGui.QColor:
        cat = self.node.category

        # 虚拟引脚节点使用特殊颜色
        if self.node.is_virtual_pin:
            return QtGui.QColor(GraphPalette.CATEGORY_VIRTUAL_IN_DARK) if self.node.is_virtual_pin_input else QtGui.QColor(GraphPalette.CATEGORY_VIRTUAL_OUT_DARK)

        # 复合节点使用集中管理的银白渐变色（优先于category判断）
        if hasattr(self.node, "composite_id") and self.node.composite_id:
            return QtGui.QColor(Colors.NODE_HEADER_COMPOSITE_END)

        # 支持简化版（"事件"）和完整版（"事件节点"）
        color_map = {
            "查询": QtGui.QColor(GraphPalette.CATEGORY_QUERY_DARK),
            "查询节点": QtGui.QColor(GraphPalette.CATEGORY_QUERY_DARK),
            "事件": QtGui.QColor(GraphPalette.CATEGORY_EVENT_DARK),
            "事件节点": QtGui.QColor(GraphPalette.CATEGORY_EVENT_DARK),
            "运算": QtGui.QColor(GraphPalette.CATEGORY_COMPUTE_DARK),
            "运算节点": QtGui.QColor(GraphPalette.CATEGORY_COMPUTE_DARK),
            "执行": QtGui.QColor(GraphPalette.CATEGORY_EXECUTION_DARK),
            "执行节点": QtGui.QColor(GraphPalette.CATEGORY_EXECUTION_DARK),
            "流程控制": QtGui.QColor(GraphPalette.CATEGORY_FLOW_DARK),
            "流程控制节点": QtGui.QColor(GraphPalette.CATEGORY_FLOW_DARK),
            "复合": QtGui.QColor(Colors.NODE_HEADER_COMPOSITE_END),
            "复合节点": QtGui.QColor(Colors.NODE_HEADER_COMPOSITE_END),
        }
        return color_map.get(cat, QtGui.QColor(GraphPalette.NODE_CONTENT_BORDER))

