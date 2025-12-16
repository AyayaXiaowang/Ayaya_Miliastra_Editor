from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from ...internal.layout_models import LayoutBlock

from .types import PositioningEngineConfig


@dataclass(frozen=True)
class ColumnXSolveInput:
    block_to_column_index: Dict[LayoutBlock, int]


def solve_column_x_positions(
    config: PositioningEngineConfig,
    solve_input: ColumnXSolveInput,
) -> Dict[int, float]:
    """
    计算每列的像素X坐标。

    重要：该函数为“逻辑搬迁”，要求与旧实现完全一致（包含“空列不压缩”的 gap 语义）。
    """
    block_to_column_index = solve_input.block_to_column_index
    if not block_to_column_index:
        return {}

    distinct_columns = sorted({column_index for column_index in block_to_column_index.values()})

    # 计算每一列的最大宽度（无块的列宽视为0）
    column_max_width: Dict[int, float] = {column_index: 0.0 for column_index in distinct_columns}
    for block, column_index in block_to_column_index.items():
        current_width = float(block.width)
        if current_width > column_max_width[column_index]:
            column_max_width[column_index] = current_width

    # 将稀疏列转为连续坐标（保持列差不变，不压缩"空列"）
    column_left_x: Dict[int, float] = {}
    if not distinct_columns:
        return column_left_x

    current_left_x = float(config.initial_x)
    previous_column_index: Optional[int] = None
    for column_index in distinct_columns:
        if previous_column_index is None:
            column_left_x[column_index] = current_left_x
        else:
            gap = column_index - previous_column_index
            previous_width = column_max_width.get(previous_column_index, 0.0)
            current_left_x = current_left_x + previous_width + float(config.block_x_spacing) * float(gap)
            column_left_x[column_index] = current_left_x
        previous_column_index = column_index

    return column_left_x


