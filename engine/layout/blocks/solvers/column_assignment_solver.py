from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from ...internal.layout_models import LayoutBlock
from ...utils.longest_path import resolve_levels_with_parents

from .types import PositioningEngineConfig


@dataclass(frozen=True)
class ColumnIndexSolveInput:
    group_blocks_set: Set[LayoutBlock]
    ordered_children: Dict[LayoutBlock, List[LayoutBlock]]
    parent_sets: Optional[Dict[LayoutBlock, Set[LayoutBlock]]] = None


def solve_column_indices(
    config: PositioningEngineConfig,
    solve_input: ColumnIndexSolveInput,
) -> Dict[LayoutBlock, int]:
    """
    计算每个块的列索引（基于最长路径约束）。

    重要：该函数为“逻辑搬迁”，要求与旧实现完全一致（包含排序与父集合过滤语义）。
    """
    group_blocks_set = solve_input.group_blocks_set
    ordered_children = solve_input.ordered_children
    parent_sets = solve_input.parent_sets

    if not group_blocks_set:
        return {}

    stable_group_blocks = sorted(group_blocks_set, key=config.stable_sort_key)
    adjacency: Dict[LayoutBlock, List[LayoutBlock]] = {}
    parent_sets = parent_sets or {}

    for block in stable_group_blocks:
        adjacency[block] = [
            child
            for child in ordered_children.get(block, [])
            if child in group_blocks_set and child is not block
        ]

    def _children_provider(block: LayoutBlock) -> List[LayoutBlock]:
        return adjacency.get(block, [])

    resolved_levels = resolve_levels_with_parents(
        stable_group_blocks,
        _children_provider,
        parent_provider=lambda block_item: parent_sets.get(block_item, set()),
        order_key=lambda block_item: block_item.order_index,
    )

    return {block: int(resolved_levels.get(block, 0.0)) for block in stable_group_blocks}


