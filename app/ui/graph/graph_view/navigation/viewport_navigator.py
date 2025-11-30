"""视口导航器

负责视口居中、聚焦、适应等导航操作。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6 import QtCore, QtWidgets

if TYPE_CHECKING:
    from ui.graph.graph_view import GraphView


class ViewportNavigator:
    """视口导航器
    
    提供居中、聚焦、适应等视口操作的统一接口。
    """
    
    @staticmethod
    def center_on_node(view: "GraphView", node_id: str) -> None:
        """将视图居中到指定节点"""
        if not view.scene():
            return
        
        node_item = view.scene().get_node_item(node_id)
        if node_item:
            # 获取节点的场景坐标
            node_pos = node_item.pos()
            # 将视图居中到该点
            view.centerOn(node_pos)
    
    @staticmethod
    def fit_all(view: "GraphView", use_animation: bool | None = None) -> None:
        """适应所有内容到视图（带动态边距与额外缩小系数）"""
        if not view.scene():
            return
        
        # 获取所有节点的边界框
        items_rect = view.scene().itemsBoundingRect()
        if not items_rect.isNull():
            # 动态边距：按比例与最小像素共同决定
            base_margin = 100.0
            dynamic_ratio = 0.10  # 基于内容尺寸的10%
            margin_x = max(items_rect.width() * dynamic_ratio, base_margin)
            margin_y = max(items_rect.height() * dynamic_ratio, base_margin)
            focus_rect = items_rect.adjusted(-margin_x, -margin_y, margin_x, margin_y)
            
            # 额外缩小10%，确保内容不被标尺/叠加层遮挡
            padding_ratio = 0.90
            # 使用改进的矩形聚焦，确保精确居中与合适缩放（支持动画）
            ViewportNavigator.execute_focus_on_rect(
                view,
                focus_rect,
                use_animation=use_animation,
                padding_ratio=padding_ratio,
            )
    
    @staticmethod
    def focus_on_node(
        view: "GraphView",
        node_id: str,
        margin_ratio: float = 1.0,
        *,
        use_animation: bool | None = None,
    ) -> None:
        """聚焦并缩放到单个节点
        
        Args:
            view: 图视图
            node_id: 节点ID
            margin_ratio: 边距比例（相对于节点尺寸），默认1.0表示在节点周围留出与节点同等大小的空间
            use_animation: 是否启用平滑动画（None 表示遵循视图设置）
        """
        if not view.scene():
            return
        
        node_item = view.scene().get_node_item(node_id)
        if not node_item:
            return
        
        # 获取节点在场景中的边界矩形
        node_rect = node_item.sceneBoundingRect()
        
        # 添加边距（让用户能看到周围的节点）
        margin_x = node_rect.width() * margin_ratio
        margin_y = node_rect.height() * margin_ratio
        focus_rect = node_rect.adjusted(-margin_x, -margin_y, margin_x, margin_y)
        
        # 执行聚焦（使用改进的方法）
        ViewportNavigator.execute_focus_on_rect(
            view,
            focus_rect,
            use_animation=use_animation,
        )
    
    @staticmethod
    def focus_on_nodes_and_edge(
        view: "GraphView",
        src_node_id: str,
        dst_node_id: str,
        edge_id: str = None,
        *,
        use_animation: bool | None = None,
    ) -> None:
        """聚焦并缩放到两个节点及其连线
        
        Args:
            view: 图视图
            src_node_id: 源节点ID
            dst_node_id: 目标节点ID
            edge_id: 连线ID（可选）
            use_animation: 是否启用平滑动画（None 表示遵循视图设置）
        """
        if not view.scene():
            return
        
        src_node = view.scene().get_node_item(src_node_id)
        dst_node = view.scene().get_node_item(dst_node_id)
        
        if not src_node or not dst_node:
            return
        
        # 计算两个节点的组合边界矩形
        src_rect = src_node.sceneBoundingRect()
        dst_rect = dst_node.sceneBoundingRect()
        combined_rect = src_rect.united(dst_rect)
        
        # 添加边距（50%的组合尺寸，让用户能看到周围的上下文）
        margin_x = combined_rect.width() * 0.5
        margin_y = combined_rect.height() * 0.5
        focus_rect = combined_rect.adjusted(-margin_x, -margin_y, margin_x, margin_y)
        
        # 确保focus_rect有一个合理的最小尺寸（避免两个节点很近时缩放过度）
        min_width = 800.0  # 最小宽度（场景单位）
        min_height = 600.0  # 最小高度（场景单位）
        
        if focus_rect.width() < min_width:
            # 从中心向两侧扩展到最小宽度
            center_x = focus_rect.center().x()
            focus_rect.setLeft(center_x - min_width / 2)
            focus_rect.setRight(center_x + min_width / 2)
        
        if focus_rect.height() < min_height:
            # 从中心向上下扩展到最小高度
            center_y = focus_rect.center().y()
            focus_rect.setTop(center_y - min_height / 2)
            focus_rect.setBottom(center_y + min_height / 2)
        
        # 执行聚焦（使用改进的方法）
        ViewportNavigator.execute_focus_on_rect(
            view,
            focus_rect,
            use_animation=use_animation,
        )
    
    @staticmethod
    def execute_focus_on_rect(view: "GraphView", focus_rect: QtCore.QRectF, max_scale: float = 1.5, use_animation: bool = None, padding_ratio: float = 1.0) -> None:
        """执行聚焦到指定矩形区域的核心方法
        
        这个方法解决了fitInView可能导致的居中偏移问题。
        支持平滑过渡动画。
        
        Args:
            view: 图视图
            focus_rect: 要聚焦的场景矩形区域
            max_scale: 最大缩放比例（默认1.5，即150%）
            use_animation: 是否使用动画（None表示使用全局设置）
            padding_ratio: 额外缩放系数（<1.0 进一步缩小，>1.0 放大），用于留出可视边距
        """
        if not view.scene() or focus_rect.isEmpty():
            return
        
        # 确保视图已经有有效的尺寸
        viewport_size = view.viewport().size()
        if viewport_size.width() <= 0 or viewport_size.height() <= 0:
            return
        
        # 决定是否使用动画
        should_animate = use_animation if use_animation is not None else view.enable_smooth_transition
        
        if should_animate:
            # 使用动画过渡
            view.transform_animation.start_transition(focus_rect, duration=1000, max_scale=max_scale, padding_ratio=padding_ratio)
        else:
            # 立即跳转（原有逻辑）
            # 保存原始锚点设置
            old_anchor = view.transformationAnchor()
            old_resize_anchor = view.resizeAnchor()
            
            # 设置为无锚点模式，这样我们可以完全控制变换
            view.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.NoAnchor)
            view.setResizeAnchor(QtWidgets.QGraphicsView.ViewportAnchor.NoAnchor)
            
            # 步骤1: 使用fitInView设置合适的缩放比例
            # fitInView会同时调整缩放和位置，但位置可能不准确
            view.fitInView(focus_rect, QtCore.Qt.AspectRatioMode.KeepAspectRatio)
            
            # 步骤2: 限制最大缩放
            current_transform = view.transform()
            current_scale = current_transform.m11()  # 获取当前缩放比例
            
            if current_scale > max_scale:
                # 如果当前缩放超过最大值，重置到最大缩放
                scale_factor = max_scale / current_scale
                view.scale(scale_factor, scale_factor)
            
            # 步骤3: 根据padding_ratio进一步缩小或放大，以预留边距
            if padding_ratio != 1.0:
                view.scale(padding_ratio, padding_ratio)
            
            # 步骤4: 使用centerOn精确居中
            # fitInView之后，缩放已经设置好了，现在只需要调整位置
            # centerOn会确保指定的场景坐标点位于视口中心
            focus_center = focus_rect.center()
            view.centerOn(focus_center)
            
            # 恢复原始锚点设置
            view.setTransformationAnchor(old_anchor)
            view.setResizeAnchor(old_resize_anchor)
            
            # 强制更新视图
            view.viewport().update()

