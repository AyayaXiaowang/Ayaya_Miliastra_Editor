from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WriteUiEffectivePolicy:
    """
    导出中心：UI 写回的“强制/有效值”策略。

    约束：
    - 仅当 fmt=="gil" 且选择了 UI源码(ui_src) 时，write_ui 强制开启；
    - 非强制时，write_ui 由用户勾选决定（用于在“强制开启→取消 UI源码→恢复用户选择”间保持一致行为）。
    """

    forced: bool
    effective_write_ui: bool


def compute_write_ui_effective_policy(*, fmt: str, ui_src_selected: bool, user_choice: bool) -> WriteUiEffectivePolicy:
    fmt2 = str(fmt or "").strip()
    forced = (fmt2 == "gil") and bool(ui_src_selected)
    effective = True if bool(forced) else bool(user_choice)
    return WriteUiEffectivePolicy(forced=bool(forced), effective_write_ui=bool(effective))


__all__ = ["WriteUiEffectivePolicy", "compute_write_ui_effective_policy"]

