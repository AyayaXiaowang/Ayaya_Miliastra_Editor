from __future__ import annotations

import time

from PyQt6 import QtCore, QtGui, QtWidgets

from app.ui.graph.graph_palette import GraphPalette
from app.ui.graph.graph_view.overlays.ruler_overlay_painter import RulerOverlayPainter


class PanFreezeOverlay(QtWidgets.QWidget):
    """平移/缩放期间的"全场景快照"覆盖层。

    设计理念：
    - 预先将整个节点图（不仅是当前视口）渲染为一张全场景缓存图；
    - 平移/缩放开始时显示覆盖层，交互过程中直接从缓存图中取对应视口区域绘制（极低成本）；
    - 松手后隐藏覆盖层，恢复真实渲染。

    优势（对比旧版 viewport.grab 仅抓可见区域）：
    - 全场景可见：平移时能看到原本不在视口内的节点，不再有空白区域；
    - 缓存复用：只有场景内容变化（节点移动/增删）时标记脏，下次冻结时按需重建；
    - 缩放自然：缩放时从全场景图中裁剪对应区域，效果更接近真实渲染。

    层级设计：
    - 父控件为 **viewport**（而非 view），使其与 MiniMapWidget 同为 viewport 的直接子控件，
      从而 minimap.raise_() 能正确将小地图置于覆盖层之上。
    - 冻结期间 GraphView.paintEvent 不运行（NoViewportUpdate），标尺由覆盖层自行补绘。
    - view 级子控件（SearchOverlay/PerfOverlay/TopRightButtons）自然位于 viewport 之上，
      无需额外处理。

    注意：
    - 覆盖层必须对鼠标事件透明，否则会阻断 ScrollHandDrag；
    - 当 NoViewportUpdate 生效时，Qt 不会调用 viewport.scroll()，因此 viewport 的
      子控件（包括本覆盖层和 MiniMap）不会被物理滚动偏移；
    - 覆盖层绘制保持 fillRect + drawPixmap + ruler 的常数级开销。
    """

    # 全场景缓存的最大像素尺寸（宽或高不超过此值），平衡画质与内存
    MAX_CACHE_DIM: int = 4096
    # 场景边距（场景单位），避免节点贴边
    SCENE_MARGIN: float = 200.0
    # 局部高清缓存：目标覆盖倍率（相对于视口的 sceneRect 宽高）
    #
    # 说明：
    # - 值越大，拖拽期间“高清可用范围”越大，但 begin_freeze 时的渲染成本越高；
    # - 会根据当前视口像素尺寸自动限幅，确保像素尺寸不超过 LOCAL_MAX_CACHE_DIM（除非视口本身更大）。
    LOCAL_TARGET_OVERSCAN: float = 1.7
    # 局部高清缓存的最大像素尺寸上限（宽或高不超过此值，除非视口本身更大）。
    LOCAL_MAX_CACHE_DIM: int = 4096

    def __init__(self, view: QtWidgets.QGraphicsView) -> None:
        # 父控件改为 viewport：与 MiniMapWidget 同级，
        # 使 raise_() 可以正确控制两者的 z-order。
        viewport = view.viewport()
        super().__init__(viewport if viewport is not None else view)
        self._view: QtWidgets.QGraphicsView = view

        # --- 全场景缓存 ---
        self._scene_pixmap: QtGui.QPixmap | None = None  # 全场景渲染结果
        self._scene_rect: QtCore.QRectF = QtCore.QRectF()  # 缓存对应的场景坐标范围
        self._scene_scale: float = 1.0  # 场景坐标 → pixmap 像素的缩放因子
        self._cache_dirty: bool = True  # 是否需要重建缓存
        self._rebuilding: bool = False  # 防止 scene.render 触发 _on_scene_changed 循环

        # --- 视口周边的局部高清缓存（用于保证冻结期间的可读性） ---
        #
        # 设计目标：
        # - 全局缓存用于“永远有内容、不空白”，但在超大图下会因为 MAX_CACHE_DIM 被迫降采样导致模糊；
        # - 局部缓存只覆盖视口附近（可配置 overscan），像素密度以当前 view 缩放为基准，
        #   从而在冻结期间仍能清晰阅读节点标题/端口等细节。
        self._local_pixmap: QtGui.QPixmap | None = None
        self._local_scene_rect: QtCore.QRectF = QtCore.QRectF()
        self._local_scene_scale_x: float = 1.0  # 场景坐标 → pixmap 像素的缩放因子（通常≈view_scale*dpr）
        self._local_scene_scale_y: float = 1.0
        self._local_cache_dirty: bool = True
        self._local_built_view_scale: float = 0.0
        self._local_built_dpr: float = 0.0

        # --- 场景连接追踪（避免重复连接/断连残留） ---
        self._connected_scene: QtWidgets.QGraphicsScene | None = None

        self.setObjectName("panFreezeOverlay")
        self.setVisible(False)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)

    # ------------------------------------------------------------------ #
    #  场景连接与缓存管理
    # ------------------------------------------------------------------ #

    def ensure_scene_connected(self) -> None:
        """确保已连接到当前视图场景的变化信号（场景切换时自动断旧连新）。"""
        scene = self._view.scene() if self._view else None
        if scene is self._connected_scene:
            return

        # 断开旧场景（若 C++ 对象已销毁，Qt 已自动断开信号，此处仅清理 Python 侧引用）
        old = self._connected_scene
        self._connected_scene = None
        if old is not None and hasattr(old, "changed"):
            from PyQt6 import sip
            if not sip.isdeleted(old):
                old.changed.disconnect(self._on_scene_changed)

        # 连接新场景
        self._connected_scene = scene
        if scene is not None and hasattr(scene, "changed"):
            scene.changed.connect(self._on_scene_changed)

        # 新场景 → 缓存失效
        self._cache_dirty = True
        self._scene_pixmap = None
        self._local_cache_dirty = True
        self._local_pixmap = None

    def _on_scene_changed(self, *_args) -> None:
        """场景内容变化回调：仅标记缓存为脏。

        不做任何定时器调度或主动重建——缓存会在下次 begin_freeze() 时按需重建，
        避免"恢复真实渲染→scene.changed 密集触发→后台 scene.render() 全图"导致的卡顿。
        """
        # scene.render() 期间不标记脏（render 本身会触发 changed）
        if self._rebuilding:
            return
        self._cache_dirty = True
        self._local_cache_dirty = True

    def invalidate_cache(self) -> None:
        """外部强制失效缓存（例如切换图/大规模批量操作后）。"""
        self._cache_dirty = True
        self._scene_pixmap = None
        self._local_cache_dirty = True
        self._local_pixmap = None

    def _get_viewport_scene_rect(self) -> QtCore.QRectF:
        view = self._view
        viewport_widget = view.viewport() if view else None
        if viewport_widget is None:
            return QtCore.QRectF()
        return view.mapToScene(viewport_widget.rect()).boundingRect()

    def _get_view_scale(self) -> float:
        view = self._view
        if view is None:
            return 1.0
        # 当前实现假设缩放为等比缩放（m11==m22）
        s = float(view.transform().m11())
        return abs(s) if s != 0.0 else 1.0

    def _get_device_pixel_ratio(self) -> float:
        # QWidget 本身是 QPaintDevice；使用自身 dpr 即可覆盖 per-monitor DPI。
        dpr = float(self.devicePixelRatioF())
        return dpr if dpr > 0.0 else 1.0

    def _rebuild_local_cache(self, viewport_scene_rect: QtCore.QRectF) -> None:
        """重建“视口周边”的局部高清缓存。

        约束：
        - 局部缓存像素尺寸以“视口像素尺寸 × overscan”计算，并自动限幅；
        - 像素密度以当前 view 的缩放为基准（≈ view_scale × devicePixelRatio），保证冻结期间可读性；
        - 不在此处做任何异步或定时器调度：重建由 begin_freeze() 按需触发。
        """
        scene = self._view.scene() if self._view else None
        if scene is None or viewport_scene_rect.isEmpty():
            self._local_pixmap = None
            self._local_cache_dirty = True
            return

        viewport_widget = self._view.viewport() if self._view else None
        if viewport_widget is None:
            self._local_pixmap = None
            self._local_cache_dirty = True
            return

        dpr = self._get_device_pixel_ratio()
        view_scale = self._get_view_scale()

        vw = max(1, int(viewport_widget.width()))
        vh = max(1, int(viewport_widget.height()))
        vw_phys = float(vw) * dpr
        vh_phys = float(vh) * dpr

        # 像素尺寸限幅：LOCAL_MAX_CACHE_DIM 作为“期望上限”，但视口本身更大时必须至少覆盖视口。
        effective_max_dim = max(self.LOCAL_MAX_CACHE_DIM, int(vw_phys), int(vh_phys))
        # 当前视口下，允许的最大 overscan（保证 w/h 均不超过 effective_max_dim）
        max_factor_w = float(effective_max_dim) / max(1.0, vw_phys)
        max_factor_h = float(effective_max_dim) / max(1.0, vh_phys)
        max_factor = max(1.0, min(max_factor_w, max_factor_h))
        factor = max(1.0, min(float(self.LOCAL_TARGET_OVERSCAN), max_factor))

        # 以 viewport_scene_rect 为中心扩展局部 scene rect
        expand_x = float(viewport_scene_rect.width()) * (factor - 1.0) * 0.5
        expand_y = float(viewport_scene_rect.height()) * (factor - 1.0) * 0.5
        local_scene_rect = viewport_scene_rect.adjusted(-expand_x, -expand_y, expand_x, expand_y)
        if local_scene_rect.isEmpty():
            self._local_pixmap = None
            self._local_cache_dirty = True
            return

        pw = max(1, int(vw_phys * factor))
        ph = max(1, int(vh_phys * factor))

        image = QtGui.QImage(pw, ph, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QtGui.QColor(GraphPalette.CANVAS_BG))
        painter = QtGui.QPainter(image)
        # 复用 view 的 renderHints 以保持风格一致（冻结期间绘制只发生在缓存构建这一刻）
        if self._view is not None:
            painter.setRenderHints(self._view.renderHints())

        self._rebuilding = True
        scene.render(painter, QtCore.QRectF(0.0, 0.0, float(pw), float(ph)), local_scene_rect)
        self._rebuilding = False

        painter.end()

        self._local_pixmap = QtGui.QPixmap.fromImage(image)
        self._local_scene_rect = local_scene_rect
        # scene → pixmap 像素缩放（通常≈ view_scale*dpr；受 pw/ph 取整影响会有微小偏差）
        self._local_scene_scale_x = float(pw) / max(1.0, float(local_scene_rect.width()))
        self._local_scene_scale_y = float(ph) / max(1.0, float(local_scene_rect.height()))
        self._local_cache_dirty = False
        self._local_built_view_scale = view_scale
        self._local_built_dpr = dpr

    def _ensure_local_cache_for_viewport(self, viewport_scene_rect: QtCore.QRectF) -> None:
        """确保局部高清缓存覆盖当前视口（必要时同步重建）。

        为避免交互期间卡顿，局部缓存只会在 begin_freeze() 入口按需构建/切换；
        scroll/zoom 的每帧更新仅触发 repaint，不做 scene.render。
        """
        if viewport_scene_rect.isEmpty():
            return

        view_scale = self._get_view_scale()
        dpr = self._get_device_pixel_ratio()

        local_ok = (
            self._local_pixmap is not None
            and not self._local_pixmap.isNull()
            and self._local_scene_rect.contains(viewport_scene_rect)
            # float 误差容忍：transform/dpr 在不同平台上可能出现极小抖动，避免无意义重建
            and abs(float(self._local_built_view_scale) - view_scale) < 1e-3
            and abs(float(self._local_built_dpr) - dpr) < 1e-3
        )
        if local_ok:
            return

        # 若缓存存在但已脏：仍可直接用旧缓存以避免延迟；
        # 但当“视口不在覆盖范围/缩放或 DPI 变化”时，继续用旧缓存会明显模糊，
        # 因此这里选择同步重建一次以保证冻结期间的可读性。
        self._rebuild_local_cache(viewport_scene_rect)

    def _rebuild_cache(self) -> None:
        """重建全场景渲染缓存。

        将 scene.itemsBoundingRect() 范围（含边距）渲染到一张受尺寸上限约束的位图中，
        供后续冻结期间按视口区域裁剪绘制。
        """
        scene = self._view.scene() if self._view else None
        if scene is None:
            self._scene_pixmap = None
            self._cache_dirty = True
            return

        items_rect = scene.itemsBoundingRect()
        if items_rect.isEmpty():
            self._scene_pixmap = None
            self._cache_dirty = False
            return
        margin = self.SCENE_MARGIN
        scene_rect = items_rect.adjusted(-margin, -margin, margin, margin)

        # 计算缩放因子使 pixmap 像素尺寸不超过上限
        sw = max(1.0, float(scene_rect.width()))
        sh = max(1.0, float(scene_rect.height()))
        scale = min(1.0, float(self.MAX_CACHE_DIM) / max(sw, sh))
        pw = max(1, int(sw * scale))
        ph = max(1, int(sh * scale))

        image = QtGui.QImage(pw, ph, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QtGui.QColor(GraphPalette.CANVAS_BG))
        painter = QtGui.QPainter(image)

        # 渲染期间屏蔽 _on_scene_changed，避免 scene.render 内部触发
        # scene.changed → _on_scene_changed → 立即标脏的无用循环
        self._rebuilding = True
        scene.render(painter, QtCore.QRectF(0.0, 0.0, float(pw), float(ph)), scene_rect)
        self._rebuilding = False

        painter.end()

        self._scene_pixmap = QtGui.QPixmap.fromImage(image)
        self._scene_rect = scene_rect
        self._scene_scale = scale
        self._cache_dirty = False

    # ------------------------------------------------------------------ #
    #  冻结生命周期
    # ------------------------------------------------------------------ #

    def begin_freeze(self) -> None:
        """显示覆盖层（使用全场景缓存）。

        - 如果缓存不存在（首次冻结或场景切换后）会立即重建；
        - 如果缓存已存在但标记为脏（例如节点移动后），仍使用旧缓存以避免延迟。
        """
        viewport = self._view.viewport() if hasattr(self._view, "viewport") else None
        if viewport is None:
            return

        self.ensure_scene_connected()

        # 首次冻结或缓存被清空：必须立即构建
        if self._scene_pixmap is None:
            self._rebuild_cache()

        # 若缓存存在但标记为脏：使用旧缓存（避免冻结开始时的延迟）

        # 父控件为 viewport，使用 viewport.rect()（原点 0,0）
        self.setGeometry(viewport.rect())
        self.show()
        # 不在这里 raise_：由控制器负责把右上角控件/小地图等置顶，避免覆盖层挡住 UI 控件。

        # 局部高清缓存：在冻结开始时按需构建（只发生一次，不会在交互过程中重建）
        viewport_scene_rect = self._get_viewport_scene_rect()
        if not viewport_scene_rect.isEmpty():
            t0 = time.perf_counter()
            self._ensure_local_cache_for_viewport(viewport_scene_rect)
            # 若局部缓存构建失败（例如 scene None），不阻断冻结；paintEvent 会自然回退到全局缓存/背景色。
            _ = (time.perf_counter() - float(t0))  # 保留钩子位以便未来接入 perf overlay
            self.update()

    def end_freeze(self) -> None:
        """隐藏覆盖层并释放冻结状态。"""
        self.hide()

    @property
    def is_active(self) -> bool:
        return bool(self.isVisible()) and (self._scene_pixmap is not None)

    # ------------------------------------------------------------------ #
    #  交互期间的更新触发
    # ------------------------------------------------------------------ #

    def scroll_by(self, dx: int, dy: int) -> None:
        """视图滚动时触发重绘。

        全场景缓存模式下不需要累积偏移量——视图的 mapToScene 已反映最新滚动位置，
        paintEvent 中直接据此裁剪缓存图的对应区域。
        """
        _ = dx, dy  # 参数保留以兼容外部调用签名
        if not self.is_active:
            return
        self.update()

    def set_zoom_transform(self, scale: float, *, pivot: QtCore.QPointF) -> None:
        """缩放期间触发重绘。

        全场景缓存模式下不需要相对缩放/枢轴计算——视图变换已包含最新缩放比例，
        paintEvent 中直接据此裁剪缓存图的对应区域。
        """
        _ = scale, pivot  # 参数保留以兼容外部调用签名
        if not self.is_active:
            return
        self.update()

    def ensure_geometry_synced(self) -> None:
        """确保覆盖层几何覆盖 viewport（resize 时调用）。"""
        viewport = self._view.viewport() if hasattr(self._view, "viewport") else None
        if viewport is None:
            return
        # 父控件为 viewport，使用 rect()（原点 0,0）
        geom = viewport.rect()
        if self.geometry() != geom:
            self.setGeometry(geom)

    # ------------------------------------------------------------------ #
    #  绘制
    # ------------------------------------------------------------------ #

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # type: ignore[override]
        _ = event
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)
        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.fillRect(self.rect(), QtGui.QColor(GraphPalette.CANVAS_BG))

        view = self._view
        viewport_widget = view.viewport() if view else None
        viewport_scene_rect = QtCore.QRectF()
        if viewport_widget is not None and view is not None:
            viewport_scene_rect = view.mapToScene(viewport_widget.rect()).boundingRect()

        # 先绘制全场景低清缓存（保证永远不空白），再叠加局部高清缓存（保证可读性）
        pix = self._scene_pixmap
        if pix is not None and not pix.isNull() and not viewport_scene_rect.isEmpty():
            # 从视图变换获取当前视口在场景坐标系中的范围
            # （视图的 scrollContentsBy / 缩放变换在调用 scroll_by / set_zoom_transform 前
            #   已由 Qt 内部更新完成，mapToScene 始终反映最新状态）
            # 将场景坐标映射到 pixmap 像素坐标
            sr = self._scene_rect
            s = self._scene_scale

            src_x = (viewport_scene_rect.x() - sr.x()) * s
            src_y = (viewport_scene_rect.y() - sr.y()) * s
            src_w = viewport_scene_rect.width() * s
            src_h = viewport_scene_rect.height() * s

            source_rect = QtCore.QRectF(src_x, src_y, src_w, src_h)
            target_rect = QtCore.QRectF(self.rect())

            # QPainter.drawPixmap 会自动裁剪超出 pixmap 范围的源区域，
            # 超出部分由上方的 fillRect 背景色覆盖。
            #
            # 体验取舍：
            # - 全局底图在超大图下必然是“低清被放大”的结果；
            # - 默认关闭 SmoothPixmapTransform 会让放大后的像素呈现明显“块状马赛克”，用户观感更像“黑方块”；
            # - 这里仅对全局底图开启平滑变换，让它更像“模糊打底”，同时局部高清层仍保持锐利。
            painter.save()
            painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.drawPixmap(target_rect, pix, source_rect)
            painter.restore()

        local_pix = self._local_pixmap
        if (
            local_pix is not None
            and not local_pix.isNull()
            and not viewport_scene_rect.isEmpty()
            and view is not None
        ):
            overlap = viewport_scene_rect.intersected(self._local_scene_rect)
            if not overlap.isEmpty():
                # 局部缓存：将重叠的场景区域映射到局部 pixmap 像素坐标
                lsr = self._local_scene_rect
                lsx = self._local_scene_scale_x
                lsy = self._local_scene_scale_y
                lsrc_x = (overlap.x() - lsr.x()) * lsx
                lsrc_y = (overlap.y() - lsr.y()) * lsy
                lsrc_w = overlap.width() * lsx
                lsrc_h = overlap.height() * lsy
                local_source_rect = QtCore.QRectF(lsrc_x, lsrc_y, lsrc_w, lsrc_h)

                # 将 overlap 的场景坐标映射到 viewport 坐标（overlay 与 viewport 同坐标原点）
                tl = view.mapFromScene(overlap.topLeft())
                br = view.mapFromScene(overlap.bottomRight())
                x0 = float(min(tl.x(), br.x()))
                y0 = float(min(tl.y(), br.y()))
                x1 = float(max(tl.x(), br.x()))
                y1 = float(max(tl.y(), br.y()))
                local_target_rect = QtCore.QRectF(x0, y0, max(0.0, x1 - x0), max(0.0, y1 - y0))

                painter.drawPixmap(local_target_rect, local_pix, local_source_rect)

        # 冻结期间 GraphView.paintEvent 不运行（NoViewportUpdate），
        # 标尺需要由覆盖层自行补绘。RulerOverlayPainter 通过
        # view.mapToScene/mapFromScene 计算坐标，视图变换在冻结期间仍然实时更新。
        RulerOverlayPainter.paint(self._view, painter)

        painter.end()
