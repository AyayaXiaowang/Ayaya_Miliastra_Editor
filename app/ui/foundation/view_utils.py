from __future__ import annotations

from PyQt6 import QtCore, QtWidgets


def compute_focus_rect_for_scene(scene: QtWidgets.QGraphicsScene, base_margin: float = 100.0, dynamic_margin_ratio: float = 0.10) -> QtCore.QRectF:
    """计算场景内所有可见项的聚焦矩形，并按比例与最小边距扩展。
    
    Args:
        scene: QGraphicsScene 实例
        base_margin: 最小边距（场景单位）
        dynamic_margin_ratio: 基于内容尺寸的动态边距比例
    Returns:
        扩展后的聚焦矩形；当场景为空时返回空矩形
    """
    if not scene:
        return QtCore.QRectF()
    items_rect = scene.itemsBoundingRect()
    if items_rect.isEmpty():
        return QtCore.QRectF()
    margin_x = max(items_rect.width() * dynamic_margin_ratio, base_margin)
    margin_y = max(items_rect.height() * dynamic_margin_ratio, base_margin)
    return items_rect.adjusted(-margin_x, -margin_y, margin_x, margin_y)


def fit_view_to_scene_items(
    view: QtWidgets.QGraphicsView,
    scene: QtWidgets.QGraphicsScene,
    base_margin: float = 100.0,
    dynamic_margin_ratio: float = 0.10,
    padding_ratio: float = 0.90,
) -> None:
    """将视图适配到场景内所有项（带动态边距与额外缩小系数）。
    
    - 通用函数，适用于任意 QGraphicsView（预览/编辑皆可）。
    - padding_ratio < 1 可额外缩小，留出可视边距以避开叠加层。
    """
    if not view or not scene:
        return
    focus_rect = compute_focus_rect_for_scene(scene, base_margin, dynamic_margin_ratio)
    if focus_rect.isEmpty():
        return
    # 保存原锚点
    old_anchor = view.transformationAnchor()
    old_resize_anchor = view.resizeAnchor()
    view.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.NoAnchor)
    view.setResizeAnchor(QtWidgets.QGraphicsView.ViewportAnchor.NoAnchor)
    # 先fit，再按padding_ratio进一步缩小，然后精确居中
    view.fitInView(focus_rect, QtCore.Qt.AspectRatioMode.KeepAspectRatio)
    if padding_ratio != 1.0:
        view.scale(padding_ratio, padding_ratio)
    view.centerOn(focus_rect.center())
    # 还原锚点
    view.setTransformationAnchor(old_anchor)
    view.setResizeAnchor(old_resize_anchor)
    view.viewport().update()


