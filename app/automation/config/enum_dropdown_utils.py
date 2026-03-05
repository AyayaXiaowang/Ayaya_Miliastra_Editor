# -*- coding: utf-8 -*-
"""
enum_dropdown_utils: 枚举/布尔下拉选项的纯逻辑辅助函数。

约束：
- 不依赖窗口/截图/执行器，只处理文本与序号/位置推断；
- 不使用 try/except，失败按返回 None/空值交给调用方决定策略。
"""

from __future__ import annotations

from typing import List, Optional, Tuple


def normalize_dropdown_option_text(text: str) -> str:
    """归一化下拉选项文本（用于 OCR 结果与枚举定义的匹配）。"""
    normalized = str(text or "").strip()
    # 统一移除常见空白（OCR 输出常混入空格/全角空格/换行）
    normalized = (
        normalized.replace(" ", "")
        .replace("\t", "")
        .replace("\r", "")
        .replace("\n", "")
        .replace("\u3000", "")
    )
    # 兼容编辑器/字体替换导致的标点差异
    normalized = normalized.replace("－", "-").replace("—", "-").replace("–", "-")
    normalized = normalized.replace("：", ":")
    # 兼容“枚举定义使用下划线分隔，但 UI 展示时下划线不显示/被吞掉”的情况
    normalized = normalized.replace("_", "").replace("＿", "")
    return normalized


def infer_order_based_click_index(
    *,
    desired_index_zero_based: int,
    expected_options_count: int,
    recognized_entries_count: int,
    scroll_cycle: int,
) -> Optional[int]:
    """当 OCR 文本无法匹配枚举定义时的顺序兜底：按“从上到下顺序”点击目标项。

    触发条件（尽量保守）：
    - 仅在第一页（scroll_cycle == 0）启用，避免滚动后“当前页只是部分选项”时误判；
    - 仅在“识别条目数 == 枚举总数”时启用，认为当前下拉无需翻页，顺序可一一映射。

    Returns:
        返回 0-based 的点击 index；不满足条件返回 None。
    """
    if int(scroll_cycle) != 0:
        return None

    expected_count = int(expected_options_count)
    recognized_count = int(recognized_entries_count)
    if expected_count <= 0:
        return None
    if recognized_count <= 0:
        return None
    if recognized_count != expected_count:
        return None

    index_value = int(desired_index_zero_based)
    if index_value < 0:
        index_value = 0
    if index_value >= expected_count:
        index_value = expected_count - 1
    return int(index_value)


def infer_missing_option_center_y_by_order(
    *,
    desired_index_zero_based: int,
    matched_indices_and_center_y: List[Tuple[int, int]],
) -> Optional[int]:
    """当 OCR 缺失目标文本时，基于“已识别项的固定顺序”推断目标选项的 y 坐标。

    规则：
    - 仅当目标 index 的上下两侧都存在已匹配锚点时才推断；
    - 采用线性插值：
      y = y_low + (y_high - y_low) * (idx - idx_low) / (idx_high - idx_low)。
    """
    desired_index_value = int(desired_index_zero_based)
    ordered = sorted(matched_indices_and_center_y, key=lambda item: int(item[0]))
    lower_anchor: Optional[Tuple[int, int]] = None
    upper_anchor: Optional[Tuple[int, int]] = None

    for option_index, center_y in ordered:
        index_value = int(option_index)
        if index_value < desired_index_value:
            lower_anchor = (index_value, int(center_y))
        if index_value > desired_index_value and upper_anchor is None:
            upper_anchor = (index_value, int(center_y))

    if lower_anchor is None or upper_anchor is None:
        return None

    lower_index, lower_y = lower_anchor
    upper_index, upper_y = upper_anchor
    if int(upper_index) <= int(lower_index):
        return None

    step_y = (float(upper_y) - float(lower_y)) / float(int(upper_index) - int(lower_index))
    inferred_y = int(round(float(lower_y) + step_y * float(desired_index_value - int(lower_index))))
    return int(inferred_y)


