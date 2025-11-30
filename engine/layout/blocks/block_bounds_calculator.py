"""
块边界计算器

负责计算块的边界并归一化节点坐标。
"""

from __future__ import annotations
from typing import Tuple

from .block_layout_context import BlockLayoutContext


class BlockBoundsCalculator:
    """块边界计算器 - 负责计算块的边界并归一化节点坐标"""

    def __init__(self, context: BlockLayoutContext, block_padding: float):
        self.context = context
        self.block_padding = block_padding

    def compute_and_normalize(self) -> Tuple[float, float]:
        """
        计算块的边界并归一化节点坐标
        
        Returns:
            (width, height) - 块的宽度和高度
        """
        if not self.context.node_local_pos:
            return 0.0, 0.0

        # 计算边界
        left_x, right_x, top_y, bottom_y = self._compute_bounds()

        width = (right_x - left_x) + 2 * self.block_padding
        height = (bottom_y - top_y) + 2 * self.block_padding

        # 归一化坐标（相对于块左上角）
        self._normalize_positions(left_x, top_y)

        return width, height

    def _compute_bounds(self) -> Tuple[float, float, float, float]:
        """计算所有节点的边界框"""
        left_x = None
        right_x = None
        top_y = None
        bottom_y = None

        for node_id, (local_x, local_y) in self.context.node_local_pos.items():
            estimated_height = self.context.get_estimated_node_height(node_id)

            node_left = local_x
            node_right = local_x + self.context.node_width
            node_top = local_y
            node_bottom = local_y + estimated_height

            left_x = node_left if left_x is None else min(left_x, node_left)
            right_x = node_right if right_x is None else max(right_x, node_right)
            top_y = node_top if top_y is None else min(top_y, node_top)
            bottom_y = node_bottom if bottom_y is None else max(bottom_y, node_bottom)

        return left_x, right_x, top_y, bottom_y

    def _normalize_positions(self, left_x: float, top_y: float) -> None:
        """将所有节点的局部坐标转换为相对于块左上角（包含内边距）"""
        offset_x = left_x - self.block_padding
        offset_y = top_y - self.block_padding

        for node_id in list(self.context.node_local_pos.keys()):
            old_x, old_y = self.context.node_local_pos[node_id]
            self.context.node_local_pos[node_id] = (old_x - offset_x, old_y - offset_y)



