"""模式切换处理器（兼容层）。

历史实现为：`enter_mode(...)` 内部分派到 `_enter_*` 函数。
当前实现已迁移到 `ui.main_window.mode_presenters`（每个 ViewMode 一个 presenter），
此文件保留为兼容 wrapper，避免外部模块仍引用 `mode_handlers.enter_mode` 时破坏行为。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.view_modes import ViewMode

if TYPE_CHECKING:
    from app.ui.main_window.main_window import MainWindowV2


def enter_mode(
    main_window: "MainWindowV2",
    *,
    view_mode: ViewMode,
    previous_mode: ViewMode,
) -> str | None:
    coordinator = getattr(main_window, "mode_presenter_coordinator", None)
    enter_method = getattr(coordinator, "enter_mode", None)
    if callable(enter_method):
        from app.ui.main_window.mode_presenters import ModeEnterRequest

        return enter_method(ModeEnterRequest(view_mode=view_mode, previous_mode=previous_mode))
    return None


