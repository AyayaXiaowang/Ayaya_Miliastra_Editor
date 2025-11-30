"""自动化模块 - 用于自动操作千星沙箱编辑器

对外稳定 API 收口（Facade），避免上层直接耦合内部实现细节。
"""

from __future__ import annotations

from typing import Optional, Tuple
from PIL import Image

from . import capture
from .input.common import (
    ExecutionOptions,
    wait_until,
    sleep_seconds,
    ensure_foreground,
    to_screen_coordinates,
    log_start,
    log_ok,
    log_fail,
)
from .input import subprocess_runner


class AutomationFacade:
    """稳定对外接口集合（轻薄门面，内部委托 capture/subprocess_runner）。"""

    def open_editor(self, executable_path: str) -> int:
        result = subprocess_runner.run_process([executable_path], capture_output=False, text_mode=False)
        return int(result.exit_code)

    def focus_editor(self, window_title_hint: str | None = None) -> bool:
        return ensure_foreground(window_title_hint)

    def capture_screen(self, region: tuple[int, int, int, int] | None = None) -> Image.Image | None:
        if region is None:
            return capture.capture_full_screen()
        x, y, w, h = region
        if int(w) <= 0 or int(h) <= 0:
            return None
        return capture.capture_screen_region((int(x), int(y), int(w), int(h)))

    def capture_window(self, window_title: str) -> Image.Image | None:
        return capture.capture_window(window_title)

    def find_color_block(
        self,
        image: Image.Image,
        color_hex: str,
        color_tolerance: int = 20,
        near_point: tuple[int, int] | None = None,
        max_distance: int = 500,
    ) -> tuple[int, int] | None:
        rectangles = capture.find_color_rectangles(
            image,
            target_color_hex=color_hex,
            color_tolerance=int(color_tolerance),
            near_point=near_point,
            max_distance=int(max_distance),
        )
        if not rectangles:
            return None
        x, y, w, h, _d = rectangles[0]
        return int(x + w // 2), int(y + h // 2)

    def ocr_region(self, image: Image.Image, region: tuple[int, int, int, int]) -> str:
        return capture.ocr_recognize_region(image, region, return_details=False)

    def click(self, point: tuple[int, int]) -> bool:
        return capture.click_left_button(int(point[0]), int(point[1]))

    def type_text(self, text: str, interval: float | None = None) -> bool:
        # interval 预留，发送方式由设置控制（clipboard / sendinput），节流交由外层控制
        return capture.input_text(text)

    def paste_from_clipboard(self, text: str) -> bool:
        return capture.input_text_via_clipboard(text)

    def run_command(self, args: list[str], options: ExecutionOptions | None = None) -> int:
        working_directory = options.working_directory if options is not None else None
        encoding = options.stdout_encoding if options is not None else "utf-8"
        result = subprocess_runner.run_process(
            args,
            working_directory=working_directory,
            capture_output=True,
            text_mode=True,
            encoding=encoding,
        )
        return int(result.exit_code)

    def wait_until(self, predicate, timeout: float, interval: float = 0.2) -> bool:
        return wait_until(predicate, timeout, interval)


__all__ = [
    "AutomationFacade",
    "ExecutionOptions",
    "wait_until",
    "sleep_seconds",
    "ensure_foreground",
    "to_screen_coordinates",
    "log_start",
    "log_ok",
    "log_fail",
    "capture",
]
