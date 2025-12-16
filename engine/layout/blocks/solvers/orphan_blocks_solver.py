from __future__ import annotations

from dataclasses import dataclass
from typing import List

from ...internal.layout_models import LayoutBlock

from .overlap_buckets import register_block_in_buckets
from .types import PositioningEngineConfig, PositioningRuntimeState


@dataclass(frozen=True)
class OrphanPlacementInput:
    layout_blocks: List[LayoutBlock]


def place_orphan_blocks(
    config: PositioningEngineConfig,
    runtime: PositioningRuntimeState,
    solve_input: OrphanPlacementInput,
) -> None:
    """放置孤立块（动态按本列最大宽更新列宽，减少横向空间浪费）"""
    orphan_blocks = [block for block in solve_input.layout_blocks if block not in runtime.positioned_blocks]
    if not orphan_blocks:
        return

    if runtime.positioned_blocks:
        max_right = max(block.top_left_pos[0] + block.width for block in runtime.positioned_blocks)
    else:
        max_right = config.initial_x

    anchor_left = max_right + config.block_x_spacing
    current_y = config.initial_y
    current_column_max_width = 0.0  # 动态记录本列的最大宽度

    for orphan_block in orphan_blocks:
        orphan_block.top_left_pos = (anchor_left, current_y)
        runtime.positioned_blocks.add(orphan_block)
        register_block_in_buckets(runtime, orphan_block)

        # 更新本列最大宽度
        if orphan_block.width > current_column_max_width:
            current_column_max_width = orphan_block.width

        current_y += orphan_block.height + config.block_y_spacing

        # 换列条件：超过高度限制
        if current_y > config.initial_y + 2000:
            anchor_left += current_column_max_width + config.block_x_spacing
            current_y = config.initial_y
            current_column_max_width = 0.0  # 重置新列的最大宽度


