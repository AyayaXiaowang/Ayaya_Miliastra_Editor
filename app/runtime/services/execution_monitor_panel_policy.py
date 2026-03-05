from __future__ import annotations


def parse_program_coord(text: str) -> float | None:
    """解析程序坐标文本为 float；不使用 try/except，非法输入返回 None。

    约定：
    - 允许前导 +/-；
    - 允许最多一个小数点；
    - 至少包含一个数字；
    - 禁止空格/科学计数法/其它字符（保持与 UI 面板一致的“保守解析”）。
    """
    raw = str(text or "").strip()
    if not raw:
        return None
    has_digit = False
    dot_count = 0
    for index, ch in enumerate(raw):
        if ch in "+-":
            if index != 0:
                return None
        elif ch == ".":
            dot_count += 1
            if dot_count > 1:
                return None
        elif ch.isdigit():
            has_digit = True
        else:
            return None
    if not has_digit:
        return None
    return float(raw)


def compute_desired_steps_width(
    *,
    column_width: int,
    scrollbar_extent: int,
    min_width: int = 240,
    extra_padding: int = 24,
) -> int:
    """精简模式：基于步骤树列宽推导“刚好够放得下步骤树”的目标宽度。"""
    cw = int(column_width or 0)
    se = int(scrollbar_extent or 0)
    return int(max(int(min_width), cw + se + int(extra_padding)))


def compute_compact_mode_desired_window_width(
    *,
    current_window_width: int,
    todo_widget_width: int,
    desired_steps_width: int,
) -> int:
    """精简模式：用当前窗口宽度与 todo_widget 占用宽度估算额外开销，并给出目标窗口宽度。"""
    overhead = max(0, int(current_window_width or 0) - int(todo_widget_width or 0))
    return int(int(desired_steps_width or 0) + int(overhead))


__all__ = [
    "compute_compact_mode_desired_window_width",
    "compute_desired_steps_width",
    "parse_program_coord",
]

