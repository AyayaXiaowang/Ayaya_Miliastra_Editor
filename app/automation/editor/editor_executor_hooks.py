# -*- coding: utf-8 -*-
"""
EditorExecutor Hooks Mixin

收敛带暂停/终止钩子的等待、文本输入与右键点击等交互封装。
"""

from __future__ import annotations

from typing import Callable, Optional

from PIL import Image

from app.automation.editor import executor_hook_utils as _hook_utils


class EditorExecutorHooksMixin:
    # ===== 公共小工具（去重：等待/点击/输入 与 暂停/终止钩子） =====
    def _wait_with_hooks(
        self,
        total_seconds: float,
        pause_hook: Optional[Callable[[], None]],
        allow_continue: Optional[Callable[[], bool]],
        interval_seconds: float = 0.1,
        log_callback=None,
    ) -> bool:
        """委托通用工具，统一等待钩子逻辑。"""
        return _hook_utils.wait_with_hooks(
            self,
            total_seconds,
            pause_hook,
            allow_continue,
            interval_seconds,
            log_callback,
        )

    def wait_with_hooks(
        self,
        total_seconds: float,
        pause_hook: Optional[Callable[[], None]],
        allow_continue: Optional[Callable[[], bool]],
        interval_seconds: float = 0.1,
        log_callback=None,
    ) -> bool:
        """
        公开的分段等待接口：语义与 `_wait_with_hooks` 一致。

        跨模块调用推荐使用本方法，便于静态检查约束私有方法访问。
        """
        return self._wait_with_hooks(
            total_seconds=total_seconds,
            pause_hook=pause_hook,
            allow_continue=allow_continue,
            interval_seconds=interval_seconds,
            log_callback=log_callback,
        )

    # 轻薄委托：文本输入（带暂停/终止钩子）
    def _input_text_with_hooks(
        self,
        text: str,
        pause_hook: Optional[Callable[[], None]] = None,
        allow_continue: Optional[Callable[[], bool]] = None,
        log_callback=None,
    ) -> bool:
        return _hook_utils.input_text_with_hooks(self, text, pause_hook, allow_continue, log_callback)

    def input_text_with_hooks(
        self,
        text: str,
        pause_hook: Optional[Callable[[], None]] = None,
        allow_continue: Optional[Callable[[], bool]] = None,
        log_callback=None,
    ) -> bool:
        """
        公开的文本输入接口：语义与 `_input_text_with_hooks` 一致。
        """
        return self._input_text_with_hooks(
            text=text,
            pause_hook=pause_hook,
            allow_continue=allow_continue,
            log_callback=log_callback,
        )

    def _right_click_with_hooks(
        self,
        screen_x: int,
        screen_y: int,
        pause_hook: Optional[Callable[[], None]] = None,
        allow_continue: Optional[Callable[[], bool]] = None,
        log_callback=None,
        visual_callback=None,
        *,
        linger_seconds: float = 0.0,
    ) -> bool:
        return _hook_utils.right_click_with_hooks(
            self,
            int(screen_x),
            int(screen_y),
            pause_hook,
            allow_continue,
            log_callback,
            visual_callback,
            linger_seconds=linger_seconds,
        )

    def right_click_with_hooks(
        self,
        screen_x: int,
        screen_y: int,
        pause_hook: Optional[Callable[[], None]] = None,
        allow_continue: Optional[Callable[[], bool]] = None,
        log_callback=None,
        visual_callback=None,
        *,
        linger_seconds: float = 0.0,
    ) -> bool:
        """
        公开的右键点击接口：语义与 `_right_click_with_hooks` 一致。
        """
        return self._right_click_with_hooks(
            screen_x=screen_x,
            screen_y=screen_y,
            pause_hook=pause_hook,
            allow_continue=allow_continue,
            log_callback=log_callback,
            visual_callback=visual_callback,
            linger_seconds=linger_seconds,
        )


