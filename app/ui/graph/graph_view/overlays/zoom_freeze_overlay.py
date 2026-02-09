from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

from app.ui.graph.graph_palette import GraphPalette


class ZoomFreezeOverlay(QtWidgets.QWidget):
    """滚轮缩放期间的“视口快照”覆盖层。

    目标：
    - 缩放期间维持极致流畅：避免 `scene.render(...)` / 全量 items 重绘；
    - 仅在 begin_freeze 时抓取一次“当前视口图像”（不含子控件），缩放过程中对该图像做仿射变换；
    - 停止滚轮后立即恢复真实渲染。

    取舍：
    - 与 PanFreezeOverlay 的“全场景缓存”不同，这里只抓取当前视口，因此缩放过程中不会出现“视口外的新内容”；
      但滚轮 debounce 较短，真实渲染会很快恢复显示新区域，换取缩放的丝滑体验。
    """

    # 视口快照的最大像素尺寸（宽或高不超过此值），避免 4K + 高 DPI 下抓图过大导致卡顿/内存飙升。
    # 说明：该覆盖层的目标是“缩放过程丝滑”，而不是完美画质；因此默认更偏向减小抓图尺寸以降低
    # 每步滚轮的绘制与一次性抓图开销（真实清晰渲染会在滚轮停止后恢复）。
    MAX_CAPTURE_DIM: int = 2048

    def __init__(self, view: QtWidgets.QGraphicsView) -> None:
        viewport = view.viewport()
        super().__init__(viewport if viewport is not None else view)
        self._view: QtWidgets.QGraphicsView = view

        self._base_pixmap: QtGui.QPixmap | None = None
        # 预览用的“相对缩放 + 枢轴”（均为 viewport 坐标系）
        self._preview_scale: float = 1.0
        self._preview_pivot: QtCore.QPointF = QtCore.QPointF(0.0, 0.0)

        self.setObjectName("zoomFreezeOverlay")
        self.setVisible(False)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)

    # ------------------------------------------------------------------ #
    #  生命周期
    # ------------------------------------------------------------------ #

    def begin_freeze(self) -> None:
        viewport = self._view.viewport() if hasattr(self._view, "viewport") else None
        if viewport is None:
            return

        self.setGeometry(viewport.rect())
        self._base_pixmap = self._capture_viewport_without_children()
        self._preview_scale = 1.0
        self._preview_pivot = QtCore.QPointF(float(viewport.width()) * 0.5, float(viewport.height()) * 0.5)

        self.show()
        self.update()

    def end_freeze(self) -> None:
        self.hide()
        # 释放像素缓存，避免长时间占用显存/内存
        self._base_pixmap = None
        self._preview_scale = 1.0
        self._preview_pivot = QtCore.QPointF(0.0, 0.0)

    @property
    def is_active(self) -> bool:
        return bool(self.isVisible()) and (self._base_pixmap is not None)

    # ------------------------------------------------------------------ #
    #  交互期间更新触发
    # ------------------------------------------------------------------ #

    def scroll_by(self, dx: int, dy: int) -> None:
        _ = dx, dy
        if not self.is_active:
            return
        self.update()

    def set_zoom_transform(self, scale: float, *, pivot: QtCore.QPointF) -> None:
        if not self.is_active:
            return
        s = float(scale or 1.0)
        if s <= 0.0:
            s = 1.0
        self._preview_scale = s
        self._preview_pivot = pivot
        self.update()

    def ensure_geometry_synced(self) -> None:
        viewport = self._view.viewport() if hasattr(self._view, "viewport") else None
        if viewport is None:
            return
        geom = viewport.rect()
        if self.geometry() != geom:
            self.setGeometry(geom)

    # ------------------------------------------------------------------ #
    #  抓取快照
    # ------------------------------------------------------------------ #

    def _capture_viewport_without_children(self) -> QtGui.QPixmap | None:
        """抓取 viewport 当前内容（不含 viewport 子控件，如 MiniMap / 覆盖层）。"""
        viewport = self._view.viewport() if hasattr(self._view, "viewport") else None
        if viewport is None:
            return None

        w = int(viewport.width())
        h = int(viewport.height())
        if w <= 0 or h <= 0:
            return None

        base_dpr = float(viewport.devicePixelRatioF())
        if base_dpr <= 0.0:
            base_dpr = 1.0

        desired_pw = float(w) * base_dpr
        desired_ph = float(h) * base_dpr
        scale = min(1.0, float(self.MAX_CAPTURE_DIM) / max(1.0, max(desired_pw, desired_ph)))
        pw = max(1, int(desired_pw * scale))
        ph = max(1, int(desired_ph * scale))
        effective_dpr = float(base_dpr * scale)
        if effective_dpr <= 0.0:
            effective_dpr = 1.0

        image = QtGui.QImage(pw, ph, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QtGui.QColor(GraphPalette.CANVAS_BG))
        # 元数据：让该 image 在后续作为 pixmap 绘制时按“逻辑像素”显示
        image.setDevicePixelRatio(effective_dpr)

        painter = QtGui.QPainter(image)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)
        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, False)

        # 关键：不绘制子控件（MiniMap/TopRight 等），避免它们被缩放进快照里。
        flags = QtWidgets.QWidget.RenderFlag.DrawWindowBackground
        viewport.render(painter, QtCore.QPoint(), QtGui.QRegion(viewport.rect()), flags)
        painter.end()

        pix = QtGui.QPixmap.fromImage(image)
        pix.setDevicePixelRatio(effective_dpr)
        return pix

    # ------------------------------------------------------------------ #
    #  绘制
    # ------------------------------------------------------------------ #

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # type: ignore[override]
        _ = event
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)
        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.fillRect(self.rect(), QtGui.QColor(GraphPalette.CANVAS_BG))

        pix = self._base_pixmap
        if pix is not None and not pix.isNull():
            # 预览：对“开始缩放时的视口快照”做一个“绕 pivot 缩放”的仿射变换即可。
            #
            # 等价关系：
            # p' = pivot + s * (p - pivot) = s*p + (1-s)*pivot
            s = float(getattr(self, "_preview_scale", 1.0) or 1.0)
            pivot = getattr(self, "_preview_pivot", QtCore.QPointF(0.0, 0.0))
            if s <= 0.0:
                s = 1.0
            src = QtCore.QRectF(0.0, 0.0, float(pix.width()), float(pix.height()))
            dx = float(pivot.x()) * (1.0 - s)
            dy = float(pivot.y()) * (1.0 - s)
            dst = QtCore.QRectF(dx, dy, float(src.width()) * s, float(src.height()) * s)
            painter.drawPixmap(dst, pix, src)
        painter.end()

