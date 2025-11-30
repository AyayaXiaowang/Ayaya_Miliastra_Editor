# -*- coding: utf-8 -*-
"""
纯绘制：矩形/圆/文字布局/标题横幅
负责在 QPixmap 上叠加可视化元素（节点框/端口圆/OCR区域等）
"""

from PyQt6 import QtCore, QtGui
from PyQt6.QtCore import Qt


def _rect_intersects_any(target: QtCore.QRect, others: list[QtCore.QRect]) -> bool:
    for other in others:
        if target.intersects(other):
            return True
    return False


def _grow_rect(rect: QtCore.QRect, margin: int) -> QtCore.QRect:
    return QtCore.QRect(rect.left() - margin, rect.top() - margin, rect.width() + margin * 2, rect.height() + margin * 2)


def _clamp_rect_to_bounds(rect: QtCore.QRect, bounds: QtCore.QRect) -> QtCore.QRect:
    x = max(bounds.left(), min(rect.left(), bounds.right() - rect.width()))
    y = max(bounds.top(), min(rect.top(), bounds.bottom() - rect.height()))
    return QtCore.QRect(x, y, rect.width(), rect.height())


def _make_qcolor(rgb: tuple[int, int, int]) -> QtGui.QColor:
    return QtGui.QColor(int(rgb[0]), int(rgb[1]), int(rgb[2]))


def _draw_header_banner(pixmap: QtGui.QPixmap, text: str) -> None:
    if not text:
        return
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
    font = painter.font()
    font.setPointSize(10)
    font.setBold(True)
    painter.setFont(font)
    metrics = painter.fontMetrics()
    margin_h = 8
    margin_v = 6
    text_width = metrics.horizontalAdvance(text)
    text_height = metrics.height()
    rect_w = int(text_width + margin_h * 2)
    rect_h = int(text_height + margin_v * 2)
    # 背景半透明黑
    bg_color = QtGui.QColor(0, 0, 0, 160)
    painter.setPen(QtCore.Qt.PenStyle.NoPen)
    painter.setBrush(QtGui.QBrush(bg_color))
    painter.drawRoundedRect(6, 6, rect_w, rect_h, 6, 6)
    # 文本白色
    pen = QtGui.QPen(QtGui.QColor(255, 255, 255))
    painter.setPen(pen)
    painter.drawText(6 + margin_h, 6 + margin_v + metrics.ascent(), text)
    painter.end()


def _draw_text_with_outline(painter: QtGui.QPainter, pos_left_top: QtCore.QPoint, text: str) -> None:
    # 以左上角为参照，转为基线位置
    font_metrics = painter.fontMetrics()
    baseline = QtCore.QPoint(pos_left_top.x(), pos_left_top.y() + font_metrics.ascent())
    path = QtGui.QPainterPath()
    path.addText(float(baseline.x()), float(baseline.y()), painter.font(), text)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
    outline_pen = QtGui.QPen(QtGui.QColor(0, 0, 0))
    outline_pen.setWidth(3)
    outline_pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
    painter.setPen(outline_pen)
    painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
    painter.drawPath(path)
    painter.setPen(QtCore.Qt.PenStyle.NoPen)
    painter.setBrush(QtGui.QBrush(QtGui.QColor(255, 255, 255)))
    painter.fillPath(path, QtGui.QColor(255, 255, 255))


