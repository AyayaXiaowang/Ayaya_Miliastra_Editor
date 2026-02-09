from __future__ import annotations

import importlib.util
from functools import lru_cache
from pathlib import Path

import pytest


@lru_cache(maxsize=1)
def get_playwright_chromium_executable_path() -> Path | None:
    """返回 Playwright chromium 的可执行文件路径（未安装 Playwright 则为 None）。

    注意：这里只做“是否存在可执行文件”的环境探测，不做 browser launch，
    以避免在缺浏览器时触发异常堆栈与噪音输出。
    """
    if importlib.util.find_spec("playwright") is None:
        return None

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        return Path(str(p.chromium.executable_path)).resolve()


def is_playwright_chromium_ready() -> bool:
    """Playwright python 包已安装且 chromium 可执行文件已就绪。"""
    exe = get_playwright_chromium_executable_path()
    return bool(exe is not None and exe.is_file())


def require_playwright_chromium(*, reason: str = "") -> None:
    """缺少 Playwright/浏览器时跳过（用于 UI Web / Playwright 用例）。"""
    if importlib.util.find_spec("playwright") is None:
        pytest.skip("缺少 Playwright（python 包 playwright），跳过 UI Web 用例。" + (f" {reason}" if reason else ""))

    exe = get_playwright_chromium_executable_path()
    if exe is None or (not exe.is_file()):
        pytest.skip(
            "Playwright 浏览器未安装（chromium 可执行文件缺失）。请在你的环境里运行 `playwright install` 后再运行该类用例。"
            + (f" {reason}" if reason else "")
        )

