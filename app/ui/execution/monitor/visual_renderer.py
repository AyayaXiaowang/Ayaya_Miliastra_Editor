# -*- coding: utf-8 -*-
"""
可视化渲染管线
职责：图片渲染、截图序列维护、双击放大预览、标题叠加策略
"""

from PyQt6 import QtCore, QtWidgets, QtGui
from PyQt6.QtCore import Qt
from PIL import Image
from io import BytesIO
import os
import textwrap

from .visual_overlays import _draw_overlays_on_pixmap, _draw_header_banner
from .preview_dialog import _ImageHistoryPreviewDialog


class VisualRenderer(QtCore.QObject):
    """可视化渲染器：负责图片渲染、截图序列维护、双击放大"""
    
    def __init__(
        self, 
        screenshot_label: QtWidgets.QLabel,
        parent_widget: QtWidgets.QWidget,
        get_current_display_title_callback,
        get_current_micro_action_callback
    ):
        super().__init__(parent_widget)
        """
        Args:
            screenshot_label: 截图显示控件
            parent_widget: 父部件（用于对话框父级）
            get_current_display_title_callback: 获取当前显示标题的回调
            get_current_micro_action_callback: 获取微动作标题的回调
        """
        self._screenshot_label = screenshot_label
        self._parent_widget = parent_widget
        self._get_current_display_title = get_current_display_title_callback
        self._get_current_micro_action = get_current_micro_action_callback
        
        # 状态
        self._last_full_pixmap: QtGui.QPixmap | None = None
        self._modeless_previews = []  # 持有非模态预览对话框的引用，避免被GC
        
        # 当前运行期的截图序列（原始尺寸，已叠加绘制）
        self._current_run_images: list[QtGui.QPixmap] = []
        self._current_run_titles: list[str] = []
        self._history_max_images: int = 200
        
        # 安装事件过滤器（双击放大预览）
        self._screenshot_label.installEventFilter(self)
    
    def render_visual(self, base_image: Image.Image, overlays: object | None) -> None:
        """渲染可视化产物到截图标签
        
        Args:
            base_image: PIL 图片
            overlays: 叠加数据字典（rects/circles/header/title）
        """
        buffer = BytesIO()
        base_image.save(buffer, format='PNG')
        buffer.seek(0)
        pixmap = QtGui.QPixmap()
        pixmap.loadFromData(buffer.getvalue())

        # 在原尺寸上绘制叠加，然后整体缩放，避免坐标换算误差
        if overlays:
            self._draw_reference_panel_on_pixmap(pixmap, overlays)
            _draw_overlays_on_pixmap(pixmap, overlays)

        # 在左上角叠加标题：
        # - 优先使用当前执行步骤标题（包含叶子/子步骤 tokens 的纯文本）
        # - 若存在更细粒度的子动作或测试标题，则作为后缀补充显示
        title_for_image = self._select_title_for_image(overlays)
        if title_for_image:
            _draw_header_banner(pixmap, str(title_for_image))

        # 记录原始完整画面，用于放大预览
        self._last_full_pixmap = QtGui.QPixmap(pixmap)
        self._append_image_to_history(self._last_full_pixmap, title_for_image)

        scaled = pixmap.scaled(
            self._screenshot_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._screenshot_label.setPixmap(scaled)
    
    def render_visual_snapshot(self, base_image: Image.Image, overlays: object | None) -> None:
        """在当前面板直接显示一次性可视化，不检查 is_running 状态。
        
        用于"检查页面"等即时测试功能。
        """
        buffer = BytesIO()
        base_image.save(buffer, format='PNG')
        buffer.seek(0)
        pixmap = QtGui.QPixmap()
        pixmap.loadFromData(buffer.getvalue())

        if overlays:
            self._draw_reference_panel_on_pixmap(pixmap, overlays)
            _draw_overlays_on_pixmap(pixmap, overlays)

        # 标题策略与常规渲染一致
        title_for_image = self._select_title_for_image(overlays)
        if title_for_image:
            _draw_header_banner(pixmap, str(title_for_image))

        self._last_full_pixmap = QtGui.QPixmap(pixmap)
        self._append_image_to_history(self._last_full_pixmap, title_for_image)
        scaled = pixmap.scaled(
            self._screenshot_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._screenshot_label.setPixmap(scaled)
    
    def clear_history(self) -> None:
        """清空截图记录（开启新监控会话时调用）"""
        self._current_run_images = []
        self._current_run_titles = []
    
    def backfill_recent_empty_titles(self) -> None:
        """将末尾连续的空标题记录回填为当前可显示标题（步骤名或tokens纯文本）。"""
        if not isinstance(self._current_run_titles, list) or len(self._current_run_titles) == 0:
            return
        new_title = self._get_current_display_title()
        if not new_title:
            return
        # 从末尾向前回填，遇到首个非空即停止
        for idx in range(len(self._current_run_titles) - 1, -1, -1):
            if not self._current_run_titles[idx]:
                self._current_run_titles[idx] = str(new_title)
            else:
                break
    
    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        """事件过滤器：处理双击放大预览"""
        if obj is self._screenshot_label and event.type() == QtCore.QEvent.Type.MouseButtonDblClick:
            if self._last_full_pixmap is not None and not self._last_full_pixmap.isNull():
                images = self._current_run_images if self._current_run_images else [self._last_full_pixmap]
                start_index = len(images) - 1
                titles = self._current_run_titles if self._current_run_titles else []
                dialog = _ImageHistoryPreviewDialog(images, start_index, self._parent_widget, titles)
                dialog.setWindowModality(Qt.WindowModality.NonModal)
                dialog.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
                self._modeless_previews.append(dialog)
                def on_destroyed(destroyed_obj=None, dlg=dialog):
                    if dlg in self._modeless_previews:
                        self._modeless_previews.remove(dlg)
                dialog.destroyed.connect(on_destroyed)
                dialog.show()
                return True
        return False
    
    def _append_image_to_history(self, image: QtGui.QPixmap, title: str | None = None) -> None:
        """追加图片到截图记录"""
        # 复制一份，避免外部修改引用
        self._current_run_images.append(QtGui.QPixmap(image))
        self._current_run_titles.append(str(title or ""))
        if self._history_max_images > 0 and len(self._current_run_images) > self._history_max_images:
            overflow = len(self._current_run_images) - self._history_max_images
            del self._current_run_images[0:overflow]
            del self._current_run_titles[0:overflow]
    
    def _extract_overlay_header(self, overlays: object | None) -> str:
        """从叠加数据中提取标题"""
        if isinstance(overlays, dict):
            header = overlays.get('header') or overlays.get('title')
            if isinstance(header, str):
                text = header.strip()
                if text:
                    return text
        return ""

    def _select_title_for_image(self, overlays: object | None) -> str:
        """
        统一选择当前截图标题：
        - 执行步骤场景：始终包含“当前执行步骤标题”，子步骤/微动作作为补充信息；
        - 测试/调试场景（仅 overlays.header/title，无步骤上下文）：直接使用叠加层标题。
        """
        overlay_title = self._extract_overlay_header(overlays)
        step_title = str(self._get_current_display_title() or "").strip()
        micro_title = str(self._get_current_micro_action() or "").strip()

        # 1) 有明确的执行步骤上下文：以步骤名为主
        if step_title:
            # 1.1 叠加层有更细粒度的标题（如 OCR/模板调试），且不与步骤名重复时，作为后缀补充
            if overlay_title:
                if overlay_title != step_title and step_title not in overlay_title:
                    return f"{step_title} · {overlay_title}"
            # 1.2 若最近一条微动作不只是“执行步骤: xxx”这类对步骤名的重复，则作为后缀补充
            if micro_title:
                if micro_title != step_title and step_title not in micro_title:
                    return f"{step_title} · {micro_title}"
            # 1.3 默认仅显示执行步骤名
            return step_title

        # 2) 无执行步骤上下文：优先叠加层标题，其次微动作
        if overlay_title:
            return overlay_title
        if micro_title:
            return micro_title
        return ""

    def _draw_reference_panel_on_pixmap(self, pixmap: QtGui.QPixmap, overlays: object | None) -> None:
        if not isinstance(overlays, dict):
            return
        panel = overlays.get('reference_panel')
        if not isinstance(panel, dict):
            return
        if panel.get('_embedded'):
            return
        title = str(panel.get('title') or "参考")
        subtitle = str(panel.get('text') or "").strip()
        image_bytes = panel.get('image_bytes')
        image_path = panel.get('image_path')
        template_pix = None
        if isinstance(image_bytes, (bytes, bytearray)) and len(image_bytes) > 0:
            tpl_pixmap = QtGui.QPixmap()
            if tpl_pixmap.loadFromData(image_bytes):
                template_pix = tpl_pixmap
        if template_pix is None and image_path and os.path.exists(str(image_path)):
            tpl_pixmap = QtGui.QPixmap(str(image_path))
            if not tpl_pixmap.isNull():
                template_pix = tpl_pixmap

        margin = 16
        padding = 10
        max_panel_w = max(160, int(pixmap.width() * 0.22))
        max_panel_h = max(140, int(pixmap.height() * 0.40))
        panel_w = max_panel_w

        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

        header_font = QtGui.QFont(painter.font())
        header_font.setPointSize(10)
        header_font.setBold(True)
        painter.setFont(header_font)
        header_metrics = painter.fontMetrics()
        header_height = header_metrics.height()

        subtitle_height = 0
        subtitle_lines: list[str] = []
        if subtitle:
            body_font = QtGui.QFont(painter.font())
            body_font.setPointSize(9)
            body_font.setBold(False)
            painter.setFont(body_font)
            normalized = " ".join(subtitle.split())
            subtitle_lines = textwrap.wrap(normalized, width=24)[:3]
            subtitle_height = len(subtitle_lines) * (painter.fontMetrics().height() + 2)
        content_space = max_panel_h - (padding * 2) - header_height - subtitle_height - 8
        image_height = 0
        scaled_template = None
        if template_pix:
            scaled_template = template_pix.scaled(
                panel_w - padding * 2,
                max(40, content_space),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            image_height = scaled_template.height()
        panel_h = padding * 2 + header_height + subtitle_height + (image_height + 8 if image_height else 0)
        if panel_h < 120:
            panel_h = 120
        if panel_h > max_panel_h:
            panel_h = max_panel_h

        panel_left = pixmap.width() - panel_w - margin
        panel_top = margin
        bg_color = QtGui.QColor(12, 12, 14, 220)
        painter.setBrush(QtGui.QBrush(bg_color))
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 180)))
        painter.drawRoundedRect(panel_left, panel_top, panel_w, panel_h, 8, 8)

        painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255)))
        painter.setFont(header_font)
        header_y = panel_top + padding + header_metrics.ascent()
        painter.drawText(panel_left + padding, header_y, title)

        current_y = panel_top + padding + header_height + 4
        if subtitle_lines:
            body_font = QtGui.QFont(painter.font())
            body_font.setPointSize(9)
            body_font.setBold(False)
            painter.setFont(body_font)
            body_metrics = painter.fontMetrics()
            for line in subtitle_lines:
                painter.drawText(panel_left + padding, current_y + body_metrics.ascent(), line)
                current_y += body_metrics.height() + 2

        if scaled_template:
            available_height = panel_top + panel_h - padding - current_y
            draw_height = min(available_height, scaled_template.height())
            draw_pixmap = scaled_template
            if draw_height < scaled_template.height():
                draw_pixmap = scaled_template.copy(0, scaled_template.height() - draw_height, scaled_template.width(), draw_height)
            painter.drawPixmap(panel_left + padding, panel_top + panel_h - padding - draw_pixmap.height(), draw_pixmap)

        painter.end()