def _place_label_around_anchor(anchor: QtCore.QRect, text_size: QtCore.QSize, image_bounds: QtCore.QRect, occupied: list[QtCore.QRect]) -> QtCore.QRect:
    margin = 6
    candidates = []
    # 外侧八个常见位置
    candidates.append(QtCore.QRect(anchor.left() - text_size.width() - margin, anchor.top() - text_size.height() - margin, text_size.width(), text_size.height()))  # 左上
    candidates.append(QtCore.QRect(anchor.right() + margin, anchor.top() - text_size.height() - margin, text_size.width(), text_size.height()))  # 右上
    candidates.append(QtCore.QRect(anchor.left() - text_size.width() - margin, anchor.bottom() + margin, text_size.width(), text_size.height()))  # 左下
    candidates.append(QtCore.QRect(anchor.right() + margin, anchor.bottom() + margin, text_size.width(), text_size.height()))  # 右下
    candidates.append(QtCore.QRect(anchor.left() - text_size.width() - margin, anchor.center().y() - text_size.height() // 2, text_size.width(), text_size.height()))  # 左中
    candidates.append(QtCore.QRect(anchor.right() + margin, anchor.center().y() - text_size.height() // 2, text_size.width(), text_size.height()))  # 右中
    candidates.append(QtCore.QRect(anchor.center().x() - text_size.width() // 2, anchor.top() - text_size.height() - margin, text_size.width(), text_size.height()))  # 上中
    candidates.append(QtCore.QRect(anchor.center().x() - text_size.width() // 2, anchor.bottom() + margin, text_size.width(), text_size.height()))  # 下中

    for cand in candidates:
        # 限定在图片范围内
        if not image_bounds.contains(cand):
            continue
        if not _rect_intersects_any(cand, occupied):
            return cand

    # 若全部失败，初步退而求其次：以上中位置为基准做钳制
    fallback = QtCore.QRect(
        anchor.center().x() - text_size.width() // 2,
        anchor.top() - text_size.height() - margin,
        text_size.width(),
        text_size.height(),
    )
    fallback = _clamp_rect_to_bounds(fallback, image_bounds)
    return fallback


def _find_non_overlapping_fallback(
    anchor: QtCore.QRect,
    text_size: QtCore.QSize,
    image_bounds: QtCore.QRect,
    occupied: list[QtCore.QRect],
) -> QtCore.QRect:
    """
    在常规候选位置均与已占用区域冲突时，围绕锚点按“扩圈”方式寻找一个不与框/文字重叠的位置。
    保证文本仍在画面内，尽量靠近锚点。
    """
    center_x = anchor.center().x()
    center_y = anchor.center().y()
    max_radius = max(image_bounds.width(), image_bounds.height())
    step = 10

    for radius in range(step, max_radius + step, step):
        offsets = [
            (radius, 0),
            (-radius, 0),
            (0, radius),
            (0, -radius),
            (radius, radius),
            (radius, -radius),
            (-radius, radius),
            (-radius, -radius),
        ]
        for dx, dy in offsets:
            cx = center_x + dx
            cy = center_y + dy
            candidate = QtCore.QRect(
                int(cx - text_size.width() // 2),
                int(cy - text_size.height() // 2),
                text_size.width(),
                text_size.height(),
            )
            candidate = _clamp_rect_to_bounds(candidate, image_bounds)
            if candidate.width() != text_size.width() or candidate.height() != text_size.height():
                # 说明被钳制后尺寸变化，可能靠近边缘，跳过以避免难以阅读
                continue
            if not _rect_intersects_any(candidate, occupied):
                return candidate

    # 仍未找到时，最后退回到以锚点中心为基准的钳制结果（可能有部分遮挡，但属于极端情况）
    final_fallback = QtCore.QRect(
        center_x - text_size.width() // 2,
        center_y - text_size.height() // 2,
        text_size.width(),
        text_size.height(),
    )
    return _clamp_rect_to_bounds(final_fallback, image_bounds)


def _choose_side_midpoint(rect: QtCore.QRect, target_center: QtCore.QPointF) -> QtCore.QPointF:
    """从矩形的四个边中点中选择一个距离目标中心最近的点。"""
    candidates: list[QtCore.QPointF] = []
    cx = rect.center().x()
    cy = rect.center().y()
    candidates.append(QtCore.QPointF(float(cx), float(rect.top())))  # 上边中点
    candidates.append(QtCore.QPointF(float(rect.right()), float(cy)))  # 右边中点
    candidates.append(QtCore.QPointF(float(cx), float(rect.bottom())))  # 下边中点
    candidates.append(QtCore.QPointF(float(rect.left()), float(cy)))  # 左边中点

    best_point = candidates[0]
    best_dist_sq = (best_point.x() - target_center.x()) ** 2 + (best_point.y() - target_center.y()) ** 2
    for point in candidates[1:]:
        dist_sq = (point.x() - target_center.x()) ** 2 + (point.y() - target_center.y()) ** 2
        if dist_sq < best_dist_sq:
            best_dist_sq = dist_sq
            best_point = point
    return best_point


def _draw_arrow_between_rects(
    painter: QtGui.QPainter,
    anchor_rect: QtCore.QRect,
    label_rect: QtCore.QRect,
    color_rgb: tuple[int, int, int] | None,
) -> None:
    """
    在锚点矩形与文字矩形之间绘制一条带箭头的连线。
    箭头起点和终点都落在各自矩形的边中点上，避免穿过框/文本内部。
    """
    if label_rect.isNull() or anchor_rect.isNull():
        return

    label_center = QtCore.QPointF(
        float(label_rect.center().x()),
        float(label_rect.center().y()),
    )
    anchor_center = QtCore.QPointF(
        float(anchor_rect.center().x()),
        float(anchor_rect.center().y()),
    )

    end_point = _choose_side_midpoint(label_rect, anchor_center)
    start_point = _choose_side_midpoint(anchor_rect, end_point)

    color = color_rgb if isinstance(color_rgb, tuple) and len(color_rgb) == 3 else (255, 255, 255)
    pen = QtGui.QPen(_make_qcolor(color))
    pen.setWidth(2)
    painter.setPen(pen)

    # 主体连线
    painter.drawLine(start_point, end_point)

    # 箭头（在终点附近画两条斜线）
    dx = float(start_point.x() - end_point.x())
    dy = float(start_point.y() - end_point.y())
    length_sq = dx * dx + dy * dy
    if length_sq <= 0.0:
        return
    length = float(length_sq ** 0.5)
    ux = dx / length
    uy = dy / length
    arrow_size = 6.0
    angle_scale = 0.6

    left_dx = ux * arrow_size - uy * arrow_size * angle_scale
    left_dy = uy * arrow_size + ux * arrow_size * angle_scale
    right_dx = ux * arrow_size + uy * arrow_size * angle_scale
    right_dy = uy * arrow_size - ux * arrow_size * angle_scale

    tip = end_point
    left_point = QtCore.QPointF(tip.x() + left_dx, tip.y() + left_dy)
    right_point = QtCore.QPointF(tip.x() + right_dx, tip.y() + right_dy)

    painter.drawLine(tip, left_point)
    painter.drawLine(tip, right_point)


def _should_reserve_rect_for_avoidance(
    item: dict,
    pixmap_size: QtCore.QSize,
) -> bool:
    """判断给定矩形是否需要作为“避让障碍”参与文本避让。

    约定：
    - 节点/端口等识别框：需要避让，保持不被文字遮挡；
    - “节点图布置区域”等巨型区域框：仅用于提示区域，不参与避让。
    """
    bbox = item.get("bbox")
    if not (bbox and isinstance(bbox, (list, tuple)) and len(bbox) == 4):
        return False

    label_value = item.get("label")
    label_text_full = str(label_value).strip() if label_value is not None else ""
    if label_text_full:
        base_label = label_text_full.split("·", 1)[0].strip()
        non_avoid_exact_labels = {
            "节点图布置区域",
            "节点图缩放区域",
            "缩放区域(激活后)",
            "Warning 搜索区域",
            "Add搜索区域",
            "安全区",
        }
        if base_label in non_avoid_exact_labels:
            return False
        if base_label.startswith("复核缩放"):
            return False
        if base_label.startswith("模板搜索:"):
            return False
        if "区域" in base_label:
            width_pixels = int(bbox[2])
            height_pixels = int(bbox[3])
            if width_pixels > 0 and height_pixels > 0:
                image_area = int(pixmap_size.width()) * int(pixmap_size.height())
                if image_area > 0:
                    rect_area = width_pixels * height_pixels
                    if rect_area >= int(image_area * 0.25):
                        return False

    return True


def _draw_overlays_build_reserved(overlays: object, pixmap_size: QtCore.QSize) -> list[QtCore.QRect]:
    reserved: list[QtCore.QRect] = []
    if not isinstance(overlays, dict):
        return reserved
    rect_items = overlays.get('rects', []) or []
    circle_items = overlays.get('circles', []) or []
    for item in rect_items:
        bbox = item.get('bbox')
        if bbox and isinstance(bbox, (list, tuple)) and len(bbox) == 4:
            if _should_reserve_rect_for_avoidance(item, pixmap_size):
                reserved.append(QtCore.QRect(int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])))
    for item in circle_items:
        center = item.get('center')
        radius = int(item.get('radius', 6))
        if center and isinstance(center, (list, tuple)) and len(center) == 2:
            cx, cy = int(center[0]), int(center[1])
            reserved.append(QtCore.QRect(cx - radius - 2, cy - radius - 2, radius * 2 + 4, radius * 2 + 4))
    # 限制到图片范围
    image_bounds = QtCore.QRect(0, 0, pixmap_size.width(), pixmap_size.height())
    clamped: list[QtCore.QRect] = []
    for r in reserved:
        clamped.append(r.intersected(image_bounds))
    return clamped


def _draw_label_for_text(
    painter: QtGui.QPainter,
    text: str,
    anchor_rect: QtCore.QRect,
    occupied: list[QtCore.QRect],
    image_bounds: QtCore.QRect,
    color_rgb: tuple[int, int, int] | None,
) -> None:
    if not text:
        return
    fm = painter.fontMetrics()
    text_rect = fm.boundingRect(text)
    # 将标准文本矩形移动到最佳位置
    target = _place_label_around_anchor(anchor_rect, text_rect.size(), image_bounds, occupied)
    # 若仍与已占用区域发生交叠，使用扩圈回退方案再尝试一次，尽量避免文本与框/其他文本重叠
    if _rect_intersects_any(target, occupied):
        target = _find_non_overlapping_fallback(anchor_rect, text_rect.size(), image_bounds, occupied)

    # 先画从框到文字的箭头，再叠加文字本身，保证箭头始终指向对应文本
    _draw_arrow_between_rects(painter, anchor_rect, target, color_rgb)
    # 实际绘制使用左上角
    _draw_text_with_outline(painter, target.topLeft(), text)
    # 记录占用区域，避免文字与文字重叠
    occupied.append(_grow_rect(target, 1))


def _draw_shape_outlines(painter: QtGui.QPainter, overlays: object) -> None:
    if not isinstance(overlays, dict):
        return
    rect_items = overlays.get('rects', []) or []
    circle_items = overlays.get('circles', []) or []
    # 形状绘制
    for item in rect_items:
        bbox = item.get('bbox')
        color = item.get('color', (255, 0, 0))
        if bbox and isinstance(bbox, (list, tuple)) and len(bbox) == 4:
            pen = QtGui.QPen(_make_qcolor(color))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawRect(int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3]))
    for item in circle_items:
        center = item.get('center')
        radius = int(item.get('radius', 6))
        color = item.get('color', (255, 255, 0))
        if center and isinstance(center, (list, tuple)) and len(center) == 2:
            pen = QtGui.QPen(_make_qcolor(color))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QtCore.QPointF(float(center[0]), float(center[1])), float(radius), float(radius))


def _draw_labels_for_overlays(painter: QtGui.QPainter, overlays: object, occupied: list[QtCore.QRect], image_bounds: QtCore.QRect) -> None:
    if not isinstance(overlays, dict):
        return
    rect_items = overlays.get('rects', []) or []
    circle_items = overlays.get('circles', []) or []
    for item in rect_items:
        bbox = item.get('bbox')
        label = item.get('label', '')
        color = item.get('color')
        if bbox and isinstance(bbox, (list, tuple)) and len(bbox) == 4 and label:
            anchor = QtCore.QRect(int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3]))
            _draw_label_for_text(
                painter,
                str(label),
                _grow_rect(anchor, 2),
                occupied,
                image_bounds,
                color,
            )
    for item in circle_items:
        center = item.get('center')
        radius = int(item.get('radius', 6))
        label = item.get('label', '')
        color = item.get('color')
        if center and isinstance(center, (list, tuple)) and len(center) == 2 and label:
            cx, cy = int(center[0]), int(center[1])
            anchor = QtCore.QRect(cx - radius, cy - radius, radius * 2, radius * 2)
            _draw_label_for_text(
                painter,
                str(label),
                _grow_rect(anchor, 2),
                occupied,
                image_bounds,
                color,
            )


def _draw_overlays_on_pixmap(pixmap: QtGui.QPixmap, overlays: object) -> None:
    painter = QtGui.QPainter(pixmap)
    font = painter.font()
    font.setPointSize(9)
    painter.setFont(font)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
    # 先绘制形状，再绘制文本
    _draw_shape_outlines(painter, overlays)
    image_bounds = QtCore.QRect(0, 0, pixmap.width(), pixmap.height())
    occupied = _draw_overlays_build_reserved(overlays, pixmap.size())
    _draw_labels_for_overlays(painter, overlays, occupied, image_bounds)
    painter.end()

