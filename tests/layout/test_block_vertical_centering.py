"""
测试块间排版的垂直居中规则（块与块之间）。

需求：
- 当一个块右侧连接多个块（A->B/C/D）时，A 应尽量位于 B/C/D 的垂直中间；
- 当一个块左侧连接多个块（A/C/D->B）时，B 应尽量位于 A/C/D 的垂直中间；

本测试不依赖完整节点图解析与块识别流程，而是直接构造 LayoutBlock 及其父子关系，
验证 BlockPositioningEngine 的列内排序与对齐策略能够满足上述居中期望。
"""

from __future__ import annotations

from engine.graph.models.graph_model import GraphModel
from engine.layout.blocks.block_positioning_engine import BlockPositioningEngine
from engine.layout.blocks.block_relationship_analyzer import BlockShiftPlan
from engine.layout.internal.layout_models import LayoutBlock


def _center_y(block: LayoutBlock) -> float:
    return float(block.top_left_pos[1]) + float(block.height) * 0.5


def _shift_plans_for(blocks: list[LayoutBlock]) -> dict[LayoutBlock, BlockShiftPlan]:
    return {block: BlockShiftPlan(shift=0.0, reference_blocks=tuple()) for block in blocks}


def test_block_with_multiple_parents_is_centered_between_parents_even_if_order_index_would_push_it_down() -> None:
    model = GraphModel(graph_id="test_graph", graph_name="test")

    parent_a = LayoutBlock(width=300, height=100, order_index=1)
    parent_c = LayoutBlock(width=300, height=100, order_index=2)
    parent_d = LayoutBlock(width=300, height=100, order_index=3)

    # 同列中的一个“无约束块”，用于验证：即使 child_b 不是列内第一个块，
    # 也应在“可行（不与上一个块重叠）”的前提下尽量贴近多父居中目标。
    # 注意：若上一个块过高会使“精确居中”不可行（非重叠约束优先），因此此处高度设置为较小值。
    preceding_unconstrained = LayoutBlock(width=300, height=50, order_index=1)
    child_b = LayoutBlock(width=300, height=100, order_index=2)

    all_blocks = [parent_a, parent_c, parent_d, preceding_unconstrained, child_b]
    group_blocks_set = set(all_blocks)

    # 本测试关闭紧凑 X 规则，只验证 Y 方向
    engine = BlockPositioningEngine(
        model=model,
        layout_blocks=all_blocks,
        block_map={},
        initial_x=0.0,
        initial_y=0.0,
        block_x_spacing=200.0,
        block_y_spacing=50.0,
        global_layout_context=None,
        parents_map={},
        enable_tight_block_spacing=False,
    )

    block_to_column_index = {
        parent_a: 0,
        parent_c: 0,
        parent_d: 0,
        preceding_unconstrained: 1,
        child_b: 1,
    }
    column_left_x = {0: 0.0, 1: 600.0}

    ordered_children = {block: [] for block in all_blocks}
    parent_sets = {
        parent_a: set(),
        parent_c: set(),
        parent_d: set(),
        preceding_unconstrained: set(),
        child_b: {parent_a, parent_c, parent_d},
    }

    engine.stack_blocks_in_columns(
        block_to_column_index=block_to_column_index,
        column_left_x=column_left_x,
        current_group_top_y=0.0,
        group_blocks_set=group_blocks_set,
        ordered_children=ordered_children,
        shift_plans=_shift_plans_for(all_blocks),
        parent_sets=parent_sets,
    )

    expected_center = (_center_y(parent_a) + _center_y(parent_c) + _center_y(parent_d)) / 3.0
    assert abs(_center_y(child_b) - expected_center) < 1e-6

    # child_b 仍需位于同列前序块之下（非重叠约束）
    assert float(child_b.top_left_pos[1]) >= float(preceding_unconstrained.top_left_pos[1]) + float(preceding_unconstrained.height)


