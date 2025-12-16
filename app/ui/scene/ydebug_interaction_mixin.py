"""Y 调试交互 Mixin，仅负责协调 Tooltip/高亮/状态服务。"""

from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from app.ui.scene.highlight_manager import YDebugHighlightManager
from app.ui.scene.interaction_state import YDebugInteractionState
from app.ui.scene.tooltip_overlay import YDebugTooltipOverlay


class YDebugInteractionMixin:
    """Y 调试相关交互 Mixin。
    
    宿主需提供:
    - model/node_items/edge_items/update()/views()
    - _get_ydebug_icon_rect_for_item(NodeGraphicsItem) 以支持图标回退命中区域计算。
    """

    @property
    def _ydebug_state(self) -> YDebugInteractionState:
        if not hasattr(self, "_ydebug_state_instance"):
            self._ydebug_state_instance = YDebugInteractionState()
        return self._ydebug_state_instance

    @property
    def _ydebug_highlight_manager(self) -> YDebugHighlightManager:
        if not hasattr(self, "_ydebug_highlight_manager_instance"):
            self._ydebug_highlight_manager_instance = YDebugHighlightManager(
                state=self._ydebug_state,
                model_provider=lambda: self.model,
                node_items_provider=lambda: self.node_items,
                edge_items_provider=lambda: self.edge_items,
                update_scene=self.update,
                clear_port_highlights=getattr(self, "_clear_port_highlights", None),
            )
        return self._ydebug_highlight_manager_instance

    @property
    def _ydebug_tooltip_overlay(self) -> YDebugTooltipOverlay:
        if not hasattr(self, "_ydebug_tooltip_overlay_instance"):
            self._ydebug_tooltip_overlay_instance = YDebugTooltipOverlay(
                state=self._ydebug_state,
                view_provider=self.views,
                node_lookup=lambda node_id: self.node_items.get(node_id),
                model_provider=lambda: self.model,
                highlight_manager=self._ydebug_highlight_manager,
            )
        return self._ydebug_tooltip_overlay_instance

    def _open_ydebug_tooltip(self, node_id: str, anchor_scene_pos: QtCore.QPointF) -> None:
        self._ydebug_tooltip_overlay.open(node_id, anchor_scene_pos)

    def _close_ydebug_tooltip(self) -> None:
        self._ydebug_tooltip_overlay.close()

    def _reposition_ydebug_tooltip(self, force_initial: bool = False) -> None:
        self._ydebug_tooltip_overlay.reposition(force_initial=force_initial)

    def _refresh_ydebug_tooltip_label(self) -> None:
        self._ydebug_tooltip_overlay.refresh()

    def _apply_all_chains_highlight(self) -> None:
        self._ydebug_highlight_manager.apply_all_chains_highlight()

    def _clear_all_chains_highlight(self) -> None:
        self._ydebug_highlight_manager.clear_all_chains_highlight()

    def _apply_chain_highlight_by_chain_id(self, chain_id: int) -> None:
        self._ydebug_highlight_manager.highlight_chain(chain_id)

    def _clear_chain_highlight(self) -> None:
        self._ydebug_highlight_manager.clear_chain_highlight()

    # === 事件级钩子：Y 调试图标点击 ===

    def _handle_ydebug_mouse_press(
        self,
        event: QtWidgets.QGraphicsSceneMouseEvent,
    ) -> bool:
        """处理场景中的 Y 调试图标点击。

        返回:
            bool: 若本方法已处理并接受事件, 则返回 True, 否则返回 False。
        """
        from engine.configs.settings import settings as _settings_ydebug

        if not getattr(_settings_ydebug, "SHOW_LAYOUT_Y_DEBUG", False):
            return False

        scene_pos = event.scenePos()
        icon_map = getattr(self, "_ydebug_icon_rects", {}) or {}

        # 优先使用已缓存的图标矩形进行命中检测
        hit_node_id = None
        for node_id, rect in icon_map.items():
            if rect.contains(scene_pos):
                hit_node_id = node_id
                break
            # 扩展命中区域 ±6 提升可点性
            expanded = rect.adjusted(-6.0, -6.0, 6.0, 6.0)
            if expanded.contains(scene_pos):
                hit_node_id = node_id
                break

        if hit_node_id:
            node_item = self.node_items.get(hit_node_id)
            if node_item:
                node_rect = node_item.sceneBoundingRect()
                # 图标在右上角时, Tooltip 锚点靠右
                icon_anchor = QtCore.QPointF(
                    float(node_rect.right()) - 3.0,
                    float(node_rect.top()) + 3.0,
                )
            else:
                icon_anchor = scene_pos
            self._open_ydebug_tooltip(hit_node_id, icon_anchor)
            event.accept()
            return True

        # 回退命中: 若缓存矩形未命中, 基于节点矩形即时推导图标矩形
        debug_map = getattr(self.model, "_layout_y_debug_info", {}) or {}
        fallback_hit_id = None
        for node_id, node_item in self.node_items.items():
            if node_id not in debug_map:
                continue
            rect = self._get_ydebug_icon_rect_for_item(node_item)
            expanded = rect.adjusted(-8.0, -8.0, 8.0, 8.0)
            if expanded.contains(scene_pos):
                fallback_hit_id = node_id
                break

        if fallback_hit_id:
            node_item = self.node_items.get(fallback_hit_id)
            if node_item:
                node_rect = node_item.sceneBoundingRect()
                icon_anchor = QtCore.QPointF(
                    float(node_rect.right()) - 3.0,
                    float(node_rect.top()) + 3.0,
                )
            else:
                icon_anchor = scene_pos

            self._open_ydebug_tooltip(fallback_hit_id, icon_anchor)
            event.accept()
            return True

        # 未命中图标时保留已有 Tooltip, 不再因为点击空白区域自动关闭
        return False
