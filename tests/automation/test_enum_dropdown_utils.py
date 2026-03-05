from __future__ import annotations

from app.automation.config.enum_dropdown_utils import (
    normalize_dropdown_option_text,
    infer_order_based_click_index,
    infer_missing_option_center_y_by_order,
)


def test_normalize_dropdown_option_text_removes_spaces_and_normalizes_punctuation() -> None:
    assert normalize_dropdown_option_text(" 技能1 - E ") == "技能1-E"
    assert normalize_dropdown_option_text("技能1－E") == "技能1-E"
    assert normalize_dropdown_option_text("键：值") == "键:值"
    assert normalize_dropdown_option_text("界面控件组状态_关闭") == "界面控件组状态关闭"
    assert normalize_dropdown_option_text("界面控件组状态＿关闭") == "界面控件组状态关闭"


def test_infer_order_based_click_index_requires_first_page_and_equal_counts() -> None:
    assert (
        infer_order_based_click_index(
            desired_index_zero_based=2,
            expected_options_count=5,
            recognized_entries_count=5,
            scroll_cycle=0,
        )
        == 2
    )
    assert (
        infer_order_based_click_index(
            desired_index_zero_based=2,
            expected_options_count=5,
            recognized_entries_count=4,
            scroll_cycle=0,
        )
        is None
    )
    assert (
        infer_order_based_click_index(
            desired_index_zero_based=2,
            expected_options_count=5,
            recognized_entries_count=5,
            scroll_cycle=1,
        )
        is None
    )


def test_infer_order_based_click_index_clamps_out_of_range_index() -> None:
    assert (
        infer_order_based_click_index(
            desired_index_zero_based=-1,
            expected_options_count=3,
            recognized_entries_count=3,
            scroll_cycle=0,
        )
        == 0
    )
    assert (
        infer_order_based_click_index(
            desired_index_zero_based=99,
            expected_options_count=3,
            recognized_entries_count=3,
            scroll_cycle=0,
        )
        == 2
    )

def test_infer_missing_option_center_y_by_order_requires_both_sides() -> None:
    # 只有下锚点：无法推断
    assert (
        infer_missing_option_center_y_by_order(
            desired_index_zero_based=1,
            matched_indices_and_center_y=[(0, 10)],
        )
        is None
    )
    # 只有上锚点：无法推断
    assert (
        infer_missing_option_center_y_by_order(
            desired_index_zero_based=1,
            matched_indices_and_center_y=[(2, 50)],
        )
        is None
    )


def test_infer_missing_option_center_y_by_order_linear_interpolation() -> None:
    # 0 -> y=10, 2 -> y=50，则 1 应推断为 y=30
    inferred = infer_missing_option_center_y_by_order(
        desired_index_zero_based=1,
        matched_indices_and_center_y=[(0, 10), (2, 50)],
    )
    assert inferred == 30

    # 更大跨度：0->10, 3->70，则 1->30, 2->50
    inferred_1 = infer_missing_option_center_y_by_order(
        desired_index_zero_based=1,
        matched_indices_and_center_y=[(0, 10), (3, 70)],
    )
    inferred_2 = infer_missing_option_center_y_by_order(
        desired_index_zero_based=2,
        matched_indices_and_center_y=[(0, 10), (3, 70)],
    )
    assert inferred_1 == 30
    assert inferred_2 == 50


