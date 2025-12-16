# -*- coding: utf-8 -*-
"""
截图序列预览对话框
左侧缩略图列表 + 右侧大图，支持滚轮缩放、拖拽平移、键盘左右切换
"""

from PyQt6 import QtCore, QtWidgets, QtGui
from PyQt6.QtCore import Qt

from app.ui.foundation.base_widgets import BaseDialog


class _ImageHistoryPreviewDialog(BaseDialog):
    """图片预览对话框：左侧缩略图列表 + 右侧大图，支持滚轮缩放、拖拽平移、键盘左右切换。"""

    def __init__(self, images: list[QtGui.QPixmap], start_index: int, parent: QtWidgets.QWidget | None = None, titles: list[str] | None = None):
        super().__init__(
            title="截图预览（当前运行序列）",
            width=1200,
            height=800,
            buttons=QtWidgets.QDialogButtonBox.StandardButton.Close,
            parent=parent,
        )
        self._images = images
        self._current_index = max(0, min(start_index, len(images) - 1))
        self._current_scale = 1.0
        self._titles = list(titles) if isinstance(titles, list) else [""] * len(images)

        # 底部关闭按钮不需要显示，隐藏 BaseDialog 自带按钮栏
        self.button_box.hide()
        self.button_box.setEnabled(False)

        container = QtWidgets.QWidget()
        root = QtWidgets.QHBoxLayout(container)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.content_layout.addWidget(container)

        # 左侧缩略图列表
        self.thumb_list = QtWidgets.QListWidget()
        self.thumb_list.setViewMode(QtWidgets.QListView.ViewMode.IconMode)
        self.thumb_list.setIconSize(QtCore.QSize(160, 90))
        self.thumb_list.setResizeMode(QtWidgets.QListView.ResizeMode.Adjust)
        self.thumb_list.setMovement(QtWidgets.QListView.Movement.Static)
        self.thumb_list.setSpacing(6)
        self.thumb_list.setUniformItemSizes(True)
        self.thumb_list.setWordWrap(False)
        self.thumb_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.thumb_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.thumb_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.thumb_list.setMinimumWidth(200)
        for i, pm in enumerate(self._images):
            thumb = pm.scaled(160, 90, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            title_text = str(self._titles[i] if i < len(self._titles) else "")
            if len(title_text) > 24:
                title_text = title_text[:24] + "…"
            item = QtWidgets.QListWidgetItem(QtGui.QIcon(thumb), f"{i+1}. {title_text}")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, i)
            self.thumb_list.addItem(item)
        self.thumb_list.currentItemChanged.connect(self._on_thumb_changed)
        self.thumb_list.itemClicked.connect(self._on_thumb_clicked)
        root.addWidget(self.thumb_list)

        # 右侧大图区域（沿用平移/缩放交互）
        right_panel = QtWidgets.QVBoxLayout()
        right_panel.setContentsMargins(0, 0, 0, 0)
        right_panel.setSpacing(0)

        self.scroll_area = QtWidgets.QScrollArea(self)
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.image_label = QtWidgets.QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setBackgroundRole(QtGui.QPalette.ColorRole.Base)
        self.image_label.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Ignored)
        self.image_label.setScaledContents(False)

        self.scroll_area.setWidget(self.image_label)
        right_panel.addWidget(self.scroll_area)
        root.addLayout(right_panel, 1)

        # 初始化窗口尺寸
        screen = QtWidgets.QApplication.primaryScreen()
        if screen is not None and len(self._images) > 0:
            pm = self._images[self._current_index]
            available = screen.availableGeometry()
            w = min(int(available.width() * 0.95), max(1000, pm.width() + 240))
            h = min(int(available.height() * 0.95), max(720, pm.height()))
            self.resize(w, h)
        else:
            self.resize(1200, 800)

        # 交互：滚轮缩放 + 拖拽平移
        self._is_panning = False
        self._last_drag_pos = QtCore.QPointF()
        viewport = self.scroll_area.viewport()
        viewport.setCursor(Qt.CursorShape.OpenHandCursor)
        self.image_label.setCursor(Qt.CursorShape.OpenHandCursor)
        viewport.installEventFilter(self)
        self.image_label.installEventFilter(self)

        # 设定默认选中与显示
        if self.thumb_list.count() > 0:
            self.thumb_list.setCurrentRow(self._current_index)
            self._set_current_image(self._current_index, reset_scale=True)
            # 延迟一帧在布局完成后再次按视口自适应，以避免初始化阶段 viewport 尺寸过小导致缩得过度
            QtCore.QTimer.singleShot(0, self._fit_to_viewport_after_layout)

    # 切换缩略图
    def _on_thumb_changed(self, current: QtWidgets.QListWidgetItem | None, previous: QtWidgets.QListWidgetItem | None) -> None:
        if current is None:
            return
        idx = int(current.data(QtCore.Qt.ItemDataRole.UserRole))
        self._set_current_image(idx, reset_scale=True)

    def _on_thumb_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        idx = int(item.data(QtCore.Qt.ItemDataRole.UserRole))
        self._set_current_image(idx, reset_scale=True)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_A):
            self._navigate(-1)
            return
        if event.key() in (Qt.Key.Key_Right, Qt.Key.Key_D):
            self._navigate(1)
            return
        super().keyPressEvent(event)

    def _navigate(self, delta: int) -> None:
        if len(self._images) == 0:
            return
        new_index = self._current_index + delta
        if new_index < 0:
            new_index = 0
        if new_index >= len(self._images):
            new_index = len(self._images) - 1
        if new_index != self._current_index:
            self._current_index = new_index
            self.thumb_list.setCurrentRow(new_index)
            self._set_current_image(new_index, reset_scale=True)

    # 核心：设置当前大图
    def _set_current_image(self, index: int, reset_scale: bool) -> None:
        self._current_index = index
        pm = self._images[index]
        self._original_pixmap = pm
        if reset_scale:
            # 初始按视口自适应缩放，保证整图完整显示且居中
            vp_size = self.scroll_area.viewport().size()
            pw = int(pm.width()) if pm is not None else 0
            ph = int(pm.height()) if pm is not None else 0
            vw = int(vp_size.width())
            vh = int(vp_size.height())
            if pw > 0 and ph > 0 and vw > 0 and vh > 0:
                sx = float(vw) / float(pw)
                sy = float(vh) / float(ph)
                self._current_scale = float(min(sx, sy, 1.0))
            else:
                self._current_scale = 1.0
        self._apply_scale(self._current_scale, force=True)

    def _fit_to_viewport_after_layout(self) -> None:
        # 若用户未滚轮缩放过（仍是首次比例），按最新 viewport 尺寸再做一次自适应
        if not hasattr(self, "_original_pixmap"):
            return
        pm = self._original_pixmap
        if pm is None or pm.isNull():
            return
        vp = self.scroll_area.viewport().size()
        vw = int(vp.width())
        vh = int(vp.height())
        pw = int(pm.width())
        ph = int(pm.height())
        if vw <= 0 or vh <= 0 or pw <= 0 or ph <= 0:
            return
        sx = float(vw) / float(pw)
        sy = float(vh) / float(ph)
        new_scale = float(min(sx, sy, 1.0))
        # 若当前比例明显小于自适应结果（初始化阶段可能过小），则提升到自适应比例
        if new_scale > self._current_scale + 1e-3:
            self._apply_scale(new_scale, force=True)

    # 视图交互：缩放/平移
    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        self._handle_wheel_zoom(event)

    def _apply_scale(self, scale: float, force: bool = False) -> None:
        if not hasattr(self, "_original_pixmap"):
            return
        if not force and abs(scale - self._current_scale) < 1e-6:
            return
        self._current_scale = scale
        target_w = int(self._original_pixmap.width() * self._current_scale)
        target_h = int(self._original_pixmap.height() * self._current_scale)
        if target_w <= 0:
            target_w = 1
        if target_h <= 0:
            target_h = 1
        scaled = self._original_pixmap.scaled(
            target_w,
            target_h,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_label.setPixmap(scaled)
        self.image_label.resize(target_w, target_h)

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if obj is self.scroll_area.viewport() or obj is self.image_label:
            if event.type() == QtCore.QEvent.Type.Wheel and isinstance(event, QtGui.QWheelEvent):
                self._handle_wheel_zoom(event)
                return True
            if event.type() == QtCore.QEvent.Type.MouseButtonPress and isinstance(event, QtGui.QMouseEvent):
                if event.button() == QtCore.Qt.MouseButton.LeftButton:
                    self._is_panning = True
                    self._last_drag_pos = event.globalPosition()
                    self.scroll_area.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
                    self.image_label.setCursor(Qt.CursorShape.ClosedHandCursor)
                    event.accept()
                    return True
            elif event.type() == QtCore.QEvent.Type.MouseMove and isinstance(event, QtGui.QMouseEvent):
                if self._is_panning:
                    delta = event.globalPosition() - self._last_drag_pos
                    self._last_drag_pos = event.globalPosition()
                    hsb = self.scroll_area.horizontalScrollBar()
                    vsb = self.scroll_area.verticalScrollBar()
                    hsb.setValue(hsb.value() - int(delta.x()))
                    vsb.setValue(vsb.value() - int(delta.y()))
                    event.accept()
                    return True
            elif event.type() == QtCore.QEvent.Type.MouseButtonRelease and isinstance(event, QtGui.QMouseEvent):
                if event.button() == QtCore.Qt.MouseButton.LeftButton:
                    self._is_panning = False
                    self.scroll_area.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
                    self.image_label.setCursor(Qt.CursorShape.OpenHandCursor)
                    event.accept()
                    return True
        return super().eventFilter(obj, event)

    def _handle_wheel_zoom(self, event: QtGui.QWheelEvent) -> None:
        from app.ui.foundation.interaction_helpers import handle_wheel_zoom_for_scroll_area
        handle_wheel_zoom_for_scroll_area(
            self.scroll_area,
            self.image_label,
            event,
            base_factor_per_step=1.15,
            min_scale=0.1,
            max_scale=8.0,
            current_scale_getter=lambda: self._current_scale,
            apply_scale=lambda s: self._apply_scale(s),
        )

    def _zoom_with_anchor(self, new_scale: float, global_pos: QtCore.QPointF) -> None:
        viewport = self.scroll_area.viewport()
        hsb = self.scroll_area.horizontalScrollBar()
        vsb = self.scroll_area.verticalScrollBar()

        vp_mouse = viewport.mapFromGlobal(QtCore.QPoint(int(global_pos.x()), int(global_pos.y())))
        lbl_mouse_before = self.image_label.mapFromGlobal(QtCore.QPoint(int(global_pos.x()), int(global_pos.y())))
        ratio_x = 0.0 if self.image_label.width() <= 1 else lbl_mouse_before.x() / float(self.image_label.width())
        ratio_y = 0.0 if self.image_label.height() <= 1 else lbl_mouse_before.y() / float(self.image_label.height())

        self._apply_scale(new_scale)

        anchor_x_new = int(self.image_label.width() * ratio_x)
        anchor_y_new = int(self.image_label.height() * ratio_y)
        target_scroll_x = anchor_x_new - int(vp_mouse.x())
        target_scroll_y = anchor_y_new - int(vp_mouse.y())

        target_scroll_x = max(0, min(target_scroll_x, hsb.maximum()))
        target_scroll_y = max(0, min(target_scroll_y, vsb.maximum()))
        hsb.setValue(target_scroll_x)
        vsb.setValue(target_scroll_y)

