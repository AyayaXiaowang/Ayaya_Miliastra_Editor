"""主窗口导航历史：提供“后退/前进”所需的最小状态机（纯内存，不做持久化）。

设计目标：
- 像浏览器一样维护 back/forward 栈：普通导航会清空 forward；后退后可前进；
- 只记录“页面级”的位置（目前以 ViewMode.to_string() 的 mode_string 为主）；
- 允许在当前位置上增量补齐上下文（例如复合节点选中后再写入 composite_id）。

注意：本模块不依赖 Qt，避免在单元测试与服务层中引入 UI 组件。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional


@dataclass(slots=True)
class NavigationEntry:
    """一次可回放的导航位置。"""

    mode_string: str
    context: dict[str, Any] = field(default_factory=dict)


class NavigationHistory:
    """最小导航历史：支持后退/前进与当前 entry 的上下文更新。"""

    def __init__(self, *, max_entries: int = 100) -> None:
        max_entries_int = int(max_entries)
        if max_entries_int <= 0:
            raise ValueError("max_entries 必须为正整数")
        self._max_entries = max_entries_int
        self._entries: list[NavigationEntry] = []
        self._index: int = -1

    def clear(self) -> None:
        self._entries.clear()
        self._index = -1

    def bootstrap(self, entry: NavigationEntry) -> None:
        """初始化第一条 entry（通常在启动完成后调用一次）。"""
        self._entries = [entry]
        self._index = 0

    def current(self) -> Optional[NavigationEntry]:
        if self._index < 0 or self._index >= len(self._entries):
            return None
        return self._entries[self._index]

    def can_go_back(self) -> bool:
        return self._index > 0

    def can_go_forward(self) -> bool:
        return 0 <= self._index < (len(self._entries) - 1)

    def record(self, entry: NavigationEntry) -> None:
        """记录一次新的导航。

        规则：
        - 若当前指针不在末尾，先丢弃 forward 段；
        - 若与当前 entry 的 mode_string 相同，则忽略（避免重复入栈）；
        - 超过最大长度时丢弃最旧 entry，并修正 index。
        """
        if not entry.mode_string:
            return

        current_entry = self.current()
        if current_entry is not None and current_entry.mode_string == entry.mode_string:
            return

        if self._index < (len(self._entries) - 1):
            self._entries = self._entries[: self._index + 1]

        self._entries.append(entry)
        self._index = len(self._entries) - 1

        if len(self._entries) > self._max_entries:
            overflow = len(self._entries) - self._max_entries
            if overflow > 0:
                self._entries = self._entries[overflow:]
                self._index = max(0, self._index - overflow)

    def go_back(self) -> Optional[NavigationEntry]:
        if not self.can_go_back():
            return None
        self._index -= 1
        return self.current()

    def go_forward(self) -> Optional[NavigationEntry]:
        if not self.can_go_forward():
            return None
        self._index += 1
        return self.current()

    def update_current_context(self, updates: Mapping[str, Any]) -> None:
        """更新当前位置的 context（不改变历史指针）。"""
        if not updates:
            return
        entry = self.current()
        if entry is None:
            return
        entry.context.update(dict(updates))

