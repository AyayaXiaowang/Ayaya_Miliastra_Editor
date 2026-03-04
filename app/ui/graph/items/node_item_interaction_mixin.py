"""NodeGraphicsItem：交互相关逻辑（移动钩子、点击占位控件 materialize）。"""

from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from engine.configs.settings import settings


class NodeInteractionMixin:
    def itemChange(self, change, value):
        """节点位置/选中状态变化时的钩子。

        - 移动相关逻辑（模型更新、撤销命令、场景索引维护）统一委托给场景，
          避免视图对象直接操作 GraphScene 内部字段或 GraphModel。
        - 本类仅在合适的时机调用宿主场景提供的钩子方法：
          - on_node_item_position_change_started(node_item, old_pos)
          - on_node_item_position_changed(node_item, new_pos)
        """
        from app.ui.scene.interaction_mixin import SceneInteractionMixin
        # 当节点位置即将改变时，通知场景记录旧位置（用于撤销命令）
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            current_scene = self.scene()
            # Qt 可能在 QGraphicsItem 构造/挂载阶段提前触发 itemChange；
            # 此时 Python 侧字段尚未初始化完成，因此这里必须允许缺省为 False。
            moving_started = bool(getattr(self, "_moving_started", False))
            if current_scene and not moving_started:
                old_pos = self.pos()
                if isinstance(current_scene, SceneInteractionMixin):
                    current_scene.on_node_item_position_change_started(
                        self,
                        (old_pos.x(), old_pos.y()),
                    )
                self._moving_started = True  # 标记一次拖拽开始

        # 当节点位置已经改变时，仅通知场景刷新与该节点相连的连线
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            current_scene = self.scene()
            if isinstance(current_scene, SceneInteractionMixin):
                new_pos = self.pos()
                current_scene.on_node_item_position_changed(
                    self,
                    (new_pos.x(), new_pos.y()),
                )

        # 当选中状态改变时，触发重绘以更新高亮效果
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            self.update()

        return super().itemChange(change, value)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        """鼠标按下：在虚拟化开启时，允许点击常量占位区域按需创建真实控件。"""
        if event is None:
            return
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            if self._is_inline_constant_virtualization_active() and self.isSelected():
                # LOD：低倍率缩放时不允许 materialize（此时常量控件/占位本应隐藏）
                if bool(getattr(settings, "GRAPH_LOD_ENABLED", True)):
                    scene_ref = self.scene()
                    scale_hint = float(getattr(scene_ref, "view_scale_hint", 1.0) or 1.0) if scene_ref is not None else 1.0
                    details_min_scale = float(getattr(settings, "GRAPH_LOD_NODE_DETAILS_MIN_SCALE", 0.55))
                    if scale_hint < details_min_scale:
                        super().mousePressEvent(event)
                        return
                pos = event.pos()
                for port_name in list(self._control_positions.keys()):
                    rect = self._inline_constant_rect_for_port(port_name)
                    if rect is not None and rect.contains(pos):
                        self.materialize_inline_constant_editor(str(port_name), focus=True)
                        event.accept()
                        return
        super().mousePressEvent(event)

