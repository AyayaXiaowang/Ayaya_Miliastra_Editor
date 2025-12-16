"""
块间关系分析器

负责分析基本块之间的关系，包括：
- 构建块间的父子关系（按端口顺序）
- 计算每个块的Y轴偏移量（基于多父/多子规则）
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Set, List, Tuple, Optional, TYPE_CHECKING

from ..internal.layout_models import LayoutBlock
from ..utils.graph_query_utils import is_jump_out_edge

if TYPE_CHECKING:
    from engine.graph.models import GraphModel


@dataclass(frozen=True)
class BlockShiftPlan:
    """块的Y轴偏移计划"""

    shift: float
    reference_blocks: Tuple["LayoutBlock", ...]


class BlockRelationshipAnalyzer:
    """块间关系分析器"""

    def __init__(
        self,
        model: GraphModel,
        layout_blocks: List["LayoutBlock"],
    ):
        self.model = model
        self.layout_blocks = layout_blocks
        self.block_map: Dict[str, "LayoutBlock"] = {}
        self.parent_map: Dict["LayoutBlock", Set["LayoutBlock"]] = {}

    def analyze_relationships(self) -> Dict["LayoutBlock", List["LayoutBlock"]]:
        """
        构建块间的有向关系（按端口顺序）
        
        Returns:
            ordered_children: 每个块的子块列表（按端口顺序排列）
        """
        # 构建 flow_node_id → LayoutBlock 的映射
        self.block_map.clear()
        for layout_block in self.layout_blocks:
            for flow_node_id in layout_block.flow_nodes:
                self.block_map[flow_node_id] = layout_block

        # 构建"按端口顺序"的块级有向关系（跳出循环边不参与）
        ordered_children: Dict["LayoutBlock", List["LayoutBlock"]] = {}
        self.parent_map = {block: set() for block in self.layout_blocks}
        for block in self.layout_blocks:
            children_list: List["LayoutBlock"] = []
            if block.flow_nodes:
                last_node_id = block.flow_nodes[-1]
                for port_name, next_node_id in block.last_node_branches:
                    # 跳过"跳出循环"的流程边
                    if is_jump_out_edge(self.model, last_node_id, next_node_id):
                        continue
                    next_block = self.block_map.get(next_node_id)
                    if next_block is not None and next_block is not block:
                        # 已按端口索引预排序；此处保持顺序
                        children_list.append(next_block)
                        self.parent_map.setdefault(next_block, set()).add(block)
            ordered_children[block] = children_list

        return ordered_children

    def compute_y_shifts(
        self,
        ordered_children: Dict["LayoutBlock", List["LayoutBlock"]],
    ) -> Dict["LayoutBlock", BlockShiftPlan]:
        """
        预计算每个块的Y轴下移偏移计划
        
        规则：
        - 仅当存在"右侧唯一子块数量≥2"或"左侧唯一父块数量≥2"时生效
        - 偏移量 = 0.5 × max(右侧唯一子块高度总和, 左侧唯一父块高度总和)
        
        Args:
            ordered_children: 每个块的子块列表
            
        Returns:
            每个块的Y轴偏移量字典
        """
        # 如尚未构建父关系，补充一次（保持与 ordered_children 同步）
        if not self.parent_map:
            self.parent_map = {block: set() for block in self.layout_blocks}
            for parent_block, children_blocks in ordered_children.items():
                for child_block in children_blocks:
                    self.parent_map.setdefault(child_block, set()).add(parent_block)

        # 计算偏移
        per_block_shift: Dict["LayoutBlock", BlockShiftPlan] = {}
        for layout_block in self.layout_blocks:
            right_children = ordered_children.get(layout_block, [])
            unique_right_children: Set["LayoutBlock"] = set(right_children) if right_children else set()
            left_parents: Set["LayoutBlock"] = self.parent_map.get(layout_block, set())

            if len(unique_right_children) >= 2:
                right_sum_heights = sum(float(child.height) for child in unique_right_children)
            else:
                right_sum_heights = 0.0

            if len(left_parents) >= 2:
                left_sum_heights = sum(float(parent.height) for parent in left_parents)
            else:
                left_sum_heights = 0.0

            raw_shift = 0.5 * max(right_sum_heights, left_sum_heights)
            if raw_shift <= 0.0:
                per_block_shift[layout_block] = BlockShiftPlan(0.0, tuple())
                continue

            use_right = right_sum_heights >= left_sum_heights
            reference_source = unique_right_children if use_right else left_parents
            reference = tuple(sorted(reference_source, key=lambda blk: blk.order_index))
            per_block_shift[layout_block] = BlockShiftPlan(raw_shift, reference)

        return per_block_shift


def build_block_relationship_snapshot(
    layout_blocks: List["LayoutBlock"],
    ordered_children: Dict["LayoutBlock", List["LayoutBlock"]],
    block_map: Dict[str, "LayoutBlock"],
) -> Dict[str, object]:
    """
    构建块关系快照，供其它模块复用布局顺序与端口分支信息。
    """
    node_index_in_block: Dict[str, int] = {}
    for block in layout_blocks:
        for index, flow_node_id in enumerate(block.flow_nodes):
            node_index_in_block[flow_node_id] = index

    branches_by_block: Dict["LayoutBlock", List[Tuple[Optional[str], str]]] = {}
    for block in layout_blocks:
        child_blocks = ordered_children.get(block, [])
        if not child_blocks:
            continue
        pairs: List[Tuple[str | None, str]] = []
        for child_block in child_blocks:
            target_port_name: Optional[str] = None
            target_node_id: Optional[str] = None
            for port_name, candidate_node_id in block.last_node_branches:
                if block_map.get(candidate_node_id) == child_block:
                    target_port_name = port_name
                    target_node_id = candidate_node_id
                    break
            if target_node_id is not None:
                pairs.append((target_port_name, target_node_id))
        if pairs:
            branches_by_block[block] = pairs

    return {
        "block_map": dict(block_map),
        "ordered_children": {block: list(children) for block, children in ordered_children.items()},
        "node_index_in_block": node_index_in_block,
        "branches_by_block": branches_by_block,
    }
