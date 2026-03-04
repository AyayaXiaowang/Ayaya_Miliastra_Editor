"""纯 Python 的分页/懒加载计算助手（无 PyQt 依赖）。"""

from __future__ import annotations


def compute_lazy_pagination_target_index(
    *,
    total: int,
    next_index: int,
    ensure_total: int | None = None,
    add_count: int | None = None,
    default_chunk_size: int = 200,
) -> int:
    """计算“懒加载列表/树”的目标加载上限（end index，左闭右开）。

    语义对齐 UI 懒加载常用策略：
    - `ensure_total`：确保至少加载到该总数（不会回退 next_index）；
    - `add_count`：在当前 next_index 基础上追加加载 N 条（若无效则回退到 default_chunk_size）。

    返回值范围固定在 `[0, total]`。
    """
    normalized_total = int(total) if isinstance(total, int) else 0
    if normalized_total < 0:
        normalized_total = 0

    normalized_next = int(next_index) if isinstance(next_index, int) else 0
    if normalized_next < 0:
        normalized_next = 0
    if normalized_next > normalized_total:
        normalized_next = normalized_total

    if ensure_total is not None:
        ensure_value = int(ensure_total) if isinstance(ensure_total, int) else 0
        if ensure_value < 0:
            ensure_value = 0
        if ensure_value > normalized_total:
            ensure_value = normalized_total
        return max(normalized_next, ensure_value)

    delta = (
        int(add_count)
        if isinstance(add_count, int) and int(add_count) > 0
        else int(default_chunk_size)
        if isinstance(default_chunk_size, int) and int(default_chunk_size) > 0
        else 0
    )
    target = normalized_next + delta
    if target > normalized_total:
        target = normalized_total
    return int(target)