def test_block_with_multiple_children_is_centered_between_children_using_preview_positions() -> None:
    model = GraphModel(graph_id="test_graph_children", graph_name="test")

    parent_a = LayoutBlock(width=300, height=100, order_index=1)
    child_b = LayoutBlock(width=300, height=100, order_index=1)
    child_c = LayoutBlock(width=300, height=100, order_index=2)
    child_d = LayoutBlock(width=300, height=100, order_index=3)

    all_blocks = [parent_a, child_b, child_c, child_d]
    group_blocks_set = set(all_blocks)

    engine = BlockPositioningEngine(
        model=model,
        layout_blocks=all_blocks,
        block_map={},
        initial_x=0.0,
        initial_y=0.0,
        block_x_spacing=200.0,
        block_y_spacing=50.0,
        global_layout_context=None,
        parents_map={},
        enable_tight_block_spacing=False,
    )

    block_to_column_index = {
        parent_a: 0,
        child_b: 1,
        child_c: 1,
        child_d: 1,
    }
    column_left_x = {0: 0.0, 1: 600.0}

    ordered_children = {
        parent_a: [child_b, child_c, child_d],
        child_b: [],
        child_c: [],
        child_d: [],
    }
    # 子块单父不强制对齐（此处不提供 parent_sets），避免破坏“父块位于子块组中间”的目标
    parent_sets = {block: set() for block in all_blocks}

    engine.stack_blocks_in_columns(
        block_to_column_index=block_to_column_index,
        column_left_x=column_left_x,
        current_group_top_y=0.0,
        group_blocks_set=group_blocks_set,
        ordered_children=ordered_children,
        shift_plans=_shift_plans_for(all_blocks),
        parent_sets=parent_sets,
    )

    expected_center = (_center_y(child_b) + _center_y(child_c) + _center_y(child_d)) / 3.0
    assert abs(_center_y(parent_a) - expected_center) < 1e-6


def test_unique_parent_child_chain_aligns_top_y_even_if_child_column_has_other_blocks_below() -> None:
    model = GraphModel(graph_id="test_graph_unique_chain", graph_name="test")

    # 父列：先放一个前序块，把 parent 拉到更低的 top_y
    preceding_parent_column = LayoutBlock(width=300, height=120, order_index=1)
    parent = LayoutBlock(width=300, height=200, order_index=2)

    # 子列：child 与 parent 是“互为唯一父子”；子列还包含额外块，验证 child 下移会带着后续块一起下移
    child = LayoutBlock(width=300, height=150, order_index=1)
    trailing_child_column = LayoutBlock(width=300, height=100, order_index=2)

    all_blocks = [preceding_parent_column, parent, child, trailing_child_column]
    group_blocks_set = set(all_blocks)

    engine = BlockPositioningEngine(
        model=model,
        layout_blocks=all_blocks,
        block_map={},
        initial_x=0.0,
        initial_y=0.0,
        block_x_spacing=200.0,
        block_y_spacing=50.0,
        global_layout_context=None,
        parents_map={},
        enable_tight_block_spacing=False,
    )

    block_to_column_index = {
        preceding_parent_column: 0,
        parent: 0,
        child: 1,
        trailing_child_column: 1,
    }
    column_left_x = {0: 0.0, 1: 600.0}

    ordered_children = {block: [] for block in all_blocks}
    ordered_children[parent] = [child]

    parent_sets = {block: set() for block in all_blocks}
    parent_sets[child] = {parent}

    engine.stack_blocks_in_columns(
        block_to_column_index=block_to_column_index,
        column_left_x=column_left_x,
        current_group_top_y=0.0,
        group_blocks_set=group_blocks_set,
        ordered_children=ordered_children,
        shift_plans=_shift_plans_for(all_blocks),
        parent_sets=parent_sets,
    )

    # 核心断言：互为唯一父子 → top_y 必须对齐
    assert abs(float(child.top_left_pos[1]) - float(parent.top_left_pos[1])) < 1e-6

    # 同列后续块必须仍保持不重叠且位于 child 下方
    assert float(trailing_child_column.top_left_pos[1]) >= float(child.top_left_pos[1]) + float(child.height)


