"""Mode presenter 体系的轻量请求对象。

将共享的数据结构拆到独立模块，避免 coordinator <-> presenters 的循环导入。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.view_modes import ViewMode


@dataclass(slots=True)
class ModeEnterRequest:
    view_mode: ViewMode
    previous_mode: ViewMode


