"""State container for Y-轴调试交互."""

from __future__ import annotations

from PyQt6 import QtCore
from typing import Optional


class YDebugInteractionState:
    """集中维护 Y 调试相关的运行状态（活动节点、分页、Tooltip 几何）。"""

    def __init__(self) -> None:
        self.active_node_id: Optional[str] = None
        self.tooltip_anchor_scene_pos: Optional[QtCore.QPointF] = None
        self.tooltip_anchor_view_rect: Optional[QtCore.QRect] = None
        self.tooltip_last_auto_pos: Optional[QtCore.QPoint] = None
        self.tooltip_manual_offset: QtCore.QPoint = QtCore.QPoint()
        self.tooltip_orientation: Optional[int] = None
        self.chain_pages: dict[str, int] = {}

    def set_active_node(self, node_id: Optional[str]) -> None:
        self.active_node_id = node_id

    def reset_tooltip_geometry(self) -> None:
        self.tooltip_anchor_scene_pos = None
        self.tooltip_anchor_view_rect = None
        self.tooltip_last_auto_pos = None
        self.tooltip_manual_offset = QtCore.QPoint()
        self.tooltip_orientation = None

    def set_anchor_scene_pos(self, pos: QtCore.QPointF) -> None:
        self.tooltip_anchor_scene_pos = QtCore.QPointF(pos)

    def set_anchor_view_rect(self, rect: Optional[QtCore.QRect]) -> None:
        self.tooltip_anchor_view_rect = rect

    def set_last_auto_pos(self, pos: QtCore.QPoint) -> None:
        self.tooltip_last_auto_pos = QtCore.QPoint(pos)

    def set_manual_offset(self, offset: QtCore.QPoint) -> None:
        self.tooltip_manual_offset = QtCore.QPoint(offset)

    def set_orientation(self, quadrant: int) -> None:
        self.tooltip_orientation = quadrant

    def get_page_index(self, node_id: Optional[str]) -> int:
        if not node_id:
            return 0
        return int(self.chain_pages.get(node_id, 0))

    def set_page_index(self, node_id: Optional[str], index: int) -> None:
        if not node_id:
            return
        self.chain_pages[node_id] = int(max(0, index))