def test_unique_chain_top_y_alignment_moves_root_down_when_child_is_branching_parent() -> None:
    model = GraphModel(graph_id="test_graph_unique_chain_branching_ok", graph_name="test")

    root = LayoutBlock(width=300, height=100, order_index=1)
    branching = LayoutBlock(width=300, height=120, order_index=2)
    leaf_a = LayoutBlock(width=300, height=180, order_index=3)
    leaf_b = LayoutBlock(width=300, height=220, order_index=4)

    all_blocks = [root, branching, leaf_a, leaf_b]
    engine = BlockPositioningEngine(
        model=model,
        layout_blocks=all_blocks,
        block_map={},
        initial_x=0.0,
        initial_y=0.0,
        block_x_spacing=200.0,
        block_y_spacing=50.0,
        global_layout_context=None,
        parents_map={},
        enable_tight_block_spacing=False,
    )

    block_to_column_index = {root: 0, branching: 1, leaf_a: 2, leaf_b: 2}
    column_left_x = {0: 0.0, 1: 600.0, 2: 1200.0}

    # root -> branching 是唯一连接；即使 branching 自身有两个子块，也允许链条整体下移满足分支居中，
    # 并保持 root/branching top_y 对齐（入口块跟随下移）。
    ordered_children = {block: [] for block in all_blocks}
    ordered_children[root] = [branching]
    ordered_children[branching] = [leaf_a, leaf_b]

    parent_sets = {block: set() for block in all_blocks}
    parent_sets[branching] = {root}
    parent_sets[leaf_a] = {branching}
    parent_sets[leaf_b] = {branching}

    engine.stack_blocks_in_columns(
        block_to_column_index=block_to_column_index,
        column_left_x=column_left_x,
        current_group_top_y=0.0,
        group_blocks_set=set(all_blocks),
        ordered_children=ordered_children,
        shift_plans=_shift_plans_for(all_blocks),
        parent_sets=parent_sets,
    )

    # 1) root/branching top_y 对齐（但允许整体下移）
    assert abs(float(root.top_left_pos[1]) - float(branching.top_left_pos[1])) < 1e-6

    # 2) branching 必须位于 leaf_a/leaf_b 的中心区间内
    cy_branching = _center_y(branching)
    lo = min(_center_y(leaf_a), _center_y(leaf_b))
    hi = max(_center_y(leaf_a), _center_y(leaf_b))
    assert lo <= cy_branching <= hi


def test_branch_children_reorder_is_local_and_does_not_move_unrelated_blocks_in_same_column() -> None:
    """
    回归测试：防止“整列重排”破坏列内结构。

    场景：
    - parent 在左列，右列有两个分叉子块 child_first/child_second
    - 右列中间夹着一个 unrelated 块（与 parent 的分叉无关）
    期望：
    - 子块可按端口顺序互换，但只能在它们原本占据的槽位上调整
    - unrelated 必须保持在中间槽位，不应被“整体重排”挤到上/下
    """
    model = GraphModel(graph_id="test_graph_branch_local_swap", graph_name="test")

    parent = LayoutBlock(width=300, height=100, order_index=1)
    # 右列：三个块高度一致，便于严格断言槽位
    child_first = LayoutBlock(width=300, height=100, order_index=1)
    unrelated = LayoutBlock(width=300, height=100, order_index=2)
    child_second = LayoutBlock(width=300, height=100, order_index=3)

    all_blocks = [parent, child_first, unrelated, child_second]
    group_blocks_set = set(all_blocks)

    engine = BlockPositioningEngine(
        model=model,
        layout_blocks=all_blocks,
        block_map={},
        initial_x=0.0,
        initial_y=0.0,
        block_x_spacing=200.0,
        block_y_spacing=50.0,
        global_layout_context=None,
        parents_map={},
        enable_tight_block_spacing=False,
    )

    block_to_column_index = {
        parent: 0,
        child_first: 1,
        unrelated: 1,
        child_second: 1,
    }
    column_left_x = {0: 0.0, 1: 600.0}

    # 端口顺序刻意与 order_index 顺序相反，用于触发“分叉子块按端口顺序”的局部互换
    ordered_children = {block: [] for block in all_blocks}
    ordered_children[parent] = [child_second, child_first]

    parent_sets = {block: set() for block in all_blocks}
    parent_sets[child_first] = {parent}
    parent_sets[child_second] = {parent}

    engine.stack_blocks_in_columns(
        block_to_column_index=block_to_column_index,
        column_left_x=column_left_x,
        current_group_top_y=0.0,
        group_blocks_set=group_blocks_set,
        ordered_children=ordered_children,
        shift_plans=_shift_plans_for(all_blocks),
        parent_sets=parent_sets,
    )

    # 断言“结构不被破坏”：
    # - unrelated 必须仍位于两个分叉子块之间（不可被整列重排挤到顶部/底部）
    # - 且相邻槽位间距保持为 (height + spacing) = 150
    child_y_values = sorted([float(child_first.top_left_pos[1]), float(child_second.top_left_pos[1])])
    unrelated_y = float(unrelated.top_left_pos[1])
    expected_gap = 150.0
    assert child_y_values[0] < unrelated_y < child_y_values[1]
    assert abs(unrelated_y - child_y_values[0] - expected_gap) < 1e-6
    assert abs(child_y_values[1] - unrelated_y - expected_gap) < 1e-6


