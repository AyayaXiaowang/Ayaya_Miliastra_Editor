"""纯 Python 的“列表刷新后选中恢复”策略（无 PyQt 依赖）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence


@dataclass(frozen=True)
class SelectionRestoreDecision:
    """描述一次“选中恢复”决策。

    action:
      - "restored": 恢复到 previous_key 对应行
      - "first":    恢复失败但列表非空，选中第一行
      - "cleared":  列表为空且刷新前存在选中，应通知上层清空右侧面板等联动
      - "none":     无需动作（列表为空且刷新前也无选中）
    """

    action: str
    row_index: int | None
    key: Any | None


def compute_selection_restore_decision(
    *,
    keys_by_row: Sequence[Any | None],
    previous_key: Any | None,
    had_selection_before_refresh: bool,
) -> SelectionRestoreDecision:
    """根据 key 列表与 previous_key 计算刷新后的选中恢复策略。"""
    if previous_key is not None:
        for idx, key in enumerate(keys_by_row):
            if key is not None and key == previous_key:
                return SelectionRestoreDecision(action="restored", row_index=int(idx), key=previous_key)

    if not keys_by_row:
        if had_selection_before_refresh:
            return SelectionRestoreDecision(action="cleared", row_index=None, key=None)
        return SelectionRestoreDecision(action="none", row_index=None, key=None)

    # previous_key 为空或无法恢复，但当前列表非空：默认选中第一条。
    return SelectionRestoreDecision(action="first", row_index=0, key=keys_by_row[0])

