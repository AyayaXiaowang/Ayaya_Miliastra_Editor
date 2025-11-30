from __future__ import annotations

from PyQt6 import QtGui, QtWidgets, QtCore


def _extract_wheel_delta(event: QtGui.QWheelEvent) -> float:
    """
    提取统一的滚轮“步进”增量（所有 QGraphicsView/QScrollArea 缩放都应复用本函数）。

    - 鼠标滚轮：angleDelta().y()（标准 120 为一步）
    - 触控板：pixelDelta().y()（以 120 像素近似一标准步）
    返回值为“步数”，可正可负，可能为浮点数（触控板）。
    """
    angle = event.angleDelta().y()
    if angle != 0:
        return float(angle) / 120.0
    pixel = event.pixelDelta().y()
    if pixel != 0:
        return float(pixel) / 120.0
    return 0.0


def handle_wheel_zoom_for_view(
    view: QtWidgets.QGraphicsView,
    event: QtGui.QWheelEvent,
    *,
    base_factor_per_step: float = 1.15,
    min_scale: float = 0.2,
    max_scale: float = 5.0,
) -> None:
    """
    统一的 QGraphicsView 滚轮缩放处理。

    所有基于场景的缩放视图（节点图、复合节点预览、UI 预览画布等）都应调用本函数，
    避免在各个模块中复制一份略有差异的缩放逻辑。

    特性：
    - 支持鼠标与触控板（pixelDelta）
    - 以鼠标位置为锚点（需外部将 anchor 设为 AnchorUnderMouse）
    - 限制最小/最大缩放（通过 m11 近似）
    """
    steps = _extract_wheel_delta(event)
    if steps == 0.0:
        return

    # 当前缩放（近似取 x 方向缩放分量）
    current_scale = float(view.transform().m11())
    if steps > 0:
        factor = base_factor_per_step ** steps
    else:
        factor = (1.0 / base_factor_per_step) ** abs(steps)

    # 约束缩放边界
    new_scale = current_scale * factor
    if new_scale < min_scale:
        factor = min_scale / current_scale
    elif new_scale > max_scale:
        factor = max_scale / current_scale

    view.scale(factor, factor)
    event.accept()


def handle_wheel_zoom_for_scroll_area(
    scroll_area: QtWidgets.QScrollArea,
    content_widget: QtWidgets.QWidget,
    event: QtGui.QWheelEvent,
    *,
    base_factor_per_step: float = 1.15,
    min_scale: float = 0.1,
    max_scale: float = 8.0,
    current_scale_getter: callable | None = None,
    apply_scale: callable | None = None,
) -> None:
    """
    统一的 QScrollArea 场景滚轮缩放（以鼠标为锚点）。

    新增基于 ScrollArea 的平面预览/缩放场景时，应始终通过本函数处理缩放，
    而不是在局部 widget 内部重复实现一套自己的滚轮缩放算法。

    - scroll_area: 容器（用于计算 viewport 与滚动条）
    - content_widget: 内容部件（缩放后大小变化）
    - current_scale_getter: () -> float，返回当前缩放比例（必需）
    - apply_scale: (scale: float) -> None，应用新的缩放比例（必需）
    """
    if current_scale_getter is None or apply_scale is None:
        return

    steps = _extract_wheel_delta(event)
    if steps == 0.0:
        return

    current_scale = float(current_scale_getter())
    if steps > 0:
        factor = base_factor_per_step ** steps
    else:
        factor = (1.0 / base_factor_per_step) ** abs(steps)

    new_scale = current_scale * factor
    if new_scale < min_scale:
        new_scale = min_scale
    elif new_scale > max_scale:
        new_scale = max_scale

    viewport = scroll_area.viewport()
    hsb = scroll_area.horizontalScrollBar()
    vsb = scroll_area.verticalScrollBar()

    global_pos_f = event.globalPosition()
    global_pos = QtCore.QPoint(int(global_pos_f.x()), int(global_pos_f.y()))
    vp_mouse = viewport.mapFromGlobal(global_pos)
    lbl_mouse_before = content_widget.mapFromGlobal(global_pos)

    ratio_x = 0.0 if content_widget.width() <= 1 else lbl_mouse_before.x() / float(content_widget.width())
    ratio_y = 0.0 if content_widget.height() <= 1 else lbl_mouse_before.y() / float(content_widget.height())

    apply_scale(float(new_scale))

    anchor_x_new = int(content_widget.width() * ratio_x)
    anchor_y_new = int(content_widget.height() * ratio_y)
    target_scroll_x = anchor_x_new - int(vp_mouse.x())
    target_scroll_y = anchor_y_new - int(vp_mouse.y())

    target_scroll_x = max(0, min(target_scroll_x, hsb.maximum()))
    target_scroll_y = max(0, min(target_scroll_y, vsb.maximum()))
    hsb.setValue(target_scroll_x)
    vsb.setValue(target_scroll_y)
    event.accept()

